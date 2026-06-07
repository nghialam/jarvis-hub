"""
cache_manager.py -- Unified TTL-based cache for Jarvis Hub.

Replaces scattered _cache dict (app.py) and _symbol_cache (market.py).
All services (Market, News, Evaluation) now read via this single cache.

Features:
- Per-key TTL (configurable per data type)
- Automatic stale entry eviction on access
- Thread-safe access
- CacheStats for monitoring
"""
import threading
import time
from typing import Any, Optional


# Default TTLs by category (seconds)
DEFAULT_TTLS = {
    "market_data": 300,     # Stock/crypto prices: 5 min
    "fx_rates": 60,        # Exchange rates: 1 min
    "rss_feeds": 300,      # Articles/feed: 5 min
    "evaluations": 86400,   # Daily eval: 24h
    "technicals": 600,     # Technical indicators: 10 min
    "knowledge": 43200,     # KB entries: 12 hours
}


class CacheStats:
    """Track cache hit/miss ratio for monitoring."""
    def __init__(self):
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._lock = threading.Lock()

    @property
    def hits(self): return self._hits
    @property
    def misses(self): return self._misses
    @property
    def hit_ratio(self):
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def record_hit(self):
        with self._lock:
            self._hits += 1

    def record_miss(self):
        with self._lock:
            self._misses += 1

    def record_eviction(self):
        with self._lock:
            self._evictions += 1

    def summary(self):
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_ratio": round(self.hit_ratio * 100, 1),
            "evictions": self._evictions,
        }


class CacheManager:
    """Thread-safe cache with per-key TTL and stale eviction."""

    def __init__(self, default_ttls=None):
        self._store = {}             # key -> {"data": ..., "ts": float}
        self._ttl_map = dict(DEFAULT_TTLS)
        if default_ttls:
            self._ttl_map.update(default_ttls)
        self._lock = threading.Lock()
        self.stats = CacheStats()

    def set(self, key: str, data: Any, ttl: Optional[int] = None):
        """Store data with TTL in seconds."""
        if ttl is None:
            ttl = self._ttl_map.get(key, 300)
        ts = time.time()
        with self._lock:
            self._store[key] = {"data": data, "ts": ts}

    def get(self, key: str):
        """Retrieve data if fresh. Returns None on miss or expired."""
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                self.stats.record_miss()
                return None
            ttl = self._ttl_map.get(key, 300)
            if now - entry["ts"] >= ttl:
                # Expired
                del self._store[key]
                self.stats.record_eviction()
                self.stats.record_miss()
                return None
            self.stats.record_hit()
            return entry["data"]

    def keys(self):
        """Return non-expired keys."""
        with self._lock:
            now = time.time()
            expired = []
            valid_keys = []
            for k, v in self._store.items():
                ttl = self._ttl_map.get(k, 300)
                if now - v["ts"] >= ttl:
                    expired.append(k)
                else:
                    valid_keys.append(k)
            for k in expired:
                del self._store[k]
                self.stats.record_eviction()
            return valid_keys

    def size(self):
        """Return count of non-expired entries."""
        return len(self.keys())

    def clear_all(self):
        """Remove all entries (stale only)."""
        with self._lock:
            now = time.time()
            expired = []
            for k, v in self._store.items():
                ttl = self._ttl_map.get(k, 300)
                if now - v["ts"] >= ttl:
                    expired.append(k)
            for k in expired:
                del self._store[k]
                self.stats.record_eviction()

    def refresh_key(self, key: str):
        """Clear a specific entry to force next get() to reload."""
        with self._lock:
            if key in self._store:
                del self._store[key]
                self.stats.record_miss()

    def snapshot(self):
        """Return shallow copy of all non-expired data."""
        with self._lock:
            now = time.time()
            result = {}
            for k, v in list(self._store.items()):
                ttl = self._ttl_map.get(k, 300)
                if now - v["ts"] < ttl:
                    result[k] = v["data"]
            return result
