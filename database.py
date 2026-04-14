
from __future__ import annotations

import os
import sqlite3

DEFAULT_RENDER_DATA_DIR = "/opt/render/project/data"
APP_DATA_DIR = os.getenv(
    "APP_DATA_DIR",
    DEFAULT_RENDER_DATA_DIR if os.path.isdir(DEFAULT_RENDER_DATA_DIR) else os.getcwd(),
)
os.makedirs(APP_DATA_DIR, exist_ok=True)

DB_PATH = os.getenv("DB_PATH", os.path.join(APP_DATA_DIR, "users.db"))

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("PRAGMA journal_mode=WAL")
cursor.execute("PRAGMA synchronous=NORMAL")
cursor.execute("PRAGMA foreign_keys=ON")
cursor.execute("PRAGMA busy_timeout=5000")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    payment_status TEXT DEFAULT 'none',
    order_id TEXT,
    proof_message_id INTEGER,
    admin_message_id INTEGER,
    selected_payment TEXT,
    selected_subjects TEXT DEFAULT '',
    approved_subjects TEXT DEFAULT '',
    support_pending INTEGER DEFAULT 0,
    last_lecture_compound TEXT,
    created_at TEXT,
    request_at TEXT,
    approved_at TEXT,
    form_step TEXT,
    cash_full_name TEXT,
    cash_phone TEXT,
    cash_amount TEXT,
    cash_subject_count TEXT,
    cash_subject_names TEXT,
    security_pin TEXT,
    is_verified INTEGER DEFAULT 0,
    session_expires_at TEXT,
    pin_attempts INTEGER DEFAULT 0,
    locked_until TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS watched(
    user_id INTEGER,
    subject_key TEXT,
    lecture_key TEXT,
    watched_at TEXT,
    UNIQUE(user_id, subject_key, lecture_key)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS sales(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    order_id TEXT,
    subjects TEXT,
    payment_method TEXT,
    amount REAL DEFAULT 0,
    status TEXT,
    approved_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_state(
    key TEXT PRIMARY KEY,
    value TEXT
)
""")
conn.commit()

def ensure_column(table_name: str, column_name: str, definition: str):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
        conn.commit()

ensure_column("users", "selected_subjects", "TEXT DEFAULT ''")
ensure_column("users", "approved_subjects", "TEXT DEFAULT ''")
ensure_column("users", "last_lecture_compound", "TEXT")
ensure_column("users", "form_step", "TEXT")
ensure_column("users", "cash_full_name", "TEXT")
ensure_column("users", "cash_phone", "TEXT")
ensure_column("users", "cash_amount", "TEXT")
ensure_column("users", "cash_subject_count", "TEXT")
ensure_column("users", "cash_subject_names", "TEXT")
ensure_column("users", "security_pin", "TEXT")
ensure_column("users", "is_verified", "INTEGER DEFAULT 0")
ensure_column("users", "session_expires_at", "TEXT")
ensure_column("users", "pin_attempts", "INTEGER DEFAULT 0")
ensure_column("users", "locked_until", "TEXT")
ensure_column("sales", "subjects", "TEXT")
ensure_column("sales", "amount", "REAL DEFAULT 0")
