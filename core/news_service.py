"""
news_service.py -- Unified news service with caching layer for Jarvis Hub.

Encapsulates RSS feed fetching, sentiment analysis (heuristic + LLM-layer),
categorization, and exchange rate retrieval. All backed by a single TTL cache.

Usage:
    articles = get_articles(category="general")      # cached 3min
    rates = get_exchange_rates()                     # cached 1min
"""
import json
import re
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import feedparser
import html as html_module
import numpy as np
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# Rate limiting retries for Yahoo Finance (avoids 429)
_MAX_YAHOO_RETRY = 3
_YAHOO_RETRY_DELAY = 2


def _yahoo_retry(url, headers=None, timeout=15):
    """Fetch with exponential back-off to handle Yahoo rate-limit."""
    hdrs = headers or _HEADERS
    last_err = None
    for attempt in range(_MAX_YAHOO_RETRY):
        try:
            r = requests.get(url, timeout=timeout, headers=hdrs)
            if r.status_code == 429:
                wait = _YAHOO_RETRY_DELAY * (2 ** attempt)
                print(f"[RETRY] Yahoo 429 for {url}, waits {wait}s (attempt {attempt+1}/{_MAX_YAHOO_RETRY})", file=sys.stderr)
                time.sleep(wait)
                continue
            if r.status_code >= 500:
                wait = _YAHOO_RETRY_DELAY * (2 ** attempt)
                print(f"[RETRY] Yahoo {r.status_code} for {url}, waits {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            return r
        except requests.exceptions.Timeout as e:
            last_err = e
            wait = _YAHOO_RETRY_DELAY * (2 ** attempt)
            print(f"[RETRY] Timeout for {url}, waits {wait}s", file=sys.stderr)
            time.sleep(wait)
        except requests.exceptions.ConnectionError as e:
            last_err = e
            if attempt < _MAX_YAHOO_RETRY - 1:
                time.sleep(2 * (attempt + 1))
    print(f"[ERROR] All retries failed for {url}: {last_err}", file=sys.stderr)
    return None


_BULLISH_PATTERNS = [
    "tăng", "lãi", "khởi sắc", "bùng nổ", "tăng mạnh", "vượt",
    "lợi nhuận", "doanh thu", "trọng điểm", "mua thêm", "nạp thêm",
    "phát hành cổ phiếu", "chia cổ tức", "mua vào", "vượt trội",
    "tăng trưởng", "mở rộng", "đầu tư", "hợp đồng", "vượt mức",
    "tích lũy", "lãi gộp", "lãi ròng", "doanh thu thuần",
    "xuất khẩu", "phục hồi", "tăng giá", "tốt", "tốt hơn",
    "khẳng định", "thuận lợi", "vượt dự đoán", "khởi điểm",
    "bứt phá", "lãi suất giảm", "fpi", "fdi", "dòng vốn",
    "sổ lãi", "lợi nhuận cao", "doanh số tăng", "top đầu",
    "vốn hóa tăng", "khối ngoại mua", "tăng điểm", "phục hồi mạnh",
    "mua ròng", "đón sóng", "hứng thú", "năng lực", "đột phá",
]

_BEARISH_PATTERNS = [
    "giảm", "rớt", "sụt giảm", "thất bại", "thua lỗ", "rủi ro",
    "đình chỉ", "rút lui", "rút tiền", "suy giảm", "rơi tự do",
    "phá sản", "sụp đổ", "giảm giá", "rào cản", "căng thẳng",
    "sai sót", "vi phạm", "bị phạt", "suy thoái", "sổ lỗ",
    "số lỗ", "nợ", "kháng cáo", "thua", "sụt", "đóng băng",
    "đứng yên", "bất ổn", "khủng hoảng", "sáp nhập", "đuổi",
    "bán tháo", "rút vốn", "dòng vốn chảy ra", "khối ngoại bán",
    "áp lực giảm", "rơi sâu", "sập", "thắt chặt", "tăng nợ",
    "rủi ro cao", "đe dọa", "tố cáo", "bị điều tra", "lạm phát",
    "đình chỉ giao dịch", "cảnh báo", "phơi nhiễm", "thất thoát",
    "xâm nhập", "bắt giữ", "chốt lời", "bán ròng", "thấp kỷ lục",
    "tệ nhất", "cao kỷ lục", "đáy", "nghiêm trọng", "thảm họa",
]

_SECTOR_TAGS = {
    "ngân hàng": ["ngân hàng", "bank", "acb", "vcb", "vpb", "tcb", "mb", " bid", "ctg", "tpb", "hdb", "stb", "vib"],
    "bất động sản": ["bất động sản", "real estate", "vhm", "vic", "nha", "hut"],
    "năng lượng": ["năng lượng", "energy", "pow", "gas", "dcs", "tpp"],
    "công nghệ": ["công nghệ", "technology", "fpt", "gvr", "hsg"],
    "chứng khoán": ["chứng khoán", "brokerage", "ssi", " vnd", "vps"],
    "thực phẩm": ["thực phẩm", "fmcb", "vnm", "dhg", "msn"],
}


class _NewsCache:
    """Simple TTL cache for news data."""
    TTLS = {'articles': 180, 'rates': 60}

    def __init__(self):
        self._store = {}
        self._ts = {}

    def get(self, key):
        if key in self._store and (datetime.utcnow().timestamp() - self._ts.get(key, 0)) < self.TTLS.get(key, 180):
            return self._store[key]
        return None

    def put(self, key, data):
        self._store[key] = data
        self._ts[key] = datetime.utcnow().timestamp()


_NEWS_CACHE = _NewsCache()


def _get_config():
    import core.config as cfg_mod
    return cfg_mod.load_config() if hasattr(cfg_mod, "load_config") else None


def _heuristic_sentiment(title: str, summary: str) -> Tuple[str, int, int]:
    """Layer 1: Heuristic sentiment scoring."""
    text = (title + " " + summary).lower()
    bull = sum(1 for w in _BULLISH_PATTERNS if w in text)
    bear = sum(1 for w in _BEARISH_PATTERNS if w in text)
    if bull > bear and bull >= 1:
        label = "TÍCH_CỰC"
    elif bear > bull and bear >= 1:
        label = "TIÊU_CỰC"
    else:
        label = "TRUNG_LẬP"
    return label, bull, bear


def _categorize(article: dict) -> str:
    """Categorize article into sectors based on content keywords."""
    text = (article["title"] + " " + article.get("summary_raw", "")).lower()
    max_score = 0
    best_sector = "general"
    for sector, keywords in _SECTOR_TAGS.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > max_score:
            max_score = score
            best_sector = sector
    return best_sector


def _get_db():
    import core.db as db_mod
    return db_mod.Database() if hasattr(db_mod, "Database") else None


_SYS = __import__("sys")


def fetch_and_categorize_articles(limit: int = 30) -> List[dict]:
    """Fetch RSS feeds from all sources, deduplicate, and return articles."""
    config = _get_config() or {}
    sources = config.get("feed", {}).get("sources", [
        {"name": "Cafef Doanh nghiệp", "url": "https://cafef.vn/doanh-nghiep.rss", "priority": 1},
        {"name": "VnExpress Kinh doanh", "url": "https://vnexpress.net/rss/kinh-doanh.rss", "priority": 2},
        {"name": "VnExpress Kinh tế", "url": "https://vnexpress.net/rss/kinh-te.rss", "priority": 2},
    ])

    articles = []
    seen_links = set()

    for source in sources:
        try:
            feed = feedparser.parse(source["url"])
            if feed.bozo and not feed.entries:
                continue
            for entry in feed.entries[:5]:
                link = entry.get("link", "") or entry.get("id", "")
                if not link or link in seen_links:
                    continue

                title = entry.get("title", "").strip()
                summary = entry.get("summary", "").strip()

                pub_parsed = entry.get("published_parsed")
                is_recent = False
                if pub_parsed:
                    pub_dt = datetime(*pub_parsed[:6])
                    hours_old = (datetime.now() - pub_dt).total_seconds() / 3600
                    is_recent = hours_old <= 48

                articles.append({
                    "title": title,
                    "link": link,
                    "summary_raw": summary.replace("<[^>]+>", ""),
                    "published": entry.get("published", entry.get("updated", "")),
                    "source": source["name"],
                    "category": source.get("category", "general"),
                    "priority": source.get("priority", 2),
                    "is_recent": is_recent,
                })
                seen_links.add(link)
        except Exception as e:
            print("[WARN] RSS fetch failed for %s: %s" % (source["name"], e), file=sys.stderr)

    articles.sort(key=lambda a: (a.get("priority", 2), not a["is_recent"]))
    return articles[:limit]


def enrich_article(article: dict, use_llm: bool = False) -> dict:
    """Apply sentiment analysis and categorization to an article."""
    title = article["title"]
    summary = article.get("summary_raw", "")

    sent_label, bull_c, bear_c = _heuristic_sentiment(title, summary)
    sent_map = {
        "TÍCH_CỰC": "\U0001f7e2 tích cực",
        "TIÊU_CỰC": "\U0001f534 tiêu cực",
    }
    article["sentiment_layer1"] = sent_map.get(sent_label, "\U0001f7e1 trung lập")
    article["bull_count"] = bull_c
    article["bear_count"] = bear_c

    if use_llm and _get_config() is not None:
        try:
            config = _get_config()
            ollama_url = config.get("ollama", {}).get("url", "http://localhost:11434")
            model = config.get("ollama", {}).get("model", "qwen3.6:latest")

            prompt = (
                 "Ban la tro gi phan tich thi truong tai chinh Viet Nam.\n"
                 "Title: %s\nContent: %s\n\n"
                 '{"sentiment": "tich_cuc|tieu_cuc|trung_lap", "reason": "reason text"}'
            ) % (title, summary[:500])

            resp = requests.post(
                ollama_url + "/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": "Title: %s\nContent: %s" % (title, summary[:500])}
                    ],
                    "stream": False,
                    "num_predict": 4096,
                },
                timeout=12,
            )
            if resp.status_code == 200:
                result_text = (resp.json().get("message", {}).get("content", "") or "").strip()
                json_match = re.search(r"```(?:json)?\s*(.+?)\s*```", result_text, re.DOTALL)
                if json_match:
                    result_text = json_match.group(1)
                parsed = json.loads(result_text)
                sent = parsed.get("sentiment", "trung_lap")
                reason = parsed.get("reason", "")
                disp_map = {
                    "tich_cuc": "\U0001f7e2 tích cực",
                    "tieu_cuc": "\U0001f534 tiêu cực",
                    "trung_lap": "\U0001f7e1 trung lập",
                }
                article["sentiment_layer2"] = disp_map.get(sent, sent)
                article["llm_reasoning"] = reason
        except Exception as exc:
            print("[WARN] LLM sentiment failed: %s" % exc, file=sys.stderr)

    article["sector"] = _categorize(article)
    return article


def get_exchange_rates() -> dict:
    """Fetch USD/VND exchange rates from Vietcombank."""
    cached = _NEWS_CACHE.get("rates")
    if cached:
        return cached

    rate_obj = {"source": "vietcombank", "updated": "N/A"}
    try:
        resp = requests.get(
            "https://www.vietcombank.com.vn/vi-VN/KHCN/Cong-cu-Tien-ich/Ty-gia",
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        )
        if resp.status_code == 200:
            match = re.search(r'id="currentDataExchange"\s+value="([^"]+)"', resp.text)
            if match:
                raw = html_module.unescape(match.group(1))
                data = json.loads(raw)
                updated = data.get("UpdatedDate", "")
                rate_obj["updated"] = updated
                for curr in (data if isinstance(data, dict) else {}).get("Data", []):
                    code = curr.get("currencyCode", "")
                    rate_obj[code] = {
                        "cash": round(float(curr.get("cash", 0)) / 100, 4),
                        "transfer": round(float(curr.get("transfer", 0)) / 100, 4),
                        "sell": round(float(curr.get("sell", 0)) / 100, 4),
                    }
    except Exception as e:
        print("[WARN] FX rates fetch failed: %s" % e, file=sys.stderr)

    _NEWS_CACHE.put("rates", rate_obj)
    return rate_obj


def get_articles(category=None, limit=30) -> List[dict]:
    """Get articles with sentiment scores. Cached for 3 minutes."""
    cached = _NEWS_CACHE.get("articles")
    if cached and category is None:
        result = [a for a in cached if not category or (a.get("category", "").lower() == category.lower())]
        return result

    articles = fetch_and_categorize_articles(limit)
    for a in articles:
        enrich_article(a, use_llm=False)

    if category:
        articles = [a for a in articles if (a.get("category", "").lower() == category.lower())]

    _NEWS_CACHE.put("articles", articles)
    return articles


def search_knowledge(db, query: str) -> List[dict]:
    """Search knowledge base with relevance scoring."""
    if not db or not query:
        return []
    cleaned = query.strip().lower()
    stop_words = {
        "la", "va", "hoac", "trong", "cua", "de", "du", "co",
        "the", "is", "are", "was", "were", "be", "been", "being",
        "will", "would", "could", "should", "may", "might", "must",
        "can", "a", "an", "the", "at", "to", "for", "of", "in",
        "on", "with", "by", "from", "about",
    }
    meaningful = [w for w in cleaned.split() if len(w) >= 3 and w not in stop_words]

    if not meaningful:
        return []

    results = {}
    for word in meaningful[:3]:
        rows = db._c().execute(
            "SELECT id, term, content, tags, updated_at FROM knowledge WHERE LOWER(term) LIKE ?",
            ("%" + word + "%",),
        ).fetchall()

        for row in rows:
            d = dict(row)
            term_lower = d["term"].lower()
            score = 0

            if term_lower == cleaned or term_lower.startswith(cleaned):
                score += 30

            term_words_list = term_lower.split()
            matched_count = 0
            word_order_correct = True
            last_term_idx = -1

            for qi, qword in enumerate(meaningful[:2]):
                if qword in term_words_list:
                    matched_count += 1
                    tpos = term_words_list.index(qword)
                    if tpos < last_term_idx and matched_count > 1:
                        word_order_correct = False
                    last_term_idx = tpos

            if matched_count >= 2 and word_order_correct:
                score += 50
            elif matched_count >= 2:
                score += 35
            elif matched_count == 1:
                score += 20

            if not any(ww in term_lower for ww in meaningful[:2]):
                score += 5

            existing = results.get(d["term"])
            if existing is None or score > existing[0]:
                results[d["term"]] = (score, d)

        filtered_results = {k: v for k, v in results.items() if v[0] >= 20}
        if not filtered_results:
            for i in range(len(meaningful)):
                pattern1 = "%" + meaningful[i] + "%"
                if i + 1 < len(meaningful):
                    pattern2 = "%" + meaningful[i + 1] + "%"
                    rows2 = db._c().execute(
                        "SELECT id, term, content, tags, updated_at FROM knowledge WHERE LOWER(content) LIKE ? AND LOWER(content) LIKE ?",
                        (pattern1, pattern2),
                    ).fetchall()

                    for row in rows2:
                        d = dict(row)
                        if d["term"] not in results:
                            content_lower = d["content"].lower()
                            pos1 = content_lower.find(pattern1.replace("%", ""))
                            pos2 = content_lower.find(pattern2.replace("%", ""))
                            sr = 10
                            if pos1 >= 0 and pos2 >= 0 and pos1 < pos2:
                                sr = 25
                            results[d["term"]] = (sr, d)
                else:
                    rows3 = db._c().execute(
                        "SELECT id, term, content, tags, updated_at FROM knowledge WHERE LOWER(content) LIKE ?",
                        (pattern1,),
                    ).fetchall()
                    for row in rows3:
                        d = dict(row)
                        if d["term"] not in results:
                            results[d["term"]] = (5, d)

    sorted_results = sorted(results.items(), key=lambda x: x[0], reverse=True)
    return [item[1] for item in sorted_results[:10]] if sorted_results else []


# ---- Market index fetching ----

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "application/json",
}


def fetch_market_indices() -> dict:
    """Fetch VN-Index + global indices from Yahoo Finance in parallel."""
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

    vn_indices = {}
    global_indices = {}
    from concurrent.futures import ThreadPoolExecutor, as_completed

    try:
        r = _yahoo_retry(
             "https://query1.finance.yahoo.com/v8/finance/chart/^VNINDEX.VN",
            timeout=15
         )
        if r and r.status_code == 200:
            result_list = r.json().get("chart", {}).get("result")
            if result_list:
                meta = result_list[0].get("meta", {})
                prev = float(meta.get("previousClose", 0) or 1)
                p = float(meta.get("regularMarketPrice", 0))
                vn_indices["VN-Index"] = {
                     "price": round(p, 2),
                     "change": round(p - prev, 2),
                     "change_pct": round((p - prev) / max(prev, 1) * 100, 2),
                     "prev_close": round(prev, 2),
                 }
    except Exception:
        pass

     # Fetch global indices sequentially to avoid rate limit
    for i, sym in enumerate(name_map.keys()):
        display = name_map.get(sym)
        time.sleep(1.0 + 0.5 * i)   # stagger requests
        _display, data = _fetch_single_index(sym, {sym: display})
        if isinstance(_display, str):
            vn_indices[_display] = data or {}
        elif data:
            global_indices[_display[0]] = data

    return {
        "vn_indices": vn_indices,
        "global_indices": global_indices,
    }


def _fetch_single_index(symbol: str, name_map: dict):
    """Fetch a single index from Yahoo Finance."""
    display_name_info = name_map.get(symbol)
    if not display_name_info:
        return (symbol, None)

    try:
        r = _yahoo_retry(
              "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol,
            timeout=15
          )
        if r is None or r.status_code != 200:
            return (display_name_info, None)
        data = r.json()
        result_data = data.get("chart", {}).get("result")
        if not result_data:
            return (display_name_info, None)

        meta = result_data[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        prev_close = meta.get("previousClose")

        if price is None or prev_close is None:
            return (display_name_info, None)

        prev = float(prev_close)
        cur = float(price)
        parsed_result = {
              "price": round(cur, 2),
              "change": round(cur - prev, 2),
              "change_pct": round((cur - prev) / max(prev, 1) * 100, 2),
              "prev_close": round(prev, 2),
         }
        return (display_name_info, parsed_result)

    except Exception as exc:
        print("[WARN] Yahoo index fetch failed for %s: %s" % (symbol, exc), file=sys.stderr)
        return (display_name_info, None)


def fetch_crypto(symbol: str) -> Optional[dict]:
    """Fetch crypto price from Binance API."""
    sym_upper = symbol.upper().lstrip("$")
    binance_map = {
        "BTC": "BTCUSDT", "ETH": "ETHUSDT",
        "SOL": "SOLUSDT", "BNB": "BNBUSDT",
    }
    b_symbol = binance_map.get(sym_upper, sym_upper + "USDT")

    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr?symbol=" + b_symbol,
            timeout=8
        )
        if r.status_code == 200:
            data = r.json()
            name_sym = "Bitcoin" if "BTC" in sym_upper else ("Ethereum" if "ETH" in sym_upper else symbol.title())
            return {
                "symbol": symbol, "name": name_sym,
                "price": round(float(data.get("lastPrice", 0)), 2),
                "change_pct": round(float(data.get("priceChangePercent", 0)), 2),
                "volume": data.get("quoteVolume"),
                "high_24h": round(float(data.get("highPrice", 0)), 2),
                "low_24h": round(float(data.get("lowPrice", 0)), 2),
                "currency": "USD", "type": "crypto",
            }
    except Exception as e:
        print("[WARN] Binance fetch failed for %s: %s" % (symbol, e), file=sys.stderr)
    return None


def fetch_gold() -> Optional[dict]:
    """Fetch gold spot price via Yahoo or fallback sources."""
    candidates = ["XAU/USD", "GC=F", "GLD", "XAUUSD=X"]
    for sym in candidates:
        try:
            r = _yahoo_retry(
                 "https://query1.finance.yahoo.com/v8/finance/chart/" + sym,
                timeout=15
              )
            if r and r.status_code == 200:
                result_list = r.json().get("chart", {}).get("result", [{}])
                meta = result_list[0].get("meta", {})
                price = meta.get("regularMarketPrice")
                prev_close = meta.get("previousClose")
                currency = meta.get("currency", "USD")

                if price and prev_close and prev_close > 0:
                    return {
                        "symbol": "XAU/USD", "name": "Gold (" + sym + ")",
                        "price": round(float(price), 2),
                        "change_pct": round((float(price) - float(prev_close)) / float(prev_close) * 100, 2),
                        "currency": currency, "type": "gold",
                    }
        except Exception:
            continue
    return None


def fetch_dxy() -> Optional[dict]:
    """Fetch DXY (US Dollar Index)."""
    try:
        r = _yahoo_retry(
                 "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB",
                timeout=15
               )
        if r and r.status_code == 200:
            result_list = r.json().get("chart", {}).get("result", [{}])
            meta = result_list[0].get("meta", {})
            price = meta.get("regularMarketPrice")
            prev_close = meta.get("previousClose")
            if price and prev_close and prev_close > 0:
                return {
                    "symbol": "DXY", "name": "US Dollar Index",
                    "price": round(float(price), 2),
                    "change_pct": round((float(price) - float(prev_close)) / float(prev_close) * 100, 2),
                    "currency": "USD", "type": "dxy",
                }
    except Exception as exc:
        print("[WARN] DXY fetch failed: %s" % exc, file=sys.stderr)
    return None


def fetch_oil() -> Optional[dict]:
    """Fetch WTI crude oil price."""
    try:
        r = _yahoo_retry(
                 "https://query1.finance.yahoo.com/v8/finance/chart/CL=F",
                timeout=15
               )
        if r and r.status_code == 200:
            result_list = r.json().get("chart", {}).get("result", [{}])
            meta = result_list[0].get("meta", {})
            price = meta.get("regularMarketPrice")
            prev_close = meta.get("previousClose")
            if price and prev_close and prev_close > 0:
                return {
                    "symbol": "WTI", "name": "Crude Oil (WTI)",
                    "price": round(float(price), 2),
                    "change_pct": round((float(price) - float(prev_close)) / float(prev_close) * 100, 2),
                    "currency": "USD", "type": "oil",
                }
    except Exception as exc:
        print("[WARN] Oil fetch failed: %s" % exc, file=sys.stderr)
    return None


def fetch_gold_prices() -> Optional[dict]:
    """Alias for fetch_gold - kept for backward compatibility."""
    return fetch_gold()


# ============================================================================
# AI INTELLIGENCE FEED — Full LLM-powered analysis
# ============================================================================

_AIF_FEED_URLS = [
    {"name": "AITrends", "url": "https://www.aibulletin.com/feed/", "section": "AI & Tech"},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/", "section": "AI & Tech"},
    {"name": "The Gradient AI", "url": "https://thegradient.pub/rss.xml", "section": "AI Research"},
    {"name": "Simon Willison AI", "url": "https://simonwillison.net/index.xml", "section": "AI General"},
    {"name": "Ars Technica AI", "url": "https://feeds.arstechnical.com/arstechnica/artificial-intelligence", "section": "AI & Tech"},
]

_AIF_GLOBAL_FEEDS = [
    {"name": "Bloomberg Business", "url": "https://feeds.bloomberg.com/business/news/rss", "section": "Economy"},
    {"name": "Reuters Top", "url": "https://www.reutersagency.com/feed/", "section": "Global News"},
    {"name": "Cafef Doanh nghiệp", "url": "https://cafef.vn/doanh-nghiep.rss", "section": "VN Economy"},
]

_AIF_PROMPTS = {
    "overview": (
        "You are Jarvis, an intelligent news analyst. Analyze the following collected AI & technology news articles. "
        "Provide a concise synthesis of the most prominent events in the last 24 hours.\n"
        "Priority #1: Breakthroughs in AI (new models, tools, regulatory updates).\n"
        "Also cover: Politics/Economy, Technology trends, other sectors.\n"
        "Format with clear sections and bullet points. Be sharp and strategic."
    ),
    "trends": (
        "Based on the collected AI & tech news, provide a trend analysis overview:\n"
        "1. What is the focal point? Is there a correlation between AI events and other sectors?\n"
        "2. Key trends to watch this week.\n"
        "3. Any emerging themes across multiple sources?"
    ),
    "recommendations": (
        "Based on current market context and AI trends, provide 2-3 actionable recommendations:\n"
        "1. How to apply new AI tools in work/life optimization.\n"
        "2. Investment/tech direction observations.\n"
        "Keep it specific and practical, not generic."
    ),
    "tech_lab": (
        "Analyze emerging tech trends from these articles. Propose ONE specific project or prototype\n"
        "that you and a developer can start building immediately with current technology.\n"
        "Clearly explain why this project is feasible and provides practical value.\n"
        "Suggest 1 concrete project outline (title, description, tech stack, expected output)."
    ),
}



def _call_llm_for_analysis(system_prompt: str, articles_list: list) -> Optional[str]:
    """Generate LLM analysis of news articles using Ollama."""
    global _config
    if not _config or "ollama" not in (_config or {}):
        return None

    ollama_url = _config.get("ollama", {}).get("url", "http://localhost:11434")
    model = _config.get("ollama", {}).get("model", "qwen3.6:35b-a3b-mxfp8")
    combined = ""
    for i, art in enumerate(articles_list[:20]):
        title = (art.get("title", "") or "").strip()
        summary = (art.get("summary", "") or art.get("description", "") or "").strip()
        if len(summary) > 300:
            summary = summary[:300] + "..."
        combined += f"{i+1}. ({art.get('source', 'Unknown')}) [{art.get('section', '')}] {title}: {summary}\n\n"

    prompt = f"{system_prompt}\n\n---\nCollected articles:\n{combined}"

    try:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are Jarvis, an intelligent news analyst and strategy advisor. Be concise, sharp, strategic."},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 2048,
            }
        }

        import json as _json_module
        req_data = _json_module.dumps(payload).encode("utf-8")
        req_headers = {"Content-Type": "application/json"}
        
        req = urllib.request.Request(
            f"{ollama_url}/v1/chat/completions",
            data=req_data,
            headers=req_headers,
        )

        response = urllib.request.urlopen(req, timeout=120)
        result = _json_module.loads(response.read())

        # Extract assistant message content from chat format
        for msg in result.get("message", {}).get("content", []) or []:
            if isinstance(msg, dict):
                return msg.get("content", "")
        
        content = result.get("message", {}).get("content", "")
        return content if content else None

    except Exception as e:
        print(f"[AI FEED] LLM analysis error: {e}", file=sys.stderr)
        return None



def _perform_ai_feed_collection(limit=40) -> Optional[dict]:
    """Fetch AI intelligence feed with LLM-powered analysis.
    
    Returns structured data with multiple analysis sections, ready for display 
    in the Jarvis Hub dashboard or Telegram briefing delivery.
    """
    import json as _json_module
    import time as _time

    print("[AI FEED] Starting full intelligence feed collection...")

    try:
        # ===== Phase 1: Fetch RSS feeds (parallel) =====
        articles = []
        
        all_sources = list(_AIF_FEED_URLS) + list(_AIF_GLOBAL_FEEDS)
        
        def fetch_feed(source_info):
            try:
                d = feedparser.parse(source_info["url"])
                if d.bozo and not d.entries:
                    return []
                results = []
                for entry in d.entries[:4]:
                    link = (entry.get("link") or entry.get("id") or "").strip()
                    title = (entry.get("title") or "").strip()
                    summary = (entry.get("summary") or entry.get("description") or "").strip()
                    if not link or len(title) < 15:
                        continue
                    results.append({
                        "title": title,
                        "link": link,
                        "summary": summary[:400] if summary else "",
                        "published": entry.get("published", ""),
                        "source": source_info["name"],
                        "section": source_info.get("section", "General"),
                    })
                return results
            except Exception as e:
                print(f"[AI FEED] Feed error ({source_info['name']}): {e}")
                return []

        with ThreadPoolExecutor(max_workers=8) as executor:
            future_list = {
                executor.submit(fetch_feed, src): src["name"]
                for src in all_sources
            }
            for future in as_completed(future_list):
                name = future_list[future]
                try:
                    feed_articles = future.result()
                    articles.extend(feed_articles)
                except Exception as e:
                    print(f"[AI FEED] Task error ({name}): {e}")

        # Deduplicate by title similarity
        seen_titles = set()
        unique_articles = []
        for art in sorted(articles, key=lambda a: a.get("published", "")):
            key = art["title"].strip().lower()
            if key not in seen_titles and len(key) > 10:
                seen_titles.add(key)
                unique_articles.append(art)

        articles = unique_articles[:limit]

        if not articles:
            return {"status": "error", "error": "No articles fetched from any source", "tasks": [], "total_articles": 0, "total_sources": 0}

        total_sources = len(set(a["section"] for a in articles))
        print(f"[AI FEED] Collected {len(articles)} articles from {total_sources} sources")

        # ===== Phase 2: LLM Analysis (parallel by section) =====
        tasks = []
        
        analysis_futures = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            for section_name, prompt in _AIF_PROMPTS.items():
                future = executor.submit(_call_llm_for_analysis, prompt, articles)
                analysis_futures[future] = section_name

            for future in as_completed(analysis_futures):
                section_name = analysis_futures[future]
                try:
                    analysis_text = future.result()
                    if analysis_text and len(analysis_text.strip()) > 50:
                        emoji_map = {
                            "overview": "🔴",
                            "trends": "📊", 
                            "recommendations": "💡",
                            "tech_lab": "🔬",
                        }
                        emoji = emoji_map.get(section_name, "📰")
                        tasks.append({
                            "section": f"{emoji} {section_name.replace('_', ' ').title()}",
                            "analysis": analysis_text.strip(),
                        })
                    else:
                        print(f"[AI FEED] Skipped empty analysis for {section_name}")
                except Exception as e:
                    print(f"[AI FEED] Analysis error ({section_name}): {e}")

        return {
            "status": "ok",
            "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "total_articles": len(articles),
            "total_sources": total_sources,
            "tasks": tasks,
            "articles_preview": articles[:5],  # First 5 for UI preview
        }

    except Exception as exc:
        print(f"[AI FEED] Critical error: {exc}", file=sys.stderr)
        return {"status": "error", "error": str(exc), "tasks": [], "total_articles": 0, "total_sources": 0}


def get_fast_feed(limit=30):
    """Quick feed without LLM — just RSS aggregation for fast access."""
    import json as _json_module
    
    articles = []
    for source in _AIF_FEED_URLS:
        try:
            d = feedparser.parse(source["url"])
            if d.bozo and not d.entries:
                continue
            for entry in d.entries[:3]:
                link = (entry.get("link") or entry.get("id") or "").strip()
                title = (entry.get("title") or "").strip()
                summary = (entry.get("summary") or entry.get("description") or "").strip()
                if not link or len(title) < 15:
                    continue
                articles.append({
                    "title": title,
                    "link": link,
                    "summary": summary[:200] if summary else "",
                    "published": entry.get("published", ""),
                    "source": source["name"],
                    "section": source.get("section", "General"),
                })
        except Exception:
            pass

    # Deduplicate
    seen = set()
    unique = []
    for a in articles:
        key = a["title"].strip().lower()
        if key not in seen and len(key) > 10:
            seen.add(key)
            unique.append(a)
    
    return {"status": "ok", "articles": unique[:limit], "total_articles": len(unique)}

def get_ai_feed(limit=40):
    """Public entry point for AI intelligence feed - calls the main implementation."""
    try:
        return _get_ai_feed_unlocked(limit)
    except Exception as exc:
        print(f"[AI FEED] Critical error: {exc}", file=sys.stderr)
        return {"status": "error", "error": str(exc), "tasks": [], "total_articles": 0, "total_sources": 0}


def _get_ai_feed_unlocked(limit=40):
    """Core AI feed logic (unlocked version called from get_ai_feed wrapper)."""
    try:
        return _perform_ai_feed_collection(limit)
    except Exception as exc:
        print(f"[AI FEED] Collection error: {exc}", file=sys.stderr)
        raise


