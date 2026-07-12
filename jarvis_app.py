"""

app.py - Jarvis Hub Flask web dashboard v2 (Clean Architecture).

Serves a local web UI for daily news briefings, market analysis, 

knowledge base search, watchlist management, and market evaluation.

Service layer integrated: market_service.py + news_service.py

Eval generation fixed: always forces fresh data refresh before LLM call.

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

# --- App & service initialization -------------------------------------------

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

_cache_time = 0  # Unix timestamp of last data refresh

def _load_config():

    global config

    try:

        config = cfg_module.load_config()

        print("[CFG] Loaded configuration OK")

    except Exception as e:

        print("[CFG] Config load failed: %s" % e)

        config = {"ollama": {"url": "http://localhost:11434", "model": "qwen3.6:35b-a3b-mxfp8"}, "db_path": ":memory:"}

def _load_db():

    global db

    try:

        path = (config or {}).get("db_path", os.path.join(SCRIPT_DIR, "jarvis_hub.db")) if config else os.path.join(SCRIPT_DIR, "jarvis_hub.db")

        db = Database(path)

        print("[DB] Connected OK")

    except Exception as e:

        print("[DB] Connect failed: %s - using in-memory DB" % e)

        db = Database()

def _refresh_data():

    """Fetch ALL market + news data in parallel. Called by init + force refresh."""

    global _cache_time, _fresh_cache, _fresh_cache

    try:

         # Parallel fetch of independent sources

        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = {}

        with ThreadPoolExecutor(max_workers=8) as ex:

            futures = {

                ex.submit(fetch_market_indices): "indices",

                ex.submit(get_exchange_rates): "rates",

                ex.submit(lambda: fetch_crypto("BTC")): "crypto_BTC",

                ex.submit(lambda: fetch_crypto("ETH")): "crypto_ETH",

                ex.submit(lambda: fetch_crypto("SOL")): "crypto_SOL",

                ex.submit(fetch_gold): "gold",

                ex.submit(fetch_dxy): "dxy",

                ex.submit(fetch_oil): "oil",

            }

            for f in futures:

                try:

                    name = futures[f]

                    data = f.result()

                    if data is not None:

                        results[name] = data

                    else:

                        print("[REFRESH] %s returned None" % name)

                except Exception as ex:

                    print("[REFRESH] %s fetch failed: %s" % (futures[f], ex))

        # Gather articles

        try:

            articles = get_articles()[:30]

            if articles:

                results["articles"] = articles

        except Exception as e:

            print("[REFRESH] Articles fetch failed: %s" % e)

        _cache_time = datetime.now().timestamp()

        # Save to global cache for dashboard access

        try:

            with _cache_lock:

                 _fresh_cache.update(results)

        except Exception:

            pass

         # Log completed sources

        if results:

            print("[REFRESH] Fetched %d data sources OK at %s" % (

                len(results), datetime.now().strftime("%H:%M:%S")

            ))

    except Exception as e:

        print("[REFRESH] Full refresh failed: %s" % e)

def _init():

    """Run on startup: config, db, then data."""

    global config, db

    try:

        _load_config()

        _load_db()

        print("[INIT] Fetching initial data...")

        _refresh_data()

        print("[INIT] All data loaded successfully!")

    except Exception as e:

        print("[INIT] Error during init: %s" % e)

_init_lock = threading.Lock()

@app.before_request

def _ensure_loaded():

    """Ensure at least initial data load happened, with timeout guard."""

    if not db and datetime.now().timestamp() - _cache_time < 600:

        # Try to trigger one-time init (will only run once thanks to lock)

        threading.Thread(target=_do_init_once, daemon=True).start()

def _do_init_once():

    """One-shot init with lock to avoid duplicate loads."""

    with _init_lock:

        _load_config()

        _load_db()

        if not config or not db:

            return

        try:

            _refresh_data()

        except Exception as e:

            print("[INIT] First-load refresh failed: %s" % e)

# --- Homepage ----------------------------------------------------------------

@app.route("/")

def index():

    activities = db.get_activities(5) if db else []

    dates = db.get_all_dates()[:3] if db else []

    try:

        art = get_articles()

    except Exception:

        art = []

    try:

        idx = fetch_market_indices()

    except Exception:

        idx = {"vn_indices": {}, "global_indices": {}}

    try:

        rates = get_exchange_rates()

    except Exception:

        rates = {}

    return render_template(

        "index.html",

        articles=art[:10],

        indices=idx,

        rates=rates,

        activities=activities,

        dates=dates,

        watchlist=db.get_watchlist() if db else [],

        cache_time=_cache_time,

    )

# --- API: Knowledge base search ---------------------------------------------

@app.route("/api/search", methods=["GET"])

def api_search():

    query = request.args.get("q", "").strip()

    if not query or len(query) < 2:

        return jsonify({"error": "Query too short", "results": []})

    generate = request.args.get("generate", "").lower() == "true"

    try:

        results = search_knowledge(db, query) if db else []

    except Exception as e:

        print("[WARN] KB search failed: %s" % e)

        results = []

    generated_text = None

    if generate and config and not results:

        try:

            ollama_url = config.get("ollama", {}).get("url", "http://localhost:11434")

            model = config.get("ollama", {}).get("model", "qwen3.6:latest")

            system_prompt = "Chuyen gia phan tich tai chinh Viet Nam."

            user_prompt = "Dinh nghia thuat nguoi tai chinh '%s' bang tieng Viet. Ngan gon (100-200 tu), bao gom cac y chINH." % query

            full_key = system_prompt + "|||" + user_prompt

            cached = llm_cache.get_or_call(full_key, lambda fp: None)

            if cached is not None:

                generated_text = cached

                if db:

                    db.save_term(query, generated_text, tags="generated:" + datetime.now().strftime("%Y-%m-%d"))

                return jsonify({"query": query, "generated": generated_text, "saved": True})

            r = requests.post(

                "%s/v1/chat/completions" % ollama_url,

                json={

                    "model": model,

                    "messages": [

                        {"role": "system", "content": system_prompt},

                        {"role": "user", "content": user_prompt},

                    ],

                    "stream": False,

                    "num_predict": 4096,

                },

                timeout=12,

            )

            if r.status_code == 200:

                generated_text = (r.json().get("message", {}).get("content", "") or "").strip()

                if not generated_text:

                    generated_text = (r.json().get("response", "") or "").strip()

                if generated_text:

                    db.save_term(query, generated_text, tags="generated:" + datetime.now().strftime("%Y-%m-%d")) if db else None

            llm_cache.put(full_key, generated_text)

        except Exception as e:

            print("[WARN] AI KB generation failed: %s" % e)

    return jsonify({"query": query, "generated": generated_text, "results": results})

# --- API: Articles ------------------------------------------------------------

@app.route("/api/articles", methods=["GET"])

def api_articles():

    cat_filter = request.args.get("category", "").lower() or None

    try:

        articles = get_articles(category=cat_filter)

    except Exception as e:

        return jsonify({"count": 0, "articles": [], "error": str(e)})

    result = []

    for a in articles:

        sent_layer1 = a.get("sentiment_layer1", "").strip()

        sent_map = {

            "\U0001f7e2 tic ccc": "positive",

            "\U0001f534 tieu ccc": "negative",

            "\U0001f7e1 trung lar": "neutral",

            "\U0001f7e2 tích ccc": "positive",

            "\U0001f534 tiêu ccc": "negative",

            "\U0001f7e1 trung lâp": "neutral",

        }

        # Simple mapping without emoji codes - check original labels directly

        label = a.get("sentiment_layer1", "").lower()

        if "tích" in label or "tích cực" in label:

            sent_class = "positive"

        elif "tiêu" in label:

            sent_class = "negative"

        else:

            sent_class = "neutral"

        result.append({

            "id": a.get("link", ""),

            "title": a.get("title", "").strip(),

            "source": a.get("source", ""),

            "category": a.get("category", "general"),

            "sentiment": sent_layer1,

            "sentiment_class": sent_class,

            "link": a.get("link", ""),

            "published": a.get("published", ""),

            "priority": a.get("priority", 2),

            "bull_count": a.get("bull_count", 0),

            "bear_count": a.get("bear_count", 0),

        })

    return jsonify({"count": len(result), "articles": result})

# --- API: Watchlist -----------------------------------------------------------

@app.route("/api/watchlist", methods=["GET"])

def api_get_watchlist():

    if not db:

        return jsonify([])

    try:

        items = db.get_watchlist()

        return jsonify({"watchlist": items})

    except Exception as e:

        return jsonify({"error": str(e), "watchlist": []})

@app.route("/api/watchlist/add", methods=["POST"])

def api_add_watchlist():

    if not db:

        return jsonify({"success": False, "error": "DB not initialized"}), 500

    data = request.get_json() or {}

    symbol = str(data.get("symbol", "")).strip().upper()

    if not symbol:

        return jsonify({"success": False, "error": "Missing symbol"})

    # Basic validation - no special chars except . and letters/numbers

    import re

    if not re.match(r'^[A-Z0-9.]+$', symbol):

        return jsonify({"success": False, "error": "Invalid symbol format"})

    if db.add_watchlist(symbol):

        print("[WATCHLIST] Added %s" % symbol)

        return jsonify({"success": True})

    else:

        return jsonify({"success": False, "error": "Duplicate or save failed"}), 409

@app.route("/api/watchlist/remove", methods=["POST"])

def api_remove_watchlist():

    if not db:

        return jsonify({"success": False, "error": "DB not initialized"}), 500

    data = request.get_json() or {}

    symbol = str(data.get("symbol", "")).strip().upper()

    if not symbol:

        return jsonify({"success": False, "error": "Missing symbol"})

    db.remove_watchlist(symbol)

    print("[WATCHLIST] Removed %s" % symbol)

    return jsonify({"success": True})

# --- API: Market Analysis -----------------------------------------------------

@app.route("/api/analyze", methods=["POST"])

def api_analyze():

    data = request.get_json() or {}

    symbol = str(data.get("symbol", "")).strip().upper()

    if not symbol or len(symbol) < 2:

        return jsonify({"error": "Invalid symbol"}), 400

    try:

        # Normalize AAPL.US -> AAPL for lookup, then analyze

        sym_base = re.sub(r'\.(US|VN|AU|CN|HK)$', '', symbol)

        result = analyze_stock(sym_base)

        if not result or "error" in result:

            # Try with original full symbol (AAPL.US format)

            result = analyze_stock(symbol)

    except Exception as e:

        print("[ANALYZE] Failed for %s: %s" % (symbol, e))

        return jsonify({"error": str(e)}), 500

    # Add symbol to watchlist if it exists and not in list

    if db and result and result.get("price") is not None:

        try:

            wl = [s["symbol"] for s in db.get_watchlist()]

            if symbol not in wl and sym_base not in wl:

                db.add_watchlist(symbol)

        except Exception:

            pass

    return jsonify(result)

# --- API: Crypto/Gold/Exchange Rates ------------------------------------------

@app.route("/api/crypto", methods=["GET"])

def api_crypto():

    symbol = request.args.get("symbol", "BTC").upper()

    data = fetch_crypto(symbol)

    return jsonify(data or {"error": "Fetch failed"})

@app.route("/api/gold", methods=["GET"])

def api_gold():

    try:

        data = fetch_gold() or {}

    except Exception as e:

        data = {"error": str(e), "symbol": "XAU/USD"}

    return jsonify(data)

@app.route("/api/rates", methods=["GET"])

def api_rates():

    try:

        return jsonify(get_exchange_rates())

    except Exception as e:

        return jsonify({"error": str(e), "source": "vietcombank"})

@app.route("/api/dxy", methods=["GET"])

def api_dxy():

    data = fetch_dxy() or {"symbol": "DXY"}

    return jsonify(data)

@app.route("/api/oil", methods=["GET"])

def api_oil():

    data = fetch_oil() or {"symbol": "WTI"}

    return jsonify(data)

# --- API: Market Evaluation ---------------------------------------------------

@app.route("/api/market-evaluation", methods=["GET"])

def api_market_evaluation():

    force_refresh = request.args.get("force", "false").lower() == "true"

    day_eval = None

    # Load from DB if available

    try:

        day_eval = db.get_today_evaluation() if db else None

    except Exception:

        pass

    now = datetime.now()

    # Force refresh if requested or no eval exists / old data (FIX: remove 30-min cache threshold)

    needs_refresh = force_refresh or not day_eval or day_eval.get("date") != now.strftime("%Y-%m-%d")

    if needs_refresh:

        try:

            # STEP 1: Force refresh ALL data sources first (FIX: includes RSS feeds for sentiment)

            print("[EVAL] Freshening all data sources...")

            # Fetch articles with heuristic enrichment (fast, no LLM needed)

            try:

                art = get_articles(limit=20)

                # Only apply heuristic layer 1, skip LLM layer 2 for speed

                for a in art:

                    _enrich_article(a, use_llm=False)

                results_articles = art

            except Exception as e:

                print("[EVAL] Articles refresh failed: %s" % e)

                results_articles = []

            # Fetch all market data in parallel

            from concurrent.futures import ThreadPoolExecutor, as_completed

            cache_updates = {}

            with ThreadPoolExecutor(max_workers=8) as executor:

                flist = [

                    executor.submit(fetch_market_indices),

                    executor.submit(get_exchange_rates),

                    executor.submit(lambda: fetch_crypto("BTC")),

                    executor.submit(lambda: fetch_crypto("ETH")),

                    executor.submit(lambda: fetch_crypto("SOL")),

                    executor.submit(fetch_gold),

                ]

                # Optional sources

                if callable(fetch_dxy):

                    flist.append(executor.submit(fetch_dxy))

                if callable(fetch_oil):

                    flist.append(executor.submit(fetch_oil))

                for fut in as_completed(flist):

                    try:

                        data = fut.result()

                        if data is not None:

                            key = "unknown"

                            # Identify which service produced this result

                            if isinstance(data, dict):

                                sym = data.get("symbol") or data.get("vn_indices", {}).get("VN-Index", {}).get("price", 999)

                                if data.get("type") == "crypto":

                                    key = "crypto_" + (data.get("name", "")[:3])

                                elif data.get("type") == "gold":

                                    key = "gold"

                                elif data.get("type") == "dxy":

                                    key = "dxy"

                                elif data.get("type") == "oil":

                                    key = "oil"

                                elif "vn_indices" in data:  # indices

                                    key = "indices"

                                else:

                                    # FX rates (contains USD)

                                    if "USD" in data and ("transfer" in data.get("USD", {}) or "cash" in data.get("USD", {})):

                                        key = "rates"

                                    else:

                                        key = "other_%s" % sym

                            cache_updates[key] = data

                    except Exception as e:

                        print("[EVAL] Fetch failed during parallel exec: %s" % e)

            sys.stdout.flush()

            print("[EVAL] Cache refreshed (%d sources fetched). Generating evaluation..." % len(cache_updates))

            sys.stdout.flush()

            # STEP 2: Generate evaluation with FRESH data

            eval_result = _generate_daily_evaluation(results_articles, cache_updates)

            if eval_result:

                db.save_market_evaluation(

                    now.strftime("%Y-%m-%d"),

                    eval_result.get("evaluation", ""),

                    eval_result.get("summary", ""),

                )

                day_eval = eval_result

        except Exception as e:

            print("[EVAL] Refresh/generation failed: %s" % e)

    # Fallback to historical if today's not available yet

    if not day_eval or day_eval.get("date") != now.strftime("%Y-%m-%d"):

        try:

            all_evals = db.get_all_evaluations() if db else []

            for ev in sorted(all_evals, key=lambda e: e.get("date", ""), reverse=True):

                if ev.get("date") < now.strftime("%Y-%m-%d"):

                    day_eval = ev

                    break

        except Exception:

            pass

    if not day_eval:

        return jsonify({

            "status": "pending",

            "message": "Chua co danh gia hom nay. Nhap 'Generate' de tao danh gia.",

            "date": now.strftime("%Y-%m-%d"),

        })

    return jsonify({

        "status": "ok",

        "date": day_eval.get("date"),

        "evaluation": day_eval.get("evaluation", ""),

        "summary": day_eval.get("summary", ""),

    })

def _generate_daily_evaluation(articles, cache_data):

    def _sa(v, default=0.0):

        """Safe abs - handles strings from Yahoo JSON."""

        try:

            return abs(float(v))

        except (TypeError, ValueError):

            return float(default)

    def _sf(v, default=None):

        """Safe float - converts string or number to float."""

        if v is None:

            return default

        try:

            return float(v)

        except (TypeError, ValueError):

            return default

    """Generate daily market evaluation using Ollama LLM. All data is fresh at this point."""

    def _fetch_single_index(sym, name_map):

        try:

            r = requests.get(

                "https://query1.finance.yahoo.com/v8/finance/chart/" + sym,

                timeout=5,

                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},

            )

            if r.status_code == 200:

                rd = r.json().get("chart", {}).get("result")

                if rd:

                    meta = rd[0].get("meta", {})

                    price = meta.get("regularMarketPrice")

                    prev_close = meta.get("previousClose")

                    pf_price = _sf(price, 0)

                    pf_prev = _sf(prev_close, 0)

                    if pf_price > 0 and pf_prev > 0:

                        return {

                             "price": round(pf_price, 2),

                             "change": round(pf_price - pf_prev, 2),

                             "change_pct": round((pf_price / pf_prev) * 100, 2),

                             "prev_close": round(pf_prev, 2),

                         }

        except Exception as e:

            print("[EVAL] Index fetch failed %s: %s" % (sym, e))

        return None

    name_map = {

        "^VNINDEX.VN": "VN-Index",

        "^GSPC": ("S&P 500", "US"),

        "^DJI": ("Dow Jones", "US"),

        "^IXIC": ("NASDAQ", "US"),

        "^N225": ("Nikkei 225", "Asia"),

        "^HSI": ("Hang Seng", "Asia"),

        "^KS11": ("KOSPI", "Asia"),

        "^GDAXI": ("DAX", "Europe"),

        "^FTSE": ("FTSE 100", "Europe"),

    }

    try:

        ollama_url = (config or {}).get("ollama", {}).get("url", "http://localhost:11434")

        model = (config or {}).get("ollama", {}).get("model", "qwen3.6:35b-a3b-mxfp8")

        # --- Build context from FRESH cache_data + fresh articles ---

        # Index info

        indices_info = []

        vn_idx = cache_data.get("vn_indices", {}) or cache_data.get("indices", {}).get("vn_indices", {}) or {}

        for name, data in vn_idx.items():

            if isinstance(data, dict) and "price" in data:

                up_arrow = "\u25B2"

                change_pct = data.get("change_pct", 0)

                arrow = up_arrow if change_pct >= 0 else "\u25BC"

                indices_info.append("%s: %s (%.2f%%)" % (name, data.get('price', '?'), _sa(change_pct)))

        global_idx = cache_data.get("global_indices", {}) or cache_data.get("indices", {}).get("global_indices", {})

        for name, info in sorted(global_idx.items())[:5]:

            if isinstance(info, dict) and "price" in info:

                arrow = "\u25B2" if info.get("change_pct", 0) >= 0 else "\u25BC"

                indices_info.append("%s: %s (%.2f%%)" % (name, info.get('price', '?'), _sa(info.get('change_pct', 0))))

        # Crypto info

        crypto_info = []

        for key_prefix in ("BTC", "ETH", "SOL"):

            for k, v in cache_data.items():

                if k.startswith("crypto_" + key_prefix) and isinstance(v, dict):

                    symbol_1 = v.get('symbol', key_prefix)

                    name_1 = v.get('name', key_prefix)

                    ch_pct = v.get('change_pct', 0) or 0

                    crypto_info.append("%s: $%s (%.2f%%)" % (symbol_1, v.get('price', '?'), _sa(ch_pct)))

        # Gold

        gold_data = cache_data.get("gold", {})

        gold_info = ""

        if isinstance(gold_data, dict) and "price" in gold_data:

            arrow_g = "\u25B2" if gold_data.get("change_pct", 0) >= 0 else "\u25BC"

            gold_info = "Vang: $%s (%.2f%%)" % (gold_data.get('price', 'N/A'), _sa(gold_data.get('change_pct', 0)))

        # DXY

        dxy_info = ""

        if isinstance(cache_data.get("dxy"), dict) and "price" in cache_data["dxy"]:

            dxy_info = "DXY: %s" % cache_data["dxy"].get('price', 'N/A')

        # Oil

        oil_info = ""

        if isinstance(cache_data.get("oil"), dict) and "price" in cache_data["oil"]:

            oil_input = {"price": cache_data["oil"]["price"]}

            price_raw = oil_input.get("price", None)

            if price_raw is not None:

                oil_info = "Dau khi (WTI): $%s" % str(price_raw)

        # Exchange rates

        rates_data = cache_data.get("rates", {})

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

        # Sentiment from fresh articles

        sent_counts = {"positive": 0, "negative": 0, "neutral": 0}

        for a in articles[:20]:

            sc = a.get("sentiment_class", "neutral")

            if sc in sent_counts:

                sent_counts[sc] += 1

        context_text = "\n".join([

            "VIEN BAN:",

            "INDICES: %s" % (", ".join(indices_info) if indices_info else "N/A"),

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

            "Dua tren du lieu hien tai:\n%s\n\n"

            "[OUTPUT REQUIREMENTS]\n"

            "Hay dua ra ban danh gia thi truong hom nay bang tieng Viet, khoang 400-800 tu. Bao gom:\n\n"

            "1. TONG QUAN XU HUONG: Danh gia xu huong chinh (bullish/bearish/neutral) + muc do tu tin (1-100%%) + ly do Chinh.\n\n"

            "2. CHI TIET TUNG PHAM TRU:\n"

            "       - Stock VN: Xu huong VN-Index, thanh phan sector manh/yeu nhat.\n"

            "       - Crypto: Top mover 24h, xu huong Bitcoin/ETH.\n"

            "       - VVBN/Vang: Gia vang hien tai, xu huong.\n"

            "       - Dau khi/Oil & USD Index/DXY: Di dong chinh va anh huong den VN market.\n\n"

            "3. RUI RO VA CO HOI:\n"

            "       - 2-3 rui ro can chu y (internal/external).\n"

            "       - 2-3 co hoi dau tu co the khai thac.\n\n"

            "4. KHUYEN NGHI DAU TU:\n"

            "       - Short-term (1-5 ngay): Actionable recommendation (Mua/Ban/Khoi hold) theo sector/currency.\n"

            "       - Risk level: Thap/Trung binh/Cao cho moi vung gia tri.\n"

            "       - Stop-loss suggested level (neu co).\n\n"

            "[FORMAT]\n"

            "Sinh ket qua theo duong dan markdown format, su dung bullet poinrs và headers de de doc. KHONG SU DUNG DANH SO 1-2-3-"

        )

        # Call Ollama with FRESH context - use .replace() for the data placeholder

        r = requests.post(

             "%s/v1/chat/completions" % ollama_url,

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

                return {

                    "evaluation": text,

                    "summary": summary,

                }

        print("[EVAL] Ollama returned status %s" % r.status_code)

    except requests.exceptions.Timeout as e:

        print("[EVAL] Timeout after refresh and prompt preparation: %s" % e)

    except Exception as e:

        print("[EVAL] Evaluation generation failed: %s" % e)

    return None

@app.route("/api/market-evaluation/generate", methods=["POST"])

def api_generate_evaluation():

    """Trigger LLM to generate a new evaluation with fresh data."""

    if not config:

        return jsonify({"error": "Config not loaded yet"}), 503

    ready = True  # Removed forced 30s wait - should be fast enough now

    try:

        result = api_market_evaluation.__wrapped__().get("data") if hasattr(api_market_evaluation, "__wrapped__") else None

        # Direct force refresh approach instead of wrapper

        print("[EVAL] Generating fresh evaluation with manual fetch...")

        articles = []

        try:

            art_fresh = get_articles(limit=20)

            for a in art_fresh:

                _enrich_article(a, use_llm=False)

            articles = art_fresh

        except Exception as e:

            print("[EVAL] Articles refresh failed: %s" % e)

        from concurrent.futures import ThreadPoolExecutor, as_completed

        fresh_data = {}

        with ThreadPoolExecutor(max_workers=8) as executor:

            flist = [

                executor.submit(fetch_market_indices),

                executor.submit(get_exchange_rates),

                executor.submit(lambda: fetch_crypto("BTC")),

                executor.submit(lambda: fetch_crypto("ETH")),

                executor.submit(lambda: fetch_crypto("SOL")),

                executor.submit(fetch_gold),

            ]

            if callable(fetch_dxy):

                flist.append(executor.submit(fetch_dxy))

            if callable(fetch_oil):

                flist.append(executor.submit(fetch_oil))

            for fut in as_completed(flist):

                try:

                    data = fut.result()

                    if data is not None:

                        key = "unknown"

                        if isinstance(data, dict):

                            sym_flag = data.get("symbol") or data.get("vn_indices", {}).get("VN-Index", {}).get("price", 999)

                            if data.get("type") == "crypto":

                                key = "crypto_" + data.get("name", "")[:3]

                            elif data.get("type") == "gold":

                                key = "gold"

                            elif data.get("type") == "dxy":

                                key = "dxy"

                            elif data.get("type") == "oil":

                                key = "oil"

                            elif "vn_indices" in data:

                                key = "indices"

                            elif "USD" in data and ("transfer" in data.get("USD", {}) or "cash" in data.get("USD", {})):

                                key = "rates"

                            else:

                                key = "other_%s" % sym_flag

                        fresh_data[key] = data

                except Exception as e2:

                    print("[EVAL] Fetch failed during generation: %s" % e2)

        sys.stdout.flush()

        gen_result = _generate_daily_evaluation(articles, fresh_data)

        if not gen_result:

            return jsonify({"error": "Generation failed - Ollama may be unavailable"}), 500

        db.save_market_evaluation(

            datetime.now().strftime("%Y-%m-%d"),

            gen_result.get("evaluation", ""),

            gen_result.get("summary", ""),

        )

        return jsonify({"status": "ok", "data": gen_result})

    except Exception as e:

        print("[EVAL] Generation error: %s" % e)

        return jsonify({"error": str(e)[:100]}), 500

@app.route("/api/market-evaluation/history", methods=["GET"])

def api_eval_history():

    """Return historical market evaluations."""

    try:

        all_evals = db.get_all_evaluations() if db else []

        return jsonify({"status": "ok", "evaluations": all_evals})

    except Exception as e:

        print("[WARN] Eval history fetch failed: %s" % e)

        return jsonify({"status": "error", "evaluations": [], "error": str(e)[:100]}), 500

# --- API: Daily snapshots ----------------------------------------------------

@app.route("/api/daily-snapshots", methods=["GET"])

def api_daily_snapshots():

    """Return list of available dates for daily briefings."""

    try:

        dates = db.get_all_dates() if db else []

        return jsonify({"status": "ok", "dates": dates})

    except Exception as e:

        return jsonify({

            "status": "error",

            "dates": [],

              "message": str(e),

        }), 400

@app.route("/api/daily-snapshot/<date>", methods=["GET"])

def api_daily_snapshot(date):

     """Return a daily snapshot for a specific date."""

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

def api_daily_snapshot_plural(date):

    """Alias for /api/daily-snapshot/<date>."""

    return api_daily_snapshot(date)

# --- API: Activities & Health -----------------------------------------------

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

            "indices_ok": indices is not None and "vn_indices" in indices,

            "gold_ok": "price" in gold,

            "cache_time": _cache_time,

        })

    except Exception as e:

        return jsonify({"status": "error", "message": str(e)})

@app.route("/api/health", methods=["GET"])

def api_health():

    ollama_status = "unknown"

    try:

        base_url = (config or {}).get("ollama", {}).get("url", "http://localhost:11434") if config else "http://localhost:11434"

        r = requests.get(base_url + "/health", timeout=5)

        ollama_status = "online" if r.status_code == 200 else "offline"

    except Exception as e:

        ollama_status = "error: %s" % str(e)[:40]

    db_path = (config or {}).get("db_path", "N/A") if config else "N/A"

     # Fetch market data from global cache for dashboard display

    idx_cache = (_fresh_cache.get("indices", {}) if isinstance(_fresh_cache, dict) else {}).get("vn_indices", {})

    global_raw = (_fresh_cache.get("indices", {}) if isinstance(_fresh_cache, dict) else {}).get("global_indices", _fresh_cache.get("global") if _fresh_cache else {})

    indices_data = {}

    gold_data = {}

    dxy_data = {}

    oil_data = {}

    rates_data = {}

    try:

        if idx_cache and isinstance(idx_cache, dict):

             indices_data['VN-Index'] = idx_cache

        if global_raw and isinstance(global_raw, dict):

            indices_data['global'] = global_raw

        # Cached market data from _fresh_cache

        if isinstance(_fresh_cache, dict):

            gold_data = _fresh_cache.get("gold", {}).copy() if _fresh_cache.get("gold") else {}

            dxy_data = _fresh_cache.get("dxy", {}).copy() if _fresh_cache.get("dxy") else {}

            oil_data = _fresh_cache.get("oil", {}).copy() if _fresh_cache.get("oil") else {}

            rates_data = _fresh_cache.get("rates", {}).copy() if _fresh_cache.get("rates") else {}

    except Exception:

        pass

    return jsonify({

             "status": "ok",

             "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),

             "ollama": ollama_status,

             "db_path": db_path,

             "cache_age_seconds": int(datetime.now().timestamp() - _cache_time) if _cache_time else 99999,

             "indices": indices_data,

             "gold": gold_data if gold_data else {},

             "dxy": dxy_data if dxy_data else {},

             "oil": oil_data if oil_data else {},

             "rates": rates_data if rates_data else {},

         })

@app.route("/api/shutdown", methods=["POST"])

def api_shutdown():

    """Graceful shutdown (for deployment purposes)."""

    import os

    os._exit(0)

def _signal_handler(signum, frame):

    print("\n[SHUTDOWN] Received signal %d, shutting down gracefully..." % signum)

    import os

    try:

        os._exit(0)

    except Exception:

        pass

# --- Main --------------------------------------------------------------------

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

        try:

            # Table 1: signals_log (from trading bot)

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

            print("[SIGNALS] signals_log error: %s" % e)

        try:

            # Table 2: trading_alerts (from auto-scan engine)

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

                del r["alert_data"]  # Clean up

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

            print("[SIGNALS] trading_alerts error: %s" % e)

        # Sort by timestamp descending (newest first)

        all_signals.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Deduplication

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

        seen_symbols_neutral = set()

        deduped_neutral = []

        for s in neutral_kept:

            if s["symbol"] not in seen_symbols_neutral:

                seen_symbols_neutral.add(s["symbol"])

                deduped_neutral.append(s)

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

    """Get the N most recent signals for grid overview."""

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

    """Get all signals for a specific symbol full history."""

    if not db:

        return jsonify({"symbol": symbol, "signals": []})

    symbol = str(symbol).upper().strip()

    signals = []

    # From signals_log

    try:

        rows = db._c().execute("""

            SELECT symbol, 'TRADING_BOT', signal_type, CAST(strength AS REAL) as strength,

                   price, details, detected_at, delivered as is_delivered, delivery_channel

            FROM signals_log WHERE UPPER(symbol)=UPPER(?) ORDER BY detected_at DESC

        """, (symbol,)).fetchall()

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

        print("[SIGNALS] signals_log lookup %s error: %s" % (symbol, e))

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

        """, (symbol,)).fetchall()

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

        print("[SIGNALS] trading_alerts lookup %s error: %s" % (symbol, e))

    signals.sort(key=lambda x: (x.get("detected_at", "") or x.get("timestamp", "")), reverse=True)

    return jsonify({"symbol": symbol, "signals": signals})

@app.route("/api/signals/add", methods=["POST"])

def api_signal_append():

    """Manual signal entry via dashboard or API."""

    if not db:

        return jsonify({"success": False, "error": "DB not initialized"}), 500

    data = request.get_json() or {}

    symbol = str(data.get("symbol", "")).strip().upper()

    signal_type = str(data.get("signal", "")).upper()

    strength = float(data.get("strength", 0))

    if not symbol or len(symbol) < 2:

        return jsonify({"success": False, "error": "Invalid symbol"}), 400

    valid_types = ("BUY", "SELL", "HOLD", "STOP_LOSS", "TAKE_PROFIT", "WATCH", "NEUTRAL")

    if signal_type and signal_type not in valid_types:

        return jsonify({"success": False, "error": "Invalid signal type"}), 400

    details = {k: v for k, v in data.items() if k not in ("symbol", "signal", "strength")}

    # Persist to signals_log

    try:

        import json as _json

        db._c().execute("""

            INSERT INTO signals_log (symbol, signal_type, strength, price, details, detected_at)

            VALUES (?, ?, ?, ?, ?, ?)

        """, (symbol, signal_type if signal_type else "NEUTRAL", strength,

              data.get("price"), _json.dumps(details), _utc_now_iso()))

        db._conn.commit()

        print("[SIGNALS] Added %s: %s (%.1f)" % (symbol, signal_type, strength))

        return jsonify({"success": True})

    except sqlite3.Error as e:

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

        rowcount = db._c().execute("""

            UPDATE signals_log SET delivered=1 WHERE id=? AND is_delivered=0

        """, (request.json.get("id"),)).rowcount if request.json else 0

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

        return jsonify({"scanned": 0, "new_alerts": 0, "error": "DB/Config not init"})

    try:

        watchlist = db.get_watchlist()

        if not watchlist:

            return jsonify({"scanned": 0, "new_alerts": 0, "message": "Watchlist empty"})

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

        signal_filter = request.args.get("signal", "").upper()   # BUY / SELL / HOLD

        severity_filter = request.args.get("severity", "").upper()

        symbol_filter = request.args.get("symbol", "").upper()

        only_unread = request.args.get("unread", "false").lower() == "true"

        # Fetch signals from BOTH tables

        all_signals = []

        source_counts = {"signals_log": 0, "trading_alerts": 0}

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

            print("[SIGNALS] signals_log error: %s" % e)

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

                raw = r.get("alert_data")

                if isinstance(raw, str):

                    try:

                        import json as _json

                        r["alert_parsed"] = _json.loads(raw)

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

        # Sort by timestamp descending (newest first)

        all_signals.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Deduplication: keep latest signal per symbol

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

        seen_symbols_neutral = set()

        deduped_neutral = []

        for s in neutral_kept:

            if s["symbol"] not in seen_symbols_neutral:

                seen_symbols_neutral.add(s["symbol"])

                deduped_neutral.append(s)

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

    """Get the N most recent signals for grid overview."""

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

    """Get all signals for a specific symbol full history."""

    if not db:

        return jsonify({"symbol": symbol, "signals": []})

    symbol = str(symbol).upper().strip()

    signals = []

    # From signals_log

    try:

        rows = db._c().execute("""

            SELECT symbol, 'TRADING_BOT', signal_type, CAST(strength AS REAL) as strength,

                   price, details, detected_at, delivered as is_delivered, delivery_channel

            FROM signals_log WHERE UPPER(symbol)=UPPER(?) ORDER BY detected_at DESC

        """, (symbol,)).fetchall()

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

        print("[SIGNALS] signals_log lookup %s error: %s" % (symbol, e))

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

        """, (symbol,)).fetchall()

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

        print("[SIGNALS] trading_alerts lookup %s error: %s" % (symbol, e))

    signals.sort(key=lambda x: (x.get("detected_at", "") or x.get("timestamp", "")), reverse=True)

    return jsonify({"symbol": symbol, "signals": signals})

@app.route("/api/signals/add", methods=["POST"])

def api_signal_append():

    """Manual signal entry via dashboard or API."""

    if not db:

        return jsonify({"success": False, "error": "DB not initialized"}), 500

    data = request.get_json() or {}

    symbol = str(data.get("symbol", "")).strip().upper()

    signal_type = str(data.get("signal", "")).upper()

    strength = float(data.get("strength", 0))

    if not symbol or len(symbol) < 2:

        return jsonify({"success": False, "error": "Invalid symbol"}), 400

    valid_types = ("BUY", "SELL", "HOLD", "STOP_LOSS", "TAKE_PROFIT", "WATCH", "NEUTRAL")

    if signal_type and signal_type not in valid_types:

        return jsonify({"success": False, "error": "Invalid signal type"}), 400

    details = {k: v for k, v in data.items() if k not in ("symbol", "signal", "strength")}

    try:

        import json as _json

        db._c().execute("""

            INSERT INTO signals_log (symbol, signal_type, strength, price, details, detected_at)

            VALUES (?, ?, ?, ?, ?, ?)

        """, (symbol, signal_type if signal_type else "NEUTRAL", strength,

              data.get("price"), _json.dumps(details), _utc_now_iso()))

        db._conn.commit()

        print("[SIGNALS] Added %s: %s (%.1f)" % (symbol, signal_type, strength))

        return jsonify({"success": True})

    except sqlite3.Error as e:

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

        if request.json:

            rowcount = (db._c().execute(

                "UPDATE signals_log SET delivered=1 WHERE id=? AND is_delivered=0", 

                (request.json.get("id"),)).rowcount)

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

    signal = request.args.get("signal", "").upper()   # BUY / SELL / HOLD

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

           params,

        ).fetchall()

        alerts = [dict(r) for r in rows]

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

        return jsonify({"scanned": 0, "new_alerts": 0, "error": "DB/Config not init"})

    try:

        watchlist = db.get_watchlist()

        if not watchlist:

            return jsonify({"scanned": 0, "new_alerts": 0, "message": "Watchlist empty"})

        results = {"scanned": 0, "new_alerts": 0}

        for item in watchlist:

            sym = item["symbol"]

            try:

                result = analyze_stock(sym)

                if result and "error" not in result and result.get("price"):

                    results["scanned"] += 1

                    tech = result.get("technical", {}) or {}

                    rsi_val = tech.get("rsi") or tech.get("RSI") or tech.get("RSI_14", 50)

                    sma20 = tech.get("sma_20")

                    macd_hist = tech.get("macd_histogram") if tech else None

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

                    rsi_num = float(rsi_val) if rsi_val else 50

                    change_pct = float(result.get("change_pct", 0))

                    if rsi_num <= 30:

                        reason_parts.append("RSI oversold (%.1f)" % rsi_num)

                        signal_type = "BUY" if signal_type in ("NEUTRAL", "SELL") else signal_type

                    elif rsi_num >= 70:

                        reason_parts.append("RSI overbought (%.1f)" % rsi_num)

                        signal_type = "SELL" if signal_type in ("NEUTRAL", "BUY") else signal_type

                    price_num = float(result.get("price", 0))

                    if sma20 and price_num:

                        if price_num < sma20 * 0.95:   # 5% below SMA

                            reason_parts.append("Price below SMA20 (%.2f)" % sma20)

                            signal_type = "SELL" if signal_type in ("NEUTRAL", "BUY") else signal_type

                    if macd_hist is not None and float(macd_hist) < -0.5:

                        reason_parts.append("MACD momentum bearish")

                        signal_type = "SELL" if signal_type in ("NEUTRAL", "BUY") else signal_type

                    elif macd_hist is not None and float(macd_hist) > 0.5:

                        reason_parts.append("MACD momentum bullish")

                        signal_type = "BUY" if signal_type in ("NEUTRAL", "SELL") else signal_type

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

                    is_neutral = signal_type == "NEUTRAL"

                    existing = db._c().execute(

                         "SELECT id FROM trading_alerts WHERE symbol=? AND timestamp > datetime('now', '-6 hours') LIMIT 1",

                         (sym,),

                    ).fetchone()

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

                    elif is_neutral and not existing:

                        recent = db._c().execute(

                             "SELECT id FROM trading_alerts WHERE symbol=? AND signal_type='NEUTRAL' AND timestamp > datetime('now', '-24 hours') LIMIT 1",

                             (sym,),

                         ).fetchone()

                        if not recent:

                            trigger_alert(sym, "NEUTRAL", {

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

        db.mark_alerts_as_read()

        return jsonify({"success": True})

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(description="Jarvis Hub Dashboard")

    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")

    parser.add_argument("--port", type=int, default=8100, help="Port to listen on")

    args = parser.parse_args()

    print("=" * 60)

    print("JARVIS HUB v2 Dashboard starting...")

    print("Open: http://%s:%s" % (args.host, args.port))

    print("=" * 60)

    # Signal handlers

    try:

        import signal

        signal.signal(signal.SIGINT, _signal_handler)

        signal.signal(signal.SIGTERM, _signal_handler)

    except (OSError, ValueError):

        pass

    # Start background init (non-blocking)

    threading.Thread(target=_init, daemon=True).start()

    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)

