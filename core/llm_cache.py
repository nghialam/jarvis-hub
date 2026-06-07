"""
llm_cache.py -- Thread-safe, TTL-based cache for LLM (Ollama) responses.

Prevents redundant API calls when the same prompt/hash is requested multiple times
within a short window (default 300s / 5 min). Used by:
- app.py /api/analyze endpoint (stock/crypto analyze reports)
- core/news.py llm_sentiment (article sentiment analysis)
- core/market.py llm_due_diligence

Circuit breaker pattern integrated to prevent hammering a failing Ollama instance.

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
    """Thread-safe, TTL-based cache for LLM responses with circuit breaker."""

    def __init__(self, ttl=300, max_size=None, circuit_threshold=3, recovery_window=60):
        self._cache = {}
        self._lock = threading.Lock()
        self._max_size = max_size
        self._order = []
        self._ttl = ttl
        self._breaker = CircuitBreaker(
            failure_threshold=circuit_threshold,
            recovery_window=recovery_window,
        )

    @staticmethod
    def hash_prompt(prompt):
        """Create a short SHA-256 hash of the prompt for caching key."""
        return hashlib.sha256(prompt.encode()).hexdigest()[:16]

    # pylint: disable=unnecessary-pass
    def _get_cache_entry(self, key):
        """Get cached entry if it exists and is fresh. Returns None on miss/expiry."""
        with self._lock:
            if key not in self._cache:
                return None
            entry = self._cache[key]
            entry_ttl = entry.get("ttl", self._ttl)
            if time.time() - entry["ts"] < entry_ttl:
                entry["hits"] += 1
                return entry
        # If we got here, the entry is expired
        with self._lock:
            if key in self._cache:
                del self._cache[key]
        return None

    def _store(self, key, value):
        """Thread-safe helper to store in cache with LRU eviction."""
        if self._max_size is not None and len(self._order) >= self._max_size:
            oldest = self._order[0]
            self._order.pop(0)
            if oldest in self._cache:
                del self._cache[oldest]

        with self._lock:
            # Remove key from order list if it exists there already (update case)
            try:
                self._order.remove(key)
            except ValueError:
                pass
            entry = {"value": value, "ts": time.time(), "hits": 1, "ttl": self._ttl}
            self._cache[key] = entry
            self._order.append(key)

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
        with self._lock:
            expired_keys = [
                k for k, v in self._cache.items()
                if now - v["ts"] >= v.get("ttl", self._ttl)
            ]
            for k in expired_keys:
                del self._cache[k]
                try:
                    self._order.remove(k)
                except ValueError:
                    pass
            return len(expired_keys)

    def get_stats(self):
        """Return cache statistics (size, hit rate approx)."""
        with self._lock:
            now = time.time()
            active = {
                k: v for k, v in self._cache.items()
                if now - v["ts"] < v.get("ttl", self._ttl)
            }
            return {
                "total_entries": len(self._cache),
                "active_entries": len(active),
                "expired_entries": len(self._cache) - len(active),
                "ttl_seconds": self._ttl,
                "circuit_breaker_state": self._breaker.state,
                "circuit_failures": self._breaker._failure_count,
            }

    @property
    def circuit_breaker(self):
        """Expose the circuit breaker for direct inspection."""
        return self._breaker


# Global cache instance.
# - 300s TTL (5 min) for successful responses.
# - max_size=500 to cap memory growth and evict old entries via LRU.
# - Circuit opens after 3 consecutive failures, recovers after 60s half-open probe.
llm_cache = LLMResponseCache(
    ttl=300, max_size=500, circuit_threshold=3, recovery_window=60,
)
