
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, UTC
import hashlib
import json
import os
import random

from config import ADMIN_ID, DEFAULT_CATALOG, PAYMENT_LABELS, DYNAMIC_CONTENT_FILE, SESSION_MINUTES
from database import cursor, conn

def now_utc() -> datetime:
    return datetime.now(UTC)

def now_str() -> str:
    return now_utc().strftime("%Y-%m-%d %H:%M:%S UTC")

def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=UTC)
    except ValueError:
        return None

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def in_private_chat(update) -> bool:
    chat = getattr(update, "effective_chat", None)
    return bool(chat and chat.type == "private")

def generate_order_id() -> str:
    return f"ORD-{random.randint(10000, 99999)}"

def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()

def set_state(key: str, value: str):
    cursor.execute("INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)", (key, value))
    conn.commit()

def get_state(key: str):
    cursor.execute("SELECT value FROM bot_state WHERE key=?", (key,))
    row = cursor.fetchone()
    return row[0] if row else None

def clear_state(key: str):
    cursor.execute("DELETE FROM bot_state WHERE key=?", (key,))
    conn.commit()

def ensure_user(user_id: int, username: str | None, first_name: str | None) -> None:
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, created_at) VALUES (?, ?, ?, ?)",
        (user_id, username, first_name, now_str()),
    )
    cursor.execute(
        "UPDATE users SET username=?, first_name=? WHERE user_id=?",
        (username, first_name, user_id),
    )
    conn.commit()

def parse_subjects(text: str | None) -> list[str]:
    if not text:
        return []
    return [item for item in text.split(",") if item]

def join_subjects(subjects: list[str]) -> str:
    unique: list[str] = []
    for subject in subjects:
        if subject and subject not in unique:
            unique.append(subject)
    return ",".join(unique)

def get_payment_label(payment_key: str | None) -> str:
    return PAYMENT_LABELS.get(payment_key or "", "غير محدد")

def ensure_dynamic_content_file():
    if not os.path.exists(DYNAMIC_CONTENT_FILE):
        with open(DYNAMIC_CONTENT_FILE, "w", encoding="utf-8") as f:
            json.dump({"years": {}}, f, ensure_ascii=False, indent=2)

def load_dynamic_content() -> dict:
    ensure_dynamic_content_file()
    with open(DYNAMIC_CONTENT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_dynamic_content(data: dict):
    with open(DYNAMIC_CONTENT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_catalog() -> dict:
    catalog = deepcopy(DEFAULT_CATALOG)
    dynamic = load_dynamic_content().get("years", {})
    for year_key, year_data in dynamic.items():
        if year_key not in catalog:
            catalog[year_key] = year_data
            continue
        if "title" in year_data:
            catalog[year_key]["title"] = year_data["title"]
        catalog[year_key].setdefault("subjects", {})
        for subject_key, subject_data in year_data.get("subjects", {}).items():
            catalog[year_key]["subjects"][subject_key] = subject_data
    return catalog

def flatten_subjects() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for year_key, year in get_catalog().items():
        for subject_key, subject in year.get("subjects", {}).items():
            row = deepcopy(subject)
            row["year_key"] = year_key
            row["year_title"] = year.get("title", year_key)
            out[subject_key] = row
    return out

def get_years() -> dict:
    return get_catalog()

def get_subject(subject_key: str):
    return flatten_subjects().get(subject_key)

def get_subject_title(subject_key: str) -> str:
    subject = get_subject(subject_key)
    return subject["title"] if subject else "غير محددة"

def get_subject_price(subject_key: str) -> float:
    subject = get_subject(subject_key)
    return float(subject.get("price", 0)) if subject else 0.0

def get_subjects_text(subject_keys: list[str]) -> str:
    if not subject_keys:
        return "لا يوجد"
    lines = []
    subjects = flatten_subjects()
    for key in subject_keys:
        if key in subjects:
            subject = subjects[key]
            lines.append(f"• {subject['title']} — {subject.get('price', 0)}$")
    return "\n".join(lines) if lines else "لا يوجد"

def calc_total(subject_keys: list[str]) -> float:
    return sum(get_subject_price(key) for key in subject_keys)

def find_lecture(subject_key: str, lecture_key: str):
    subject = get_subject(subject_key)
    if not subject:
        return None
    for lecture in subject.get("lectures", []):
        if lecture["key"] == lecture_key:
            return lecture
    return None

def total_lectures_count() -> int:
    return sum(len(subject.get("lectures", [])) for subject in flatten_subjects().values())

def add_subject(year_key: str, subject_key: str, title: str, description: str, price: float):
    data = load_dynamic_content()
    data.setdefault("years", {})
    if year_key not in data["years"]:
        years = get_years()
        title_year = years.get(year_key, {}).get("title", year_key)
        data["years"][year_key] = {"title": title_year, "subjects": {}}
    data["years"][year_key].setdefault("subjects", {})
    data["years"][year_key]["subjects"][subject_key] = {
        "title": title,
        "description": description,
        "price": float(price),
        "lectures": [],
    }
    save_dynamic_content(data)

def delete_subject(subject_key: str) -> bool:
    data = load_dynamic_content()
    changed = False
    for year_data in data.get("years", {}).values():
        subjects = year_data.get("subjects", {})
        if subject_key in subjects:
            del subjects[subject_key]
            changed = True
    if changed:
        save_dynamic_content(data)
    return changed

def edit_subject_price(subject_key: str, new_price: float) -> bool:
    data = load_dynamic_content()
    found = False
    for year_key, year in get_catalog().items():
        if subject_key in year.get("subjects", {}):
            data.setdefault("years", {}).setdefault(year_key, {"title": year.get("title", year_key), "subjects": {}})
            data["years"][year_key].setdefault("subjects", {})
            subj = deepcopy(year["subjects"][subject_key])
            subj["price"] = float(new_price)
            data["years"][year_key]["subjects"][subject_key] = subj
            found = True
            break
    if found:
        save_dynamic_content(data)
    return found

def add_lecture(subject_key: str, title: str, file_id: str, is_new: bool = True) -> str:
    data = load_dynamic_content()
    years = get_catalog()
    for year_key, year in years.items():
        if subject_key in year.get("subjects", {}):
            data.setdefault("years", {}).setdefault(year_key, {"title": year.get("title", year_key), "subjects": {}})
            data["years"][year_key].setdefault("subjects", {})
            subj = deepcopy(year["subjects"][subject_key])
            lectures = subj.setdefault("lectures", [])
            lecture_key = f"lec{len(lectures) + 1}"
            lectures.append({"key": lecture_key, "title": title, "file_id": file_id, "is_new": is_new})
            data["years"][year_key]["subjects"][subject_key] = subj
            save_dynamic_content(data)
            return lecture_key
    raise ValueError("المادة غير موجودة")

def delete_lecture(subject_key: str, lecture_key: str) -> bool:
    data = load_dynamic_content()
    years = get_catalog()
    for year_key, year in years.items():
        if subject_key in year.get("subjects", {}):
            subj = deepcopy(year["subjects"][subject_key])
            lectures = subj.get("lectures", [])
            new_lectures = [lec for lec in lectures if lec["key"] != lecture_key]
            if len(new_lectures) == len(lectures):
                return False
            # reindex keys
            for idx, lecture in enumerate(new_lectures, start=1):
                lecture["key"] = f"lec{idx}"
            data.setdefault("years", {}).setdefault(year_key, {"title": year.get("title", year_key), "subjects": {}})
            data["years"][year_key].setdefault("subjects", {})
            subj["lectures"] = new_lectures
            data["years"][year_key]["subjects"][subject_key] = subj
            save_dynamic_content(data)
            return True
    return False

def get_user_row(user_id: int) -> dict:
    cursor.execute("""
        SELECT payment_status, order_id, selected_payment, selected_subjects, approved_subjects,
               support_pending, last_lecture_compound, form_step, cash_full_name, cash_phone,
               cash_amount, cash_subject_count, cash_subject_names, security_pin, is_verified,
               session_expires_at, pin_attempts, locked_until, proof_message_id, admin_message_id
        FROM users WHERE user_id=?
    """, (user_id,))
    row = cursor.fetchone()

    if not row:
        return {
            "payment_status": "none",
            "order_id": None,
            "selected_payment": None,
            "selected_subjects": [],
            "approved_subjects": [],
            "support_pending": 0,
            "last_lecture_compound": None,
            "form_step": None,
            "cash_full_name": None,
            "cash_phone": None,
            "cash_amount": None,
            "cash_subject_count": None,
            "cash_subject_names": None,
            "security_pin": None,
            "is_verified": 0,
            "session_expires_at": None,
            "pin_attempts": 0,
            "locked_until": None,
            "proof_message_id": None,
            "admin_message_id": None,
        }

    return {
        "payment_status": row["payment_status"],
        "order_id": row["order_id"],
        "selected_payment": row["selected_payment"],
        "selected_subjects": parse_subjects(row["selected_subjects"]),
        "approved_subjects": parse_subjects(row["approved_subjects"]),
        "support_pending": row["support_pending"],
        "last_lecture_compound": row["last_lecture_compound"],
        "form_step": row["form_step"],
        "cash_full_name": row["cash_full_name"],
        "cash_phone": row["cash_phone"],
        "cash_amount": row["cash_amount"],
        "cash_subject_count": row["cash_subject_count"],
        "cash_subject_names": row["cash_subject_names"],
        "security_pin": row["security_pin"],
        "is_verified": row["is_verified"],
        "session_expires_at": row["session_expires_at"],
        "pin_attempts": row["pin_attempts"],
        "locked_until": row["locked_until"],
        "proof_message_id": row["proof_message_id"],
        "admin_message_id": row["admin_message_id"],
    }
def user_has_any_approved_subject(user_id: int) -> bool:
    return len(get_user_row(user_id)["approved_subjects"]) > 0

def subject_is_approved_for_user(user_id: int, subject_key: str) -> bool:
    return subject_key in get_user_row(user_id)["approved_subjects"]

def lecture_allowed_by_order(user_id: int, subject_key: str, lecture_key: str) -> bool:
    subject = get_subject(subject_key)
    if not subject:
        return False
    lectures = subject.get("lectures", [])
    idx = next((i for i, lec in enumerate(lectures) if lec["key"] == lecture_key), None)
    if idx is None:
        return False
    if idx == 0:
        return True
    previous_key = lectures[idx - 1]["key"]
    cursor.execute(
        "SELECT 1 FROM watched WHERE user_id=? AND subject_key=? AND lecture_key=?",
        (user_id, subject_key, previous_key),
    )
    return cursor.fetchone() is not None

def is_session_valid(user_id: int) -> bool:
    row = get_user_row(user_id)
    if not row["security_pin"] or row["is_verified"] != 1:
        return False
    expires = parse_dt(row["session_expires_at"])
    return bool(expires and expires > now_utc())

def require_security(user_id: int) -> bool:
    return user_has_any_approved_subject(user_id)

def start_session(user_id: int):
    expires_at = (now_utc() + timedelta(minutes=SESSION_MINUTES)).strftime("%Y-%m-%d %H:%M:%S UTC")
    cursor.execute(
        "UPDATE users SET is_verified=1, session_expires_at=?, pin_attempts=0 WHERE user_id=?",
        (expires_at, user_id),
    )
    conn.commit()

def lock_session(user_id: int):
    cursor.execute(
        "UPDATE users SET is_verified=0, session_expires_at=NULL WHERE user_id=?",
        (user_id,),
    )
    conn.commit()

def is_locked_out(user_id: int) -> tuple[bool, str | None]:
    row = get_user_row(user_id)
    locked_until = parse_dt(row["locked_until"])
    if locked_until and locked_until > now_utc():
        return True, locked_until.strftime("%H:%M")
    return False, None

def record_failed_pin(user_id: int) -> int:
    row = get_user_row(user_id)
    attempts = int(row["pin_attempts"] or 0) + 1
    locked_until = row["locked_until"]
    if attempts >= 5:
        locked_until = (now_utc() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S UTC")
        attempts = 0
    cursor.execute(
        "UPDATE users SET pin_attempts=?, locked_until=? WHERE user_id=?",
        (attempts, locked_until, user_id),
    )
    conn.commit()
    return attempts

def clear_failed_pin(user_id: int):
    cursor.execute(
        "UPDATE users SET pin_attempts=0, locked_until=NULL WHERE user_id=?",
        (user_id,),
    )
    conn.commit()

def admin_state_key(user_id: int, name: str) -> str:
    return f"admin_{user_id}_{name}"

def clear_admin_flow(user_id: int):
    keys = [
        "step", "year_key", "subject_key", "subject_title", "subject_description",
        "lecture_subject_key", "lecture_title", "delete_subject_key", "edit_subject_key",
        "delete_lecture_subject_key"
    ]
    for key in keys:
        clear_state(admin_state_key(user_id, key))
