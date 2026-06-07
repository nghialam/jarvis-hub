"""
news.py -- News feed fetching + sentiment analysis engine for Jarvis Hub.

Layers:
  Layer 1 (fast): heuristic keyword scoring
  Layer 2 (deep): Ollama LLM-powered sentiment reasoning per article
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import feedparser
import html
import requests

# Lazy init of config/db
_config = None
_db = None


def _get_config():
    global _config
    if _config is None:
        _config = __import__("core.config", fromlist=["load_config"]).load_config()
    return _config


def _get_db():
    global _db
    if _db is None:
        _db = __import__("core.db", fromlist=["Database"]).Database()
    return _db


HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

# --- Heuristic sentiment patterns (Layer 1) -------------------------------

BULLISH_PATTERNS = [
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

BEARISH_PATTERNS = [
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

# Sector tags for categorization
SECTOR_TAGS = {
    "ngân hàng": ["ngân hàng", "bank", "acb", "vcb", "vpb", "tcb", "mb", " bid", "ctg", "tpb", "hdb", "stb", "vib"],
    "bất động sản": ["bất động sản", "real estate", "vhm", "vic", "nha", "hut"],
    "năng lượng": ["năng lượng", "energy", "pow", "gas", "dcs", "tpp"],
    "công nghệ": ["công nghệ", "technology", "fpt", "gvr", "hsg"],
    "chứng khoán": ["chứng khoán", "brokerage", "ssi", " vnd", "vps"],
    "thực phẩm": ["thực phẩm", "fmcb", "vnm", "dhg", "msn"],
}


def categorize(article: dict) -> str:
    """Categorize article into sectors based on content keywords."""
    text = (article["title"] + " " + article.get("summary_raw", "")).lower()
    max_score = 0
    best_sector = "general"

    for sector, keywords in SECTOR_TAGS.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > max_score:
            max_score = score
            best_sector = sector
    return best_sector


def heuristic_sentiment(title: str, summary: str) -> Tuple[str, int, int]:
    """Layer 1: Heuristic sentiment scoring.
    Returns (label, bull_count, bear_count)."""
    text = (title + " " + summary).lower()

    bull = sum(1 for w in BULLISH_PATTERNS if w in text)
    bear = sum(1 for w in BEARISH_PATTERNS if w in text)

    if bull > bear and bull >= 1:
        label = "TÍCH_CỰC"
    elif bear > bull and bear >= 1:
        label = "TIÊU_CỰC"
    else:
        label = "TRUNG_LẬP"

    return label, bull, bear


def llm_sentiment(title: str, summary: str) -> tuple:
    """Layer 2: Ollama LLM-powered sentiment analysis per article.
    Returns (sentiment_label, brief_reasoning) or None if Ollama unavailable."""
    try:
        config = _get_config()
        ollama_url = config.get("ollama", {}).get("url", "http://localhost:11434")
        model = config.get("ollama", {}).get("model", "qwen3.6:latest")

        prompt = (
            "Ban la tro gi phan tich thi truong tai chinh Viet Nam. "
            "Phan tich cam xuc tin tuc sau:\n\n"
            f"Tieu de: {title}\n"
            f"Noi dung: {summary[:500]}\n\n"
            'Hay tra ve JSON voi format:\n'
            '{"sentiment": "tich_cuc|tieu_cuc|trung_lap", '
            '"reason": "ly do ngan gon (duoi 20 tu)"}\n\n'
            "Chi tra ve JSON, khong them giai thich gi khac."
        )


        def _call_ollama():
            try:
                resp = requests.post(
                    ollama_url + "/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": f"Title: {title}\nContent: {summary[:500]}"}
                        ],
                        "stream": False,
                        "num_predict": 4096,
                    },
                    timeout=30,
                )
                if resp.status_code != 200:
                    print(f"[WARN] Ollama returned {resp.status_code} for {title[:50]}")
                    return None

                data = resp.json()
                result_text = data.get("message", {}).get("content", "").strip()

                # Extract JSON from markdown code blocks if present
                json_match = re.search(r"```(?:json)?\\s*(.+?)\\s*```", result_text, re.DOTALL)
                if json_match:
                    result_text = json_match.group(1)

                parsed = json.loads(result_text)
                sentiment = parsed.get("sentiment", "trung_lap")
                reasoning = parsed.get("reason", "")
                return (sentiment, reasoning)
            except Exception as e:
                print(f"[WARN] Ollama call failed for {title[:50]}: {e}", file=sys.stderr)
                return None

        # Single get_or_call - lambda delegates to _call_ollama on MISS
        result = llm_cache.get_or_call(prompt, _call_ollama)
        return result

    except Exception as e:
        print(f"[WARN] LLM sentiment failed for {title[:50]}: {e}", file=sys.stderr)
        return None


def enrich_article(article: dict, llm_rank: int = -1):
    """Apply sentiment analysis + categorization to an article."""

    # Layer 1: heuristic (always runs)
    sentiment_heuristic, bull_c, bear_c = heuristic_sentiment(
        article["title"], article.get("summary_raw", "")
    )

    if "TICH_CUC" in sentiment_heuristic or "TÍCH_CỰC" in sentiment_heuristic:
        article["sentiment_layer1"] = "🟢 tích cực"
    elif "TIEU_CUC" in sentiment_heuristic or "TIÊU_CỰC" in sentiment_heuristic:
        article["sentiment_layer1"] = "🔴 tiêu cực"
    else:
        article["sentiment_layer1"] = "🟡 trung lập"

    article["bull_count"] = bull_c
    article["bear_count"] = bear_c

    # Layer 2: LLM - only for top N articles to avoid blocking
    if llm_rank >= 0 and llm_rank < 15:
        try:
            result = llm_sentiment(article["title"], article.get("summary_raw", ""))
            if result:
                sent_label, reason = result
                display_map = {
                    "tich_cuc": ("🟢 tích cực", None),
                    "tieu_cuc": ("🔴 tiêu cực", None),
                    "trung_lap": ("🟡 trung lập", None),
                }
                display_text, _ = display_map.get(sent_label, (sent_label, None))
                article["sentiment_layer2"] = display_text
                article["llm_reasoning"] = reason
            else:
                article["sentiment_layer2"] = None
                article["llm_reasoning"] = None
        except Exception:
            article["sentiment_layer2"] = None
            article["llm_reasoning"] = None
    else:
        article["sentiment_layer2"] = None
        article["llm_reasoning"] = None

    # Categorize
    article["sector"] = categorize(article)


def _fetch_feed_source(source: dict):
    """Fetch articles from a single RSS source. Used for parallel fetching."""
    results = []
    skipped_urls = set()
    try:
        feed = feedparser.parse(source["url"])

        if feed.bozo and not feed.entries:
            return ("", [])   # Signal: failed to fetch or no entries

        for entry in feed.entries[:5]:    # max 5 per source
            link = entry.get("link", "") or entry.get("id", "")
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "").strip()

            if not link or link in skipped_urls:
                continue

            # Quick freshness filter via RSS metadata
            pub_parsed = entry.get("published_parsed")
            is_recent = False

            if pub_parsed:
                pub_dt = datetime(*pub_parsed[:6])
                hours_old = (datetime.now() - pub_dt).total_seconds() / 3600
                is_recent = hours_old <= 48    # relaxed from 24h to reduce noise

            results.append({
                "title": title,
                "link": link,
                "summary_raw": summary.replace("<[^>]+>", ""),
                "published": entry.get("published", entry.get("updated", "")),
                "source": source["name"],
                "category": source.get("category", "general"),
                "priority": source.get("priority", 2),
                "is_recent": is_recent,
            })
            skipped_urls.add(link)

    except Exception as e:
        print(f"[WARN] RSS fetch failed for {source['name']}: {e}", file=sys.stderr)
        return ("", [])    # Signal error via empty string first arg

    return (None, results)


def fetch_rss_feeds() -> List[dict]:
    """Fetch articles from all configured RSS sources in parallel.
    Returns list of article dicts with keys: title, link, summary_raw,
    source, priority, is_recent (boolean)."""
    config = _get_config()
    sources = config.get("feed", {}).get("sources", [
        {"name": "Cafef Doanh nghiệp", "url": "https://cafef.vn/doanh-nghiep.rss", "priority": 1},
        {"name": "VnExpress Kinh doanh", "url": "https://vnexpress.net/rss/kinh-doanh.rss", "priority": 2},
        {"name": "VnExpress Kinh tế", "url": "https://vnexpress.net/rss/kinh-te.rss", "priority": 2},
    ])

    articles = {}
    failed_sources = []
    all_results = []    # (source_name, results)

    # Parallel RSS fetch using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(len(sources), 5)) as executor:
        futures = {executor.submit(_fetch_feed_source, src): src["name"] for src in sources}
        for future in as_completed(futures):
            source_name = futures[future]
            try:
                failed, results = future.result()
                if failed is not None:
                    failed_sources.append(source_name)
                else:
                    all_results.extend(results)
            except Exception as e:
                print(f"[WARN] RSS fetch error for {source_name}: {e}", file=sys.stderr)
                failed_sources.append(source_name)

    # Deduplicate by title keyword (same as before)
    unique = []
    seen_titles = set()
    all_results.sort(key=lambda a: (a.get("priority", 2), not a["is_recent"]))

    for a in all_results[:30]:
        title_key = a["title"][:50].strip().lower()
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique.append(a)

    # Deduplicate by link too
    link_seen = set()
    deduped = []
    for r in unique:
        if r["link"] not in link_seen:
            link_seen.add(r["link"])
            deduped.append(r)

    return deduped


def get_exchange_rate() -> dict:
    """Fetch USD/VND rate from Vietcombank."""
    config = _get_config()
    rates = {"source": config.get("exchange_rates_source", "vietcombank"), "updated": "N/A"}

    try:
        r = requests.get(
            "https://www.vietcombank.com.vn/vi-VN/KHCN/Cong-cu-Tien-ich/Ty-gia",
            timeout=10, headers=HEADERS
        )

        if r.status_code == 200:
            match = re.search(r'id="currentDataExchange"\s+value="([^"]+)"', r.text)
            print(f"[DEBUG] VC fetch status: {r.status_code}, matches: {match is not None}", file=sys.stderr)

            if match:
                raw = html.unescape(match.group(1))
                data = json.loads(raw)
                updated = data.get("UpdatedDate", "")
                rates["updated"] = updated

                for curr in data.get("Data", []):
                    code = curr.get("currencyCode", "")
                    rates[code] = {
                        "cash": round(float(curr.get("cash", 0)) / 100, 4) if curr.get("cash") else None,
                        "transfer": round(float(curr.get("transfer", 0)) / 100, 4) if curr.get("transfer") else None,
                        "sell": round(float(curr.get("sell", 0)) / 100, 4) if curr.get("sell") else None,
                    }
    except Exception as e:
        print(f"[WARN] Exchange rate fetch failed: {e}", file=sys.stderr)

    return rates


def _fetch_single_index(symbol: str):
    """Fetch a single index from Yahoo Finance. Returns (name_or_region, result)."""
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

    display_name_info = name_map.get(symbol)
    if not display_name_info:
        return (symbol, None)

    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        r = requests.get(url, timeout=10, headers=HEADERS)
        data = r.json()

        result_data = data.get("chart", {}).get("result")
        if not result_data:
            return (display_name_info, None)

        meta = result_data[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        prev_close = meta.get("previousClose")

        if price is None or prev_close is None:
            return (display_name_info, None)

        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0

        parsed_result = {
            "price": round(price, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "prev_close": round(prev_close, 2),
            "symbol": symbol,
        }
        return (display_name_info, parsed_result)

    except Exception as e:
        print(f"[WARN] Yahoo fetch failed for {symbol}: {e}", file=sys.stderr)
        return (display_name_info, None)


def _parse_fetch_result(result, is_vn=False):
    """Parse a single fetch result into index_data format."""
    display_name_info, data = result

    if data is None:
        return None, display_name_info

    if is_vn:    # VN-Index (string name)
        return {
            "price": data["price"],
            "change": data["change"],
            "change_pct": data["change_pct"],
            "prev_close": data["prev_close"],
        }, display_name_info

    # Global index (tuple of (name, region))
    return {
        "price": data["price"],
        "change": data["change"],
        "change_pct": data["change_pct"],
        "region": display_name_info[1],
    }, display_name_info[0]


def fetch_market_indices():
    """Fetch VN + global market indices from Yahoo Finance in parallel.
    Returns dict with keys: 'VN-Index' and 'global': {name: {...}}."""
    vn_symbols = ["^VNINDEX.VN"]

    index_data = {}
    failures = []

    # Parallel fetch using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch_single_index, sym): sym for sym in vn_symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                result = future.result()
                parsed, name = _parse_fetch_result(result, is_vn=True)
                if parsed:
                    index_data[name] = parsed
                else:
                    failures.append(f"VN {name}")
            except Exception as e:
                print(f"[WARN] VN index fetch error for {symbol}: {e}", file=sys.stderr)
                failures.append(f"VN {symbol}")

    # Global indices — parallel fetch
    config = _get_config()
    global_syms = list(config.get("global_indices", {
        "^GSPC": {"name": "S&P 500", "region": "US"},
        "^DJI": {"name": "Dow Jones", "region": "US"},
        "^IXIC": {"name": "NASDAQ", "region": "US"},
        "^N225": {"name": "Nikkei 225", "region": "Asia"},
        "^HSI": {"name": "Hang Seng", "region": "Asia"},
        "^KS11": {"name": "KOSPI", "region": "Asia"},
        "^GDAXI": {"name": "DAX", "region": "Europe"},
        "^FTSE": {"name": "FTSE 100", "region": "Europe"},
    }).keys())

    global_data = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch_single_index, sym): sym for sym in global_syms}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                result = future.result()
                parsed, name = _parse_fetch_result(result, is_vn=False)
                if parsed:
                    global_data[name] = parsed
                else:
                    failures.append(f"Global {name}")
            except Exception as e:
                print(f"[WARN] Global index fetch error for {symbol}: {e}", file=sys.stderr)
                failures.append(f"Global {symbol}")

    index_data["global"] = global_data

    if failures:
        print(f"[WARN] Index fetch failed: {', '.join(failures)}", file=sys.stderr)

    return index_data
