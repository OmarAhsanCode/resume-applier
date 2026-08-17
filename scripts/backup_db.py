#!/usr/bin/env python3
"""
scripts/backup_db.py - Safe online backup tool for SQLite database.
Uses sqlite3.Connection.backup to perform consistent, non-blocking online backups.
"""

import os
import sys
import sqlite3
import shutil
from datetime import datetime

# Adjust path to import database module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import database

def backup_database(destination_dir: str = "backups", max_retention: int = 10) -> str:
    """
    Safely creates a timestamped online backup of the SQLite database.
    Retains up to max_retention latest backup files.
    """
    os.makedirs(destination_dir, exist_ok=True)
    db_path = database.DB_PATH

    if not os.path.exists(db_path):
        print(f"[BACKUP] Source database file '{db_path}' does not exist yet. Nothing to backup.")
        return ""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"jobs_backup_{timestamp}.db"
    backup_path = os.path.join(destination_dir, backup_filename)

    print(f"[BACKUP] Starting online backup from '{db_path}' to '{backup_path}'...")
    
    src_conn = database.get_connection()
    dst_conn = sqlite3.connect(backup_path)

    try:
        # Non-blocking page-by-page backup
        with dst_conn:
            src_conn.backup(dst_conn, pages=100)
        print(f"[BACKUP] Backup completed successfully: {backup_path} ({os.path.getsize(backup_path)} bytes)")
    finally:
        dst_conn.close()
        src_conn.close()

    # Retention enforcement
    existing_backups = sorted([
        os.path.join(destination_dir, f)
        for f in os.listdir(destination_dir)
        if f.startswith("jobs_backup_") and f.endswith(".db")
    ])

    if len(existing_backups) > max_retention:
        to_delete = existing_backups[:-max_retention]
        for old_backup in to_delete:
            try:
                os.remove(old_backup)
                print(f"[BACKUP] Pruned old backup: {old_backup}")
            except OSError as e:
                print(f"[BACKUP] Warning: Could not delete old backup {old_backup}: {e}")

    return backup_path

if __name__ == "__main__":
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "backups"
    backup_database(target_dir)
