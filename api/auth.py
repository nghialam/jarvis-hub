"""
api/auth.py - Authentication Endpoints (Phase 4.3)

JH3.0: JWT-based auth endpoints for login, logout, register, and user management.
"""

import logging
from flask import Blueprint, request, jsonify

log = logging.getLogger(__name__)

# Create auth blueprint
auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Authenticate user and return JWT token.
    
    Request body:
        username: str
        password: str
    
    Response:
        {
            "token": "eyJ...",
            "username": "admin",
            "role": "admin",
            "expires_at": "2026-08-29T10:00:00"
        }
    """
    try:
        from core.auth import AuthService
        
        data = request.get_json() or {}
        username = data.get("username", "").strip()
        password = data.get("password", "")
        
        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400
        
        auth = AuthService()
        result = auth.login(username, password)
        
        if result:
            return jsonify(result)
        else:
            return jsonify({"error": "Invalid credentials"}), 401
    
    except Exception as e:
        log.error("Login error: %s", e)
        return jsonify({"error": "Authentication service error"}), 500


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """
    Invalidate JWT token.
    
    Request headers:
        Authorization: Bearer <token>
    
    Response:
        {"message": "Logged out successfully"}
    """
    try:
        from core.auth import AuthService
        
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        
        if not token:
            return jsonify({"error": "Token required"}), 400
        
        auth = AuthService()
        auth.logout(token)
        
        return jsonify({"message": "Logged out successfully"})
    
    except Exception as e:
        log.error("Logout error: %s", e)
        return jsonify({"error": "Logout service error"}), 500


@auth_bp.route("/register", methods=["POST"])
def register():
    """
    Register a new user.
    
    Request body:
        username: str
        password: str
        role: str (optional, default: "viewer")
    
    Response:
        {"message": "User registered successfully"}
    """
    try:
        from core.auth import AuthService
        
        data = request.get_json() or {}
        username = data.get("username", "").strip()
        password = data.get("password", "")
        role = data.get("role", "viewer")
        
        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400
        
        if len(password) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400
        
        auth = AuthService()
        success = auth.register_user(username, password, role)
        
        if success:
            return jsonify({"message": "User registered successfully"}), 201
        else:
            return jsonify({"error": "Username already exists or invalid role"}), 400
    
    except Exception as e:
        log.error("Registration error: %s", e)
        return jsonify({"error": "Registration service error"}), 500


@auth_bp.route("/users", methods=["GET"])
def get_users():
    """
    Get all registered users (admin only).
    
    Request headers:
        Authorization: Bearer <token>
    
    Response:
        [
            {
                "id": 1,
                "username": "admin",
                "role": "admin",
                "created_at": "2026-08-28T10:00:00",
                "active": true
            }
        ]
    """
    try:
        from core.auth import AuthService, require_auth
        
        @require_auth
        def _get_users():
            auth = AuthService()
            users = auth.get_users()
            return jsonify(users)
        
        return _get_users()
    
    except Exception as e:
        log.error("Get users error: %s", e)
        return jsonify({"error": "Failed to get users"}), 500


@auth_bp.route("/users/<username>", methods=["PUT"])
def update_user(username):
    """
    Update user role or active status (admin only).
    
    Request headers:
        Authorization: Bearer <token>
    
    Request body:
        role: str (optional)
        active: bool (optional)
    
    Response:
        {"message": "User updated successfully"}
    """
    try:
        from core.auth import AuthService, require_auth
        
        @require_auth
        def _update_user():
            data = request.get_json() or {}
            role = data.get("role")
            active = data.get("active")
            
            if not role and active is None:
                return jsonify({"error": "role or active status required"}), 400
            
            auth = AuthService()
            success = auth.update_user(username, role=role, active=active)
            
            if success:
                return jsonify({"message": "User updated successfully"})
            else:
                return jsonify({"error": "Failed to update user"}), 500
        
        return _update_user()
    
    except Exception as e:
        log.error("Update user error: %s", e)
        return jsonify({"error": "Failed to update user"}), 500


@auth_bp.route("/users/<username>", methods=["DELETE"])
def delete_user(username):
    """
    Delete a user (admin only).
    
    Request headers:
        Authorization: Bearer <token>
    
    Response:
        {"message": "User deleted successfully"}
    """
    try:
        from core.auth import AuthService, require_auth
        
        @require_auth
        def _delete_user():
            auth = AuthService()
            success = auth.delete_user(username)
            
            if success:
                return jsonify({"message": "User deleted successfully"})
            else:
                return jsonify({"error": "Failed to delete user"}), 500
        
        return _delete_user()
    
    except Exception as e:
        log.error("Delete user error: %s", e)
        return jsonify({"error": "Failed to delete user"}), 500


@auth_bp.route("/profile", methods=["GET"])
def get_profile():
    """
    Get current user profile.
    
    Request headers:
        Authorization: Bearer <token>
    
    Response:
        {
            "username": "admin",
            "role": "admin",
            "permissions": ["read", "write", "admin"]
        }
    """
    try:
        from core.auth import AuthService, require_auth
        
        @require_auth
        def _get_profile():
            user = request.user
            role = user.get("role", "viewer")
            
            from core.auth import ROLES
            permissions = ROLES.get(role, {}).get("permissions", [])
            
            return jsonify({
                "username": user.get("username"),
                "role": role,
                "permissions": permissions,
            })
        
        return _get_profile()
    
    except Exception as e:
        log.error("Get profile error: %s", e)
        return jsonify({"error": "Failed to get profile"}), 500
