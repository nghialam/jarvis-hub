"""
news_engine.py -- Enhanced news engine for Hub 2.0 News Hub.

Covers:
  - Article enrichment (sentiment, category, importance)
  - Save to DB
  - Trending detection
  - Multi-source RSS fetching
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import feedparser
import requests

# Lazy imports
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

# --- Expanded RSS sources for Hub 2.0 ---
RSS_SOURCES = [
    {"name": "Cafef Doanh nghiệp", "url": "https://cafef.vn/doanh-nghiep.rss", "category": "vn-stock", "priority": 1},
    {"name": "Cafef Thị trường", "url": "https://cafef.vn/thi-truong.rss", "category": "vn-market", "priority": 1},
    {"name": "VnExpress Kinh doanh", "url": "https://vnexpress.net/rss/kinh-doanh.rss", "category": "vn-business", "priority": 2},
    {"name": "VnExpress Kinh tế", "url": "https://vnexpress.net/rss/kinh-te.rss", "category": "vn-economy", "priority": 2},
    {"name": "VietnamNet Công nghệ", "url": "https://vietnamnet.vn/cong-nghe.rss", "category": "vn-tech", "priority": 3},
    {"name": "Vietstock", "url": "https://vietstock.com.vn/rss.htm", "category": "vn-market", "priority": 2},
    # Global sources
    {"name": "Reuters Business", "url": "https://feeds.reuters.com/reuters/businessNews", "category": "global-business", "priority": 2},
    {"name": "BBC Business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml", "category": "global-economy", "priority": 3},
]

# --- Heuristic sentiment patterns ---
BULLISH = ["tăng", "lãi", "khởi sắc", "bùng nổ", "vượt", "lợi nhuận", "doanh thu",
           "phục hồi", "mở rộng", "đầu tư", "tốt", "bứt phá", "tích lũy",
           "mua ròng", "đón sóng", "hứng thú", "năng lực", "đột phá"]

BEARISH = ["giảm", "rớt", "sụt giảm", "thất bại", "thua lỗ", "rủi ro", "suy giảm",
           "rơi tự do", "phá sản", "sụp đổ", "căng thẳng", "suy thoái", "sổ lỗ",
           "nợ", "bất ổn", "khủng hoảng", "đình chỉ", "bán tháo", "rút vốn",
           "áp lực giảm", "rơi sâu", "sập", "thắt chặt", "tăng nợ"]


def _heuristic_sentiment(text: str) -> tuple:
    """Layer 1: heuristic sentiment scoring from text.
    Returns: (sentiment_str, score_float)
    """
    text_lower = text.lower()
    bull = sum(1 for p in BULLISH if p in text_lower)
    bear = sum(1 for p in BEARISH if p in text_lower)
    score = bull - bear

    if score > 2:
        return ("tich_cuc", round(score / max(bull + bear, 1), 2))
    elif score < -2:
        return ("tieu_cuc", round(score / max(bull + bear, 1), 2))
    else:
        return ("trung_lap", round(score / max(bull + bear, 1), 2))


def _classify_category(title: str, summary: str) -> str:
    """Classify article into a category using keyword matching."""
    text = (title + " " + summary).lower()

    cat_keywords = {
        "banking": ["ngân hàng", "acb", "vpb", "vcb", "techcombank", "bidv", "agri", "vietcombank"],
        "real_estate": ["bất động sản", "batdongsan", "novaland", "vingroup", "gamuda", "kotena"],
        "tech": ["công nghệ", "technology", "fpt", "vrc", "gvr", "ttm", "mastera"],
        "energy": ["năng lượng", "electricity", "pvn", "pvcom", "petrolimex", "nhonTrinh"],
        "automotive": ["ô tô", "oto", "vinafarm", "thaco", "hoanghachina"],
        "fmcg": ["tiêu dùng", "vnm", "mct", "dhg", "sabeco", "hag", "masan"],
        "finance": ["chứng khoán", "stock", "ssi", "vci", "hcm", "scs", "tcbs"],
        "healthcare": ["dược", "healthcare", "pharmacy", "bid", "nhathuoc"],
        "macro": ["lãi suất", "tiền tệ", "ndv", "fed", "inflation", "gdp", "xuất nhập khẩu"],
    }

    for category, keywords in cat_keywords.items():
        for kw in keywords:
            if kw in text:
                return category

    return "general"


def extract_articles_from_feed(feed) -> list:
    """Extract articles from a feedparser result."""
    if feed.bozo and not feed.entries:
        return []

    articles = []
    for entry in feed.entries[:8]:
        link = entry.get("link", "") or entry.get("id", "")
        title = entry.get("title", "").strip()
        summary = entry.get("summary", "").strip()

        if not link or not title:
            continue

        # Parse publication time
        pub_dt = ""
        pub_parsed = entry.get("published_parsed")
        if pub_parsed:
            pub_dt = datetime(*pub_parsed[:6]).isoformat()

        articles.append({
            "title": title,
            "link": link,
            "summary_raw": re.sub(r"<[^>]+>", "", summary),
            "published_date": pub_dt,
        })

    return articles


def _fetch_source(source: dict) -> tuple:
    """Fetch a single RSS source. Returns (name, articles, error)."""
    try:
        r = requests.get(source["url"], timeout=10, headers=HEADERS)
        if r.status_code != 200:
            return (source["name"], [], "HTTP %d" % r.status_code)

        feed = feedparser.parse(r.text)
        articles = extract_articles_from_feed(feed)
        return (source["name"], articles, None)
    except Exception as e:
        return (source["name"], [], str(e))


def fetch_all_news(timeframe_hours=48) -> list:
    """Fetch all RSS sources in parallel.
    Returns: list of article dicts with enrichment.
    """
    config = _get_config()
    sources = RSS_SOURCES + config.get("feed", {}).get("sources", [])

    # Remove duplicates by URL
    seen_urls = set()
    unique_sources = []
    for src in sources:
        if src["url"] not in seen_urls:
            seen_urls.add(src["url"])
            unique_sources.append(src)

    all_articles = []
    failed_sources = []

    with ThreadPoolExecutor(max_workers=min(len(unique_sources), 5)) as executor:
        futures = {executor.submit(_fetch_source, src): src for src in unique_sources}
        for future in as_completed(futures):
            src = futures[future]
            try:
                name, articles, error = future.result()
                if error:
                    failed_sources.append(name)
                else:
                    for art in articles:
                        art["source"] = name
                        art["category"] = src.get("category", "general")
                        art["priority"] = src.get("priority", 2)
                        all_articles.append(art)
            except Exception as e:
                failed_sources.append(src["name"])

    # Deduplicate by title
    seen_titles = set()
    deduped = []
    for art in all_articles:
        key = art["title"][:60].strip().lower()
        if key not in seen_titles:
            seen_titles.add(key)
            deduped.append(art)

    # Enrich with sentiment + category
    for art in deduped:
        text = art.get("title", "") + " " + art.get("summary_raw", "")
        sentiment, score = _heuristic_sentiment(text)
        art["sentiment"] = sentiment
        art["sentiment_score"] = score
        art["category"] = _classify_category(art.get("title", ""), art.get("summary_raw", ""))

    return deduped


def save_news_to_db(articles: list, run_id: str = "default") -> int:
    """Save fetched articles to the enhanced news table.
    Returns count of saved articles.
    """
    if not articles:
        return 0

    db = _get_db()
    run_id = run_id or datetime.now().strftime("%Y-%m-%d")

    for art in articles:
        text = art.get("title", "") + " " + art.get("summary_raw", "")
        sentiment, score = _heuristic_sentiment(text)

        db.save_news_enhanced(
            title=art.get("title", ""),
            summary=art.get("summary_raw", "")[:500],
            content=None,
            url=art.get("link", ""),
            source=art.get("source", ""),
            published_at=art.get("published_date", datetime.now().isoformat()),
            category=art.get("category", "general"),
            sentiment=sentiment,
            sentiment_score=score,
            importance=0,  # LLM to fill this later
        )

    return len(articles)


def get_news_feed(category=None, sentiment=None, limit=30, timeframe_days=7):
    """Get news feed with filters. Used by API."""
    db = _get_db()
    return db.get_news_enhanced(
        category=category or "all",
        sentiment=sentiment or "all",
        limit=limit,
        timeframe_days=timeframe_days,
    )


def get_trending(limit=10):
    """Get trending news from DB."""
    db = _get_db()
    return db.get_trending_news(limit=limit)
