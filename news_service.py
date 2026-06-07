#!/usr/bin/env python3
"""
news_service.py - AI News Feed & Intelligence Engine for Jarvis Hub.

Fetches RSS feeds, scores/analyzes with LLM, returns structured intelligence feed
with SOURCE ATTRIBUTION for every claim.
"""

import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

LLM_URL = "http://localhost:11434"

FEED_SOURCES = {
    "reuters_mw": "https://feeds.feedburner.com/MarketWatchTopStories",
    "bbc_business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "cafef": "https://cafef.vn/rap109/default.rss",
    "vnexpress": "https://vnexpress.net/rss/kinh-doanh.rss",
    "ttoit_general": "https://www.tuoitre.vn/rss/international.rss",
    "techcrunch": "https://techcrunch.com/feed/",
    "ai_news": "https://www.artificialintelligence-news.com/feed/",
}

CATEGORY_KEYWORDS = {
    "AI breakthroughs": [
        "gpt", "claude", "llama", "grok", "reasoning", "agent", "agentic",
        "o1", "o3", "gemini", "deepmind", "anthropic", "openai", "chatgpt",
        "multimodal", "transformer", "mixture of experts", "moE"
    ],
    "AI regulation": [
        "executive order", "regulation", "policy", "bill", "legislation",
        "ethics", "encyclical", "governance", "safety", "banned", "ban",
        "moratorium", "eu ai act", "artificial intelligence act"
    ],
    "AI companies & startups": [
        "startup", "funding", "valuation", "ipo", "merger", "acquisition",
        "perplexity", "cohere", "elevenlabs", "midjourney", "stability ai",
        "databricks"
    ],
    "AI hardware": [
        "chip", "gpu", "nvidia", "tpu", "quantum", "silicon", "data center",
        "server", "infrastructure", "compute", "ram", "memory", "semiconductor"
    ],
    "Energy & Climate AI": [
        "energy", "grid", "solar", "nuclear", "renewable", "climate",
        "carbon", "electricity", "power", "fuel", "gas", "oil price"
    ],
    "AI Applications": [
        "healthcare", "finance", "coding", "robotics", "autonomous", "f1",
        "cooking", "agriculture", "education", "law", "defense", "aerospace"
    ],
    "General Tech": [
        "apple", "google", "meta", "microsoft", "amazon", "tesla", "spacex",
        "browser", "os", "security", "hack", "cyber", "spyware", "app store",
        "iphone", "android"
    ],
    "Sports & Culture": [
        "sport", "football", "soccer", "tennis", "olympics", "gold medal",
        "tournament", "championship", "world cup", "music", "festival",
        "game", "entertain", "concert", "artist", "exhibit"
    ],
    "Politics": [
        "politic", "election", "government", "parliament", "senate",
        "minister", "president", "policy", "diplomacy", "tariff",
        "sanction", "bilateral", "multilateral", "congress", "prime minister"
    ],
    "Entertainment": [
        "film", "movie", "music", "song", "album", "celebrity",
        "showbiz", "awards", "oscar", "grammy", "netflix", "discovery",
        "streaming", "theater", "award show", "premiere", "box office"
    ],
    "Finance": [
        "stock", "share", "market", "trading", "index", "price", "value",
        "revenue", "profit", "earnings", "dividend", "bond", "equity",
        "valuation", "bank", "loan", "credit", "interest rate", "inflation",
        "forex", "currency", "exchange", "fund", "portfolio", "wealth",
        "investment", "bonds", "futures",
        # Vietnamese keywords (normalized via VIET_NORM before matching)
        "gia vang", "dau thoa", "co phieu", "thi truong",
        "tang truong", "ngan hang", "lien ket", "sap xep",
    ],
    "Economy": [
        "economy", "economic", "growth", "gdp", "inflation", "deflation",
        "employment", "unemployment", "trade", "imports", "exports",
        "manufacturing", "retail", "consumer spending", "fiscal policy",
        # Vietnamese keywords (normalized via VIET_NORM before matching)
        "kinh te", "dao tao", "cong nghiep", "nhiem vu", "chinh sach",
        "phat trien", "doanh nghiep", "doanh thu", "gia ca",
        "xuat nhap khau", "luong tam",
    ],
}

# Vietnamese diacritics to ASCII mapping - comprehensive set for keyword matching
VIET_NORM = {
     # a variants (with acute, grave, hook, tilde, dot-below)
     '\u00e0': 'a', '\u00e1': 'a', '\u1ea3': 'a', '\u00e3': 'a', '\u1ea1': 'a',
     # a with breve variants
     '\u0103': 'a', '\u1ebd': 'a', '\u1ea5': 'a', '\u1ebb': 'a', '\u1ebf': 'a', '\u1ea7': 'a',
     # a with circumflex variants
     '\u00e2': 'a', '\u1ea9': 'a', '\u1ead': 'a', '\u1eab': 'a',
    "\u0111": "d",
    "\u00e8": "e", "\u00e9": "e", "\u1ecb": "e", "\u00eb": "e",
    "\u00ea": "e", "\u1ec1": "e", "\u1ec3": "e", "\u1ec5": "e", "\u1ec7": "e", "\u1ec9": "e",
    "\u00ed": "i", "\u00ec": "i", "\u2089": "i",
    "\u00f2": "o", "\u00f3": "o", "\u00f4": "o", "\u00f5": "o",
    "\u1ed1": "o", "\u1ed3": "o", "\u1ed5": "o", "\u1ed7": "o", "\u1ed9": "o",
    "\u01a1": "o", "\u1edd": "o", "\u1edf": "o", "\u1ee1": "o", "\u1eee": "o", "\u1ef2": "o",
    "\u00f9": "u", "\u00fa": "u", "\u1eed": "u", "\u1ef1": "u", "\u00fb": "u",
    "\u01b0": "u", "\u1ee9": "u", "\u1eeb": "u", "\u1ef3": "u", "\u1eef": "u", "\u1ee7": "u",
    "\u00fd": "y", "\u1ecf": "y",
}


def normalize_vi(text):
     """Normalize Vietnamese diacritics to ASCII for keyword matching."""
    return "".join(VIET_NORM.get(ch, ch) for ch in text.lower())


# --------------------------------------------------------------------------- #
# RSS fetching with source attribution tracking
# --------------------------------------------------------------------------- #

def fetch_feed(url, timeout=10):
    """Fetch RSS feed XML and return root element. Returns None on failure."""
    headers = {"User-Agent": "JarvisHub/1.0 (Intelligence Feed)"}
    req = Request(url, headers=headers)
    try:
        resp = urlopen(req, timeout=timeout)
        xml_bytes = resp.read()
        return ET.fromstring(xml_bytes.decode("utf-8", errors="replace"))
    except (URLError, HTTPError, ET.ParseError):
        return None


def extract_articles(feed_root, source_name):
    """Extract articles from RSS feed, preserving source attribution."""
    articles = []
    if feed_root is None:
        return articles
    for item in feed_root.findall(".//item"):
        title_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description")
        date_el = item.find("pubDate")
        title = title_el.text if title_el is not None else ""
        link = link_el.text if link_el is not None else ""
        description = desc_el.text if desc_el is not None else ""
        description = re.sub(r"<[^>]+>", "", description).strip()
        pub_date = date_el.text if date_el is not None else ""

        try:
            pub_dt = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %Z")
        except (ValueError, TypeError):
            try:
                pub_dt = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S +0000")
            except (ValueError, TypeError):
                pub_dt = None

        articles.append({
            "source": source_name,
            "title": title.strip() if title else "",
            "link": link.strip() if link else "",
            "description": description[:500] if description else "",
            "pub_date": pub_dt.isoformat() if pub_dt else pub_date,
        })
    return articles


def fetch_all_feeds():
    """Fetch all RSS feeds and combine with source attribution tracking."""
    all_articles = []
    sources_working = 0
    sources_failed = 0

    for source, url in FEED_SOURCES.items():
        feed = fetch_feed(url)
        if feed is not None:
            articles = extract_articles(feed, source)
            if articles:
                sources_working += 1
            else:
                sources_failed += 1
        else:
            sources_failed += 1
        all_articles.extend(articles)

    valid = [a for a in all_articles if a["pub_date"]]
    invalid = [a for a in all_articles if not a["pub_date"]]
    valid.sort(key=lambda x: x["pub_date"] or "", reverse=True)

    return {
        "articles": valid + invalid,
        "sources_working": sources_working,
        "sources_failed": sources_failed,
    }


def get_source_name(slug):
    """Return display name for source slug."""
    names = {
        "reuters_mw": "Reuters/MarketWatch",
        "bbc_business": "BBC Business",
        "cafef": "CafeF",
        "vnexpress": "VnExpress",
        "ttoit_general": "TuoiTre International",
        "techcrunch": "TechCrunch",
        "ai_news": "AI News",
    }
    return names.get(slug, slug)


def classify_article(article):
    """Classify article into categories based on keywords.

    Uses Vietnamese diacritic normalization so that articles with tone marks
     (e.g., 'gia vang') match ASCII keywords ('gia vang').
    """
    raw_text = article["title"] + " " + article["description"]
    text = normalize_vi(raw_text).lower()

    matched = []
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                matched.append(cat)
                break
    return matched if matched else ["Uncategorized"]


# --------------------------------------------------------------------------- #
# LLM ANALYSIS with SOURCE ATTRIBUTION and separate sport/culture section
# --------------------------------------------------------------------------- #

def requests_post(url, payload, timeout=120):
    """POST JSON to Ollama API with retry and error handling."""
    import requests as req
    try:
        r = req.post(
            url, json=payload, timeout=timeout,
            headers={"Content-Type": "application/json"}
        )
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def analyze_with_llm(articles, model="qwen3.6:35b-a3b-mxfp8"):
    """Use Ollama to analyze articles with SOURCE ATTRIBUTION in output.

    Each claim/reasoning must cite its source so humans can double-check.
    Sports & Culture are separated into a distinct delivery section.
    """
    categorized = {}
    uncategorized = []

    for a in articles[:60]:
        cats = classify_article(a)
        for cat in cats:
            categorized.setdefault(cat, []).append(a)
        if len(cats) == 1 and cats[0] == "Uncategorized":
            uncategorized.append(a)

    summary_tasks = []

    # AI/Tech analysis - always included
    ai_cats = [k for k in list(categorized.keys()) if "AI" in k or k == "General Tech"]
    ai_articles = []
    for cat in ai_cats:
        ai_articles.extend(categorized.pop(cat, []))
    if ai_articles:
        summary_tasks.append((
            "AI & Tech Analysis",
            ai_articles[:30],
            (
                "Phan tich tin tuc AI/Tech hang dau. Tom tat su kien chinh, "
                "nhan dinh xu huong, de xuat hanh dong chien luoc.\n"
                "QUAN TRONG: Voi moi thong tin hoac nhan dinh, PHAI ghi ro nguon "
                "(VD: Theo Reuters/BBC/CafeF/VnExpress/TuoiTre)."
            )
        ))

    # Sports & Culture - SEPARATE section (delivered as distinct message)
    sport_articles = categorized.pop("Sports & Culture", [])
    entertainment_articles = categorized.pop("Entertainment", [])

    both_cat = sport_articles + entertainment_articles
    if both_cat:
        summary_tasks.append((
            "Van Hoa - The Thao - Giai Tri",
            both_cat[:12],
            (
                "Tong hop tin tuc van hoa, the thao, giai tri gan nhat. "
                "Moi tin ghi ro nguon o cuoi [Nguon: ...]."
            )
        ))

    # Economy/Finance + Politics - merged category (everything else)
    for cat in list(categorized.keys()):
        if cat not in ("Sports & Culture", "Entertainment"):
            categorized[cat] = categorized.pop(cat, [])

    result_tasks = []
    system_prompt = (
        "Ban la Jarvis - tro ly AI thong thai phan tich tin tu va dua ra nhan dinh chien luoc.\n"
        "Viet tieng Viet, phong cach sac sao, tap trung vao hanh dong.\n"
        "Dung markdown. PHAI ghi ro nguon cho moi thong tin/nhan dinh."
    )

    for task_name, task_articles, instructions in summary_tasks:
        context_text = ""
        for i, art in enumerate(task_articles):
            pub = art["pub_date"][:16] if art["pub_date"] else "unknown"
            category = classify_article(art)[0]
            source_name = get_source_name(art["source"])
            context_text += (
                f"[{i+1}] ({category}) [{source_name}] [{pub}]\n"
                f"    Title: {art['title']}\n"
                f"    Summary: {art['description'][:200]}\n\n"
            )

        prompt = (
            f"[SECTION]\n{task_name}\n\n"
            f"[ARTICLES]\n{context_text}"
            f"[INSTRUCTIONS]\n{instructions}"
        )

        task_payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 2048}
        }

        try:
            resp = requests_post(f"{LLM_URL}/api/chat", task_payload)
            if resp and resp.get("message", {}).get("content"):
                result_tasks.append({
                    "section": task_name,
                    "analysis": resp["message"]["content"],
                    "source_count": len(set(a["source"] for a in task_articles)),
                })
            else:
                result_tasks.append({
                    "section": task_name,
                    "analysis": "[LLM returned empty response]"
                })
        except Exception as e:
            result_tasks.append({
                "section": task_name,
                "analysis": f"[ERROR: {str(e)}]"
            })

    return {
        "tasks": result_tasks,
        "fetch_time": datetime.utcnow().isoformat(),
        "total_articles": len(articles),
    }


# --------------------------------------------------------------------------- #
# ENTRY POINTS
# --------------------------------------------------------------------------- #

def get_ai_feed(limit=60):
    """Fetch and analyze all feeds - main entry point for the feed API."""
    fetched = fetch_all_feeds()
    articles = fetched["articles"]

    if not articles:
        return {
            "error": "Could not fetch any feeds",
            "articles": [],
            "analysis": [],
            "sources_working": 0,
            "sources_failed": len(FEED_SOURCES),
            "fetch_time": datetime.utcnow().isoformat(),
        }

    raw_articles = []
    for a in articles[:limit]:
        raw_articles.append({
            "source": get_source_name(a["source"]),
            "source_slug": a["source"],
            "title": a["title"],
            "link": a["link"],
            "date": a["pub_date"][:16] if a["pub_date"] else "",
            "categories": classify_article(a),
        })

    try:
        analysis = analyze_with_llm(articles)
    except Exception as e:
        analysis = {"error": str(e), "tasks": []}

    return {
        "status": "ok",
        "total_sources": len(FEED_SOURCES),
        "sources_working": fetched["sources_working"],
        "sources_failed": fetched["sources_failed"],
        "total_articles": len(articles),
        "fetch_time": datetime.utcnow().isoformat(),
        "analysis": analysis,
        "articles": raw_articles,
    }


def generate_full_briefing():
    """Get full AI intelligence feed and return formatted briefing text."""
    feed_data = get_ai_feed(limit=60)
    if feed_data.get("error"):
        return f"Warning: Jarvis Intelligence Feed Error: {feed_data['error']}"

    tasks = feed_data.get("analysis", {}).get("tasks", [])
    sections_text = []
    for t in tasks:
        sections_text.append(f"\n{t['section']}\n\n{t['analysis']}")

    return (
        "Jarvis Intelligence Feed - "
        + datetime.utcnow().strftime("%A, %B %d, %Y") + "\n"
        + f"{feed_data['total_articles']} articles from "
        + f"{feed_data.get('sources_working', '?')}/{feed_data['total_sources']} sources\n"
        + "\n".join(sections_text)
    )


def get_fast_feed(limit=30):
    """Quick feed without LLM - just aggregated RSS with classification."""
    fetched = fetch_all_feeds()
    articles = fetched["articles"]
    if not articles:
        return {"status": "error", "articles": [], "message": "Feeds unavailable"}

    enriched = []
    for a in articles[:limit]:
        cats = classify_article(a)
        entry = {
            "source": get_source_name(a["source"]),
            "source_slug": a["source"],
            "title": a["title"],
            "link": a["link"],
            "date": a["pub_date"][:16] if a["pub_date"] else "",
            "categories": cats,
            "description": a["description"][:200],
        }
        enriched.append(entry)

    return {
        "status": "ok",
        "total_sources": len(FEED_SOURCES),
        "sources_working": fetched["sources_working"],
        "sources_failed": fetched["sources_failed"],
        "total_articles": len(articles),
        "articles": enriched,
    }
