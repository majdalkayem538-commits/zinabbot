from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from helpers import calc_total, get_years, get_subject, get_subject_title

def main_menu_keyboard(has_approved: bool, session_valid: bool):
    rows = [
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="menu_home")],
        [InlineKeyboardButton("📚 المواد والأسعار", callback_data="menu_subjects")],
        [InlineKeyboardButton("🛒 السلة والدفع", callback_data="menu_checkout")],
        [InlineKeyboardButton("📋 طلباتي", callback_data="menu_orders")],
        [InlineKeyboardButton("🎓 موادي المسجلة", callback_data="menu_my_subjects")],
    ]
    if has_approved:
        rows.append([InlineKeyboardButton("▶️ أكمل من آخر محاضرة", callback_data="continue_last")])
        rows.append([InlineKeyboardButton("🔐 قفل الجلسة", callback_data="lock_session")])
        if not session_valid:
            rows.append([InlineKeyboardButton("🔑 تسجيل دخول للمحتوى", callback_data="menu_security")])
    rows += [
        [InlineKeyboardButton("❓ الأسئلة الشائعة", callback_data="menu_faq")],
        [InlineKeyboardButton("📩 الدعم", callback_data="menu_support")],
    ]
    return InlineKeyboardMarkup(rows)


def years_keyboard(selected_subjects: list[str]):
    rows = []
    years = get_years()
    for year_key, year in years.items():
        count = sum(1 for key in year.get("subjects", {}) if key in selected_subjects)
        label = f"{year['title']} ({count})" if count else year["title"]
        rows.append([InlineKeyboardButton(label, callback_data=f"year_open|{year_key}")])
    total = calc_total(selected_subjects)
    rows.append([InlineKeyboardButton(f"💳 متابعة الدفع ({len(selected_subjects)} مادة - {total}$)", callback_data="menu_checkout")])
    rows.append([InlineKeyboardButton("🗑 إفراغ السلة", callback_data="clear_selection")])
    rows.append([InlineKeyboardButton("🏠 رجوع", callback_data="menu_home")])
    return InlineKeyboardMarkup(rows)


def year_subjects_keyboard(year_key: str, selected_subjects: list[str]):
    years = get_years()
    year = years.get(year_key)
    rows = []
    if year:
        for subject_key, subject in year.get("subjects", {}).items():
            mark = "✅" if subject_key in selected_subjects else "➕"
            rows.append([
                InlineKeyboardButton(
                    f"{mark} {subject['title']} — {subject.get('price', 0)}$",
                    callback_data=f"subject_toggle|{subject_key}",
                )
            ])
            rows.append([InlineKeyboardButton("ℹ️ تفاصيل المادة", callback_data=f"subject_info|{subject_key}")])
    rows.append([InlineKeyboardButton("⬅️ رجوع للمواد", callback_data="menu_subjects")])
    return InlineKeyboardMarkup(rows)



def orders_keyboard(has_approved: bool):
    rows = [
        [InlineKeyboardButton("🛒 السلة والدفع", callback_data="menu_checkout")],
    ]
    if has_approved:
        rows.append([InlineKeyboardButton("🎓 موادي المسجلة", callback_data="menu_my_subjects")])
    rows.append([InlineKeyboardButton("🏠 رجوع", callback_data="menu_home")])
    return InlineKeyboardMarkup(rows)


def payment_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("سيريتل كاش", callback_data="pay_syriatel")],
        [InlineKeyboardButton("شام كاش", callback_data="pay_sham")],
        [InlineKeyboardButton("حوالة نقدية", callback_data="pay_cash_transfer")],
        [InlineKeyboardButton("نقداً", callback_data="pay_cash_in_person")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="menu_subjects")],
    ])


def approved_subjects_keyboard(approved_subjects: list[str]):
    rows = []
    for key in approved_subjects:
        rows.append([InlineKeyboardButton(get_subject_title(key), callback_data=f"open_subject|{key}")])
    rows.append([InlineKeyboardButton("🏠 رجوع", callback_data="menu_home")])
    return InlineKeyboardMarkup(rows)


def lectures_keyboard(subject_key: str):
    rows = []
    subject = get_subject(subject_key)
    if subject:
        for lecture in subject.get("lectures", []):
            label = lecture["title"] + (" 🆕" if lecture.get("is_new") else "")
            rows.append([InlineKeyboardButton(label, callback_data=f"lecture|{subject_key}|{lecture['key']}")])
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="menu_my_subjects")])
    return InlineKeyboardMarkup(rows)


def admin_panel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 الإحصائيات العامة", callback_data="admin_stats")],
        [InlineKeyboardButton("📚 تقرير المواد", callback_data="admin_subject_report")],
        [InlineKeyboardButton("👥 الطلاب حسب المادة", callback_data="admin_students_per_subject")],
        [InlineKeyboardButton("🔎 بحث عن طالب", callback_data="admin_lookup_user")],
        [InlineKeyboardButton("💰 آخر العمليات", callback_data="admin_sales")],
        [InlineKeyboardButton("📥 الطلبات المعلقة", callback_data="admin_pending")],
        [InlineKeyboardButton("📁 تصدير Excel", callback_data="admin_export_excel")],
        [InlineKeyboardButton("📚 عرض المواد", callback_data="admin_list_subjects")],
        [InlineKeyboardButton("➕ إضافة مادة", callback_data="admin_add_subject")],
        [InlineKeyboardButton("🗑 حذف مادة", callback_data="admin_delete_subject")],
        [InlineKeyboardButton("💵 تعديل سعر مادة", callback_data="admin_edit_price")],
        [InlineKeyboardButton("🎥 إضافة محاضرة", callback_data="admin_add_lecture")],
        [InlineKeyboardButton("🗑 حذف محاضرة", callback_data="admin_delete_lecture")],
        [InlineKeyboardButton("📢 إرسال إعلان", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🏠 رجوع", callback_data="admin_back")],
    ])
