"""Centralized path resolution for executable and dev modes."""

from __future__ import annotations

import os
import sys


def get_app_dir() -> str:
    """Return root application directory whether running from source or PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_reports_root() -> str:
    """Return root folder for generated reports."""
    path = os.path.join(get_app_dir(), "reports")
    os.makedirs(path, exist_ok=True)
    return path


def get_db_path() -> str:
    """Return local SQLite database path (checks app directory, data subfolder, and parent repo)."""
    if os.getenv("GYMSIS_SQLITE_PATH"):
        return os.getenv("GYMSIS_SQLITE_PATH")
    
    app_dir = get_app_dir()
    root_db = os.path.join(app_dir, "gymsis.db")
    if os.path.exists(root_db):
        return root_db
        
    data_db = os.path.join(app_dir, "data", "gymsis.db")
    if os.path.exists(data_db):
        return data_db

    parent_data_db = os.path.join(os.path.dirname(app_dir), "data", "gymsis.db")
    if os.path.exists(parent_data_db):
        return parent_data_db

    target_data = os.path.join(app_dir, "data")
    os.makedirs(target_data, exist_ok=True)
    return os.path.join(target_data, "gymsis.db")


def get_backups_dir() -> str:
    """Return folder for JSON and SQLite backups."""
    path = os.path.join(get_app_dir(), "backups")
    os.makedirs(path, exist_ok=True)
    return path
