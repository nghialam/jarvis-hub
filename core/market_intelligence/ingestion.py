"""
ingestion.py — Stage 1: Ingestion

Fetch raw articles from RSS feeds and web scrapers for the last 6 hours.
Reuses patterns from news_engine.py and news_service.py.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from urllib.parse import urlparse
from urllib import request as urllib_request

import feedparser

log = logging.getLogger(__name__)

# RSS sources for Market Intelligence Agent
MARKET_INTELLIGENCE_SOURCES = [
    {"name": "Cafef Thị trường", "url": "https://cafef.vn/thi-truong.rss", "lang": "vi"},
    {"name": "Cafef Doanh nghiệp", "url": "https://cafef.vn/doanh-nghiep.rss", "lang": "vi"},
    {"name": "VnExpress Kinh doanh", "url": "https://vnexpress.net/rss/kinh-doanh.rss", "lang": "vi"},
    {"name": "VnExpress Kinh tế", "url": "https://vnexpress.net/rss/kinh-te.rss", "lang": "vi"},
    {"name": "VietnamNet Chứng khoán", "url": "https://vietnamnet.vn/vi/rss/chung-khoan.rss", "lang": "vi"},
    {"name": "Vietstock", "url": "https://vietstock.com.vn/rss.htm", "lang": "vi"},
    {"name": "Reuters Business", "url": "https://feeds.reuters.com/reuters/businessNews", "lang": "en"},
    {"name": "BBC Business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml", "lang": "en"},
    {"name": "Bloomberg Markets", "url": "https://feeds.bloomberg.com/markets/news.rss", "lang": "en"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def _fetch_source(source):
    """Fetch articles from a single RSS source."""
    url = source["url"]
    name = source["name"]
    lang = source.get("lang", "en")

    try:
        req = urllib_request.Request(url, headers=HEADERS)
        response = urllib_request.urlopen(req, timeout=15)
        raw_xml = response.read().decode("utf-8", errors="replace")

        feed = feedparser.parse(raw_xml)
        articles = []

        for entry in feed.entries:
            published = entry.get("published", entry.get("updated", ""))

            # Parse publication date
            pub_time = _parse_date(published)
            if pub_time is None:
                continue

            # Filter: only last 6 hours
            age_hours = (datetime.utcnow() - pub_time).total_seconds() / 3600
            if age_hours > 6:
                continue

            # Extract content
            content = entry.get("summary", "") or entry.get("description", "") or ""
            # Try to get full content from link if summary is short
            if len(content) < 100 and entry.get("link"):
                try:
                    full_req = urllib_request.Request(
                        entry["link"], headers=HEADERS
                    )
                    full_resp = urllib_request.urlopen(full_req, timeout=10)
                    full_html = full_resp.read().decode("utf-8", errors="replace")
                    content = _extract_text_from_html(full_html)
                except Exception:
                    pass  # Keep summary if full fetch fails

            articles.append({
                "title": entry.get("title", "").strip(),
                "date": published,
                "url": entry.get("link", ""),
                "content": content,
                "source": name,
                "lang": lang,
                "published_parsed": pub_time,
            })

        log.info(f"[MI][{name}] Fetched {len(articles)} articles from last 6h")
        return articles

    except Exception as e:
        log.warning(f"[MI][{name}] Fetch failed: {e}")
        return []


def _parse_date(date_str):
    """Parse RSS date string to datetime object."""
    if not date_str:
        return None

    # feedparser usually handles this, but try multiple formats
    try:
        return feedparser._parse_date(date_str).get("time_tuple") and \
            datetime(*feedparser._parse_date(date_str)["time_tuple"][:6])
    except Exception:
        pass

    # Try common formats
    for fmt in [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
    ]:
        try:
            dt = datetime.strptime(date_str.replace(" +0000", " UTC").replace(" -0000", " UTC"), fmt)
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except Exception:
            continue

    return None


def _extract_text_from_html(html):
    """Extract plain text from HTML, removing scripts/styles/nav."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Remove ads and sidebars
        for div in soup.find_all("div", class_=True):
            cls = div.get("class", [])
            if any(kw in " ".join(cls).lower() for kw in ["ad-", "sidebar", "banner", "nav"]):
                div.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Clean up whitespace
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)[:5000]  # Cap at 5000 chars
    except Exception:
        # Fallback: simple regex
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:5000]


def deduplicate(articles):
    """Deduplicate articles by URL and content similarity.

    First pass: exact URL match (keep first occurrence)
    Second pass: Jaccard similarity on title words > 0.8
    """
    if not articles:
        return []

    seen_urls = set()
    unique = []

    # First pass: URL dedup
    for art in articles:
        url = art.get("url", "").strip()
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(art)
        elif not url:
            unique.append(art)  # Keep articles without URL

    # Second pass: content similarity (optional, for articles from same source)
    final = []
    for i, art1 in enumerate(unique):
        is_dup = False
        for art2 in final:
            if art1["source"] != art2["source"]:
                continue
            sim = _jaccard_similarity(
                art1.get("title", "").lower().split(),
                art2.get("title", "").lower().split()
            )
            if sim > 0.8:
                is_dup = True
                break
        if not is_dup:
            final.append(art1)

    log.info(f"[MI] Deduplication: {len(articles)} → {len(final)} articles")
    return final


def _jaccard_similarity(set1, set2):
    """Calculate Jaccard similarity between two sets of words."""
    if not set1 or not set2:
        return 0.0
    intersection = set(set1) & set(set2)
    union = set(set1) | set(set2)
    return len(intersection) / len(union) if union else 0.0


def fetch_articles(hours_back=6):
    """Fetch articles from all RSS sources for the last N hours.

    Args:
        hours_back: Number of hours to look back (default 6)

    Returns:
        List of article dicts with keys: title, date, url, content, source, lang
    """
    log.info(f"[MI] Starting ingestion from {len(MARKET_INTELLIGENCE_SOURCES)} sources...")

    all_articles = []

    # Fetch in parallel
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch_source, src): src["name"] for src in MARKET_INTELLIGENCE_SOURCES}

        for future in as_completed(futures):
            source_name = futures[future]
            try:
                articles = future.result()
                all_articles.extend(articles)
            except Exception as e:
                log.warning(f"[MI][{source_name}] Pipeline error: {e}")

    # Deduplicate
    unique_articles = deduplicate(all_articles)

    # Sort by date (newest first)
    unique_articles.sort(
        key=lambda a: a.get("published_parsed") or datetime.min,
        reverse=True
    )

    log.info(f"[MI] Ingestion complete: {len(unique_articles)} unique articles")
    return unique_articles
