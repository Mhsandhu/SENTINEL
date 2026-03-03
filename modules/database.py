"""
SENTINEL — Database Module
All SQLite database operations: users, files, logs, settings.
"""

import sqlite3
import os
import pickle
import hashlib
import numpy as np
from datetime import datetime

# Database path (relative to project root)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(PROJECT_ROOT, "database")
DB_PATH = os.path.join(DB_DIR, "sentinel.db")


def get_connection():
    """Get a database connection with row factory enabled."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT UNIQUE,
            password_hash TEXT,
            face_encoding BLOB NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            status TEXT DEFAULT 'active'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS vault_files (
            file_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_filename TEXT,
            filepath TEXT NOT NULL,
            category TEXT DEFAULT 'Others',
            file_size INTEGER,
            file_type TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP,
            access_count INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS access_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action_type TEXT NOT NULL,
            action_details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            success INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS gesture_settings (
            setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            gesture_enabled INTEGER DEFAULT 1,
            sensitivity INTEGER DEFAULT 5,
            custom_gestures TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# Password helpers
# ──────────────────────────────────────────────
def hash_password(password: str) -> str:
    """SHA-256 hash for backup password login."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    return hash_password(password) == stored_hash


# ──────────────────────────────────────────────
# User CRUD
# ──────────────────────────────────────────────
def add_user(username, email, face_encoding, password=None):
    """Register a new user. face_encoding is a numpy array."""
    conn = get_connection()
    try:
        enc_blob = pickle.dumps(face_encoding)
        pw_hash = hash_password(password) if password else None
        conn.execute(
            "INSERT INTO users (username, email, face_encoding, password_hash) VALUES (?,?,?,?)",
            (username, email, enc_blob, pw_hash),
        )
        conn.commit()
        return True, "Registration successful!"
    except sqlite3.IntegrityError as e:
        msg = str(e)
        if "username" in msg:
            return False, "Username already exists."
        if "email" in msg:
            return False, "Email already registered."
        return False, msg
    finally:
        conn.close()


def get_user_by_username(username):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE username=? AND status='active'", (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users():
    conn = get_connection()
    rows = conn.execute(
        "SELECT user_id, username, email, created_at, last_login, status FROM users"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_face_encodings():
    """Return list of {user_id, username, encoding} for all active users."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT user_id, username, face_encoding FROM users WHERE status='active'"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        enc = pickle.loads(r["face_encoding"])
        result.append({"user_id": r["user_id"], "username": r["username"], "encoding": enc})
    return result


def update_last_login(user_id):
    conn = get_connection()
    conn.execute("UPDATE users SET last_login=? WHERE user_id=?", (datetime.now(), user_id))
    conn.commit()
    conn.close()


def update_face_encoding(user_id, face_encoding):
    conn = get_connection()
    conn.execute(
        "UPDATE users SET face_encoding=? WHERE user_id=?",
        (pickle.dumps(face_encoding), user_id),
    )
    conn.commit()
    conn.close()


def update_user_password(user_id, password):
    conn = get_connection()
    conn.execute(
        "UPDATE users SET password_hash=? WHERE user_id=?",
        (hash_password(password), user_id),
    )
    conn.commit()
    conn.close()


def delete_user(user_id):
    conn = get_connection()
    conn.execute("UPDATE users SET status='inactive' WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# Vault Files CRUD
# ──────────────────────────────────────────────
def add_file(user_id, filename, original_filename, filepath, category, file_size, file_type):
    conn = get_connection()
    conn.execute(
        """INSERT INTO vault_files
           (user_id, filename, original_filename, filepath, category, file_size, file_type)
           VALUES (?,?,?,?,?,?,?)""",
        (user_id, filename, original_filename, filepath, category, file_size, file_type),
    )
    conn.commit()
    conn.close()


def get_user_files(user_id, category=None):
    conn = get_connection()
    if category and category != "All":
        rows = conn.execute(
            "SELECT * FROM vault_files WHERE user_id=? AND category=? ORDER BY uploaded_at DESC",
            (user_id, category),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM vault_files WHERE user_id=? ORDER BY uploaded_at DESC",
            (user_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_file_by_id(file_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM vault_files WHERE file_id=?", (file_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_file_record(file_id):
    conn = get_connection()
    conn.execute("DELETE FROM vault_files WHERE file_id=?", (file_id,))
    conn.commit()
    conn.close()


def search_files(user_id, query):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM vault_files WHERE user_id=? AND original_filename LIKE ? ORDER BY uploaded_at DESC",
        (user_id, f"%{query}%"),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_file_access(file_id):
    conn = get_connection()
    conn.execute(
        "UPDATE vault_files SET last_accessed=?, access_count=access_count+1 WHERE file_id=?",
        (datetime.now(), file_id),
    )
    conn.commit()
    conn.close()


def get_user_storage_stats(user_id):
    conn = get_connection()
    totals = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(file_size),0) FROM vault_files WHERE user_id=?",
        (user_id,),
    ).fetchone()
    cats = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM vault_files WHERE user_id=? GROUP BY category",
        (user_id,),
    ).fetchall()
    conn.close()
    return {
        "total_files": totals[0],
        "total_size": totals[1],
        "categories": {r["category"]: r["cnt"] for r in cats},
    }


# ──────────────────────────────────────────────
# Access Logs
# ──────────────────────────────────────────────
def add_log(user_id, action_type, details="", success=True):
    conn = get_connection()
    conn.execute(
        "INSERT INTO access_logs (user_id, action_type, action_details, success) VALUES (?,?,?,?)",
        (user_id, action_type, details, 1 if success else 0),
    )
    conn.commit()
    conn.close()


def get_user_logs(user_id, limit=50):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM access_logs WHERE user_id=? ORDER BY timestamp DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_logs(limit=100):
    conn = get_connection()
    rows = conn.execute(
        """SELECT l.*, u.username FROM access_logs l
           LEFT JOIN users u ON l.user_id = u.user_id
           ORDER BY l.timestamp DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_logs_by_type(user_id, action_type, limit=50):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM access_logs WHERE user_id=? AND action_type=? ORDER BY timestamp DESC LIMIT ?",
        (user_id, action_type, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ──────────────────────────────────────────────
# Gesture Settings
# ──────────────────────────────────────────────
def get_gesture_settings(user_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM gesture_settings WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"user_id": user_id, "gesture_enabled": 1, "sensitivity": 5, "custom_gestures": None}


def update_gesture_settings(user_id, enabled=True, sensitivity=5):
    conn = get_connection()
    conn.execute(
        """INSERT INTO gesture_settings (user_id, gesture_enabled, sensitivity)
           VALUES (?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET gesture_enabled=?, sensitivity=?""",
        (user_id, int(enabled), sensitivity, int(enabled), sensitivity),
    )
    conn.commit()
    conn.close()
