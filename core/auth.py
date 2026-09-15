"""
core/auth.py - Authentication & Authorization (Phase 4.1)

JH3.0: JWT-based authentication with RBAC (Role-Based Access Control).
All secrets from env vars or config — nothing hardcoded.
"""

import hashlib
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, List, Optional, Tuple

import yaml
from flask import request, jsonify, session

log = logging.getLogger(__name__)

# RBAC Roles
ROLES = {
    "admin": {"permissions": ["read", "write", "admin"], "description": "Full access"},
    "analyst": {"permissions": ["read", "write"], "description": "Read + Write"},
    "viewer": {"permissions": ["read"], "description": "Read only"},
}

# Default admin credentials (should be overridden via env vars)
DEFAULT_ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))


class AuthService:
    """
    JWT-based authentication service.
    
    Usage:
        auth = AuthService(config)
        token = auth.login(username, password)
        user = auth.verify_token(token)
    """
    
    def __init__(self, config=None, db=None):
        self.config = config or {}
        self.db = db
        self.token_expiry = timedelta(hours=self.config.get("security", {}).get("jwt_expiry_hours", 24))
        self.max_login_attempts = self.config.get("security", {}).get("max_login_attempts", 5)
        self.lockout_minutes = self.config.get("security", {}).get("lockout_minutes", 15)
        
        # In-memory login attempt tracking (use DB in production)
        self._login_attempts = {}
        self._tokens = {}  # Simple token store (use Redis in production)
        
    def login(self, username: str, password: str) -> Optional[Dict]:
        """
        Authenticate user and return JWT token.
        
        Args:
            username: Username
            password: Password (plain text, will be hashed)
        
        Returns:
            Token dict or None if authentication fails
        """
        # Check if account is locked
        if self._is_locked(username):
            log.warning("Login attempt for locked account: %s", username)
            return None
        
        # Verify credentials
        user = self._authenticate(username, password)
        if not user:
            self._record_failed_attempt(username)
            return None
        
        # Reset failed attempts on successful login
        self._reset_attempts(username)
        
        # Generate JWT token
        token = self._generate_token(user)
        
        log.info("User logged in: %s", username)
        return {
            "token": token,
            "username": username,
            "role": user.get("role", "viewer"),
            "expires_at": (datetime.utcnow() + self.token_expiry).isoformat(),
        }
    
    def logout(self, token: str) -> bool:
        """
        Invalidate a token.
        
        Args:
            token: JWT token to invalidate
        
        Returns:
            True if invalidated, False if not found
        """
        if token in self._tokens:
            del self._tokens[token]
            log.info("Token invalidated for: %s", token[:8])
            return True
        return False
    
    def verify_token(self, token: str) -> Optional[Dict]:
        """
        Verify JWT token and return user info.
        
        Args:
            token: JWT token
        
        Returns:
            User dict or None if token is invalid
        """
        if token not in self._tokens:
            return None
        
        user_data = self._tokens[token]
        expires_at = datetime.fromisoformat(user_data["expires_at"])
        
        if datetime.utcnow() > expires_at:
            del self._tokens[token]
            log.warning("Expired token used: %s", token[:8])
            return None
        
        return user_data
    
    def register_user(self, username: str, password: str, role: str = "viewer") -> bool:
        """
        Register a new user.
        
        Args:
            username: Username
            password: Password
            role: User role (admin, analyst, viewer)
        
        Returns:
            True if registered, False if failed
        """
        if role not in ROLES:
            log.error("Invalid role: %s", role)
            return False
        
        # Check if user exists
        if self._user_exists(username):
            log.warning("User already exists: %s", username)
            return False
        
        # Hash password
        password_hash = self._hash_password(password)
        
        # Save user (in production, use DB)
        user = {
            "username": username,
            "password_hash": password_hash,
            "role": role,
            "created_at": datetime.utcnow().isoformat(),
            "active": True,
        }
        
        self._save_user(user)
        log.info("User registered: %s (role: %s)", username, role)
        return True
    
    def check_permission(self, token: str, required_permission: str) -> bool:
        """
        Check if user has required permission.
        
        Args:
            token: JWT token
            required_permission: Required permission (read, write, admin)
        
        Returns:
            True if permission granted, False otherwise
        """
        user = self.verify_token(token)
        if not user:
            return False
        
        role = user.get("role", "viewer")
        user_permissions = ROLES.get(role, {}).get("permissions", [])
        
        return required_permission in user_permissions
    
    def get_users(self) -> List[Dict]:
        """
        Get all registered users.
        
        Returns:
            List of user dicts (without password hashes)
        """
        try:
            conn = self.db.get_connection()
            rows = conn.execute(
                "SELECT id, username, role, created_at, active FROM users ORDER BY created_at DESC"
            ).fetchall()
            
            return [
                {
                    "id": row[0],
                    "username": row[1],
                    "role": row[2],
                    "created_at": row[3],
                    "active": bool(row[4]),
                }
                for row in rows
            ]
        except Exception as e:
            log.error("Failed to get users: %s", e)
            return []
    
    def update_user(self, username: str, role: str = None, active: bool = None) -> bool:
        """
        Update user role or active status.
        
        Args:
            username: Username
            role: New role (optional)
            active: New active status (optional)
        
        Returns:
            True if updated, False otherwise
        """
        try:
            conn = self.db.get_connection()
            
            if role:
                conn.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))
            if active is not None:
                conn.execute("UPDATE users SET active = ? WHERE username = ?", (active, username))
            
            conn.commit()
            log.info("User updated: %s", username)
            return True
        except Exception as e:
            log.error("Failed to update user: %s", e)
            return False
    
    def delete_user(self, username: str) -> bool:
        """
        Delete a user.
        
        Args:
            username: Username
        
        Returns:
            True if deleted, False otherwise
        """
        try:
            conn = self.db.get_connection()
            conn.execute("DELETE FROM users WHERE username = ?", (username,))
            conn.commit()
            log.info("User deleted: %s", username)
            return True
        except Exception as e:
            log.error("Failed to delete user: %s", e)
            return False
    
    # --- Private methods ---
    
    def _authenticate(self, username: str, password: str) -> Optional[Dict]:
        """Authenticate user credentials."""
        try:
            conn = self.db.get_connection()
            row = conn.execute(
                "SELECT id, username, role, password_hash, active FROM users WHERE username = ?",
                (username,)
            ).fetchone()
            
            if row and self._verify_password(password, row[3]) and row[4]:
                return {
                    "id": row[0],
                    "username": row[1],
                    "role": row[2],
                }
        except Exception as e:
            log.error("Authentication error: %s", e)
        
        return None
    
    def _generate_token(self, user: Dict) -> str:
        """Generate JWT token."""
        import hmac
        import base64
        
        payload = {
            "sub": user["username"],
            "role": user["role"],
            "iat": datetime.utcnow().isoformat(),
            "exp": (datetime.utcnow() + self.token_expiry).isoformat(),
        }
        
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            SECRET_KEY.encode(),
            payload_str.encode(),
            hashlib.sha256
        ).hexdigest()
        
        token = f"{base64.urlsafe_b64encode(payload_str.encode()).decode()}.{signature}"
        self._tokens[token] = {
            **user,
            "expires_at": (datetime.utcnow() + self.token_expiry).isoformat(),
        }
        
        return token
    
    def _hash_password(self, password: str) -> str:
        """Hash password using SHA-256 with salt."""
        salt = secrets.token_hex(16)
        password_hash = hashlib.sha256((salt + password).encode()).hexdigest()
        return f"{salt}:{password_hash}"
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash."""
        try:
            salt, stored_hash = password_hash.split(":")
            computed_hash = hashlib.sha256((salt + password).encode()).hexdigest()
            return computed_hash == stored_hash
        except Exception:
            return False
    
    def _is_locked(self, username: str) -> bool:
        """Check if account is locked due to failed attempts."""
        if username in self._login_attempts:
            attempts = self._login_attempts[username]
            if len(attempts) >= self.max_login_attempts:
                last_attempt = datetime.fromisoformat(attempts[-1])
                lockout_end = last_attempt + timedelta(minutes=self.lockout_minutes)
                if datetime.utcnow() < lockout_end:
                    return True
        
        return False
    
    def _record_failed_attempt(self, username: str):
        """Record a failed login attempt."""
        if username not in self._login_attempts:
            self._login_attempts[username] = []
        
        self._login_attempts[username].append(datetime.utcnow().isoformat())
        
        # Keep only recent attempts
        cutoff = datetime.utcnow() - timedelta(hours=1)
        self._login_attempts[username] = [
            a for a in self._login_attempts[username]
            if datetime.fromisoformat(a) > cutoff
        ]
        
        log.warning("Failed login attempt for %s (%d total)", username, len(self._login_attempts[username]))
    
    def _reset_attempts(self, username: str):
        """Reset failed login attempts."""
        if username in self._login_attempts:
            del self._login_attempts[username]
    
    def _user_exists(self, username: str) -> bool:
        """Check if user exists."""
        try:
            conn = self.db.get_connection()
            row = conn.execute(
                "SELECT COUNT(*) FROM users WHERE username = ?",
                (username,)
            ).fetchone()
            return row and row[0] > 0
        except Exception:
            return False
    
    def _save_user(self, user: Dict):
        """Save user to database."""
        try:
            conn = self.db.get_connection()
            conn.execute(
                """INSERT INTO users (username, password_hash, role, created_at, active)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    user["username"],
                    user["password_hash"],
                    user["role"],
                    user["created_at"],
                    user.get("active", True),
                )
            )
            conn.commit()
        except Exception as e:
            log.error("Failed to save user: %s", e)
            raise


# --- Flask decorators ---

def require_auth(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        
        if not token:
            return jsonify({"error": "Authentication required"}), 401
        
        auth = AuthService()
        user = auth.verify_token(token)
        
        if not user:
            return jsonify({"error": "Invalid or expired token"}), 401
        
        request.user = user
        return f(*args, **kwargs)
    
    return decorated_function


def require_role(*roles):
    """Decorator to require specific role."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            
            if not token:
                return jsonify({"error": "Authentication required"}), 401
            
            auth = AuthService()
            user = auth.verify_token(token)
            
            if not user:
                return jsonify({"error": "Invalid or expired token"}), 401
            
            if user.get("role") not in roles:
                return jsonify({"error": "Insufficient permissions"}), 403
            
            request.user = user
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def require_permission(*permissions):
    """Decorator to require specific permission."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            
            if not token:
                return jsonify({"error": "Authentication required"}), 401
            
            auth = AuthService()
            user = auth.verify_token(token)
            
            if not user:
                return jsonify({"error": "Invalid or expired token"}), 401
            
            for perm in permissions:
                if not auth.check_permission(token, perm):
                    return jsonify({"error": f"Permission denied: {perm}"}), 403
            
            request.user = user
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator
