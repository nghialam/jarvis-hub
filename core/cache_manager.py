"""
cache_manager.py -- Unified TTL-based cache for Jarvis Hub with LRU eviction and tiered caching.

Replaces scattered _cache dict (app.py) and _symbol_cache (market.py).
All services (Market, News, Evaluation) now read via this single cache.

Features:
- Per-key TTL (configurable per data type)
- Automatic stale entry eviction on access
- Thread-safe access with ordered-list for O(1) LRU tracking
- CacheStats for monitoring
- Dynamic TTL by market hours (trading closed = longer TTLs)
- Tiered TTL system: hot keys (>50 accesses) get 4x longer TTL, cold keys expire faster

Hot key tiers:
- Cold (0-49 accesses): standard TTL from DEFAULT_TTLS_*
- Hot (50+ accesses): 4x the standard TTL
"""
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional


# Default TTLs by category (seconds) — shorter during trading hours, longer when closed
DEFAULT_TTLS_OPEN = {
    "market_data": 300,      # Stock/crypto prices: 5 min
    "fx_rates": 60,          # Exchange rates: 1 min
    "rss_feeds": 300,        # Articles/feed: 5 min
    "evaluations": 86400,    # Daily eval: 24h
    "technicals": 600,       # Technical indicators: 10 min
    "knowledge": 43200,      # KB entries: 12 hours
}

DEFAULT_TTLS_CLOSED = {k: v * 4 for k, v in DEFAULT_TTLS_OPEN.items()}


def is_market_open():
    """Check if VN market is open (09:00-15:30 SGT Mon-Fri)."""
    now = datetime.now(timezone(timedelta(hours=7)))  # GMT+7
    return now.weekday() < 5 and now.hour >= 9 and (now.hour < 15 or (now.hour == 15 and now.minute <= 30))


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
    """Thread-safe cache with per-key TTL, dynamic by market hours, and LRU hot-key support.

    Uses an ordered list (_access_order) with a reverse index for O(1) promotion on access.
    Hot keys (50+ hits) get 4x longer TTL. Eviction removes the least-recently-accessed entry.
    """

    def __init__(self, default_ttls=None):
        self._store = {}             # key -> {"data": ..., "ts": float}
        self._ttl_map = dict(DEFAULT_TTLS_OPEN)
        if default_ttls:
            self._ttl_map.update(default_ttls)
        self._lock = threading.RLock()
        # Hot-key tracking
        self._key_hit_counts = {}     # key -> hit count
        self._hot_keys_threshold = 50  # hits before key becomes "hot"
        self._hot_key_multiplier = 4    # hot keys multiply TTL by this factor
        # LRU ordering: ordered list + index for O(1) position lookup
        self._access_order = []        # insertion/access order (oldest first, newest last)
        self._order_index = {}         # key -> position in _access_order
        # Eviction log
        self._evicted_keys = []        # recent evictions (last 200)
        self.stats = CacheStats()

    def _get_effective_ttl(self, key: str) -> int:
        """Return effective TTL: hot keys get 4x base, cold keys use default based on market hours."""
        base_ttls = DEFAULT_TTLS_CLOSED if not is_market_open() else DEFAULT_TTLS_OPEN
        ttl = self._ttl_map.get(key, base_ttls.get(key, 300))
        # Hot-key boost
        if self._key_hit_counts.get(key, 0) >= self._hot_keys_threshold:
            ttl *= self._hot_key_multiplier
        return ttl

    def _evict_at_position(self, pos):
        """Evict entry at a specific O(1) position in access order. Internal - caller holds lock."""
        key = self._access_order[pos]
        del self._access_order[pos]
        # Update indices for all entries after pos
        for k in list(self._order_index.keys()):
            if self._order_index[k] > pos:
                self._order_index[k] -= 1
        del self._order_index[key]
        entry = self._store.pop(key, None)
        if entry:
            self.stats.record_eviction()
        # Shrink eviction log if needed
        if len(self._evicted_keys) > 200:
            self._evicted_keys = self._evicted_keys[-200:]
        return key

    def get(self, key: str):
        """Retrieve data if fresh. Returns None on miss or expired.

        On cache hit: promotes key to end of access order (MRU).
        """
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                self.stats.record_miss()
                return None
            ttl = self._get_effective_ttl(key)
            if now - entry["ts"] >= ttl:
                # Expired — hot keys also expire but with generous TTL
                pos = self._order_index.pop(key, None)
                if pos is not None:
                    self._evict_at_position(pos)
                self.stats.record_miss()
                return None
            # Promote to MRU end of access order
            pos = self._order_index.get(key)
            if pos is not None and pos != len(self._access_order) - 1:
                self._access_order.pop(pos)
                self._access_order.append(key)
                self._order_index[key] = len(self._access_order) - 1
            # Track hit for hot-key promotion
            self._key_hit_counts[key] = self._key_hit_counts.get(key, 0) + 1
            self.stats.record_hit()
            return entry["data"]

    def put(self, key: str, data):
        """Insert or update a cache entry. Evicts LRU if max size exceeded."""
        with self._lock:
            # If updating existing key, move to MRU end
            if key in self._order_index:
                pos = self._order_index.pop(key)
                self._access_order.pop(pos)
                for k in list(self._order_index.keys()):
                    if self._order_index[k] > pos:
                        self._order_index[k] -= 1

            # Evict LRU entries until under max size (default 1000)
            max_size = 1000
            while len(self._order_index) >= max_size:
                self._evict_at_position(0)

            entry = {"data": data, "ts": time.time()}
            self._store[key] = entry
            self._access_order.append(key)
            self._order_index[key] = len(self._access_order) - 1

    def keys(self):
        """Return non-expired keys."""
        with self._lock:
            now = time.time()
            expired_pos = []
            valid_keys = []
            for i, k in enumerate(self._access_order):
                ttl = self._get_effective_ttl(k)
                if now - self._store[k]["ts"] >= ttl:
                    expired_pos.append(i)
                else:
                    valid_keys.append(k)
            # Evict expired keys (reverse order to preserve indices)
            for pos in reversed(expired_pos):
                key = self._access_order.pop(pos)
                del self._order_index[key]
                self._store.pop(key, None)
                self.stats.record_eviction()
            return valid_keys

    def size(self):
        """Return count of non-expired entries."""
        return len(self.keys())

    def clear_all(self):
        """Remove all stale entries plus excess entries to prevent cache bloat.

        Evicts LRU (oldest access order) for excess entries beyond the capacity cap.
        """
        with self._lock:
            now = time.time()
            expired_pos = []
            keep_pos = []
            max_size = 500
            for i, k in enumerate(self._access_order):
                ttl = self._get_effective_ttl(k)
                if now - self._store[k]["ts"] >= ttl:
                    expired_pos.append(i)
                else:
                    keep_pos.append(i)

            # Also evict LRU entries if still too many entries
            if len(keep_pos) > max_size:
                excess = len(keep_pos) - max_size
                for i in range(excess):
                    expired_pos.append(keep_pos[i])  # first entries are LRU

            # Evict in reverse index order to maintain validity
            for pos in reversed(sorted(expired_pos)):
                key = self._access_order.pop(pos)
                del self._order_index[key]
                self._store.pop(key, None)
                self.stats.record_eviction()

    def refresh_key(self, key: str):
        """Clear a specific entry to force next get() to reload."""
        with self._lock:
            pos = self._order_index.pop(key, None)
            if pos is not None:
                self._access_order.pop(pos)
                for k in list(self._order_index.keys()):
                    if self._order_index[k] > pos:
                        self._order_index[k] -= 1
            self._store.pop(key, None)
            if key in self._key_hit_counts:
                del self._key_hit_counts[key]
            self.stats.record_miss()

    def snapshot(self):
        """Return shallow copy of all non-expired data."""
        with self._lock:
            now = time.time()
            result = {}
            for k in self._access_order:  # iterate via order list for consistency
                if k not in self._store:
                    continue  # already evicted
                ttl = self._get_effective_ttl(k)
                entry = self._store[k]
                if now - entry["ts"] < ttl:
                    result[k] = entry["data"]
            return result

    def hot_key_stats(self):
        """Return top 20 hit-frequent keys and their TTLs."""
        with self._lock:
            sorted_by_hits = sorted(
                [(k, c) for k, c in self._key_hit_counts.items()],
                key=lambda x: x[1], reverse=True
            )[:20]
            return [
                {"key": k, "hits": c, "effective_ttl": self._get_effective_ttl(k)}
                for k, c in sorted_by_hits
            ]

    def evict_key(self, key: str):
        """Force-evict a specific key (bypass TTL)."""
        with self._lock:
            pos = self._order_index.pop(key, None)
            if pos is not None:
                self._access_order.pop(pos)
                for k in list(self._order_index.keys()):
                    if self._order_index[k] > pos:
                        self._order_index[k] -= 1
            self._store.pop(key, None)
            self.stats.record_eviction()

    def get_evicted_keys(self):
        """Return list of recently evicted keys for debugging/monitoring."""
        with self._lock:
            return list(self._evicted_keys)
