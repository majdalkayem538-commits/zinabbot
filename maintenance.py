from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler
import os
import shutil
from datetime import datetime, timedelta, UTC

from config import (
    ADMIN_ID,
    APP_DATA_DIR,
    BACKUP_DIR,
    BACKUP_INTERVAL_MINUTES,
    DYNAMIC_CONTENT_FILE,
    ERROR_NOTIFY_COOLDOWN_MINUTES,
    LOG_FILE,
    PENDING_REMINDER_REPEAT_MINUTES,
)
from database import DB_PATH, cursor, conn
from helpers import now_utc, now_str, parse_dt, set_state, get_state

logger = logging.getLogger("workbot")


def setup_logging() -> None:
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if root.handlers:
        return

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    logger.info("Logging configured")


def _safe_copy(src: str, dst: str) -> None:
    if os.path.exists(src):
        shutil.copy2(src, dst)


def _prune_old_backups(max_files: int = 24) -> None:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    files = sorted(
        [os.path.join(BACKUP_DIR, name) for name in os.listdir(BACKUP_DIR)],
        key=os.path.getmtime,
        reverse=True,
    )
    for path in files[max_files:]:
        try:
            os.remove(path)
        except OSError:
            logger.exception("Failed removing old backup: %s", path)


def create_backup() -> None:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    db_backup = os.path.join(BACKUP_DIR, f"users_{stamp}.db")
    latest_db = os.path.join(BACKUP_DIR, "users_latest.db")
    _safe_copy(DB_PATH, db_backup)
    _safe_copy(DB_PATH, latest_db)

    if os.path.exists(DYNAMIC_CONTENT_FILE):
        dyn_backup = os.path.join(BACKUP_DIR, f"dynamic_content_{stamp}.json")
        latest_dyn = os.path.join(BACKUP_DIR, "dynamic_content_latest.json")
        _safe_copy(DYNAMIC_CONTENT_FILE, dyn_backup)
        _safe_copy(DYNAMIC_CONTENT_FILE, latest_dyn)

    _prune_old_backups()
    logger.info("Backup created")


def cleanup_transient_state() -> None:
    changed = 0
    cursor.execute("SELECT user_id, session_expires_at, locked_until FROM users")
    for user_id, session_expires_at, locked_until in cursor.fetchall():
        expires = parse_dt(session_expires_at)
        lock_until_dt = parse_dt(locked_until)
        if expires and expires <= now_utc():
            cursor.execute(
                "UPDATE users SET is_verified=0, session_expires_at=NULL WHERE user_id=?",
                (user_id,),
            )
            changed += 1
        if lock_until_dt and lock_until_dt <= now_utc():
            cursor.execute(
                "UPDATE users SET locked_until=NULL WHERE user_id=?",
                (user_id,),
            )
            changed += 1
    if changed:
        conn.commit()
        logger.info("Transient cleanup touched %s rows", changed)


def _pending_summary_text() -> str | None:
    cursor.execute(
        """
        SELECT COUNT(*) AS count, MIN(request_at) AS oldest
        FROM users
        WHERE payment_status IN ('pending', 'reviewing')
        """
    )
    row = cursor.fetchone()
    pending_count = int(row[0] or 0)
    if pending_count <= 0:
        return None

    oldest = row[1] or "غير محدد"
    cursor.execute(
        """
        SELECT order_id, user_id, username, selected_payment, request_at
        FROM users
        WHERE payment_status IN ('pending', 'reviewing')
        ORDER BY request_at ASC
        LIMIT 3
        """
    )
    details = []
    for order_id, user_id, username, payment_method, request_at in cursor.fetchall():
        details.append(
            f"• {order_id or '-'} | {user_id} | @{username or 'بدون'} | {payment_method or '-'} | {request_at or '-'}"
        )
    return (
        f"⏰ تذكير بالطلبات المعلقة\n\n"
        f"📥 العدد الحالي: {pending_count}\n"
        f"🕒 أقدم طلب منذ: {oldest}\n\n"
        f"أقدم 3 طلبات:\n" + "\n".join(details)
    )


async def maybe_send_pending_reminder(application, force: bool = False) -> None:
    summary = _pending_summary_text()
    if not summary:
        set_state("pending_last_summary", "")
        return

    now = now_utc()
    last_sent = parse_dt(get_state("pending_last_sent_at"))
    last_summary = get_state("pending_last_summary") or ""
    enough_time = not last_sent or now >= last_sent + timedelta(minutes=PENDING_REMINDER_REPEAT_MINUTES)

    if force or summary != last_summary or enough_time:
        await application.bot.send_message(ADMIN_ID, summary)
        set_state("pending_last_sent_at", now_str())
        set_state("pending_last_summary", summary)
        logger.info("Pending reminder sent")


async def send_startup_notice(application) -> None:
    try:
        await application.bot.send_message(ADMIN_ID, "✅ البوت اشتغل بنجاح على Render وهو جاهز الآن.")
    except Exception:
        logger.exception("Failed to send startup notice")


async def periodic_maintenance(application) -> None:
    logger.info("Periodic maintenance loop started")
    last_backup = None
    while True:
        try:
            cleanup_transient_state()
            now = now_utc()
            if last_backup is None or now >= last_backup + timedelta(minutes=BACKUP_INTERVAL_MINUTES):
                create_backup()
                last_backup = now
            await maybe_send_pending_reminder(application)
        except Exception:
            logger.exception("Periodic maintenance failed")
        await asyncio.sleep(300)


async def error_handler(update, context) -> None:
    logger.exception("Unhandled bot error", exc_info=context.error)
    now = now_utc()
    last_sent = parse_dt(get_state("error_last_sent_at"))
    if last_sent and now < last_sent + timedelta(minutes=ERROR_NOTIFY_COOLDOWN_MINUTES):
        return
    try:
        summary = str(context.error)[:800] if context.error else "Unknown error"
        await context.bot.send_message(
            ADMIN_ID,
            f"🚨 صار خطأ داخل البوت\n\n{summary}"
        )
        set_state("error_last_sent_at", now_str())
    except Exception:
        logger.exception("Failed to notify admin about error")
