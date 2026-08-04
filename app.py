"""
app.py - Jarvis Hub Flask Web Dashboard v3 (Clean Rewrite)

Serves a local web UI for daily news briefings, market analysis,
knowledge base search, watchlist management, signal feed, and market evaluation.

Usage: python app.py [--host 0.0.0.0] [--port 8100]
"""
import json
import os
import re
import sys
import threading
from datetime import datetime, timedelta

import requests
from flask import Flask, render_template, request, jsonify
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "core"))

try:
    import config as cfg_module
    from market_service import (
        analyze_stock,
        fetch_crypto,
        fetch_gold,
        fetch_dxy,
        fetch_oil,
        calculate_technical_indicators,
    )
    from news_service import (
        get_articles,
        get_exchange_rates,
        search_knowledge,
        fetch_market_indices,
        enrich_article as _enrich_article,
    )
    from db import Database
    from llm_cache import llm_cache
except ImportError:
    print("[WARN] Core modules not found — running in standalone mode")
    cfg_module = None
    analyze_stock = lambda sym: {"symbol": sym}
    fetch_crypto = lambda x: {}
    fetch_gold = lambda: None
    fetch_dxy = lambda: None
    fetch_oil = lambda: None
    calculate_technical_indicators = lambda x: {}
    get_articles = lambda limit=20: []
    get_exchange_rates = lambda: {}
    search_knowledge = lambda q, lim=20: []
    fetch_market_indices = lambda: {}
    _enrich_article = None
    Database = type("DummyDB", (), {
        "get_daily_snapshot": lambda self, d: None,
        "get_all_dates": lambda self: [],
        "save_market_evaluation": lambda self, *a: None,
        "search_knowledge": lambda self, *a: [],
        "get_activities": lambda self, n=20: [],
        "get_watchlist": lambda self: [],
        "add_to_watchlist": lambda self, s, n=None: s,
        "remove_from_watchlist": lambda self, s: False,
        "mark_alerts_as_read": lambda self: None,
        "_c": lambda self: None,
        "_conn": None,
        "get_all_evaluations": lambda self: [],
    })
    llm_cache = None

# --- App & Service initialization -------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(SCRIPT_DIR, "dashboard", "templates"),
    static_folder=os.path.join(SCRIPT_DIR, "dashboard", "static"),
)

config = None
db = None
_fresh_cache = {}

_cache_lock = threading.Lock()
_cache_time = 0


# --- Background data refresh ------------------------------------------------

def _load_config():
    global config
    try:
        if cfg_module:
            config = cfg_module.load_config()
        else:
            config = {"ollama": {"url": "http://localhost:11434", "model": "Qwen3.6-35B-A3B-MLX-8bit"}, "db_path": ":memory:"}
        print("[CFG] Loaded configuration OK")
    except Exception as e:
        print("[CFG] Config load failed: %s" % e)
        config = {"ollama": {"url": "http://localhost:11434", "model": "Qwen3.6-35B-A3B-MLX-8bit"}, "db_path": ":memory:"}


def _load_db():
    global db
    try:
        path = (config or {}).get("db_path", os.path.join(SCRIPT_DIR, "jarvis_hub.db")) if config else os.path.join(SCRIPT_DIR, "jarvis_hub.db")
        db = Database(path)
        print("[DB] Connected OK at %s" % path)
    except Exception as e:
        print("[DB] Connect failed: %s — using in-memory DB" % e)
        try:
            db = Database()
        except Exception:
            db = None


def _utc_now_iso():
    return datetime.now().isoformat()


def _refresh_data():
    """Fetch ALL market + news data in parallel. Called by init + force refresh."""
    global _cache_time, _fresh_cache
    try:
        results = {}

        with threading.Lock():
            pass  # simplified: no threads needed for this demo

        if fetch_market_indices:
            try:
                idx = fetch_market_indices()
                if idx:
                    results["vn_indices"] = idx.get("vn_indices", {})
                    results["global_indices"] = idx.get("global_indices", {})
            except Exception as e:
                print("[REFRESH] Indices fetch failed: %s" % e)

        if get_exchange_rates:
            try:
                rates = get_exchange_rates()
                if rates:
                    results["rates"] = rates
            except Exception as e:
                print("[REFRESH] Rates fetch failed: %s" % e)

        for symbol, key in [("BTC", "crypto_BTC"), ("ETH", "crypto_ETH"), ("SOL", "crypto_SOL")]:
            try:
                data = fetch_crypto(symbol)
                if data:
                    results[key] = data
            except Exception as e:
                print("[REFRESH] %s fetch failed: %s" % (symbol, e))

        if fetch_gold:
            try:
                gold = fetch_gold()
                if gold:
                    results["gold"] = gold
            except Exception as e:
                print("[REFRESH] Gold fetch failed: %s" % e)

        if fetch_dxy:
            try:
                dxy = fetch_dxy()
                if dxy:
                    results["dxy"] = dxy
            except Exception as e:
                print("[REFRESH] DXY fetch failed: %s" % e)

        if fetch_oil:
            try:
                oil = fetch_oil()
                if oil:
                    results["oil"] = oil
            except Exception as e:
                print("[REFRESH] Oil fetch failed: %s" % e)

        if get_articles:
            try:
                articles = get_articles(limit=30)
                if articles:
                    results["articles"] = articles
            except Exception as e:
                print("[REFRESH] Articles fetch failed: %s" % e)

        _fresh_cache = results
        _cache_time = datetime.now().timestamp()
        print("[REFRESH] Done — %d sources loaded" % len(results))

    except Exception as e:
        print("[REFRESH] Full refresh failed: %s" % e)


# --- APScheduler Background Jobs ------------------------------------------

_scheduler = None


def _start_scheduler():
    """Start the APScheduler with Market Intelligence cron job."""
    global _scheduler
    if not APSCHEDULER_AVAILABLE:
        print("[SCHEDULER] APScheduler not available — skipping background jobs")
        return
    try:
        _scheduler = BackgroundScheduler(timezone="Asia/Saigon")

        # Market Intelligence pipeline runs every 6 hours at 06:00, 12:00, 18:00, 00:00
        _scheduler.add_job(
            func=_run_market_intelligence_pipeline,
            trigger="cron",
            hour=[6, 12, 18, 0],
            minute=0,
            id="market_intelligence_pipeline",
            replace_existing=True,
            max_instances=1,
        )

        # Refresh market data every 5 minutes
        _scheduler.add_job(
            func=_refresh_data,
            trigger="interval",
            minutes=5,
            id="market_data_refresh",
            replace_existing=True,
        )

        _scheduler.start()
        print("[SCHEDULER] Started — Market Intelligence runs at 06:00, 12:00, 18:00, 00:00 SGT")
    except Exception as e:
        print("[SCHEDULER] Failed to start: %s" % e)


def _run_market_intelligence_pipeline():
    """Wrapper for running the Market Intelligence pipeline in background."""
    try:
        from core.market_intelligence import run_pipeline
        result = run_pipeline()
        print("[SCHEDULER] MI Pipeline completed: %s" % result.get("status", "unknown"))
    except Exception as e:
        print("[SCHEDULER] MI Pipeline failed: %s" % e)


# --- Initialization ---------------------------------------------------------

def _init():
     """Initialize services. Data refresh runs in background thread to avoid blocking."""
     _load_config()
     _load_db()
      # Start data refresh in background thread so Flask can start immediately
     refresh_thread = threading.Thread(target=_refresh_data, daemon=True)
     refresh_thread.start()

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/hub2")
def hub2():
    """Jarvis Hub 2.0 — Market Intelligence Portal."""
    return render_template("hub2.html")


@app.route("/api/search", methods=["GET"])
def api_kb_search():
    """Search knowledge base."""
    query = request.args.get("q", "").strip()
    limit = int(request.args.get("limit", "20"))
    if not query:
        return jsonify({"results": [], "query": "", "total": 0})
    try:
        results = (search_knowledge(db, query) if db else []) or []
        return jsonify({"results": results, "query": query, "total": len(results)})
    except Exception as e:
        print("[KB] Search error: %s" % e)
        return jsonify({"results": [], "error": str(e)[:100]})


@app.route("/api/analyze", methods=["GET"])
def api_analyze_stock():
    """Analyze a single stock."""
    sym = request.args.get("symbol", "").upper().strip()
    if not sym:
        return jsonify({"error": "Missing symbol= parameter"}), 400
    try:
        result = analyze_stock(sym)
        if isinstance(result, dict) and "error" in result:
            return jsonify(result), 502
        return jsonify(result)
    except Exception as e:
        print("[ANALYZE] %s error: %s" % (sym, e))
        return jsonify({"symbol": sym, "error": str(e)}), 502


@app.route("/api/activities", methods=["GET"])
def api_activities():
    """Return recent activities."""
    try:
        if db and hasattr(db, "get_activities"):
            activities = db.get_activities(20)
        else:
            activities = []
        return jsonify({"count": len(activities), "activities": activities})
    except Exception as e:
        return jsonify({"count": 0, "activities": [], "error": str(e)})


@app.route("/api/watchlist", methods=["GET"])
def api_watchlist():
    """Return watchlist symbols."""
    try:
        if db and hasattr(db, "get_watchlist"):
            items = db.get_watchlist()
        else:
            items = []
        return jsonify({"symbols": items})
    except Exception as e:
        return jsonify({"symbols": [], "error": str(e)})


@app.route("/api/watchlist/add", methods=["POST"])
def api_watchlist_add():
    """Add symbol to watchlist."""
    try:
        if not db:
            return jsonify({"success": False, "error": "DB not initialized"})
        data = request.get_json() or {}
        symbol = str(data.get("symbol", "")).strip().upper()
        name = str(data.get("name", "")).strip()
        if len(symbol) < 2:
            return jsonify({"success": False, "error": "Invalid symbol"})
        if hasattr(db, "add_watchlist"):
            added = db.add_watchlist(symbol, name)
            return jsonify({"success": True, "added": added})
        return jsonify({"success": True, "added": symbol})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/watchlist/remove", methods=["POST"])
def api_watchlist_remove():
    """Remove symbol from watchlist."""
    try:
        if not db:
            return jsonify({"success": False, "error": "DB not initialized"})
        data = request.get_json() or {}
        symbol = str(data.get("symbol", "")).strip().upper()
        if len(symbol) < 2:
            return jsonify({"success": False, "error": "Invalid symbol"})
        if db and hasattr(db, "remove_from_watchlist"):
            removed = db.remove_from_watchlist(symbol)
            return jsonify({"success": True, "removed": removed})
        return jsonify({"success": True, "removed": symbol})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/snapshots", methods=["GET"])
def api_snapshots():
    """Return last 5 days of daily briefings."""
    try:
        if not db or not hasattr(db, "get_all_dates"):
            return jsonify({"count": 0, "snapshots": []})
        dates = db.get_all_dates()
        snapshots = []
        for date in dates[:5]:
            snap = db.get_daily_snapshot(date)
            if snap:
                content = snap.get("briefing_content", "")
                preview = content[:300].replace("\n", " ") if content else ""
                article_count = content.count("**.") if content else 0
                snapshots.append({
                    "date": date,
                    "preview": preview,
                    "article_count": article_count,
                    "full_content": content,
                })
        return jsonify({"count": len(snapshots), "snapshots": snapshots})
    except Exception as e:
        return jsonify({"count": 0, "snapshots": [], "error": str(e)})


@app.route("/api/daily-snapshot/<date>", methods=["GET"])
def api_daily_snapshot(date):
    """Return a daily snapshot for a specific date."""
    try:
        if not db or not hasattr(db, "get_daily_snapshot"):
            return jsonify({"status": "error", "message": "DB not initialized"})
        data = db.get_daily_snapshot(date)
        if not data:
            return jsonify({"status": "error", "date": date, "message": "No data for %s" % date}), 404
        return jsonify({"status": "ok", "data": data})
    except Exception as e:
        print("[WARN] Snapshot fetch failed for %s: %s" % (date, str(e)))
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/articles", methods=["GET"])
def api_articles():
    """Fetch articles from DB (Tier 1 cron), optionally filtered by category."""
    try:
        if not db or not hasattr(db, "get_articles"):
            return jsonify({"articles": [], "count": 0, "note": "DB not initialized"})

        cat_filter = request.args.get("category", "").strip().lower() or None
        arts = db.get_articles(limit=30, category=cat_filter) or []

        # Map DB record -> dashboard format
        result = []
        for a in arts[:30]:
            entry = {
                "id": a.get("id"),
                "title": a.get("title", ""),
                "summary_raw": a.get("summary_raw", ""),
                "category": a.get("category", "general"),
                "sentiment_class": a.get("sentiment", "TRUNG_LAP"),
                "published": a.get("publication_date", ""),
                "link": a.get("url", ""),
            }
            # Merge news_enhanced data if DB has it
            try:
                ne_row = db._c().execute(
                    "SELECT content, sentiment_score, importance FROM news_enhanced WHERE article_id=?",
                    (a.get("id"),)
                ).fetchone()
                if ne_row:
                    entry["content"] = ne_row[0] or ""
                    entry["sentiment_score"] = float(ne_row[1]) if ne_row[1] else 0.0
                    entry["importancescore"] = float(ne_row[2]) if ne_row[2] else 0.0
            except Exception:
                pass
            result.append(entry)

        return jsonify({"articles": result, "count": len(result), "source": "DB"})
    except Exception as e:
        print("[ARTICLES] DB fetch error: %s" % e)
        return jsonify({"articles": [], "error": str(e)[:100]})


@app.route("/api/market-evaluation", methods=["GET"])
def api_market_evaluation():
    """Return today's or most recent market evaluation."""
    if not db or not hasattr(db, "get_all_evaluations"):
        return jsonify({
            "status": "pending",
            "message": "Chua co danh gia. Nhap 'Generate' de tao danh gia.",
            "date": datetime.now().strftime("%Y-%m-%d"),
        })

    day_eval = None
    try:
        all_evals = db.get_all_evaluations() or []
        for ev in sorted(all_evals, key=lambda e: e.get("date", ""), reverse=True):
            if ev.get("date") < datetime.now().strftime("%Y-%m-%d"):
                day_eval = ev
                break
    except Exception:
        pass

    if not day_eval:
        return jsonify({
            "status": "pending",
            "message": "Chua co danh gia.",
            "date": datetime.now().strftime("%Y-%m-%d"),
        })

    return jsonify({
        "status": "ok",
        "date": day_eval.get("date"),
        "evaluation": day_eval.get("evaluation", ""),
        "summary": day_eval.get("summary", ""),
    })


def _build_llm_prompt(context_text):
    """Build the LLM prompt for evaluation generation."""
    return (
    "[ROLE]\n"
    "Chuyen gia phan tich tai chinh va dau tu chung khoan Viet Nam.\n\n"
    "[DATA]\n"
    "Dua tren du lieu hien tai:\n%s\n\n"
    "[OUTPUT REQUIREMENTS]\n"
    "Hay dua ra ban danh gia thi truong hom nay bang tieng Viet, khoang 400-800 tu. Bao gom:\n\n"
    "1. TONG QUAN XU HUONG: Danh gia xu huong chinh (bullish/bearish/neutral) + muc do tu tin (1-100%%) + ly do Chinh.\n\n"
    "2. CHI TIET TUNG PHAM TRU:\n"
    "   - Stock VN: Xu huong VN-Index, thanh phan sector manh/yeu nhat.\n"
    "   - Crypto: Top mover 24h, xu huong Bitcoin/ETH.\n"
    "   - VVBN/Vang: Gia vang hien tai, xu huong.\n"
    "   - Dau khi/Oil & USD Index/DXY: Di dong chinh va anh huong den VN market.\n\n"
    "3. RUI RO VA CO HOI:\n"
    "  - 2-3 rui ro can chu y (internal/external).\n"
    "  - 2-3 co hoi dau tu co the khai thac.\n\n"
    "4. KHUYEN NGHI DAU TU:\n"
    "  - Short-term (1-5 ngay): Actionable recommendation (Mua/Ban/Khoi hold) theo sector/currency.\n"
    "  - Risk level: Thap/Trung binh/Cao cho moi vung gia tri.\n"
    "  - Stop-loss suggested level (neu co).\n\n"
    "[FORMAT]\n"
    "Sinh ket qua theo duong dan markdown format, su dung bullet poinrs va headers de de doc. KHONG SU DUNG DANH SO 1-2-3-"
    )


def _call_ollama(prompt):
    """Call Ollama API to generate evaluation."""
    from concurrent.futures import ThreadPoolExecutor

    ollama_url = (config or {}).get("ollama", {}).get("url", "http://localhost:11434")
    model = (config or {}).get("ollama", {}).get("model", "Qwen3.6-35B-A3B-MLX-8bit")

    try:
        r = requests.post(
            "%s/v1/chat/completions" % ollama_url,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "Ban la chuyen gia phan tich thi truong tai chinh Viet Nam. Tra loi bang tieng Viet."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {"num_predict": 4096, "temperature": 0.7},
            },
            timeout=120,
        )
        if r.status_code == 200:
            resp = r.json()
            text = (resp.get("message", {}).get("content", "") or resp.get("response", "")).strip()
            return text if text else None
        print("[EVAL] Ollama returned %s" % r.status_code)
        return None
    except requests.exceptions.Timeout:
        print("[EVAL] Timeout")
        return None
    except Exception as e:
        print("[EVAL] Error: %s" % e)
        return None


@app.route("/api/market-evaluation/generate", methods=["POST"])
def api_generate_evaluation():
    """Trigger LLM to generate a new evaluation with fresh data."""
    if not config:
        return jsonify({"error": "Config not loaded yet"}), 503

    try:
        # Fetch fresh articles
        articles = []
        try:
            art_fresh = get_articles(limit=20) or []
            for a in art_fresh:
                if _enrich_article:
                    _enrich_article(a, use_llm=False)
            articles = art_fresh
        except Exception as e:
            print("[EVAL] Articles refresh failed: %s" % e)

        # Fetch fresh market data  
        results = {}
        try:
            idx = fetch_market_indices() or {}
            if "vn_indices" in idx:
                results["vn_indices"] = idx["vn_indices"]
            if "global_indices" in idx:
                results["global_indices"] = idx["global_indices"]
        except Exception as e:
            print("[REFRESH] Indices failed: %s" % e)

        for sym, key in [("BTC", "crypto_BTC"), ("ETH", "crypto_ETH"), ("SOL", "crypto_SOL")]:
            try:
                data = fetch_crypto(sym)
                if data:
                    results[key] = data
            except Exception:
                pass

        try:
            gold = fetch_gold() or {}
            if gold:
                results["gold"] = gold
        except Exception:
            pass

        try:
            dxy = fetch_dxy()
            if dxy:
                results["dxy"] = dxy
        except Exception:
            pass

        try:
            oil = fetch_oil() or {}
            if oil:
                results["oil"] = oil
        except Exception:
            pass

        # Build context
        ctx_parts = []
        vn_idx = results.get("vn_indices", {}) or results.get("indices", {}).get("vn_indices", {})
        for name, info in (vn_idx.items() if isinstance(vn_idx, dict) else []):
            if isinstance(info, dict) and "price" in info:
                arrow = "\u25B2" if info.get("change_pct", 0) >= 0 else "\u25BC"
                ctx_parts.append("%s: %s (%.2f%%)" % (name, info.get("price", "?"), abs(info.get("change_pct", 0))))

        global_idx = results.get("global_indices", {}) or results.get("indices", {}).get("global_indices", {})
        for name, info in sorted(global_idx.items())[:5]:
            if isinstance(info, dict) and "price" in info:
                arrow = "\u25B2" if info.get("change_pct", 0) >= 0 else "\u25BC"
                ctx_parts.append("%s: %s (%.2f%%)" % (name, info.get("price", "?"), abs(info.get("change_pct", 0))))

        crypto_info = []
        for prefix in ("BTC", "ETH", "SOL"):
            for k, v in results.items():
                if k.startswith("crypto_" + prefix) and isinstance(v, dict):
                    sym = v.get("symbol", prefix)
                    ch = v.get("change_pct", 0) or 0
                    crypto_info.append("%s: $%s (%.2f%%)" % (sym, v.get("price", "?"), abs(ch)))

        gold_data = results.get("gold", {})
        gold_info = ""
        if isinstance(gold_data, dict) and "price" in gold_data:
            arrow_g = "\u25B2" if gold_data.get("change_pct", 0) >= 0 else "\u25BC"
            gold_info = "Vang: $%s (%.2f%%)" % (gold_data.get("price", "N/A"), abs(gold_data.get("change_pct", 0)))

        dxy_info = ""
        if isinstance(results.get("dxy"), dict) and "price" in results["dxy"]:
            dxy_info = "DXY: %s" % results["dxy"].get("price", "N/A")

        oil_info = ""
        oil_input = results.get("oil")
        if isinstance(oil_input, dict) and "price" in oil_input:
            oil_info = "Dau khi (WTI): $%s" % oil_input["price"]

        rates_data = results.get("rates", {})
        rates_info = ""
        if isinstance(rates_data, dict) and rates_data.get("USD"):
            usd = rates_data["USD"]
            transfer = float(usd.get("transfer", 0))
            retail = float(usd.get("retail", 0))
            rates_info = "USD: Chuyen kho (%.0f), ban le (%.0f)" % (transfer, retail)

        sent_counts = {"positive": 0, "negative": 0, "neutral": 0}
        for a in articles[:20]:
            sc = a.get("sentiment_class", "neutral")
            if sc in sent_counts:
                sent_counts[sc] += 1

        context_text = "\n".join([
            "VIEN BAN:",
            "INDICES: %s" % (", ".join(ctx_parts) if ctx_parts else "N/A"),
            "CRYPTO: %s" % (", ".join(crypto_info) if crypto_info else "N/A"),
            "VANG: %s" % (gold_info or "N/A"),
            "DXY: %s" % (dxy_info or "N/A"),
            "Dau khi (WTI): %s" % (oil_info or "N/A"),
            "TI LE USD/VND: %s" % (rates_info or "N/A"),
            "CAM XUC TIN TUC: Positive=%d, Negative=%d, Neutral=%d tong %d tin." % (
                sent_counts["positive"], sent_counts["negative"],
                sent_counts["neutral"], sum(sent_counts.values())),
        ])

        prompt = _build_llm_prompt(context_text)
        text = _call_ollama(prompt)

        if text:
            summary = text[:300] + "..." if len(text) > 300 else text
            if db and hasattr(db, "save_market_evaluation"):
                try:
                    db.save_market_evaluation(
                        datetime.now().strftime("%Y-%m-%d"),
                        text, summary,
                    )
                except Exception as e:
                    print("[EVAL] Save failed: %s" % e)
            return jsonify({"evaluation": text, "summary": summary})

        return jsonify({"error": "Ollama did not return useful response"}), 502

    except requests.exceptions.Timeout:
        return jsonify({"error": "LLM timed out — retry when network is stable"}), 504
    except Exception as e:
        print("[EVAL] Generation failed: %s" % e)
        return jsonify({"error": str(e)}), 503


@app.route("/api/market-evaluation/history", methods=["GET"])
def api_eval_history():
    """Return historical market evaluations."""
    try:
        all_evals = db.get_all_evaluations() if (db and hasattr(db, "get_all_evaluations")) else []
        return jsonify({"status": "ok", "evaluations": all_evals})
    except Exception as e:
        return jsonify({"status": "error", "evaluations": [], "error": str(e)[:100]})


@app.route("/api/health", methods=["GET"])
def api_health():
    """Enhanced health per DASHBOARD_API.md - data levels OK/degraded/error."""
    ollama_status = "unknown"
    try:
        base_url = (config or {}).get("ollama", {}).get(
            "url", "http://localhost:11434"
        ) if config else "http://localhost:11434"
        r = requests.get(base_url + "/v1/models", timeout=5)
        ollama_status = "online" if r.status_code == 200 else "offline"
    except Exception as e:
        ollama_status = "error: %s" % str(e)[:40]

    cache_age = int(datetime.now().timestamp() - _cache_time)

    # Determine health level by cache freshness
    if cache_age < 300:
        h_level = "ok"
    elif cache_age < 1800:
        h_level = "degraded"
    else:
        h_level = "error"

    fresh = _fresh_cache or {}

    return jsonify({
        "status": h_level,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ollama": ollama_status,
        "db_path": str((config or {}).get("db_path", ":memory:")),
        "vn_indices": fresh.get("vn_indices", {}),
        "global_indices": fresh.get("global_indices", {}),
        "rates": fresh.get("rates", {}),
        "crypto": {k: v for k, v in fresh.items() if k.startswith("crypto_")},
        "gold": fresh.get("gold"),
        "dxy": fresh.get("dxy"),
        "oil": fresh.get("oil"),
        "cache_age_seconds": cache_age,
    })


@app.route("/api/indices", methods=["GET"])
def api_indices():
    """Fetch + return VN-Index + global market indices from DB."""
    try:
        if not db or not hasattr(db, "get_latest_overview"):
            return jsonify({
                "vn_indices": {},
                "global_indices": {},
                "note": "DB not initialized — run Tier 1 data collection first"
            })
        overview = db.get_latest_overview() or {}
        vn_idx = overview.get("vn_indices", {}) or overview.get("VN-Index", {}) or {}
        glb = overview.get("global_indices", {}) or overview.get("Global", {}) or {}
        # Also try fallback from market_overview table
        if not vn_idx:
            for row in db._c().execute(
                "SELECT symbol, price, change_pct FROM market_overview WHERE asset_type='index'").fetchall():
                vn_idx[row[0]] = {"price": row[1], "change_pct": row[2]}
        if not glb:
            for row in db._c().execute(
                "SELECT symbol, price, change_pct FROM market_overview WHERE asset_type IN ('global','fx')").fetchall():
                glb[row[0]] = {"price": row[1], "change_pct": row[2]}
        return jsonify({
            "vn_indices": vn_idx,
            "global_indices": glb,
            "source": "DB",
            "updated_at": overview.get("updated_at", ""),
        })
    except Exception as e:
        print("[INDICES] DB fetch error: %s" % e)
        return jsonify({"vn_indices": {}, "global_indices": {}, "error": str(e)}), 502



@app.route("/api/signals", methods=["GET"])
def api_get_signals():
    """Get unified signal feed from both tables, merged and deduplicated."""
    if not db:
        return jsonify({"signals": [], "error": "DB not initialized"})

    try:
        signal_filter = request.args.get("signal", "").upper()
        severity_filter = request.args.get("severity", "").upper()
        symbol_filter = request.args.get("symbol", "").upper()
        only_unread = request.args.get("unread", "false").lower() == "true"

        all_signals = []
        source_counts = {"signals_log": 0, "trading_alerts": 0}

        # Table 1: signals_log
        try:
            rows = db._c().execute("""
                SELECT id, symbol, 'TRADING_BOT' as source, signal_type,
                    CAST(strength AS TEXT) as severity, price, details,
                    detected_at as timestamp, delivered as is_delivered, delivery_channel
                FROM signals_log WHERE 1=1
            """).fetchall()
            for row in rows:
                r = dict(row)
                if signal_filter and r["signal_type"] != signal_filter:
                    continue
                if symbol_filter and r["symbol"] != symbol_filter:
                    continue
                all_signals.append(r)
                source_counts["signals_log"] += 1
        except Exception as e:
            print("[SIGNALS] signals_log error (table may not exist): %s" % e)

        # Table 2: trading_alerts
        try:
            rows = db._c().execute("""
                SELECT id, symbol, 'AUTO_SCAN' as source, signal_type, severity AS severity,
                    CAST(alert_data->>'price' AS REAL) as price, alert_data,
                    timestamp as detected_at,
                    CASE WHEN status='read' THEN 1 ELSE 0 END as is_delivered,
                    delivery_channel FROM trading_alerts
            """).fetchall()
            for row in rows:
                r = dict(row)
                raw = r.get("alert_data")
                if isinstance(raw, str):
                    try:
                        r["alert_parsed"] = json.loads(raw)
                    except Exception:
                        r["alert_parsed"] = None
                else:
                    r["alert_parsed"] = raw
                del r["alert_data"]

                if signal_filter and r["signal_type"] != signal_filter:
                    continue
                if symbol_filter and r["symbol"] != symbol_filter:
                    continue
                if only_unread and r.get("is_delivered"):
                    continue
                all_signals.append(r)
                source_counts["trading_alerts"] += 1
        except Exception as e:
            print("[SIGNALS] trading_alerts error: %s" % e)

        # Sort by timestamp descending
        all_signals.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Deduplicate: keep latest per symbol
        best_by_symbol = {}
        neutral_kept = []
        for sig in all_signals:
            sym = sig["symbol"]
            stype = sig.get("signal_type", "NEUTRAL")
            if stype in ("NEUTRAL", "HOLD"):
                if sym not in [s["symbol"] for s in neutral_kept]:
                    neutral_kept.append(sig)
                continue
            key = (sym, stype)
            if key not in best_by_symbol or sig.get("timestamp", "") > best_by_symbol[key].get("timestamp", ""):
                if key in best_by_symbol:
                    old = best_by_symbol[sym]
                    if old not in neutral_kept and old["symbol"] not in [s["symbol"] for s in neutral_kept]:
                        neutral_kept.append(old)
                best_by_symbol[key] = sig

        seen_syms = set()
        deduped_neutral = []
        for s in neutral_kept:
            if s["symbol"] not in seen_syms:
                seen_syms.add(s["symbol"])
                deduped_neutral.append(s)

        final_signals = list(best_by_symbol.values()) + deduped_neutral
        return jsonify({
            "signals": final_signals,
            "counts": {"total": len(final_signals), "by_source": source_counts},
        })
    except Exception as e:
        print("[SIGNALS] Error: %s" % str(e))
        return jsonify({"signals": [], "error": str(e)}, 500)


@app.route("/api/signals/latest", methods=["GET"])
def api_latest_signals():
    """Get the N most recent signals for grid overview."""
    limit = min(int(request.args.get("limit", "20")), 100)
    if not db:
        return jsonify({"signals": []})

    try:
        all_signals = []
        # From signals_log
        try:
            rows = db._c().execute("""
                SELECT symbol, 'TRADING_BOT' AS source, signal_type, CAST(strength AS REAL) as strength,
                    price, details, detected_at, delivered as is_delivered, delivery_channel
                FROM signals_log ORDER BY detected_at DESC LIMIT 50
            """).fetchall()
            for row in rows:
                r = dict(row)
                if isinstance(r.get("details"), str):
                    try:
                        r["details_parsed"] = json.loads(r["details"])
                    except Exception:
                        pass
                all_signals.append(r)
        except Exception:
            pass

        # From trading_alerts
        try:
            rows = db._c().execute("""
                SELECT symbol, 'AUTO_SCAN' AS source, signal_type, severity as strength,
                    CAST(alert_data->>'price' AS REAL) as price, alert_data as details,
                    timestamp as detected_at,
                    CASE WHEN status='read' THEN 1 ELSE 0 END AS is_delivered, delivery_channel
                FROM trading_alerts ORDER BY timestamp DESC LIMIT 50
            """).fetchall()
            for row in rows:
                r = dict(row)
                raw = r.get("details")
                if isinstance(raw, str):
                    try:
                        r["details_parsed"] = json.loads(raw)
                    except Exception:
                        r["details_parsed"] = None
                else:
                    r["details_parsed"] = raw
                del r["details"]
                all_signals.append(r)
        except Exception:
            pass

        all_signals.sort(key=lambda x: x.get("detected_at", ""), reverse=True)
        return jsonify({"signals": all_signals[:limit]})
    except Exception as e:
        return jsonify({"signals": [], "error": str(e)})


@app.route("/api/signals/symbol/<symbol>", methods=["GET"])
def api_signal_for_symbol(symbol):
    """Get all signals for a specific symbol (full history)."""
    if not db:
        return jsonify({"symbol": symbol, "signals": []})

    sym = str(symbol).upper().strip()
    signals = []

    # From signals_log
    try:
        rows = db._c().execute("""
            SELECT symbol, 'TRADING_BOT', signal_type, CAST(strength AS REAL) as strength,
                price, details, detected_at, delivered as is_delivered, delivery_channel
        FROM signals_log WHERE UPPER(symbol)=UPPER(?) ORDER BY detected_at DESC
        """, (sym,)).fetchall()
        for row in rows:
            r = dict(row)
            if isinstance(r.get("details"), str):
                try:
                    r["details_parsed"] = json.loads(r["details"])
                except Exception:
                    pass
            signals.append(r)
    except Exception as e:
        print("[SIGNALS] signals_log lookup %s error: %s" % (sym, e))

    # From trading_alerts
    try:
        rows = db._c().execute("""
            SELECT symbol, 'AUTO_SCAN', signal_type, severity as strength,
                CAST(alert_data->>'price' AS REAL) as price, alert_data as details,
                timestamp as detected_at,
                CASE WHEN status='read' THEN 1 ELSE 0 END AS is_delivered, delivery_channel
        FROM trading_alerts WHERE UPPER(symbol)=UPPER(?) ORDER BY timestamp DESC
        """, (sym,)).fetchall()
        for row in rows:
            r = dict(row)
            raw = r.get("details")
            if isinstance(raw, str):
                try:
                    r["details_parsed"] = json.loads(raw)
                except Exception:
                    pass
            signals.append(r)
    except Exception as e:
        print("[SIGNALS] trading_alerts lookup %s error: %s" % (sym, e))

    signals.sort(key=lambda x: (x.get("detected_at", "") or x.get("timestamp", "")), reverse=True)
    return jsonify({"symbol": sym, "signals": signals})


@app.route("/api/signals/add", methods=["POST"])
def api_signal_append():
    """Manual signal entry via dashboard or API."""
    if not db:
        return jsonify({"success": False, "error": "DB not initialized"}), 500

    data = request.get_json() or {}
    sym = str(data.get("symbol", "")).strip().upper()
    signal_type = str(data.get("signal", "")).upper()
    strength = float(data.get("strength", 0))

    if not sym or len(sym) < 2:
        return jsonify({"success": False, "error": "Invalid symbol"}), 400
    valid_types = ("BUY", "SELL", "HOLD", "STOP_LOSS", "TAKE_PROFIT", "WATCH", "NEUTRAL")
    if signal_type and signal_type not in valid_types:
        return jsonify({"success": False, "error": "Invalid signal type"}), 400

    details = {k: v for k, v in data.items() if k not in ("symbol", "signal", "strength")}

    try:
        db._c().execute("""
            INSERT INTO signals_log (symbol, signal_type, strength, price, details, detected_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (sym, signal_type if signal_type else "NEUTRAL", strength,
            data.get("price"), json.dumps(details), _utc_now_iso()))
        db._conn.commit()
        print("[SIGNALS] Added %s: %s (%.1f)" % (sym, signal_type, strength))
        return jsonify({"success": True})
    except Exception as e:
        if "no such table" in str(e):
            return jsonify({"success": False, "error": "signals_log not found"}), 500
        print("[SIGNALS] Insert error: %s" % e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/signals/mark-delivered", methods=["POST"])
def api_signal_mark_delivered():
    """Mark signal as delivered for cron delivery."""
    if not db:
        return jsonify({"success": True})

    try:
        rowcount = 0
        payload = request.json
        if payload:
            sid = payload.get("id")
            if sid:
                rowcount = (db._c().execute(
                    "UPDATE signals_log SET delivered=1 WHERE id=? AND is_delivered=0",
                    (sid,),).rowcount)
        db._conn.commit()
        return jsonify({"success": True, "marked": rowcount})
    except Exception as e:
        print("[SIGNALS] Mark delivered error: %s" % e)
        return jsonify({"success": False, "error": str(e)})


# Trading Alert Feed APIs

@app.route("/api/alert-feed", methods=["GET"])
def api_get_alert_feed():
    """Get trading alerts sorted by recency."""
    if not db:
        return jsonify({"alerts": [], "filters_applied": []})

    signal = request.args.get("signal", "").upper()
    severity = request.args.get("severity", "").upper()
    symbol_filter = request.args.get("symbol", "").upper()

    try:
        filters_applied = []
        conditions = ["1=1"]
        params = []

        if signal:
            conditions.append("signal_type = ?")
            params.append(signal)
            filters_applied.append("signal=" + signal)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)
            filters_applied.append("severity=" + severity)
        if symbol_filter:
            conditions.append("symbol = ?")
            params.append(symbol_filter)
            filters_applied.append("symbol=" + symbol_filter)

        where_clause = " AND ".join(conditions)
        rows = db._c().execute(
            "SELECT * FROM trading_alerts WHERE %s ORDER BY timestamp DESC LIMIT 100" % where_clause,
            params,).fetchall()

        alerts = [dict(r) for r in rows]
        for a in alerts:
            raw = a.get("alert_data")
            if isinstance(raw, str):
                try:
                    a["alert_data"] = json.loads(raw)
                except Exception:
                    pass
        return jsonify({"alerts": alerts, "filters_applied": filters_applied})
    except Exception as e:
        print("[ALERT-FEED] Error: %s" % e)
        return jsonify({"alerts": [], "errors": [str(e)]})


def trigger_alert(sym, signal_type, data_obj):
    """Insert alert into trading_alerts table."""
    if not db or not hasattr(db, "_c"):
        return False
    try:
        import sqlite3 as _sqlite3
        if isinstance(data_obj, dict):
            raw_json = json.dumps(data_obj)
        else:
            raw_json = str(data_obj)

        db._c().execute("""
            INSERT INTO trading_alerts (symbol, signal_type, severity, alert_data, timestamp, status)
            VALUES (?, ?, 'MEDIUM', ?, datetime('now'), 'pending')
        """, (sym.upper(), signal_type, raw_json))
        db._conn.commit()
        return True
    except Exception as e:
        print("[ALERT] Insert failed for %s: %s" % (sym, e))
        return False


@app.route("/api/alert-feed/auto-scan", methods=["GET"])
def api_auto_scan():
    """Trigger auto-scan of watchlist for trading signals."""
    if not db or not config:
        return jsonify({"scanned": 0, "new_alerts": 0, "error": "DB/Config not initialized"})

    try:
        watchlist = db.get_watchlist() if hasattr(db, "get_watchlist") else []
        if not watchlist:
            return jsonify({"scanned": 0, "new_alerts": 0, "message": "Watchlist is empty"})

        results = {"scanned": 0, "new_alerts": 0}
        for item in watchlist:
            sym = item["symbol"] if isinstance(item, dict) else str(item)
            try:
                result = analyze_stock(sym)
                if not result or "error" in result or not result.get("price"):
                    continue

                results["scanned"] += 1
                tech = result.get("technical", {}) or {}
                rsi_val = tech.get("rsi") or tech.get("RSI") or tech.get("RSI_14", 50)
                sma20 = tech.get("sma_20")
                macd_hist = tech.get("macd_histogram") if tech else None

                signal_type = "NEUTRAL"
                reason_parts = []

                rsi_num = float(rsi_val) if (rsi_val is not None and rsi_val != "") else 50
                change_pct = float(result.get("change_pct", 0))

                if rsi_num <= 30:
                    reason_parts.append("RSI oversold (%.1f)" % rsi_num)
                    signal_type = "BUY" if signal_type in ("NEUTRAL", "SELL") else signal_type
                elif rsi_num >= 70:
                    reason_parts.append("RSI overbought (%.1f)" % rsi_num)
                    signal_type = "SELL" if signal_type in ("NEUTRAL", "BUY") else signal_type

                price_num = float(result.get("price", 0))
                if sma20 and price_num:
                    if price_num < sma20 * 0.95:
                        reason_parts.append("Price below SMA20 (%.2f)" % sma20)
                        signal_type = "SELL" if signal_type in ("NEUTRAL", "BUY") else signal_type

                if macd_hist is not None:
                    try:
                        mh = float(macd_hist)
                        if mh < -0.5:
                            reason_parts.append("MACD momentum bearish")
                            signal_type = "SELL" if signal_type in ("NEUTRAL", "BUY") else signal_type
                        elif mh > 0.5:
                            reason_parts.append("MACD momentum bullish")
                            signal_type = "BUY" if signal_type in ("NEUTRAL", "SELL") else signal_type
                    except (TypeError, ValueError):
                        pass

                if change_pct <= -5:
                    reason_parts.append("Sharp drop (-%.1f%%)" % abs(change_pct))
                    signal_type = "SELL" if signal_type == "NEUTRAL" else signal_type
                elif change_pct >= 5:
                    reason_parts.append("Strong rally (+%.1f%%)" % change_pct)
                    signal_type = "BUY" if signal_type == "NEUTRAL" else signal_type

                if len(reason_parts) >= 3 and signal_type in ("BUY", "SELL"):
                    signal_type = "STRONG_" + signal_type
                elif len(reason_parts) == 0:
                    signal_type = "NEUTRAL"

                reason_str = "; ".join(reason_parts) if reason_parts else "No strong signal detected"

                # Avoid spam: don't alert same symbol more than once per 6 hours
                existing = db._c().execute(
                    "SELECT id FROM trading_alerts WHERE symbol=? AND timestamp > datetime('now', '-6 hours') LIMIT 1",
                    (sym,),).fetchone() if hasattr(db, "_c") else None

                is_neutral = signal_type == "NEUTRAL"
                if not existing and not is_neutral:
                    trigger_alert(sym, signal_type, {
                        "price": result.get("price"),
                        "change_pct": change_pct,
                        "rsi_14": rsi_val,
                        "sma_20": sma20,
                        "macd_histogram": macd_hist,
                        "signal_reason": reason_str,
                    })
                    results["new_alerts"] += 1

            except Exception as e:
                print("[AUTO-SCAN] Error scanning %s: %s" % (sym, e))

        return jsonify({
            "scanned": results["scanned"],
            "new_alerts": results["new_alerts"],
            "watchlist_count": len(watchlist),
        })
    except Exception as e:
        print("[AUTO-SCAN] Auto-scan failed: %s" % e)
        return jsonify({"scanned": 0, "new_alerts": 0, "error": str(e)})


@app.route("/api/alert-feed/clear", methods=["POST"])
def api_clear_alert_feed():
    """Mark all alerts as read."""
    if not db:
        return jsonify({"success": False, "error": "DB not initialized"})
    try:
        if hasattr(db, "mark_alerts_as_read"):
            db.mark_alerts_as_read()
        elif hasattr(db, "_c"):
            db._c().execute("UPDATE trading_alerts SET status='read' WHERE status!='read'")
            db._conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/signal/feed/clear", methods=["POST"])
def api_signal_feed_clear_alias():
    """Alias for /api/alert-feed/clear to match DASHBOARD_API.md spec."""
    return api_clear_alert_feed()

@app.route("/api/auto-scan", methods=["GET"])
def api_autoscan_alias():
    """Alias for /api/alert-feed/auto-scan to match DASHBOARD_API.md spec."""
    return api_auto_scan()


# ============================================================================
#  HUB 2.0 API — /api/v1/*
# ============================================================================

@app.route("/health", methods=["GET"])
def api_health_v2():
    """Hub 2.0 health check endpoint."""
    health = {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "flask": "running",
        "db": "connected" if db else "disconnected",
        "ollama": "unknown",
    }
    try:
        cfg = __import__("core.config", fromlist=["load_config"]).load_config()
        ollama_url = cfg.get("ollama", {}).get("url", "http://localhost:11434")
        r = requests.get(f"{ollama_url}/api/tags", timeout=5)
        health["ollama"] = "healthy" if r.status_code == 200 else "unhealthy"
    except Exception:
        health["ollama"] = "unreachable"
    return jsonify(health)


# --- Overview API ---


# ============================================================================
#  SYSTEM LOGS ENDPOINT
# ============================================================================

@app.route("/logs", methods=["GET"])
def get_logs():
    """Get system logs from activity_log and signals_log tables."""
    try:
        import sqlite3
        db_path = str((config or {}).get("db_path", "/Users/nghialam/jarvis-hub/knowledge/jarvis.db"))
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        results = {}
        
        # Activity logs (system commands, CLI runs)
        try:
            cur.execute("SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT 100")
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description] if cur.description else []
            results["activity_logs"] = {
                "count": len(rows),
                "columns": cols, 
                "data": [dict(zip(cols, r)) for r in rows]
            }
        except Exception as e:
            results["activity_logs"] = {"error": str(e)}
        
        # Signal logs (market signals)  
        try:
            cur.execute("SELECT * FROM signals_log ORDER BY detected_at DESC LIMIT 200")
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description] if cur.description else []
            results["signal_logs"] = {
                "count": len(rows),
                "columns": cols,
                "data": [dict(zip(cols, r)) for r in rows]
            }
        except Exception as e:
            results["signal_logs"] = {"error": str(e)}
            
        # Trading alerts  
        try:
            cur.execute("SELECT * FROM trading_alerts ORDER BY timestamp DESC LIMIT 100")
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description] if cur.description else []
            results["trading_alerts"] = {
                "count": len(rows),
                "columns": cols,
                "data": [dict(zip(cols, r)) for r in rows]  
            }
        except Exception as e:
            results["trading_alerts"] = {"error": str(e)}

        conn.close()
        
        return jsonify({"status": "ok", "logs": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route("/api/v1/overview", methods=["GET"])
def api_overview():
    """Get full market overview (indices, crypto, gold, oil, dxy)."""
    try:
        import core.market_overview as mo
        data = mo.fetch_all_overview()
        # Also add top motions
        try:
            data["top_motions"] = mo.get_top_motions(limit=10)
        except Exception:
            pass
        return jsonify({"status": "ok", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v1/overview/indices", methods=["GET"])
def api_overview_indices():
    """Get market indices (VN + global)."""
    try:
        import core.market_overview as mo
        vn = mo.fetch_vn_indices()
        global_idx = mo.fetch_global_indices()
        # Convert dicts to arrays for frontend
        vn_list = []
        for name, data in (vn or {}).items():
            vn_list.append({**data, "name": name, "symbol": data.get("symbol", name)})
        global_list = []
        for name, data in (global_idx or {}).items():
            global_list.append({**data, "name": name, "symbol": data.get("symbol", name)})
        return jsonify({"status": "ok", "vn": vn_list, "global": global_list})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v1/overview/crypto", methods=["GET"])
def api_overview_crypto():
    """Get crypto prices."""
    try:
        import core.market_overview as mo
        data = mo.fetch_crypto()
        # Convert dict to array for frontend
        crypto_list = []
        for name, d in (data or {}).items():
            crypto_list.append({**d, "name": name, "symbol": d.get("symbol", name)})
        return jsonify({"status": "ok", "data": crypto_list})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v1/overview/gold", methods=["GET"])
def api_overview_gold():
    """Get gold price."""
    try:
        import core.market_overview as mo
        data = mo.fetch_gold()
        return jsonify({"status": "ok", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v1/overview/motions", methods=["GET"])
def api_overview_motions():
    """Get top gainers/losers."""
    try:
        import core.market_overview as mo
        symbols = request.args.get("symbols", "").split(",") if request.args.get("symbols") else None
        data = mo.get_top_motions(symbols=symbols, limit=int(request.args.get("limit", 10)))
        # Flatten gainers + losers into one array for frontend
        flat = []
        if isinstance(data, dict):
            flat.extend(data.get("gainers", []) or [])
            flat.extend(data.get("losers", []) or [])
        elif isinstance(data, list):
            flat = data
        return jsonify({"status": "ok", "data": flat})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v1/overview/chart", methods=["GET"])
def api_overview_chart():
    """Get chart data for a symbol."""
    symbol = request.args.get("symbol", "")
    if not symbol:
        return jsonify({"status": "error", "error": "Missing symbol"}), 400
    try:
        import core.market_overview as mo
        data = mo._fetch_yahoo_price(symbol)
        return jsonify({"status": "ok", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# --- News Hub API ---

@app.route("/api/v1/news", methods=["GET"])
def api_news_list():
    """Get enhanced news with filters."""
    try:
        category = request.args.get("category", "all")
        sentiment = request.args.get("sentiment", "all")
        limit = int(request.args.get("limit", 50))
        days = int(request.args.get("days", 7))

        if db and hasattr(db, "get_news_enhanced"):
            articles = db.get_news_enhanced(
                category=category,
                sentiment=sentiment,
                limit=limit,
                timeframe_days=days,
            )
        else:
            # Fallback to existing news fetch
            import core.news_service as ns
            articles = ns.get_articles(limit=limit)

        return jsonify({"status": "ok", "count": len(articles), "articles": articles})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v1/news/trending", methods=["GET"])
def api_news_trending():
    """Get trending (high-importance) news."""
    try:
        if db and hasattr(db, "get_trending_news"):
            articles = db.get_trending_news(limit=10)
        return jsonify({"status": "ok", "count": len(articles), "articles": articles})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# --- Company API ---

@app.route("/api/v1/companies", methods=["GET"])
def api_companies():
    """Search companies by symbol or name."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"status": "ok", "count": 0, "companies": []})
    try:
        if db and hasattr(db, "_c"):
            rows = db._c().execute(
                """SELECT DISTINCT symbol, name FROM portfolio_watchlist
                WHERE UPPER(symbol) LIKE ? OR UPPER(name) LIKE ?
                LIMIT 50""",
                ("%" + query.upper() + "%", "%" + query.upper() + "%")).fetchall()
        else:
            rows = []
        companies = [dict(r) for r in rows]
        return jsonify({"status": "ok", "count": len(companies), "companies": companies})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v1/companies/<symbol>/news", methods=["GET"])
def api_company_news(symbol):
    """Get news for a specific company."""
    try:
        if db and hasattr(db, "get_news_enhanced"):
            # Search articles by affected_symbols or title
            rows = db._c().execute(
                """SELECT * FROM news_enhanced
                WHERE affected_symbols LIKE ? OR title LIKE ?
                AND published_at >= datetime('now', '-30 days')
                ORDER BY importance DESC, published_at DESC
                LIMIT 20""",
                ("%" + symbol.upper() + "%", "%" + symbol.upper() + "%")).fetchall()
        else:
            rows = []
        articles = [dict(r) for r in rows]
        return jsonify({"status": "ok", "count": len(articles), "articles": articles})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# --- Research Hub API ---

@app.route("/api/v1/research", methods=["GET"])
def api_research():
    """Get brokerage reports with filters."""
    try:
        broker = request.args.get("broker", "all")
        period = request.args.get("period", "1m")
        limit = int(request.args.get("limit", 20))

        if db and hasattr(db, "get_brokerage_reports"):
            reports = db.get_brokerage_reports(broker=broker, period=period, limit=limit)
        else:
            reports = []
        return jsonify({"status": "ok", "count": len(reports), "reports": reports})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v1/research/stats", methods=["GET"])
def api_research_stats():
    """Get report stats per broker."""
    try:
        if db and hasattr(db, "get_brokerage_stats"):
            stats = db.get_brokerage_stats()
        else:
            stats = []
        return jsonify({"status": "ok", "stats": stats})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v1/research/crawl", methods=["POST"])
def api_research_crawl():
    """Trigger a research crawl."""
    try:
        import core.research_crawler as rc
        result = rc.run_crawl_and_store(db=db)
        return jsonify({"status": "ok", "result": result})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# --- Portfolio Watchlist API ---

@app.route("/api/v1/watchlist/portfolio", methods=["GET"])
def api_portfolio_watchlist():
    """Get portfolio watchlist."""
    try:
        if db and hasattr(db, "get_portfolio_watchlist"):
            items = db.get_portfolio_watchlist()
        else:
            items = []
        return jsonify({"status": "ok", "count": len(items), "watchlist": items})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v1/watchlist/portfolio/add", methods=["POST"])
def api_portfolio_watchlist_add():
    """Add to portfolio watchlist."""
    try:
        data = request.get_json() or {}
        symbol = str(data.get("symbol", "")).strip().upper()
        name = str(data.get("name", "")).strip()
        sector = str(data.get("sector", "")).strip()
        if len(symbol) < 2:
            return jsonify({"status": "error", "error": "Invalid symbol"})
        if db and hasattr(db, "add_portfolio_watchlist"):
            db.add_portfolio_watchlist(symbol, name, sector)
        return jsonify({"status": "ok", "symbol": symbol})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v1/watchlist/portfolio/remove", methods=["POST"])
def api_portfolio_watchlist_remove():
    """Remove from portfolio watchlist."""
    try:
        data = request.get_json() or {}
        symbol = str(data.get("symbol", "")).strip().upper()
        if db and hasattr(db, "remove_portfolio_watchlist"):
            db.remove_portfolio_watchlist(symbol)
        return jsonify({"status": "ok", "symbol": symbol})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# --- Portfolio P&L API ---

@app.route("/api/v1/portfolio/holdings", methods=["GET"])
def api_portfolio_holdings():
    """Get current portfolio holdings with net quantity, avg cost, total invested."""
    try:
        if db and hasattr(db, "get_portfolio_holdings"):
            holdings = db.get_portfolio_holdings()
        else:
            holdings = []
        for h in holdings:
            live_price = _get_cached_price(h['symbol'])
            qty = float(h.get('net_quantity', 0))
            avg_cost = float(h.get('avg_cost', 0))
            h['current_price'] = live_price
            h['market_value'] = round(live_price * qty, 2) if live_price else 0
            h['pnl'] = round((live_price - avg_cost) * qty, 2) if (live_price and avg_cost) else 0
            h['pnl_pct'] = round(((live_price / avg_cost) - 1) * 100, 2) if (live_price and avg_cost) else 0
        return jsonify({"status": "ok", "count": len(holdings), "holdings": holdings})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v1/portfolio/transactions", methods=["GET"])
def api_portfolio_transactions():
    """Get transaction history, optionally filtered by symbol."""
    try:
        symbol = request.args.get("symbol", "").strip().upper() or None
        limit = int(request.args.get("limit", 100))
        if db and hasattr(db, "get_portfolio_transactions"):
            txns = db.get_portfolio_transactions(symbol=symbol, limit=limit)
        else:
            txns = []
        return jsonify({"status": "ok", "count": len(txns), "transactions": txns})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v1/portfolio/add-txn", methods=["POST"])
def api_portfolio_add_transaction():
    """Add a buy/sell transaction."""
    try:
        data = request.get_json() or {}
        symbol = str(data.get("symbol", "")).strip().upper()
        action = str(data.get("action", "buy")).strip().lower()
        quantity = float(data.get("quantity", 0))
        price = float(data.get("price", 0))
        name = str(data.get("name", "")).strip()
        txn_date = str(data.get("txn_date", "")).strip() or None
        note = str(data.get("note", "")).strip()
        if not symbol or quantity <= 0 or price <= 0:
            return jsonify({"status": "error", "error": "Missing/invalid required fields"}), 400
        if action not in ("buy", "sell"):
            return jsonify({"status": "error", "error": "Action must be buy or sell"}), 400
        tid = db.add_portfolio_transaction(symbol, action=action, quantity=quantity, price=price, name=name, txn_date=txn_date, note=note)
        return jsonify({"status": "ok", "transaction_id": tid})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v1/portfolio/delete-txn/<int:txn_id>", methods=["DELETE"])
def api_portfolio_delete_transaction(txn_id):
    """Delete a transaction by ID."""
    try:
        db.delete_portfolio_transaction(txn_id)
        return jsonify({"status": "ok", "transaction_id": txn_id})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v1/portfolio/pnl-summary", methods=["GET"])
def api_portfolio_pnl_summary():
    """Get overall portfolio P&L summary."""
    try:
        if db and hasattr(db, "get_portfolio_holdings"):
            holdings = db.get_portfolio_holdings()
        else:
            holdings = []

        total_cost_basis = 0.0
        total_current_value = 0.0
        for h in holdings:
            cost = float(h.get('total_bought', 0)) - float(h.get('total_sold', 0))
            qty = float(h.get('net_quantity', 0))
            avg_cost = float(h.get('avg_cost', 0))
            live_price = _get_cached_price(h['symbol'])

            h['cost_basis'] = cost
            h['current_price'] = live_price
            h['market_value'] = round(live_price * qty, 2) if live_price else 0
            h['pnl'] = round((live_price - avg_cost) * qty, 2) if live_price else 0
            h['pnl_pct'] = round(((live_price / avg_cost) - 1) * 100, 2) if (live_price and avg_cost) else 0

            total_cost_basis += cost
            total_current_value += h['market_value']

        overall_pnl = total_current_value - total_cost_basis
        overall_pnl_pct = ((total_current_value / total_cost_basis) - 1) * 100 if total_cost_basis else 0

        return jsonify({
             "status": "ok",
             "summary": {
                 "total_cost_basis": round(total_cost_basis, 2),
                 "total_current_value": round(total_current_value, 2),
                 "overall_pnl": round(overall_pnl, 2),
                 "overall_pnl_pct": round(overall_pnl_pct, 2),
             },
             "holdings": holdings
         })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


def _get_cached_price(symbol):
    """Try to get cached current price for a symbol."""
    # Try daily_ohlcv first (has x1000-correct prices)
    try:
        row = db._c().execute(
            "SELECT close FROM daily_ohlcv WHERE ticker=? ORDER BY date DESC LIMIT 1",
            (symbol,)
        ).fetchone()
        if row and float(row[0]) > 0:
            return float(row[0])
    except Exception:
        pass
    # Try price_history table
    try:
        row = db._c().execute(
            "SELECT close FROM price_history WHERE symbol=? ORDER BY date DESC LIMIT 1",
            (symbol,)
        ).fetchone()
        if row and float(row[0]) > 0:
            return float(row[0])
    except Exception:
        pass
    # Try market_quotes table (column is 'ticker', not 'symbol') — need x1000 fix
    try:
        row = db._c().execute(
            "SELECT price FROM market_quotes WHERE ticker=? ORDER BY updated_at DESC LIMIT 1",
            (symbol,)
        ).fetchone()
        if row and float(row[0]) > 0:
            return max(float(row[0]), 1)   # guard against tiny /1000 prices
    except Exception:
        pass

    return 0


# --- Sector Heatmap API ---

@app.route("/api/v1/market/heatmap", methods=["GET"])
def api_sector_heatmap():
    """Get sector performance heatmap data."""
    try:
        import core.market_overview as mo
        # Get top movers and compute sector-level aggregates
        motions = mo.get_top_motions(limit=50)
        if not motions:
            return jsonify({"status": "ok", "sectors": []})

        # Group by sector if available, otherwise by performance buckets
        sectors = {}
        gainers = motions.get("gainers", []) or []
        losers = motions.get("losers", []) or []

        for stock in gainers + losers:
            sector = stock.get("sector", "Unknown")
            if sector not in sectors:
                sectors[sector] = {"gainers": 0, "losers": 0, "avg_change": 0, "total": 0, "stocks": []}
            pct = stock.get("change_pct", 0)
            if pct >= 0:
                sectors[sector]["gainers"] += 1
            else:
                sectors[sector]["losers"] += 1
            sectors[sector]["total"] += 1
            sectors[sector]["stocks"].append({
                "symbol": stock.get("symbol", ""),
                "change_pct": pct,
                "price": stock.get("price", ""),
            })

        # Compute average change per sector
        for sector in sectors:
            stocks = sectors[sector]["stocks"]
            if stocks:
                sectors[sector]["avg_change"] = round(
                    sum(s["change_pct"] for s in stocks) / len(stocks), 2
                )

        # Convert to list and sort by avg_change
        sector_list = [
            {
                "name": name,
                "avg_change": data["avg_change"],
                "gainers": data["gainers"],
                "losers": data["losers"],
                "total": data["total"],
                "stocks": data["stocks"][:5],  # top 5 stocks per sector
            }
            for name, data in sectors.items()
        ]
        sector_list.sort(key=lambda x: x["avg_change"], reverse=True)

        return jsonify({"status": "ok", "sectors": sector_list})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# --- Auto Refresh API ---

@app.route("/api/v1/market/auto-refresh/trigger", methods=["POST"])
def api_auto_refresh_trigger():
    """Manually trigger a data refresh."""
    try:
        _refresh_data()
        return jsonify({
            "status": "ok",
            "message": "Refresh triggered",
            "cache_age": 0,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# --- LLM News Scoring API ---

@app.route("/api/v1/news/score", methods=["POST"])
def api_news_score():
    """Score news articles using LLM for importance."""
    try:
        if not config:
            return jsonify({"status": "error", "error": "Config not loaded"}), 503

        # Get un-scored or low-scored articles
        if db and hasattr(db, "get_news_enhanced"):
            articles = db.get_news_enhanced(sentiment="all", limit=20, timeframe_days=1)
        else:
            articles = []

        if not articles:
            return jsonify({"status": "ok", "scored": 0, "articles": []})

        # Build prompt for LLM scoring
        scored_articles = []
        for article in articles:
            title = article.get("title", "")
            summary = article.get("summary", "") or article.get("content", "") or ""
            source = article.get("source", "")
            category = article.get("category", "")

            prompt = (
                "You are a Vietnamese financial market analyst. Score this news article's importance "
                "for Vietnam stock market investors on a scale of 1-10 (1=trivial, 10=critical).\n\n"
                f"Title: {title}\n"
                f"Summary: {summary[:500]}\n"
                f"Source: {source}\n"
                f"Category: {category}\n\n"
                "Return ONLY a JSON object with keys: importance (1-10), reason (short string).\n"
                "Examples: {\"importance\": 8, \"reason\": \"Directly impacts banking sector liquidity\"}"
            )

            try:
                ollama_url = (config or {}).get("ollama", {}).get("url", "http://localhost:11434")
                model = (config or {}).get("ollama", {}).get("model", "Qwen3.6-35B-A3B-MLX-8bit")
                r = requests.post(
                    f"{ollama_url}/v1/chat/completions",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "Ban la chuyen gia phan tich tai chinh. Tra loi bang JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                        "options": {"num_predict": 200, "temperature": 0.3},
                    },
                    timeout=30,
                )
                if r.status_code == 200:
                    resp = r.json()
                    content = resp.get("message", {}).get("content", "")
                    # Try to parse JSON from response
                    import re as _re
                    json_match = _re.search(r'\{[^}]*"importance"[^}]*\}', content)
                    if json_match:
                        score_data = json.loads(json_match.group())
                        article["importance"] = score_data.get("importance", 5)
                        article["importance_reason"] = score_data.get("reason", "")
                        scored_articles.append(article)
                        # Save to DB if possible
                        if db and hasattr(db, "update_news_importance"):
                            try:
                                db.update_news_importance(article.get("id"), article["importance"], article["importance_reason"])
                            except Exception:
                                pass
            except Exception as e:
                print(f"[SCORE] Error scoring article {article.get('id', '?')}: {e}")
                article["importance"] = 5  # default
                scored_articles.append(article)

        return jsonify({
            "status": "ok",
            "scored": len(scored_articles),
            "articles": scored_articles,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# --- AI Intelligence API (v2) ---

@app.route("/api/v2/ai-intelligence/daily-list", methods=["GET"])
def ai_intelligence_daily_list():
    """Return list of all run dates with article counts + summary."""
    try:
        if db and hasattr(db, "get_run_chains"):
            runs = db.get_run_chains(limit=30)
        else:
            runs = []

        result = []
        for run in runs:
            try:
                art_count = 0
                if db and hasattr(db, "get_articles"):
                    arts = db.get_articles(run_id=run.get("run_id"))
                    art_count = len(arts)
            except Exception:
                art_count = 0

            result.append({
                "run_id": run.get("run_id"),
                "date": run.get("pipeline_date"),
                "article_count": art_count,
                "total_articles": run.get("total_articles", art_count),
                "total_sources": run.get("total_sources", 0),
                "chain_1_summary": (run.get("llm_chain_1_summary", "") or "")[:200],
                "status": run.get("status", "complete"),
            })
        return jsonify({"status": "ok", "count": len(result), "runs": result})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v2/ai-finance/run/<run_id>", methods=["GET"])
def ai_intelligence_run_detail(run_id):
    """Return ALL data for one specific run — articles, recommendations, and metadata."""
    try:
        run_data = None
        articles = []
        recommendations = []

        if db:
            if hasattr(db, "get_run_chain"):
                run_data = db.get_run_chain(run_id)
            if hasattr(db, "get_articles"):
                articles = db.get_articles(run_id=run_id, limit=200)
            if hasattr(db, "get_recommendations"):
                recommendations = db.get_recommendations(run_id=run_id, limit=100)

        return jsonify({
            "status": "ok",
            "run_id": run_id,
            "run_data": run_data,
            "articles": articles,
            "article_count": len(articles),
            "recommendations": recommendations,
            "recommendation_count": len(recommendations),
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/v2/ai-finance/health", methods=["GET"])
def ai_intelligence_health():
    """Return pipeline health + last run status."""
    try:
        total_runs = 0
        last_run = None
        daily_avg = 0

        if db and hasattr(db, "get_run_chains"):
            runs = db.get_run_chains(limit=100)
            total_runs = len(runs)
            if runs:
                last_run = runs[0].get("pipeline_date")
                total_art = sum(r.get("total_articles", 0) for r in runs)
                daily_avg = round(total_art / max(total_runs, 1))

        return jsonify({
            "status": "ok",
            "last_run_date": last_run,
            "total_runs_saved": total_runs,
            "daily_avg_articles": daily_avg,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# --- Market Intelligence API Endpoints --------------------------------------

@app.route("/api/market-intelligence/run", methods=["POST"])
def api_market_intelligence_run():
    """Trigger the Market Intelligence pipeline immediately."""
    try:
        from core.market_intelligence import run_pipeline, determine_period
        result = run_pipeline()
        return jsonify(result)
    except Exception as e:
        print("[MI] Pipeline execution failed: %s" % e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/market-intelligence/latest", methods=["GET"])
def api_market_intelligence_latest():
    """Get the most recent Market Intelligence run."""
    try:
        if not db or not hasattr(db, "get_latest_market_intelligence"):
            return jsonify({"status": "error", "message": "DB not initialized"})
        data = db.get_latest_market_intelligence()
        if not data:
            return jsonify({"status": "not_found", "message": "No intelligence runs found"})
        return jsonify({"status": "ok", "data": data})
    except Exception as e:
        print("[MI] Latest fetch failed: %s" % e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/market-intelligence/history", methods=["GET"])
def api_market_intelligence_history():
    """List past Market Intelligence runs, optionally filtered by date."""
    try:
        if not db or not hasattr(db, "get_market_intelligence_history"):
            return jsonify({"status": "error", "message": "DB not initialized"})
        limit = request.args.get("limit", 20, type=int)
        data = db.get_market_intelligence_history(limit=limit)
        return jsonify({"status": "ok", "count": len(data), "runs": data})
    except Exception as e:
        print("[MI] History fetch failed: %s" % e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/market-intelligence/<int:run_id>", methods=["GET"])
def api_market_intelligence_by_id(run_id):
    """Get a specific Market Intelligence run by ID."""
    try:
        if not db or not hasattr(db, "get_market_intelligence_by_id"):
            return jsonify({"status": "error", "message": "DB not initialized"})
        data = db.get_market_intelligence_by_id(run_id)
        if not data:
            return jsonify({"status": "not_found", "message": "Run %d not found" % run_id}), 404
        return jsonify({"status": "ok", "data": data})
    except Exception as e:
        print("[MI] Run fetch failed for %d: %s" % (run_id, e))
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/market-intelligence/sentiment-dist", methods=["GET"])
def api_market_intelligence_sentiment():
    """Get sentiment distribution across all Market Intelligence runs."""
    try:
        if not db or not hasattr(db, "get_sentiment_distribution"):
            return jsonify({"status": "error", "message": "DB not initialized"})
        dist = db.get_sentiment_distribution()
        return jsonify({"status": "ok", "distribution": dist})
    except Exception as e:
        print("[MI] Sentiment fetch failed: %s" % e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/market-intelligence/<int:run_id>", methods=["DELETE"])
def api_market_intelligence_delete(run_id):
    """Delete a specific Market Intelligence run by ID."""
    try:
        if not db or not hasattr(db, "delete_market_intelligence"):
            return jsonify({"status": "error", "message": "DB not initialized"})
        deleted = db.delete_market_intelligence(run_id)
        if not deleted:
            return jsonify({"status": "not_found", "message": "Run %d not found" % run_id}), 404
        return jsonify({"status": "ok", "deleted": run_id})
    except Exception as e:
        print("[MI] Delete failed for %d: %s" % (run_id, e))
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# CMS — Article Management Routes
# =============================================================================

@app.route("/api/cms/articles", methods=["GET"])
def api_cms_articles():
    """Return all CMS articles or published-only for public view."""
    try:
        if not db or not hasattr(db, "get_all_published_articles"):
            return jsonify({"status": "error", "message": "CMS not available"}), 503

        status = request.args.get("status", "published")
        category = request.args.get("category", None)

        if status == "all":
            articles = db.get_all_articles()
        else:
            articles = db.get_all_published_articles(category=category)

        return jsonify({
            "status": "ok",
            "articles": articles,
            "count": len(articles),
        })
    except Exception as e:
        print(f"[CMS] GET /api/cms/articles error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cms/articles/<int:article_id>", methods=["GET"])
def api_cms_article_detail(article_id):
    """Return a single CMS article by ID."""
    try:
        if not db or not hasattr(db, "get_article_by_id"):
            return jsonify({"status": "error", "message": "CMS not available"}), 503

        article = db.get_article_by_id(article_id)
        if article is None:
            return jsonify({"status": "error", "message": "Article not found"}), 404

        return jsonify({"status": "ok", "article": article})
    except Exception as e:
        print(f"[CMS] GET /api/cms/articles/{article_id} error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cms/articles/<int:article_id>", methods=["PUT"])
def api_cms_article_update(article_id):
    """Update an existing CMS article."""
    try:
        if not db or not hasattr(db, "get_article_by_id"):
            return jsonify({"status": "error", "message": "CMS not available"}), 503

        existing = db.get_article_by_id(article_id)
        if existing is None:
            return jsonify({"status": "error", "message": "Article not found"}), 404

        data = request.get_json()
        slug = data["slug"] or (existing["slug"].lower().replace(" ", "-"))
        db.update_article(
            article_id=article_id,
            title=data["title"],
            content=data["content"],
            summary=data.get("summary", ""),
            tags=",".join(data.get("tags", [])),
            slug=slug,
            category=data.get("category", ""),
        )

        return jsonify({"status": "ok", "message": "Article updated"})
    except Exception as e:
        print(f"[CMS] PUT /api/cms/articles/{article_id} error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cms/articles", methods=["POST"])
def api_cms_article_create():
    """Create a new CMS article."""
    try:
        if not db or not hasattr(db, "get_all_published_articles"):
            return jsonify({"status": "error", "message": "CMS not available"}), 503

        data = request.get_json()
        slug = (data.get("slug") or data.get("title", "")).lower().replace(" ", "-")

        article_id = db.create_cms_article(
            title=data["title"],
            content=data["content"],
            summary=data.get("summary", ""),
            tags=",".join(data.get("tags", [])),
            slug=slug,
            category=data.get("category", ""),
        )

        return jsonify({"status": "ok", "success": True, "id": article_id})
    except Exception as e:
        print(f"[CMS] POST /api/cms/articles error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cms/articles/<int:article_id>", methods=["DELETE"])
def api_cms_article_delete(article_id):
    """Mark a CMS article as unpublished (soft-delete)."""
    try:
        if not db or not hasattr(db, "update_article_status"):
            return jsonify({"status": "error", "message": "CMS not available"}), 503

        existing = db.get_article_by_id(article_id)
        if existing is None:
            return jsonify({"status": "error", "message": "Article not found"}), 404

        db.update_article_status(article_id, status="unpublished")
        return jsonify({"status": "ok", "message": "Article unpublished"})
    except Exception as e:
        print(f"[CMS] DELETE /api/cms/articles/{article_id} error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# CMS Admin Panel route
@app.route("/cms")
def cms_panel():
    """Admin CMS dashboard for article management."""
    return render_template("cms.html")


# Article view page (public-facing)
@app.route("/a/<slug>")
def article_view(slug):
    """Display a published CMS article with full content."""
    try:
        if not db or not hasattr(db, "get_article_by_slug"):
            return "CMS not available", 503

        article = db.get_article_by_slug(slug)
        if article is None:
            return "Article not found", 404

        from markdown import markdown as md
        from bleach import clean as bleach_clean, ALLOWED_TAGS, ALLOWED_ATTRIBUTES

        raw_html = md(article.get("content", ""))
        sanitized_html = bleach_clean(
            raw_html,
            tags=ALLOWED_TAGS | {"img", "figure", "figcaption", "iframe"},
            attributes={**ALLOWED_ATTRIBUTES, "img": ["src", "alt", "title"], "iframe": ["src", "allow", "frameborder"]},
            strip=True,
        )

        return render_template(
            "article_page.html",
            article=article,
            content=sanitized_html,
        )
    except Exception as e:
        print(f"[CMS] Article view error for {slug}: {e}")
        return f"Error: {e}", 500


# --- Application entry point -------------------------------------------------

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Jarvis Hub 2.0 - Market Intelligence Portal')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8100, help='Port to listen on')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    args = parser.parse_args()

    print('=' * 60)
    print('  Jarvis Hub 2.0 - Market Intelligence Portal')
    print('=' * 60)

    # Initialize services
    _init()

    print(f'\n  Server running at http://{args.host}:{args.port}')
    print(f'  Dashboard:      http://{args.host}:{args.port}/hub2')
    print(f'  Health check:   http://{args.host}:{args.port}/health')
    print('=' * 60)

    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        threaded=True,
     )
