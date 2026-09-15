"""
gateways/news_gateway.py - News Gateway (Phase 3.13)

JH3.0: RSS feed aggregation with heuristic enrichment.
Always works without LLM, LLM optional for classification/sentiment.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from core.config import load_config
from core.db import Database
from core.fallback_engine import score_news_heuristic

log = logging.getLogger(__name__)


class NewsGateway:
    """
    News gateway with RSS feeds and heuristic enrichment.
    
    Usage:
        gateway = NewsGateway(config, db)
        articles = gateway.fetch_articles(limit=50)
        trending = gateway.get_trending(hours=24)
    """
    
    def __init__(self, config=None, db=None):
        self.config = config or load_config()
        self.db = db or Database()
        self._cache = {}
        self._cache_ttl = 600  # 10 minutes for news
    
    def fetch_articles(self, limit: int = 50, use_llm: bool = False) -> List[Dict]:
        """
        Fetch news articles from all sources.
        
        Args:
            limit: Maximum number of articles
            use_llm: Whether to run LLM enrichment (async)
        
        Returns:
            List of article dicts with heuristic scoring
        """
        cache_key = f"articles:{limit}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        articles = []
        
        # Fetch from RSS feeds
        rss_articles = self._fetch_rss_feeds()
        if rss_articles:
            articles.extend(rss_articles)
        
        # Fetch from CafeF
        cafe_articles = self._fetch_cafef()
        if cafe_articles:
            articles.extend(cafe_articles)
        
        # Fetch from database (already stored)
        db_articles = self._fetch_db_articles(limit=limit)
        articles.extend(db_articles)
        
        # Apply heuristic scoring (always runs)
        for article in articles[:limit]:
            article["score"] = score_news_heuristic(article)
            article["source"] = article.get("source", "unknown")
            if "scored" not in article:
                article["scored"] = datetime.utcnow().isoformat()
        
        # Sort by score desc
        articles.sort(key=lambda a: a.get("score", 0), reverse=True)
        articles = articles[:limit]
        
        # Cache result
        self._cache_result(cache_key, articles)
        
        # If LLM enabled, queue async enrichment
        if use_llm:
            self._queue_llm_enrichment(articles[:10])  # Top 10 only
        
        return articles
    
    def get_trending(self, hours: int = 24, limit: int = 10) -> List[Dict]:
        """
        Get trending articles from the last N hours.
        
        Args:
            hours: Time window for trending
            limit: Maximum number of trending articles
        """
        cache_key = f"trending:{hours}:{limit}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        articles = self.fetch_articles(limit=limit * 3)  # Fetch extra for filtering
        
        # Filter by recency and boost score
        trending = []
        for article in articles:
            article_time = article.get("published_at") or article.get("created_at")
            if article_time:
                try:
                    pub_time = datetime.fromisoformat(article_time.replace("Z", "+00:00").replace("+00:00", ""))
                    if pub_time >= cutoff:
                        # Boost score for recency
                        age_hours = (datetime.utcnow() - pub_time).total_seconds() / 3600
                        recency_boost = max(0, 10 - age_hours)
                        article["trending_score"] = article.get("score", 0) + recency_boost
                        trending.append(article)
                except (ValueError, TypeError):
                    continue
        
        trending.sort(key=lambda a: a.get("trending_score", 0), reverse=True)
        trending = trending[:limit]
        
        self._cache_result(cache_key, trending)
        return trending
    
    def get_categories(self) -> List[str]:
        """
        Get list of news categories.
        """
        cache_key = "categories"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        # Extract categories from articles
        articles = self.fetch_articles(limit=100)
        categories = set()
        for article in articles:
            cat = article.get("category") or article.get("tags", [None])[0]
            if cat:
                categories.add(cat)
        
        result = sorted(list(categories))
        if not result:
            result = ["Market", "Economy", "Policy", "Company", "Technology", "General"]
        
        self._cache_result(cache_key, result)
        return result
    
    def search_articles(self, query: str, limit: int = 20) -> List[Dict]:
        """
        Search articles by keyword.
        
        Args:
            query: Search keyword
            limit: Maximum results
        """
        articles = self.fetch_articles(limit=limit * 2)
        
        # Simple keyword search
        query_lower = query.lower()
        results = []
        for article in articles:
            title = (article.get("title") or "").lower()
            content = (article.get("content") or "").lower()
            if query_lower in title or query_lower in content:
                article["relevance"] = (title.count(query_lower) * 2 + content.count(query_lower))
                results.append(article)
        
        results.sort(key=lambda a: a.get("relevance", 0), reverse=True)
        return results[:limit]
    
    def get_latest_briefing(self) -> Optional[Dict]:
        """
        Get the latest market briefing.
        """
        cache_key = "latest_briefing"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        try:
            conn = self.db.get_connection()
            row = conn.execute(
                "SELECT run_id, created_at, data FROM daily_briefings ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            
            if row:
                result = {
                    "run_id": row[0],
                    "created_at": row[1],
                    "data": json.loads(row[2]) if row[2] else {}
                }
                self._cache_result(cache_key, result)
                return result
        except Exception as e:
            log.error("Failed to get latest briefing: %s", e)
        
        return None
    
    # --- Private fetch methods ---
    
    def _fetch_rss_feeds(self) -> List[Dict]:
        """Fetch articles from RSS feeds."""
        articles = []
        try:
            import feedparser
            
            feeds = [
                "https://cafef.vn/ratings.rss",
                "https://cafef.vn/price-chart.rss",
                "https://vnexpress.net/rss/kinh-doanh.rss",
            ]
            
            for feed_url in feeds:
                try:
                    feed = feedparser.parse(feed_url)
                    for entry in feed.entries[:10]:
                        articles.append({
                            "title": entry.get("title", ""),
                            "link": entry.get("link", ""),
                            "summary": entry.get("summary", ""),
                            "published_at": entry.get("published", ""),
                            "source": "rss",
                            "feed_url": feed_url,
                        })
                except Exception as e:
                    log.warning("RSS feed failed: %s - %s", feed_url, e)
        except ImportError:
            log.debug("feedparser not available")
        
        return articles
    
    def _fetch_cafef(self) -> List[Dict]:
        """Fetch articles from CafeF."""
        articles = []
        try:
            import requests
            url = "https://cafef.vn/moi-trang.rss"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                feed = feedparser.parse(resp.text)
                for entry in feed.entries[:15]:
                    articles.append({
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                        "summary": entry.get("summary", ""),
                        "published_at": entry.get("published", ""),
                        "source": "cafef",
                    })
        except ImportError:
            log.debug("feedparser not available for CafeF")
        except Exception as e:
            log.error("CafeF fetch failed: %s", e)
        
        return articles
    
    def _fetch_db_articles(self, limit: int = 50) -> List[Dict]:
        """Fetch articles from database."""
        try:
            conn = self.db.get_connection()
            rows = conn.execute(
                "SELECT id, title, content, source, created_at, category FROM articles ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            
            return [
                {
                    "id": row[0],
                    "title": row[1],
                    "content": row[2],
                    "source": row[3],
                    "created_at": row[4],
                    "category": row[5],
                }
                for row in rows
            ]
        except Exception as e:
            log.error("DB articles fetch failed: %s", e)
            return []
    
    def _queue_llm_enrichment(self, articles: List[Dict]):
        """Queue LLM enrichment for top articles."""
        try:
            from core.async_queue import get_async_queue
            queue = get_async_queue()
            
            for article in articles[:5]:  # Top 5 only
                queue.submit("enrich_article", {
                    "title": article.get("title", ""),
                    "summary": article.get("summary", ""),
                })
            
            log.info("Queued %d LLM enrichment tasks", min(len(articles), 5))
        except Exception as e:
            log.error("Failed to queue LLM enrichment: %s", e)
    
    # --- Cache utilities ---
    
    def _get_from_cache(self, key: str) -> Optional[Dict]:
        """Get cached data if still fresh."""
        if key in self._cache:
            cached_time, value = self._cache[key]
            if time.time() - cached_time < self._cache_ttl:
                return value
            del self._cache[key]
        return None
    
    def _cache_result(self, key: str, value):
        """Cache a result with timestamp."""
        self._cache[key] = (time.time(), value)
    
    def clear_cache(self):
        """Clear all cached data."""
        self._cache.clear()
