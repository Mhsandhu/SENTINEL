"""
SENTINEL — Logger Module
Convenience wrapper around database log operations.
"""

from modules import database as db
from datetime import datetime


def log_login_success(user_id, method="face"):
    """Log a successful login."""
    db.add_log(user_id, "login", f"Login successful via {method}", success=True)


def log_login_failed(user_id=None, reason="Unknown face"):
    """Log a failed login attempt."""
    db.add_log(user_id, "login_failed", reason, success=False)


def log_registration(user_id, username):
    """Log a new user registration."""
    db.add_log(user_id, "registration", f"User '{username}' registered", success=True)


def log_file_upload(user_id, filename, category):
    """Log a file upload."""
    db.add_log(user_id, "file_upload", f"{filename} ({category})", success=True)


def log_file_view(user_id, filename):
    """Log a file view/download."""
    db.add_log(user_id, "file_view", filename, success=True)


def log_file_delete(user_id, filename):
    """Log a file deletion."""
    db.add_log(user_id, "file_delete", filename, success=True)


def log_gesture(user_id, gesture, action):
    """Log a gesture action."""
    db.add_log(user_id, "gesture_used", f"{gesture} → {action}", success=True)


def log_gesture_session_start(user_id):
    """Log gesture control session start."""
    db.add_log(user_id, "gesture_session", "Gesture control started", success=True)


def log_gesture_session_end(user_id):
    """Log gesture control session end."""
    db.add_log(user_id, "gesture_session", "Gesture control stopped", success=True)


def log_settings_change(user_id, setting, value):
    """Log a settings change."""
    db.add_log(user_id, "settings_change", f"{setting} = {value}", success=True)


def log_logout(user_id):
    """Log a user logout."""
    db.add_log(user_id, "logout", "User logged out", success=True)


def get_formatted_logs(user_id, limit=50):
    """Get logs formatted for display with icons."""
    logs = db.get_user_logs(user_id, limit)
    formatted = []
    icons = {
        "login": "🔓",
        "login_failed": "🔒",
        "registration": "📝",
        "file_upload": "📤",
        "file_view": "👁️",
        "file_delete": "🗑️",
        "gesture_used": "🤚",
        "gesture_session": "🎮",
        "settings_change": "⚙️",
        "logout": "🚪",
    }
    for log in logs:
        icon = icons.get(log["action_type"], "📌")
        status = "✅" if log["success"] else "❌"
        formatted.append({
            "icon": icon,
            "status": status,
            "action": log["action_type"],
            "details": log["action_details"] or "",
            "timestamp": log["timestamp"],
            "success": log["success"],
        })
    return formatted
