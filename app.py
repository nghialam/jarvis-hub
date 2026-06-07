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
            config = {"ollama": {"url": "http://localhost:11434", "model": "qwen3.6:35b-a3b-mxfp8"}, "db_path": ":memory:"}
        print("[CFG] Loaded configuration OK")
    except Exception as e:
        print("[CFG] Config load failed: %s" % e)
        config = {"ollama": {"url": "http://localhost:11434", "model": "qwen3.6:35b-a3b-mxfp8"}, "db_path": ":memory:"}


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


# --- Initialization ---------------------------------------------------------

def _init():
    _load_config()
    _load_db()
    _refresh_data()


# ============================================================================
#  API ENDPOINTS — Dashboard + Signals + Alerts
# ============================================================================


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search", methods=["GET"])
def api_kb_search():
    """Search knowledge base."""
    query = request.args.get("q", "").strip()
    limit = int(request.args.get("limit", "20"))
    if not query:
        return jsonify({"results": [], "query": "", "total": 0})
    try:
        results = search_knowledge(query, limit) or []
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
        if db and hasattr(db, "add_to_watchlist"):
            added = db.add_to_watchlist(symbol, name)
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
    """Fetch live RSS articles, optionally filtered by category."""
    try:
        cat_filter = request.args.get("category", "").strip().lower()
        arts = get_articles(limit=30) or []
        for a in arts:
            if _enrich_article:
                try:
                    _enrich_article(a)
                except Exception:
                    pass
        if cat_filter:
            arts = [a for a in arts if a.get("category", "").lower() == cat_filter]
        return jsonify({"articles": arts[:30], "count": len(arts)})
    except Exception as e:
        print("[ARTICLES] Fetch error: %s" % e)
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
    model = (config or {}).get("ollama", {}).get("model", "qwen3.6:35b-a3b-mxfp8")

    try:
        r = requests.post(
            "%s/api/chat" % ollama_url,
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
    """Health check endpoint."""
    ollama_status = "unknown"
    try:
        base_url = (config or {}).get("ollama", {}).get("url", "http://localhost:11434") if config else "http://localhost:11434"
        r = requests.get(base_url + "/api/tags", timeout=5)
        ollama_status = "online" if r.status_code == 200 else "offline"
    except Exception as e:
        ollama_status = "error: %s" % str(e)[:40]

    db_path = str(config.get("db_path", "N/A")) if config else "N/A"
    indices_data = _fresh_cache.get("vn_indices", {}) or {}
    rates_data = _fresh_cache.get("rates", {}) or {}

    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ollama": ollama_status,
        "db_path": db_path,
        "indices": indices_data,
        "rates": rates_data,
        "crypto": _fresh_cache.get("crypto", {}),
        "dxy": _fresh_cache.get("dxy"),
        "oil": _fresh_cache.get("oil"),
        "cache_age_seconds": int(datetime.now().timestamp() - _cache_time),
    })


# ================================================================
# SIGNALS & ALERT FEED APIs (v2.0)
# ================================================================


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




def _init_server():
    try:
        _load_config()
        _load_db()
        _refresh_data()
    except Exception as e:
        print("[INIT] Error during init: %s" % e)


# Run on import (for Flask app factory pattern)
try:
    _init_server()
except Exception:
    pass


if __name__ == "__main__":
    _init_server()
    print("[APP] Starting Jarvis Hub Flask server on port 8100...")
    app.run(host="0.0.0.0", port=8100, debug=False, use_reloader=False)
