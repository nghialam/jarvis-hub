"""app.py - Jarvis Hub Flask web dashboard v2 (Clean Architecture).

Serves a local web UI for daily news briefings, market analysis, 
knowledge base search, watchlist management, and market evaluation.

Service layer integrated: market_service.py + news_service.py
Eval generation fixed: always forces fresh data refresh before LLM call.
"""
import os
import sys
import json
import re
import signal
import threading
from datetime import datetime, timedelta

try:
    from flask import Flask, jsonify, request
except ImportError:
    print("Flask not installed, but running for code validation only")
else:
    app = Flask(__name__)  # noqa: E305


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Global state
config = {}
db = None
_cache_time = 0


def _utc_now_iso():
    return datetime.now().isoformat()


def _load_config():
    global config
    import jarvis_hub.config as cfg_module
    try:
        config = cfg_module.load_config()
        print("[CFG] Loaded configuration OK")
    except Exception as e:
        print("[CFG] Config load failed: %s" % e)
        config = {"ollama": {"url": "http://localhost:11434", "model": "qwen3.6:35b-a3b-mxfp8"},
                  "db_path": ":memory:"}


def _load_db():
    global db
    path = (config or {}).get("db_path", os.path.join(SCRIPT_DIR, "jarvis_hub.db")) if config else os.path.join(SCRIPT_DIR, "jarvis_hub.db")
    try:
        import jarvis_hub.database as db_module
        db = db_module.Database(path)
        print("[DB] Loaded at %s" % path)
    except Exception as e:
        print("[DB] Failed to load DB: %s" % e)
        db = None


def _init():
    _load_config()
    _load_db()


if app is not None:
     # These imports are after Flask init since they may import flask modules
    import jarvis_hub.market_service as market_svc  # noqa: E402
    import jarvis_hub.news_service as news_svc  # noqa: E402

     # Re-export key functions for use in routes
    fetch_market_indices = market_svc.fetch_market_indices if hasattr(market_svc, "fetch_market_indices") else lambda: {}
    get_exchange_rates = market_svc.get_exchange_rates if hasattr(market_svc, "get_exchange_rates") else lambda: {}
    fetch_gold = market_svc.fetch_gold if hasattr(market_svc, "fetch_gold") else lambda: None
    fetch_dxy = market_svc.fetch_dxy if hasattr(market_svc, "fetch_dxy") and market_svc.fetch_dxy is not None else lambda: None
    fetch_oil = market_svc.fetch_oil if hasattr(market_svc, "fetch_oil") and market_svc.fetch_oil is not None else lambda: None
    fetch_crypto = market_svc.fetch_crypto if hasattr(market_svc, "fetch_crypto") else lambda x: {}

     def analyze_stock(sym):
        return market_svc.analyze_stock(sym) if hasattr(market_svc, "analyze_stock") else {"symbol": sym}

     get_articles = news_svc.get_articles if hasattr(news_svc, "get_articles") else lambda limit=20: []
     enrich_article = news_svc.enrich_article if hasattr(news_svc, "enrich_article") and news_svc.enrich_article is not None else lambda a, use_llm=False: None
     _enrich_article = news_svc._enrich_article if hasattr(news_svc, "_enrich_article") and news_svc._enrich_article is not None else enrich_article

     def trigger_alert(sym, sig_type, data_obj):
        return db.create_signal(sym, sig_type, 50, str(data_obj)) if db is not None else None

else:
    fetch_market_indices = lambda: {}
    get_exchange_rates = lambda: {}
    fetch_gold = lambda: None
    fetch_dxy = lambda: None
    fetch_oil = lambda: None
    fetch_crypto = lambda x: {}
    analyze_stock = lambda sym: {"symbol": sym}
    get_articles = lambda limit=20: []
    enrich_article = lambda a, use_llm=False: None
    _enrich_article = enrich_article
    trigger_alert = lambda *a, **k: None

# ================================================================
# API Routes
# ================================================================


@app.route("/api/health", methods=["GET"])
def api_health():
      """Health check endpoint."""
    ollama_status = "unknown"
    try:
        base_url = (config or {}).get("ollama", {}).get("url", "http://localhost:11434") if config else "http://localhost:11434"
        r = requests.get(base_url + "/v1/models", timeout=5)
        ollama_status = "online" if r.status_code == 200 else "offline"
    except Exception as e:
        ollama_status = "error: %s" % str(e)[:40]

    db_path = (config or {}).get("db_path", "N/A") if config else "N/A"

    return jsonify({
         "status": "ok",
         "ollama": ollama_status,
         "db_path": db_path,
         "cache_time": _cache_time,
     })


@app.route("/api/kb/search", methods=["GET"])
def api_kb_search():
      """Search knowledge base."""
    if not db:
        return jsonify({"results": [], "query": "", "total": 0})

    query = request.args.get("q", "")
    limit = int(request.args.get("limit", "20"))

    try:
        results = db.search_knowledge(query, limit)
        return jsonify({"results": results, "query": query, "total": len(results)})
    except Exception as e:
        print("[KB] Search error: %s" % e)
        return jsonify({"results": [], "error": str(e)[:100]})


@app.route("/api/watchlist", methods=["GET"])
def api_watchlist():
      """Return watchlist symbols."""
    if not db:
        return jsonify({"symbols": []})

    try:
        items = db.get_watchlist()
        return jsonify({"symbols": items})
    except Exception as e:
        print("[WATCHLIST] Error: %s" % e)
        return jsonify({"symbols": [], "error": str(e)[:100]})


@app.route("/api/watchlist/add", methods=["POST"])
def api_watchlist_add():
      """Add symbol to watchlist."""
    if not db:
        return jsonify({"success": False, "error": "DB not initialized"})

    data = request.get_json() or {}
    symbol = str(data.get("symbol", "")).strip().upper()
    name = str(data.get("name", "")).strip()

    if len(symbol) < 2:
        return jsonify({"success": False, "error": "Invalid symbol"})

    try:
        added = db.add_to_watchlist(symbol, name)
        return jsonify({"success": True, "added": added})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/watchlist/remove/<symbol>", methods=["DELETE"])
def api_watchlist_remove(symbol):
      """Remove symbol from watchlist."""
    if not db:
        return jsonify({"success": False, "error": "DB not initialized"})

    try:
        removed = db.remove_from_watchlist(symbol)
        return jsonify({"success": True, "removed": removed})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/market/data", methods=["GET"])
def api_market_data():
      """Return all cached market data."""
    if not db:
        return jsonify({"error": "DB not initialized"})

    try:
        indices = fetch_market_indices() or {}
        rates = get_exchange_rates() or {}
        gold = fetch_gold() or {}
        crypto_btc = fetch_crypto("BTC") or {}
        crypto_eth = fetch_crypto("ETH") or {}
        crypto_sol = fetch_crypto("SOL") or {}

        return jsonify({
             "vn_indices": indices.get("vn_indices", {}) if isinstance(indices, dict) else {},
             "rates": rates,
             "gold": gold,
             "crypto": {"BTC": crypto_btc, "ETH": crypto_eth, "SOL": crypto_sol},
         })
    except Exception as e:
        print("[MARKET] Error: %s" % e)
        return jsonify({"error": str(e)})


@app.route("/api/evaluation", methods=["GET"])
def api_market_evaluation():
      """Return today's or most recent market evaluation."""
    if not db:
        now = datetime.now()
        return jsonify({
             "status": "pending",
             "message": "Chua co danh gia hom nay. Nhap 'Generate' de tao danh gia.",
             "date": now.strftime("%Y-%m-%d"),
         })

    day_eval = None
    try:
        all_evals = db.get_all_evaluations()
        now = datetime.now()
        for ev in sorted(all_evals, key=lambda e: e.get("date", ""), reverse=True):
            if ev.get("date") < now.strftime("%Y-%m-%d"):
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


@app.route("/api/evaluation/generate", methods=["POST"])
def api_generate_evaluation():
      """Trigger LLM to generate a new evaluation with fresh data."""
    if not config:
        return jsonify({"error": "Config not loaded yet"}), 503

    try:
         # Load fresh articles
        articles = []
        try:
            art_fresh = get_articles(limit=20)
            for a in art_fresh:
                _enrich_article(a, use_llm=False)
            articles = art_fresh
        except Exception as e:
            print("[EVAL] Articles refresh failed: %s" % e)

         # Fetch fresh data with ThreadPoolExecutor
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = {}

        with ThreadPoolExecutor(max_workers=8) as ex:
            fdict = {
                ex.submit(fetch_market_indices): "indices",
                ex.submit(get_exchange_rates): "rates",
                ex.submit(lambda: fetch_crypto("BTC")): "crypto_BTC",
                ex.submit(lambda: fetch_crypto("ETH")): "crypto_ETH",
                ex.submit(lambda: fetch_crypto("SOL")): "crypto_SOL",
                ex.submit(fetch_gold): "gold",
                ex.submit(fetch_dxy if fetch_dxy else lambda: {}): "dxy",
                ex.submit(fetch_oil if fetch_oil else lambda: {}): "oil",
            }

            for f in fdict:
                try:
                    name = fdict[f]
                    data = f.result()
                    if data is not None:
                        results[name] = data
                    else:
                        print("[REFRESH] %s returned None" % name)
                except Exception as ex:
                    pass

        import jarvis_hub.market_service as market_svc

         # Call Ollama with fresh context
        ollama_url = (config or {}).get("ollama", {}).get("url", "http://localhost:11434")
        model = (config or {}).get("ollama", {}).get("model", "qwen3.6:35b-a3b-mxfp8")

        # Build context from fresh data
        ctx_parts = []
        
         # Index info
        vn_idx = results.get("vn_indices", {}) or results.get("indices", {}).get("vn_indices", {}) or {}
        for name, info in (vn_idx.items() if isinstance(vn_idx, dict) else []):
            if isinstance(info, dict) and "price" in info:
                arrow = "\u25B2" if info.get("change_pct", 0) >= 0 else "\u25BC"
                ctx_parts.append("%s: %s (%.2f%%)" % (name, info.get("price", "?"), abs(info.get("change_pct", 0))))

        global_idx = results.get("global_indices", {}) or results.get("indices", {}).get("global_indices", {})
        for name, info in sorted(global_idx.items())[:5]:
            if isinstance(info, dict) and "price" in info:
                arrow = "\u25B2" if info.get("change_pct", 0) >= 0 else "\u25BC"
                ctx_parts.append("%s (%s): %s (%.2f%%)" % (name, info.get("country", ""), info.get('price', '?'), abs(info.get('change_pct', 0))))

         # Crypto
        crypto_info = []
        for prefix in ("BTC", "ETH", "SOL"):
            for k, v in results.items():
                if k.startswith("crypto_" + prefix) and isinstance(v, dict):
                    symbol_1 = v.get('symbol', prefix)
                    ch_pct = v.get('change_pct', 0) or 0
                    crypto_info.append("%s: $%s (%.2f%%)" % (symbol_1, v.get('price', '?'), abs(ch_pct)))

        gold_data = results.get("gold", {})
        gold_info = ""
        if isinstance(gold_data, dict) and "price" in gold_data:
            arrow_g = "\u25B2" if gold_data.get("change_pct", 0) >= 0 else "\u25BC"
            gold_info = "Vang: $%s (%.2f%%)" % (gold_data.get('price', 'N/A'), abs(gold_data.get('change_pct', 0)))

        dxy_info = ""
        if isinstance(results.get("dxy"), dict) and "price" in results["dxy"]:
            dxy_info = "DXY: %s" % results["dxy"].get('price', 'N/A')

        oil_info = ""
        if isinstance(results.get("oil"), dict) and "price" in results["oil"]:
            price_raw = oil_input.get("price", None) if (oil_input := results.get("oil")) else None
            if price_raw is not None:
                oil_info = "Dau khi (WTI): $%s" % str(price_raw)

        rates_data = results.get("rates", {})
        rates_info = ""
        if isinstance(rates_data, dict) and rates_data.get("USD"):
            usd_rate = rates_data["USD"]
            transfer_raw = usd_rate.get("transfer", "N/A")
            retail_raw = usd_rate.get("retail", "N/A")
            try:
                transfer = float(transfer_raw)
            except (TypeError, ValueError):
                transfer = 0.0
            try:
                retail = float(retail_raw)
            except (TypeError, ValueError):
                retail = 0.0
            rates_info = "USD: Chuyen kho 1 don vi (%.0f), ban le (%.0f)" % (transfer, retail)

         # Sentiment from articles
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
                sent_counts["neutral"], sum(sent_counts.values())
              ),
          ])

        prompt = (
             "[ROLE]\n"
             "Chuyen gia phan tich tai chinh va dau tu chung khoan Viet Nam.\n\n"
             "[DATA]\n"
             "Dua tren du lieu hien tai:\n%s\n\n" % context_text
             "[OUTPUT REQUIREMENTS]\n"
             "Hay dua ra ban danh gia thi truong hom nay bang tieng Viet, khoang 400-800 tu. Bao gom:\n\n"
             "1. TONG QUAN XU HUONG: Danh gia xu huong chinh (bullish/bearish/neutral) + muc do tu tin (1-100%%) + ly do Chinh.\n\n"
             "2. CHI TIET TUNG PHAM TRU:\n"
             "     - Stock VN: Xu huong VN-Index, thanh phan sector manh/yeu nhat.\n"
             "     - Crypto: Top mover 24h, xu huong Bitcoin/ETH.\n"
             "     - VVBN/Vang: Gia vang hien tai, xu huong.\n"
             "     - Dau khi/Oil & USD Index/DXY: Di dong chinh va anh huong den VN market.\n\n"
             "3. RUI RO VA CO HOI:\n"
             "     - 2-3 rui ro can chu y (internal/external).\n"
             "     - 2-3 co hoi dau tu co the khai thac.\n\n"
             "4. KHUYEN NGHI DAU TU:\n"
             "     - Short-term (1-5 ngay): Actionable recommendation (Mua/Ban/Khoi hold) theo sector/currency.\n"
             "     - Risk level: Thap/Trung binh/Cao cho moi vung gia tri.\n"
             "     - Stop-loss suggested level (neu co).\n\n"
             "[FORMAT]\n"
             "Sinh ket qua theo duong dan markdown format, su dung bullet poinrs va headers de de doc. KHONG SU DUNG DANH SO 1-2-3-"
        )

         # Call Ollama with FRESH context
        r = requests.post(
              "%s/v1/chat/completions" % ollama_url,
            json={
                 "model": model,
                 "messages": [
                     {"role": "system", "content": "Ban la chuyen gia phan tich thi truong tai chinh Viet Nam. Tra loi bang tieng Viet."},
                     {"role": "user", "content": prompt % context_text},
                  ],
                 "stream": False,
                 "options": {
                     "num_predict": 4096,
                     "temperature": 0.7,
                  },
              },
            timeout=120,
          )

        if r.status_code == 200:
            resp = r.json()
            text = (resp.get("message", {}).get("content", "") or "").strip()
            
            if not text:
                text = resp.get("response", "").strip()
                
            if text:
                summary = text[:300] + "..." if len(text) > 300 else text
                db.save_market_evaluation(
                     datetime.now().strftime("%Y-%m-%d"),
                    eval_result.get("evaluation", text),
                    eval_result.get("summary", summary),
                 )
                return jsonify({
                      "evaluation": text,
                      "summary": summary,
                  })

        print("[EVAL] Ollama returned status %s" % r.status_code)
        return jsonify({"error": "Ollama did not return useful response: %s" % r.status_code}), 502

    except requests.exceptions.Timeout:
        print("[EVAL] Timeout after refresh and prompt preparation")
        return jsonify({"error": "LLM timed out - try again when network is stable"}), 504
    except Exception as e:
        print("[EVAL] Evaluation generation failed: %s" % e)
        return jsonify({"error": str(e)}), 503


@app.route("/api/evaluation/history", methods=["GET"])
def api_eval_history():
      """Return historical market evaluations."""
    all_evals = db.get_all_evaluations() if db else []
    return jsonify({"status": "ok", "evaluations": all_evals})


# ================================================================
# API: Daily snapshots & Articles
# ================================================================


@app.route("/api/snapshots", methods=["GET"])
def api_snapshots():
      """Return last 5 days of daily briefings."""
    dates = db.get_all_dates() if db else []
    snapshots = []

    for date in dates[:5]:     # Last 5 days
        snap = db.get_daily_snapshot(date)
        if snap:
            content = snap["briefing_content"]
            preview = content[:300].replace("\n", " ")
            article_count = content.count("**.")    # rough count

            snapshots.append({
                  "date": date,
                  "preview": preview,
                  "article_count": article_count,
                  "full_content": content,
              })

    return jsonify({"count": len(snapshots), "snapshots": snapshots})


@app.route("/api/daily-snapshot/<date>", methods=["GET"])
def api_daily_snapshot(date):
      """Return a daily snapshot for a specific date (YYYY-MM-DD)."""
    try:
        data = db.get_daily_snapshot(date) if db else None
        if not data:
            return jsonify({
                 "status": "error",
                 "date": date,
                 "message": "Khong tim thay du lieu cho ngay %s" % date,
             }), 404
            
        return jsonify({"status": "ok", "data": data})
    except Exception as e:
        print("[WARN] Snapshot fetch failed for %s: %s" % (date, str(e)))
        return jsonify({
              "status": "error",
              "dates": [],
              "message": str(e),
          }), 500


@app.route("/api/daily-snapshots/<date>", methods=["GET"])
def api_daily_snapshot_plural(date):
      """Alias for /api/daily-snapshot/<date>."""
    return api_daily_snapshot(date)


@app.route("/api/articles", methods=["GET"])
def api_articles():
       """Fetch live RSS articles, optionally filtered by category."""
    cat_filter = request.args.get("category", "").strip().lower()

    try:
        arts = get_articles(limit=30)
        for a in arts:
            try:
                enrich_article(a)
            except Exception:
                pass

        if cat_filter:
            arts = [a for a in arts if a.get("category", "").lower() == cat_filter]

        return jsonify({"articles": arts[:30], "count": len(arts)})
    except Exception as e:
        print("[ARTICLES] Fetch error: %s" % e)
        return jsonify({"articles": [], "error": str(e)[:100]})


@app.route("/api/activities", methods=["GET"])
def api_activities():
    try:
        activities = db.get_activities(20) if db else []
        return jsonify({"count": len(activities), "activities": activities})
    except Exception as e:
        return jsonify({"count": 0, "activities": [], "error": str(e)})


@app.route("/api/test", methods=["GET"])
def api_test():
      """Test endpoint to verify service layer."""
    try:
        rates = get_exchange_rates()
        indices = fetch_market_indices()
        gold = fetch_gold() or {}
        
        return jsonify({
              "status": "ok",
              "rates_ok": rates is not None,
              "indices_ok": indices is not None and "vn_indices" in indices if isinstance(indices, dict) else False,
              "gold_ok": "price" in gold,
              "cache_time": _cache_time,
          })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# ====================================================================
# Unified Signals Feed - NEW FEATURE (v2.0)
# Merges signals_log and trading_alerts into a single API
# ====================================================================


@app.route("/api/signals", methods=["GET"])
def api_get_signals():
    """Get unified signal feed from both tables, merged and deduplicated."""
    if not db:
        return jsonify({"signals": [], "error": "DB not initialized"})

    try:
        # Optional filters
        signal_filter = request.args.get("signal", "").upper()  # BUY / SELL / HOLD
        severity_filter = request.args.get("severity", "").upper()
        symbol_filter = request.args.get("symbol", "").upper()
        only_unread = request.args.get("unread", "false").lower() == "true"

        # Fetch signals from BOTH tables
        all_signals = []
        source_counts = {"signals_log": 0, "trading_alerts": 0}

        # Table 1: signals_log (from trading bot)
        try:
            rows = db._c().execute("""
                SELECT id, symbol, 'TRADING_BOT' as source, signal_type,
                       CAST(strength AS TEXT) as severity, price, details,
                       detected_at as timestamp, delivered as is_delivered, delivery_channel
                FROM signals_log
                WHERE 1=1
             """).fetchall()
            for row in rows:
                r = dict(row)
                # Apply filters
                if signal_filter and r["signal_type"] != signal_filter:
                    continue
                if symbol_filter and r["symbol"] != symbol_filter:
                    continue
                all_signals.append(r)
                source_counts["signals_log"] += 1
        except Exception as e:
            print("[SIGNALS] signals_log fetch error (table may not exist yet): %s" % e)

        # Table 2: trading_alerts (from auto-scan engine)
        try:
            rows = db._c().execute("""
                SELECT id, symbol, 'AUTO_SCAN' as source, signal_type,
                       severity AS severity,
                       CAST(alert_data->>'price' AS REAL) as price,
                       alert_data,
                       timestamp as detected_at,
                       CASE WHEN status='read' THEN 1 ELSE 0 END as is_delivered,
                       delivery_channel
                FROM trading_alerts
             """).fetchall()
            for row in rows:
                r = dict(row)
                # Parse JSON alert_data if string
                raw = r.get("alert_data")
                if isinstance(raw, str):
                    try:
                        import json as _json
                        r["alert_parsed"] = _json.loads(raw)
                    except Exception:
                        r["alert_parsed"] = None
                else:
                    r["alert_parsed"] = raw

                del r["alert_data"]  # Clean up raw JSON field

                # Apply filters
                if signal_filter and r["signal_type"] != signal_filter:
                    continue
                if symbol_filter and r["symbol"] != symbol_filter:
                    continue
                if only_unread and r.get("is_delivered"):
                    continue

                all_signals.append(r)
                source_counts["trading_alerts"] += 1
        except Exception as e:
            print("[SIGNALS] trading_alerts fetch error: %s" % e)

        # Sort by timestamp descending (newest first)
        all_signals.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Deduplication: keep latest signal per symbol
        best_by_symbol = {}
        neutral_kept = []
        for sig in all_signals:
            sym = sig["symbol"]
            stype = sig.get("signal_type", "NEUTRAL")

            # Neutral/HOLD signals: keep as-is (show latest per symbol)
            if stype in ("NEUTRAL", "HOLD"):
                if sym not in [s["symbol"] for s in neutral_kept]:
                    neutral_kept.append(sig)
                continue

            # Buy/Sell signals: keep only the most recent per symbol type
            key = (sym, stype)
            if key not in best_by_symbol or sig.get("timestamp", "") > best_by_symbol[key].get("timestamp", ""):
                if key in best_by_symbol:
                    old = best_by_signal[sym]
                    if old not in neutral_kept and old["symbol"] not in [s["symbol"] for s in neutral_kept]:
                        neutral_kept.append(old)
                best_by_symbol[key] = sig

        # Remove duplicates from neutral list by symbol
        seen_symbols_neutral = set()
        deduped_neutral = []
        for s in neutral_kept:
            if s["symbol"] not in seen_symbols_neutral:
                seen_symbols_neutral.add(s["symbol"])
                deduped_neutral.append(s)

        # Combine: strong signals first, then neutrals/holds at end
        final_signals = list(best_by_symbol.values()) + deduped_neutral

        return jsonify({
            "signals": final_signals,
            "counts": {
                "total": len(final_signals),
                "by_source": source_counts,
            },
        })
    except Exception as e:
        print("[SIGNALS] Error: %s" % str(e))
        return jsonify({"signals": [], "error": str(e)}, 500)


@app.route("/api/signals/latest", methods=["GET"])
def api_latest_signals():
    """Get the N most recent signals (for grid overview)."""
    limit = min(int(request.args.get("limit", "20")), 100)
    if not db:
        return jsonify({"signals": []})

    try:
        all_signals = []

        # From signals_log
        try:
            rows = db._c().execute("""
                SELECT symbol, 'TRADING_BOT', signal_type, CAST(strength AS REAL) as strength,
                       price, details, detected_at, delivered as is_delivered, delivery_channel
                FROM signals_log ORDER BY detected_at DESC LIMIT 50
             """).fetchall()
            for row in rows:
                r = dict(row)
                if isinstance(r.get("details"), str):
                    try:
                        import json as _json
                        r["details_parsed"] = _json.loads(r["details"])
                    except Exception:
                        pass
                all_signals.append(r)
        except Exception:
            pass

        # From trading_alerts
        try:
            rows = db._c().execute("""
                SELECT symbol, 'AUTO_SCAN', signal_type, severity as strength,
                       CAST(alert_data->>'price' AS REAL) as price,
                       alert_data as details,
                       timestamp as detected_at,
                       CASE WHEN status='read' THEN 1 ELSE 0 END AS is_delivered,
                       delivery_channel
                FROM trading_alerts ORDER BY timestamp DESC LIMIT 50
             """).fetchall()
            for row in rows:
                r = dict(row)
                raw = r.get("details")
                if isinstance(raw, str):
                    try:
                        import json as _json
                        r["details_parsed"] = _json.loads(raw)
                    except Exception:
                        r["details_parsed"] = None
                else:
                    r["details_parsed"] = raw
                del r["details"]  # Clean up raw JSON field
                all_signals.append(r)
        except Exception:
            pass

        # Sort and limit
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
                    import json as _json
                    r["details_parsed"] = _json.loads(r["details"])
                except Exception:
                    pass
            signals.append(r)
    except Exception as e:
        print("[SIGNALS] signals_log lookup %s error: %s" % (sym, e))

    # From trading_alerts
    try:
        rows = db._c().execute("""
            SELECT symbol, 'AUTO_SCAN', signal_type, severity as strength,
                   CAST(alert_data->>'price' AS REAL) as price,
                   alert_data as details,
                   timestamp as detected_at,
                   CASE WHEN status='read' THEN 1 ELSE 0 END AS is_delivered,
                   delivery_channel
           FROM trading_alerts WHERE UPPER(symbol)=UPPER(?) ORDER BY timestamp DESC
        """, (sym,)).fetchall()
        for row in rows:
            r = dict(row)
            raw = r.get("details")
            if isinstance(raw, str):
                try:
                    import json as _json
                    r["details_parsed"] = _json.loads(raw)
                except Exception:
                    pass
            signals.append(r)
    except Exception as e:
        print("[SIGNALS] trading_alerts lookup %s error: %s" % (sym, e))

    signals.sort(key=lambda x: (x.get("detected_at", "") or x.get("timestamp", "")), reverse=True)
    return jsonify({"symbol": sym, "signals": signals})


@app.route("/api/signals/add", methods=["POST"])
def api_signal_append():
    """Manual signal entry (via dashboard or API)."""
    if not db:
        return jsonify({"success": False, "error": "DB not initialized"}), 500

    data = request.get_json() or {}
    sym = str(data.get("symbol", "")).strip().upper()
    signal_type = str(data.get("signal", "")).upper()  # BUY / SELL / HOLD
    strength = float(data.get("strength", 0))  # 0-100

    if not sym or len(sym) < 2:
        return jsonify({"success": False, "error": "Invalid symbol"}), 400
    valid_types = ("BUY", "SELL", "HOLD", "STOP_LOSS", "TAKE_PROFIT", "WATCH", "NEUTRAL")
    if signal_type and signal_type not in valid_types:
        return jsonify({"success": False, "error": "Invalid signal type"}), 400

    details = {k: v for k, v in data.items() if k not in ("symbol", "signal", "strength")}

    # Persist to signals_log table
    try:
        import json as _json
        db._c().execute("""
            INSERT INTO signals_log (symbol, signal_type, strength, price, details, detected_at)
             VALUES (?, ?, ?, ?, ?, ?)
         """, (sym, signal_type if signal_type else "NEUTRAL", strength,
              data.get("price"), _json.dumps(details), _utc_now_iso()))
        db._conn.commit()
        print("[SIGNALS] Manual signal added for %s: %s (%.1f)" % (sym, signal_type, strength))
        return jsonify({"success": True})
    except sqlite3.Error as e:
        if "no such table" in str(e):
            return jsonify({"success": False, "error": "signals_log table not found - run DB migration"}), 500
        print("[SIGNALS] Insert error: %s" % e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/signals/mark-delivered", methods=["POST"])
def api_signal_mark_delivered():
    """Mark signal as delivered (used by cron delivery)."""
    if not db:
        return jsonify({"success": True})  # Silently OK if no DB

    try:
        rowcount = 0
        if request.json:
            rowcount = db._c().execute("""
                UPDATE signals_log SET delivered=1 WHERE id=? AND is_delivered=0
             """, (request.json.get("id"),)).rowcount
        db._conn.commit()
        return jsonify({"success": True, "marked": rowcount})
    except Exception as e:
        print("[SIGNALS] Mark delivered error: %s" % e)
        return jsonify({"success": False, "error": str(e)})


# ====================================================================
# Trading Alert Feed - NEW FEATURE
# ====================================================================


@app.route("/api/alert-feed", methods=["GET"])
def api_get_alert_feed():
    """Get trading alerts sorted by recency."""
    if not db:
        return jsonify({"alerts": [], "filters_applied": []})

    # Optional filters
    signal = request.args.get("signal", "").upper()  # BUY / SELL / HOLD
    severity = request.args.get("severity", "").upper()  # LOW / MEDIUM / HIGH / CRITICAL
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
            params,
         ).fetchall()

        alerts = [dict(r) for r in rows]
        # Parse alert_data if stored as JSON string
        for a in alerts:
            raw = a.get("alert_data")
            if isinstance(raw, str):
                import json as _json
                try:
                    a["alert_data"] = _json.loads(raw)
                except Exception:
                    pass
        return jsonify({"alerts": alerts, "filters_applied": filters_applied})
    except Exception as e:
        print("[ALERT-FEED] Error: %s" % e)
        return jsonify({"alerts": [], "errors": [str(e)]})


@app.route("/api/alert-feed/auto-scan", methods=["GET"])
def api_auto_scan():
    """Trigger auto-scan of watchlist for trading signals."""
    if not db or not config:
        return jsonify({"scanned": 0, "new_alerts": 0, "error": "DB/Config not initialized"})

    try:
        watchlist = db.get_watchlist()
        if not watchlist:
            return jsonify({"scanned": 0, "new_alerts": 0, "message": "Watchlist is empty"})

        results = {"scanned": 0, "new_alerts": 0}
        for item in watchlist:
            sym = item["symbol"]
            try:
                result = analyze_stock(sym)
                if result and "error" not in result and result.get("price"):
                    results["scanned"] += 1

                    # Detect signal from technical analysis
                    tech = result.get("technical", {}) or {}
                    rsi_val = tech.get("rsi") or tech.get("RSI") or tech.get("RSI_14", 50)
                    sma20 = tech.get("sma_20")
                    macd_hist = tech.get("macd_histogram") if tech else None

                    # Try to extract recommendation from LLM report using re
                    llm_rec = ""
                    if result.get("llm_report"):
                        rec_match = re.search(
                             r'(?:KHUYEN NGH[YIA]|RECOMMENDATION|ACTION)[\s]*([^\n]+)',
                            result["llm_report"]
                         )
                        if rec_match:
                            llm_rec = rec_match.group(1).strip().upper()

                    signal_type = "NEUTRAL"
                    reason_parts = []

                    # Technical signal detection (multi-factor)
                    rsi_num = float(rsi_val) if rsi_val else 50
                    change_pct = float(result.get("change_pct", 0))

                    # RSI signals
                    if rsi_num <= 30:
                        reason_parts.append("RSI oversold (%.1f)" % rsi_num)
                        signal_type = "BUY" if signal_type in ("NEUTRAL", "SELL") else signal_type
                    elif rsi_num >= 70:
                        reason_parts.append("RSI overbought (%.1f)" % rsi_num)
                        signal_type = "SELL" if signal_type in ("NEUTRAL", "BUY") else signal_type

                    # SMA signals
                    price_num = float(result.get("price", 0))
                    if sma20 and price_num:
                        if price_num < sma20 * 0.95:  # 5% below SMA
                            reason_parts.append("Price below SMA20 (%.2f)" % sma20)
                            signal_type = "SELL" if signal_type in ("NEUTRAL", "BUY") else signal_type

                    # MACD histogram
                    if macd_hist is not None and float(macd_hist) < -0.5:
                        reason_parts.append("MACD momentum bearish")
                        signal_type = "SELL" if signal_type in ("NEUTRAL", "BUY") else signal_type
                    elif macd_hist is not None and float(macd_hist) > 0.5:
                        reason_parts.append("MACD momentum bullish")
                        signal_type = "BUY" if signal_type in ("NEUTRAL", "SELL") else signal_type

                    # Price change over threshold
                    if change_pct <= -5:
                        reason_parts.append("Sharp drop (-%.1f%%)" % abs(change_pct))
                        signal_type = "SELL" if signal_type == "NEUTRAL" else signal_type
                    elif change_pct >= 5:
                        reason_parts.append("Strong rally (+%.1f%%)" % change_pct)
                        signal_type = "BUY" if signal_type == "NEUTRAL" else signal_type

                    # Upgrade signals based on number of confirming factors
                    if len(reason_parts) >= 3 and signal_type in ("BUY", "SELL"):
                        signal_type = "STRONG_" + signal_type
                    elif len(reason_parts) == 0:
                        signal_type = "NEUTRAL"

                    reason_str = "; ".join(reason_parts) if reason_parts else "No strong signal detected"

                    # Don't spam: only alert on non-NEUTRAL signals or first time seeing a symbol
                    is_neutral = signal_type == "NEUTRAL"

                    # Check if we already have a recent alert for this symbol in the last 6 hours
                    existing = db._c().execute(
                          "SELECT id FROM trading_alerts WHERE symbol=? AND timestamp > datetime('now', '-6 hours') LIMIT 1",
                          (sym,),
                      ).fetchone()

                    if not existing and not is_neutral:
                        data_obj = {
                             "price": result.get("price"),
                             "change_pct": change_pct,
                             "rsi_14": rsi_val,
                             "sma_20": sma20,
                             "macd_histogram": macd_hist,
                             "signal_reason": reason_str,
                         }
                        trigger_alert(sym, signal_type, data_obj)
                        results["new_alerts"] += 1

                    elif is_neutral and not existing:
                        # Only add neutral alerts for symbols we don't track yet
                        recent_neutral = db._c().execute(
                              "SELECT id FROM trading_alerts WHERE symbol=? AND signal_type='NEUTRAL' AND timestamp > datetime('now', '-24 hours') LIMIT 1",
                              (sym,),
                          ).fetchone()
                        if not recent_neutral:
                            data_obj = {
                                 "price": result.get("price"),
                                 "change_pct": change_pct,
                                 "rsi_14": rsi_val,
                                 "sma_20": sma20,
                                 "macd_histogram": macd_hist,
                                 "signal_reason": reason_str,
                             }
                            trigger_alert(sym, "NEUTRAL", data_obj)
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
        db.mark_alerts_as_read()
        return jsonify({"success": True})

