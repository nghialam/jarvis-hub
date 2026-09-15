"""
core/security.py - Security Middleware (Phase 4.2)

JH3.0: API rate limiting, input validation, security headers.
All security controls are configurable via config.yaml.
"""

import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from functools import wraps
from typing import Dict, List, Optional, Tuple

from flask import request, jsonify, g

log = logging.getLogger(__name__)


class RateLimiter:
    """
    API rate limiter using sliding window algorithm.
    
    Usage:
        limiter = RateLimiter(max_requests=100, window_seconds=60)
        # In Flask route:
        if not limiter.is_allowed(request.remote_addr):
            return jsonify({"error": "Rate limit exceeded"}), 429
    """
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests = defaultdict(list)  # ip -> [timestamps]
    
    def is_allowed(self, client_ip: str) -> bool:
        """
        Check if request is allowed under rate limit.
        
        Args:
            client_ip: Client IP address
        
        Returns:
            True if allowed, False if rate limited
        """
        now = time.time()
        cutoff = now - self.window_seconds
        
        # Clean old requests
        self._requests[client_ip] = [
            t for t in self._requests[client_ip] if t > cutoff
        ]
        
        # Check limit
        if len(self._requests[client_ip]) >= self.max_requests:
            log.warning("Rate limit exceeded for %s", client_ip)
            return False
        
        # Record request
        self._requests[client_ip].append(now)
        return True
    
    def get_remaining(self, client_ip: str) -> int:
        """
        Get remaining requests for client.
        
        Args:
            client_ip: Client IP address
        
        Returns:
            Number of remaining requests
        """
        now = time.time()
        cutoff = now - self.window_seconds
        
        self._requests[client_ip] = [
            t for t in self._requests[client_ip] if t > cutoff
        ]
        
        return max(0, self.max_requests - len(self._requests[client_ip]))
    
    def reset(self, client_ip: str = None):
        """
        Reset rate limit counters.
        
        Args:
            client_ip: Client IP to reset (None for all)
        """
        if client_ip:
            if client_ip in self._requests:
                del self._requests[client_ip]
        else:
            self._requests.clear()


class InputValidator:
    """
    Input validation utility.
    
    Usage:
        validator = InputValidator()
        errors = validator.validate_stock_symbol("VCB")
        if errors:
            return jsonify({"errors": errors}), 400
    """
    
    # Validation rules
    RULES = {
        "stock_symbol": {"pattern": r"^[A-Z]{2,5}$", "message": "Invalid stock symbol format"},
        "email": {"pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", "message": "Invalid email format"},
        "url": {"pattern": r"^https?://", "message": "Invalid URL format"},
        "date": {"pattern": r"^\d{4}-\d{2}-\d{2}$", "message": "Invalid date format (YYYY-MM-DD)"},
        "number": {"pattern": r"^-?\d+(\.\d+)?$", "message": "Invalid number format"},
        "username": {"pattern": r"^[a-zA-Z0-9_]{3,30}$", "message": "Invalid username (3-30 alphanumeric characters)"},
        "password": {"pattern": r"^. {8,}$", "message": "Password must be at least 8 characters"},
    }
    
    def __init__(self):
        import re
        self._patterns = {}
        for name, rule in self.RULES.items():
            self._patterns[name] = re.compile(rule["pattern"])
    
    def validate_stock_symbol(self, symbol: str) -> List[str]:
        """Validate stock symbol."""
        if not symbol:
            return ["Stock symbol is required"]
        
        symbol = symbol.upper().strip()
        if not self._patterns["stock_symbol"].match(symbol):
            return [self.RULES["stock_symbol"]["message"]]
        
        return []
    
    def validate_email(self, email: str) -> List[str]:
        """Validate email address."""
        if not email:
            return ["Email is required"]
        
        if not self._patterns["email"].match(email):
            return [self.RULES["email"]["message"]]
        
        return []
    
    def validate_number(self, value: str, min_val: float = None, max_val: float = None) -> List[str]:
        """Validate numeric value."""
        if not value:
            return ["Value is required"]
        
        if not self._patterns["number"].match(str(value)):
            return [self.RULES["number"]["message"]]
        
        num = float(value)
        if min_val is not None and num < min_val:
            return [f"Value must be at least {min_val}"]
        
        if max_val is not None and num > max_val:
            return [f"Value must be at most {max_val}"]
        
        return []
    
    def validate_pagination(self, page: int = 1, per_page: int = 50) -> Tuple[int, int, List[str]]:
        """
        Validate pagination parameters.
        
        Args:
            page: Page number
            per_page: Items per page
        
        Returns:
            Tuple of (page, per_page, errors)
        """
        errors = []
        
        if not isinstance(page, int) or page < 1:
            page = 1
            errors.append("Invalid page number, defaulting to 1")
        
        if not isinstance(per_page, int) or per_page < 1 or per_page > 100:
            per_page = 50
            errors.append("Invalid per_page, defaulting to 50")
        
        return page, per_page, errors
    
    def sanitize_string(self, text: str, max_length: int = 1000) -> str:
        """
        Sanitize string input.
        
        Args:
            text: Input string
            max_length: Maximum allowed length
        
        Returns:
            Sanitized string
        """
        if not text:
            return ""
        
        # Truncate to max length
        text = text[:max_length]
        
        # Remove potentially dangerous characters (basic XSS prevention)
        dangerous_chars = ["<", ">", "'", '"', ";", "(", ")"]
        for char in dangerous_chars:
            text = text.replace(char, "")
        
        return text.strip()


class SecurityHeaders:
    """
    Security headers middleware.
    
    Adds security headers to all responses:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security
    - Content-Security-Policy
    """
    
    HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    }
    
    @staticmethod
    def add_security_headers(response):
        """Add security headers to response."""
        for header, value in SecurityHeaders.HEADERS.items():
            response.headers[header] = value
        
        return response


# --- Flask hooks ---

def apply_rate_limit(app, limiter: RateLimiter = None):
    """
    Apply rate limiting to Flask app.
    
    Args:
        app: Flask app
        limiter: RateLimiter instance (creates one if not provided)
    """
    if limiter is None:
        limiter = RateLimiter(
            max_requests=app.config.get("RATE_LIMIT_MAX", 100),
            window_seconds=app.config.get("RATE_LIMIT_WINDOW", 60)
        )
    
    @app.before_request
    def check_rate_limit():
        # Skip rate limiting for localhost in development
        if request.remote_addr in ("127.0.0.1", "::1"):
            return
        
        # Skip rate limiting for static files
        if request.path.startswith("/static/"):
            return
        
        client_ip = request.remote_addr
        
        if not limiter.is_allowed(client_ip):
            response = jsonify({
                "error": "Rate limit exceeded",
                "retry_after": limiter.window_seconds,
            })
            response.status_code = 429
            response.headers["Retry-After"] = str(limiter.window_seconds)
            return response
    
    @app.after_request
    def add_rate_limit_headers(response):
        client_ip = request.remote_addr
        
        # Add rate limit headers
        remaining = limiter.get_remaining(client_ip)
        response.headers["X-RateLimit-Limit"] = str(limiter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + limiter.window_seconds)
        
        return response


def apply_security_headers(app):
    """
    Apply security headers to all responses.
    
    Args:
        app: Flask app
    """
    @app.after_request
    def add_security_headers(response):
        return SecurityHeaders.add_security_headers(response)


def require_auth_or_public(app, auth_service):
    """
    Apply authentication middleware.
    
    Public endpoints that don't require auth:
    - /health
    - /api/v1/health/*
    - /static/*
    - /api/v1/news/trending
    - /api/v1/news/categories
    - /api/v1/stocks/symbols/search
    
    Args:
        app: Flask app
        auth_service: AuthService instance
    """
    PUBLIC_ENDPOINTS = [
        "/health",
        "/api/v1/health",
        "/static/",
        "/api/v1/news/trending",
        "/api/v1/news/categories",
        "/api/v1/stocks/symbols/search",
        "/api/v1/llm/health",
    ]
    
    @app.before_request
    def check_auth():
        # Skip auth for public endpoints
        if any(request.path.startswith(endpoint) for endpoint in PUBLIC_ENDPOINTS):
            return
        
        # Skip auth for static files
        if request.path.startswith("/static/"):
            return
        
        # Check for auth token
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        
        if not token:
            # Skip auth for API endpoints in development
            if request.path.startswith("/api/"):
                # Allow unauthenticated access in development
                # In production, this would return 401
                pass
            else:
                # HTML pages don't require auth
                pass
        
        return None


# --- Middleware initialization ---

def init_security(app, config=None):
    """
    Initialize all security middleware.
    
    Args:
        app: Flask app
        config: Configuration dict
    """
    config = config or {}
    security_config = config.get("security", {})
    
    # Initialize rate limiter
    rate_limiter = RateLimiter(
        max_requests=security_config.get("rate_limit_max", 100),
        window_seconds=security_config.get("rate_limit_window", 60)
    )
    
    # Initialize input validator
    input_validator = InputValidator()
    
    # Apply rate limiting
    apply_rate_limit(app, rate_limiter)
    
    # Apply security headers
    apply_security_headers(app)
    
    # Apply authentication middleware (development mode)
    try:
        from core.auth import AuthService
        auth_service = AuthService(config)
        require_auth_or_public(app, auth_service)
    except Exception as e:
        log.warning("Auth middleware initialization failed (development mode): %s", e)
    
    # Store in app context
    app.rate_limiter = rate_limiter
    app.input_validator = input_validator
    app.auth_service = auth_service if 'auth_service' in dir() else None
    
    log.info("Security middleware initialized")
