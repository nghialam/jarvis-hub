"""
llm_cache.py -- Thread-safe, TTL-based cache for LLM (Ollama) responses with LRU eviction and hot-key detection.

Prevents redundant API calls when the same prompt/hash is requested multiple times
within a short window (default 300s / 5 min). Used by:
- app.py /api/analyze endpoint (stock/crypto analyze reports)
- core/news.py llm_sentiment (article sentiment analysis)
- core/market.py llm_due_diligence

Circuit breaker pattern integrated to prevent hammering a failing Ollama instance.
Hot-key detection: keys accessed 50+ times get extended TTL (1200s vs 300s).
LRU eviction: when cache exceeds max_size, least-recently-accessed entry is removed.

Usage:
    cache = LLMResponseCache(ttl=300, circuit_threshold=3)
    result = cache.get_or_call(prompt_hash, lambda: ollama_call(prompt))
"""
import hashlib
import threading
import time
from typing import Any, Callable, Optional


# Sentinel object to distinguish cached None from actual miss
_SENTINEL = object()

# Hot key threshold — number of hits before a key enters the "hot tier" with longer TTL
_HOT_KEY_THRESHOLD = 50

# Hot tier TTL (seconds) vs default tier TTL
_HOT_TTL = 1200


class CircuitBreaker:
    """Simple circuit breaker for external API calls.

    States:
        CLOSED   - Normal operation, requests pass through
        OPEN     - Too many failures, reject all requests immediately
        HALF_OPEN - After recovery window, allow one test request through
    """

    def __init__(self, failure_threshold=3, recovery_window=60):
        self._failure_threshold = failure_threshold
        self._recovery_window = recovery_window
        self._state = "closed"
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()

    @property
    def state(self):
        with self._lock:
            if self._state == "open":
                if time.time() - self._last_failure_time >= self._recovery_window:
                    self._state = "half_open"
            return self._state

    def record_success(self):
        """Record a successful call — closes the circuit."""
        with self._lock:
            self._failure_count = 0
            self._state = "closed"

    def record_failure(self):
        """Record a failed call — opens circuit if threshold exceeded."""
        with self._lock:
            self._last_failure_time = time.time()
            if self._state == "half_open":
                self._state = "open"
            else:
                self._failure_count += 1
                if self._failure_count >= self._failure_threshold:
                    self._state = "open"

    def allow_request(self):
        """Check if a request should be allowed through."""
        return self.state != "open"

    @property
    def is_open(self):
        return self.state == "open"


class LLMResponseCache:
    """Thread-safe, TTL-based cache for LLM responses with circuit breaker.

    Key features:
    - Ordered dict (via _order list) for O(1) LRU eviction
    - Hot-key detection: top hit-frequent keys get extended TTL (1200s vs 300s)
    - Tracks evicted keys for debugging/monitoring
    - Circuit breaker to prevent hammering a broken Ollama instance
    """

    def __init__(self, ttl=300, max_size=500, circuit_threshold=3, recovery_window=60):
        self._cache = {}                           # key -> {"value": ..., "ts": float, "hits": int}
        self._order = []                            # insertion/access order for LRU tracking
        self._lock = threading.RLock()
        self._max_size = max_size
        self._base_ttl = ttl                        # default (cold) TTL
        self._hot_ttl = _HOT_TTL                    # hot tier TTL
        self._hot_threshold = _HOT_KEY_THRESHOLD    # hit count to become "hot"
        self._order_index = {}                      # key -> position in _order for O(1) access
        self._evicted_keys = []                     # recent evictions (last 200)
        self._breaker = CircuitBreaker(
            failure_threshold=circuit_threshold,
            recovery_window=recovery_window,
        )

    @staticmethod
    def hash_prompt(prompt):
        """Create a short SHA-256 hash of the prompt for caching key."""
        return hashlib.sha256(prompt.encode()).hexdigest()[:16]

    def _is_hot_key(self, key: str) -> bool:
        """Check if a key qualifies for the hot tier."""
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return False
            return entry["hits"] >= self._hot_threshold

    def _get_effective_ttl(self, key: str) -> int:
        """Return TTL for the key — longer for hot keys."""
        if self._is_hot_key(key):
            return self._hot_ttl
        return self._base_ttl

    # pylint: disable=unnecessary-pass
    def _get_cache_entry(self, key):
        """Get cached entry if it exists and is fresh. Returns None on miss/expiry.

        On hit: moves the key to the end of _order (MRU) and increments hit counter.
        """
        with self._lock:
            if key not in self._cache:
                return None
            entry = self._cache[key]
            effective_ttl = self._get_effective_ttl(key)
            if time.time() - entry["ts"] < effective_ttl:
                # Move to end of order list (most recently used)
                pos = self._order_index.get(key)
                if pos is not None and pos != len(self._order) - 1:
                    self._order.pop(pos)
                    self._order.append(key)
                    self._order_index[key] = len(self._order) - 1
                entry["hits"] += 1
                return entry
        # If we got here, the entry is expired
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                pos = self._order_index.pop(key, None)
                if pos is not None:
                    # Shift all indices after the removed position
                    for k in list(self._order_index.keys()):
                        if self._order_index[k] > pos:
                            self._order_index[k] -= 1
                    self._order.pop(pos)
        return None

    def _store(self, key, value):
        """Thread-safe helper to store in cache with LRU eviction."""
        evicted = []
        with self._lock:
            # If key already exists, update it (move to MRU end)
            if key in self._order_index:
                pos = self._order_index.pop(key)
                self._order.pop(pos)
                for k in list(self._order_index.keys()):
                    if self._order_index[k] > pos:
                        self._order_index[k] -= 1
            else:
                # Check if we need to evict LRU entries first
                while len(self._order_index) >= (self._max_size or float('inf')):
                    lru_key = self._order.pop(0)
                    self._order_index.pop(lru_key, None)
                    removed_val = self._cache.pop(lru_key, None)
                    if removed_val is not None:
                        evicted.append(lru_key)

            entry = {
                "value": value,
                "ts": time.time(),
                "hits": 1,
                "ttl": self._base_ttl,
            }
            self._cache[key] = entry
            self._order.append(key)
            self._order_index[key] = len(self._order) - 1

        # Record evictions outside the lock to reduce hold time
        if evicted:
            with self._lock:
                self._evicted_keys.extend(evicted)
                # Keep only last N evicted keys for debugging
                keep = min(len(self._evicted_keys), 200)
                if len(self._evicted_keys) > keep:
                    self._evicted_keys = self._evicted_keys[-keep:]

    def get_or_call(self, prompt, call_func):
        """Get cached result if available and fresh, otherwise call the function.

        Circuit breaker is checked BEFORE API calls. If tripped, returns None
        immediately to prevent hammering a broken service.

        Args:
            prompt: The text to hash as cache key.
            call_func: Function to call on cache miss (returns LLM result).

        Returns:
            Cached or newly computed result, or None on miss/failure/circuit open.
        """
        # Always check circuit breaker first
        self._breaker.allow_request()
        if self._breaker.is_open:
            return None

        key = self.hash_prompt(prompt)

        # Check cache
        entry = self._get_cache_entry(key)
        if entry is not None:
            return entry["value"]

        # Cache MISS — check circuit breaker again before API call
        if not self._breaker.allow_request():
            return None

        try:
            value = call_func(prompt)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print("[LLM CACHE] Call exception: %s", exc)
            self._breaker.record_failure()
            return None

        if value is not _SENTINEL:
            self._breaker.record_success()
            self._store(key, value)

        return value if value is not _SENTINEL else None

    def clear_expired(self):
        """Remove expired entries from cache. Returns count removed."""
        now = time.time()
        evicted = []
        with self._lock:
            expired_keys = [
                k for k, v in self._cache.items()
                if now - v["ts"] >= self._get_effective_ttl(k)
            ]
            for k in expired_keys:
                del self._cache[k]
                pos = self._order_index.pop(k, None)
                if pos is not None:
                    # Shift indices after removed position
                    for key in list(self._order_index.keys()):
                        if self._order_index[key] > pos:
                            self._order_index[key] -= 1
                    self._order.pop(pos)
            evicted.extend(expired_keys)

        if evicted:
            with self._lock:
                self._evicted_keys.extend(evicted[:50])
                if len(self._evicted_keys) > 200:
                    self._evicted_keys = self._evicted_keys[-200:]
        return len(evicted)

    def get_stats(self):
        """Return cache statistics (size, hit rate, hot keys, evictions)."""
        with self._lock:
            now = time.time()
            active_entries = {}
            expired_count = 0
            hot_keys = []
            for k, v in self._cache.items():
                ttl = self._get_effective_ttl(k)
                if now - v["ts"] < ttl:
                    active_entries[k] = v
                    if v["hits"] >= self._hot_threshold:
                        hot_keys.append({"key": k, "hits": v["hits"], "ttl": ttl})
                else:
                    expired_count += 1

            return {
                "total_entries": len(self._cache),
                "active_entries": len(active_entries),
                "expired_entries": expired_count,
                "hot_keys": sorted(hot_keys, key=lambda x: x["hits"], reverse=True)[:20],
                "ttl_seconds": self._base_ttl,
                "hot_key_ttl_seconds": self._hot_ttl,
                "circuit_breaker_state": self._breaker.state,
                "circuit_failures": self._breaker._failure_count,
                "evicted_keys_last": list(self._evicted_keys[-20:]),
                "eviction_count_recent": len(self._evicted_keys),
            }

    def get_evicted_keys(self):
        """Return list of recently evicted keys for debugging/monitoring."""
        with self._lock:
            return list(self._evicted_keys)

    @property
    def circuit_breaker(self):
        """Expose the circuit breaker for direct inspection."""
        return self._breaker


# Global cache instance.
# - 300s TTL (5 min) default, 1200s (20 min) for hot keys
# - max_size=500 with LRU eviction
# - Circuit opens after 3 consecutive failures, recovers after 60s half-open probe
llm_cache = LLMResponseCache(
    ttl=300, max_size=500, circuit_threshold=3, recovery_window=60,
)
