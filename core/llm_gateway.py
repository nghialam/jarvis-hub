"""
core/llm_gateway.py - Unified LLM gateway with circuit breaker pattern

JH3.0: All LLM calls go through this gateway.
Circuit breaker prevents cascade failures when LLM is down.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: LLM failing, requests rejected immediately (fast-fail)
- HALF-OPEN: Testing if LLM recovered, limited requests allowed

Features:
- Configurable failure threshold (default: 5 failures)
- Configurable recovery timeout (default: 5 minutes)
- Configurable half-open request limit (default: 1)
- Automatic state transitions
- Per-endpoint circuit breakers
"""

import time
import json
import logging
from typing import Any, Dict, Optional, Callable
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

log = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5          # Failures before opening
    recovery_timeout: int = 300         # Seconds before half-open
    half_open_max_calls: int = 1        # Max calls in half-open state
    success_threshold: int = 2          # Successes to close in half-open


@dataclass
class CircuitBreakerState:
    """Track circuit breaker state for one endpoint."""
    endpoint: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0
    last_success_time: float = 0
    half_open_calls: int = 0
    opened_at: float = 0
    
    def to_dict(self) -> Dict:
        return {
            "endpoint": self.endpoint,
            "state": self.state.value if isinstance(self.state, CircuitState) else self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "half_open_calls": self.half_open_calls,
            "last_failure_time": self.last_failure_time,
            "opened_at": self.opened_at,
        }


class LLMLightweightGateway:
    """
    Lightweight LLM gateway with circuit breaker.
    
    This is a simplified gateway that wraps LLM calls with circuit breaker
    and falls back to heuristics when LLM is unavailable.
    
    Usage:
        gateway = LLMLightweightGateway()
        result = gateway.call("analyze", {"symbol": "VCB"}, fallback=my_heuristic)
    """
    
    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self._breakers: Dict[str, CircuitBreakerState] = {}
        self._lock = __import__("threading").Lock()
        
        # Track total stats
        self.stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "fallback_calls": 0,
            "rejected_by_circuit": 0,
        }
    
    def call(self, endpoint: str, prompt: str,
             fallback: Optional[Callable] = None,
             **kwargs) -> Optional[Any]:
        """
        Call LLM with circuit breaker protection.
        
        Args:
            endpoint: Endpoint identifier (e.g., "analyze", "market_eval")
            prompt: Input prompt
            fallback: Fallback function if LLM fails
            **kwargs: Additional arguments passed to fallback
        
        Returns:
            LLM response, fallback result, or None
        """
        self.stats["total_calls"] += 1
        
        # Get or create circuit breaker for this endpoint
        breaker = self._get_or_create_breaker(endpoint)
        
        # Check circuit breaker
        if not self._can_call(breaker):
            self.stats["rejected_by_circuit"] += 1
            log.warning("Circuit breaker OPEN for %s, rejecting call", endpoint)
            
            # Try fallback
            if fallback:
                try:
                    result = fallback(**kwargs)
                    self.stats["fallback_calls"] += 1
                    return result
                except Exception as e:
                    log.error("Fallback failed for %s: %s", endpoint, e)
                    return None
            return None
        
        # Execute LLM call
        try:
            result = self._execute_llm(endpoint, prompt, **kwargs)
            
            # Record success
            self._record_success(breaker)
            self.stats["successful_calls"] += 1
            
            return result
            
        except Exception as e:
            # Record failure
            self._record_failure(breaker)
            self.stats["failed_calls"] += 1
            log.error("LLM call failed for %s: %s", endpoint, e)
            
            # Try fallback
            if fallback:
                try:
                    result = fallback(**kwargs)
                    self.stats["fallback_calls"] += 1
                    return result
                except Exception as e2:
                    log.error("Fallback also failed for %s: %s", endpoint, e2)
            
            return None
    
    def _execute_llm(self, endpoint: str, prompt: str, **kwargs) -> Any:
        """Execute actual LLM call via llm_client."""
        try:
            from core.llm_client import llm_call
            
            return llm_call(
                prompt,
                system_prompt=kwargs.get("system_prompt", ""),
                timeout=kwargs.get("timeout", 120),
                max_tokens=kwargs.get("max_tokens", 4096),
                temperature=kwargs.get("temperature", 0.7),
            )
            
        except ImportError:
            raise Exception("llm_client not available")
        except Exception as e:
            raise e
    
    def _get_or_create_breaker(self, endpoint: str) -> CircuitBreakerState:
        """Get or create circuit breaker for endpoint."""
        with self._lock:
            if endpoint not in self._breakers:
                self._breakers[endpoint] = CircuitBreakerState(endpoint=endpoint)
            return self._breakers[endpoint]
    
    def _can_call(self, breaker: CircuitBreakerState) -> bool:
        """Check if a call is allowed based on circuit state."""
        if breaker.state == CircuitState.CLOSED:
            return True
        
        if breaker.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if time.time() - breaker.opened_at > self.config.recovery_timeout:
                breaker.state = CircuitState.HALF_OPEN
                breaker.half_open_calls = 0
                log.info("Circuit breaker for %s transitioning to HALF-OPEN", breaker.endpoint)
                return True
            return False
        
        if breaker.state == CircuitState.HALF_OPEN:
            # Allow limited calls
            if breaker.half_open_calls < self.config.half_open_max_calls:
                breaker.half_open_calls += 1
                return True
            return False
        
        return False
    
    def _record_success(self, breaker: CircuitBreakerState):
        """Record a successful call."""
        breaker.success_count += 1
        breaker.last_success_time = time.time()
        
        if breaker.state == CircuitState.HALF_OPEN:
            # Check if we have enough successes to close
            if breaker.success_count >= self.config.success_threshold:
                breaker.state = CircuitState.CLOSED
                breaker.failure_count = 0
                breaker.success_count = 0
                log.info("Circuit breaker for %s CLOSED (recovered)", breaker.endpoint)
        elif breaker.state == CircuitState.CLOSED:
            # Reset failure count on success
            breaker.failure_count = 0
    
    def _record_failure(self, breaker: CircuitBreakerState):
        """Record a failed call."""
        breaker.failure_count += 1
        breaker.last_failure_time = time.time()
        
        if breaker.state == CircuitState.HALF_OPEN:
            # Any failure in half-open reopens
            breaker.state = CircuitState.OPEN
            breaker.opened_at = time.time()
            log.warning("Circuit breaker for %s re-OPENED after half-open failure", breaker.endpoint)
        elif breaker.state == CircuitState.CLOSED:
            # Check if we've hit the failure threshold
            if breaker.failure_count >= self.config.failure_threshold:
                breaker.state = CircuitState.OPEN
                breaker.opened_at = time.time()
                log.warning("Circuit breaker for %s OPENED (%d failures)", breaker.endpoint, breaker.failure_count)
    
    def get_circuit_state(self, endpoint: str) -> Optional[Dict]:
        """Get circuit breaker state for endpoint."""
        with self._lock:
            breaker = self._breakers.get(endpoint)
            if breaker:
                return breaker.to_dict()
        return None
    
    def get_all_circuit_states(self) -> Dict[str, Dict]:
        """Get circuit breaker states for all endpoints."""
        with self._lock:
            return {ep: b.to_dict() for ep, b in self._breakers.items()}
    
    def reset_circuit(self, endpoint: str):
        """Manually reset circuit breaker to closed state."""
        with self._lock:
            if endpoint in self._breakers:
                self._breakers[endpoint] = CircuitBreakerState(endpoint=endpoint)
                log.info("Circuit breaker for %s manually reset", endpoint)
    
    def get_stats(self) -> Dict:
        """Get gateway statistics."""
        return {**self.stats, "endpoints": len(self._breakers)}


# Singleton instance
_llm_gateway_instance = None


def get_llm_gateway() -> LLMLightweightGateway:
    """Get or create LLMLightweightGateway singleton."""
    global _llm_gateway_instance
    if _llm_gateway_instance is None:
        _llm_gateway_instance = LLMLightweightGateway()
    return _llm_gateway_instance
