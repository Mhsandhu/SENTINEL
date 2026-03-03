"""
SENTINEL — Vault Manager Module
Handles file upload, download, delete, and storage organization.
"""

import os
import shutil
import uuid
from datetime import datetime
from modules import database as db

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT_ROOT = os.path.join(PROJECT_ROOT, "vault_storage")

CATEGORIES = ["Documents", "Photos", "Videos", "Others"]

# File extension → category mapping
EXT_CATEGORY = {
    # Documents
    ".pdf": "Documents", ".doc": "Documents", ".docx": "Documents",
    ".txt": "Documents", ".rtf": "Documents", ".odt": "Documents",
    ".xls": "Documents", ".xlsx": "Documents", ".csv": "Documents",
    ".ppt": "Documents", ".pptx": "Documents",
    # Photos
    ".jpg": "Photos", ".jpeg": "Photos", ".png": "Photos",
    ".gif": "Photos", ".bmp": "Photos", ".svg": "Photos",
    ".webp": "Photos", ".ico": "Photos", ".tiff": "Photos",
    # Videos
    ".mp4": "Videos", ".avi": "Videos", ".mkv": "Videos",
    ".mov": "Videos", ".wmv": "Videos", ".flv": "Videos",
    ".webm": "Videos", ".m4v": "Videos",
}


def get_user_vault_path(user_id, category=None):
    """Get the vault storage path for a user, optionally for a category."""
    path = os.path.join(VAULT_ROOT, f"user_{user_id}")
    if category:
        path = os.path.join(path, category.lower())
    os.makedirs(path, exist_ok=True)
    return path


def detect_category(filename):
    """Auto-detect file category from extension."""
    ext = os.path.splitext(filename)[1].lower()
    return EXT_CATEGORY.get(ext, "Others")


def save_file(user_id, uploaded_file, category=None):
    """
    Save an uploaded file to the vault.
    uploaded_file: Streamlit UploadedFile object (has .name, .read(), .size)
    Returns: (success, message, file_info)
    """
    original_name = uploaded_file.name
    file_size = uploaded_file.size
    file_ext = os.path.splitext(original_name)[1].lower()

    # Auto-detect category if not specified
    if not category:
        category = detect_category(original_name)

    # Generate unique filename to avoid conflicts
    unique_name = f"{uuid.uuid4().hex[:8]}_{original_name}"

    # Build storage path
    vault_path = get_user_vault_path(user_id, category)
    filepath = os.path.join(vault_path, unique_name)

    try:
        # Write file
        with open(filepath, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # Save to database
        db.add_file(
            user_id=user_id,
            filename=unique_name,
            original_filename=original_name,
            filepath=filepath,
            category=category,
            file_size=file_size,
            file_type=file_ext.lstrip("."),
        )

        return True, f"'{original_name}' uploaded successfully!", {
            "filename": unique_name,
            "original": original_name,
            "category": category,
            "size": file_size,
        }

    except Exception as e:
        return False, f"Upload failed: {e}", None


def delete_file(file_id):
    """Delete a file from vault and database."""
    file_info = db.get_file_by_id(file_id)
    if not file_info:
        return False, "File not found."

    filepath = file_info["filepath"]

    try:
        # Delete from filesystem
        if os.path.exists(filepath):
            os.remove(filepath)

        # Delete from database
        db.delete_file_record(file_id)

        return True, f"'{file_info['original_filename']}' deleted."
    except Exception as e:
        return False, f"Delete failed: {e}"


def get_file_content(file_id):
    """Read file content for download/preview. Returns (bytes, filename, mime)."""
    file_info = db.get_file_by_id(file_id)
    if not file_info:
        return None, None, None

    filepath = file_info["filepath"]
    if not os.path.exists(filepath):
        return None, None, None

    # Update access stats
    db.update_file_access(file_id)

    with open(filepath, "rb") as f:
        data = f.read()

    # Determine MIME type
    ext = file_info.get("file_type", "").lower()
    mime_map = {
        "pdf": "application/pdf",
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "gif": "image/gif",
        "mp4": "video/mp4", "avi": "video/x-msvideo",
        "txt": "text/plain", "csv": "text/csv",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "ppt": "application/vnd.ms-powerpoint",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    mime = mime_map.get(ext, "application/octet-stream")

    return data, file_info["original_filename"], mime


def get_user_files(user_id, category=None):
    """Get list of files for a user, optionally filtered by category."""
    return db.get_user_files(user_id, category)


def search_user_files(user_id, query):
    """Search files by name."""
    return db.search_files(user_id, query)


def get_storage_stats(user_id):
    """Get storage statistics for a user."""
    stats = db.get_user_storage_stats(user_id)
    # Format size
    size_bytes = stats["total_size"]
    if size_bytes < 1024:
        size_str = f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        size_str = f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        size_str = f"{size_bytes / (1024*1024):.1f} MB"
    else:
        size_str = f"{size_bytes / (1024*1024*1024):.2f} GB"

    stats["size_formatted"] = size_str
    return stats


def format_file_size(size_bytes):
    """Format bytes to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
