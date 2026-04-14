import os
from datetime import datetime
import pandas as pd
from telegram import Update
from telegram.ext import ContextTypes

from database import cursor, conn
from helpers import (
    is_admin, set_state, get_state, get_years, flatten_subjects,
    total_lectures_count, admin_state_key, clear_admin_flow, get_subject,
    add_subject, add_lecture, delete_subject, edit_subject_price, delete_lecture,
    parse_subjects, get_subject_title, get_subjects_text, get_payment_label,
    get_user_row,
)
from keyboards import admin_panel_keyboard


def export_sales_to_excel():
    cursor.execute(
        """
        SELECT user_id, order_id, subjects, payment_method, amount, status, approved_at
        FROM sales
        ORDER BY id DESC
        """
    )
    rows = cursor.fetchall()
    columns = ["User ID", "Order ID", "Subjects", "Payment Method", "Amount", "Status", "Approved At"]
    df = pd.DataFrame(rows, columns=columns)
    os.makedirs("exports", exist_ok=True)
    filename = f"exports/sales_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df.to_excel(filename, index=False, engine="xlsxwriter")
    return filename


def _approved_subject_counts() -> dict[str, int]:
    counts = {key: 0 for key in flatten_subjects().keys()}
    cursor.execute("SELECT approved_subjects FROM users")
    for (approved_text,) in cursor.fetchall():
        for subject_key in parse_subjects(approved_text):
            counts[subject_key] = counts.get(subject_key, 0) + 1
    return counts


def _pending_subject_counts() -> dict[str, int]:
    counts = {key: 0 for key in flatten_subjects().keys()}
    cursor.execute("SELECT selected_subjects FROM users WHERE payment_status IN ('pending', 'reviewing')")
    for (selected_text,) in cursor.fetchall():
        for subject_key in parse_subjects(selected_text):
            counts[subject_key] = counts.get(subject_key, 0) + 1
    return counts


def _estimated_subject_revenue() -> dict[str, float]:
    subjects = flatten_subjects()
    counts = _approved_subject_counts()
    revenue = {}
    for subject_key, count in counts.items():
        revenue[subject_key] = float(subjects.get(subject_key, {}).get("price", 0)) * count
    return revenue


def _find_user_brief(text: str):
    text = text.strip()
    if not text:
        return None

    if text.isdigit():
        cursor.execute(
            "SELECT user_id, username, first_name FROM users WHERE user_id=?",
            (int(text),),
        )
        return cursor.fetchone()

    username = text[1:] if text.startswith("@") else text
    cursor.execute(
        "SELECT user_id, username, first_name FROM users WHERE LOWER(username)=LOWER(?)",
        (username,),
    )
    row = cursor.fetchone()
    if row:
        return row

    cursor.execute(
        "SELECT user_id, username, first_name FROM users WHERE first_name LIKE ? ORDER BY created_at DESC LIMIT 5",
        (f"%{text}%",),
    )
    rows = cursor.fetchall()
    return rows


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        await update.message.reply_text("🛠 لوحة الأدمن", reply_markup=admin_panel_keyboard())


async def admin_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = query.from_user.id

    if not is_admin(admin_id):
        await query.answer("غير مسموح", show_alert=True)
        return

    if query.data == "admin_stats":
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE approved_subjects IS NOT NULL AND approved_subjects != ''")
        paid_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM sales WHERE status='approved'")
        sales_count = cursor.fetchone()[0]
        cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM sales WHERE status='approved'")
        total_profit = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM watched")
        watched_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE payment_status IN ('pending', 'reviewing')")
        pending_count = cursor.fetchone()[0]

        counts = _approved_subject_counts()
        top_subjects = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:3]
        top_lines = []
        for subject_key, count in top_subjects:
            if count > 0:
                top_lines.append(f"• {get_subject_title(subject_key)}: {count} طالب")
        top_text = "\n".join(top_lines) if top_lines else "لا يوجد بعد"

        await query.message.reply_text(
            f"📊 إحصائيات البوت\n\n"
            f"👥 عدد المستخدمين: {total_users}\n"
            f"🎓 عدد الطلاب المقبولين: {paid_users}\n"
            f"🧾 عدد العمليات المقبولة: {sales_count}\n"
            f"📥 الطلبات المعلقة: {pending_count}\n"
            f"💵 إجمالي الأرباح: {total_profit}$\n"
            f"🎥 عدد المشاهدات المسجلة: {watched_count}\n"
            f"📚 عدد المواد الحالية: {len(flatten_subjects())}\n"
            f"▶️ عدد المحاضرات الحالية: {total_lectures_count()}\n\n"
            f"🏆 أكثر المواد طلبًا حالياً:\n{top_text}"
        )
        return

    if query.data == "admin_subject_report":
        subjects = flatten_subjects()
        approved_counts = _approved_subject_counts()
        pending_counts = _pending_subject_counts()
        revenue = _estimated_subject_revenue()

        lines = ["📚 تقرير المواد"]
        for subject_key, subject in subjects.items():
            lines.append(
                f"• {subject['title']}\n"
                f"  المفتاح: {subject_key}\n"
                f"  السعر: {subject.get('price', 0)}$\n"
                f"  الطلاب المقبولون: {approved_counts.get(subject_key, 0)}\n"
                f"  الطلبات المعلقة: {pending_counts.get(subject_key, 0)}\n"
                f"  الإيراد التقديري الحالي: {revenue.get(subject_key, 0)}$\n"
                f"  عدد المحاضرات: {len(subject.get('lectures', []))}"
            )
        await query.message.reply_text("\n\n".join(lines))
        return

    if query.data == "admin_students_per_subject":
        subjects = flatten_subjects()
        lines = ["👥 الطلاب حسب المادة"]
        cursor.execute("SELECT user_id, username, first_name, approved_subjects FROM users WHERE approved_subjects IS NOT NULL AND approved_subjects != ''")
        rows = cursor.fetchall()
        for subject_key, subject in subjects.items():
            students = []
            for row in rows:
                approved = parse_subjects(row[3])
                if subject_key in approved:
                    username = f"@{row[1]}" if row[1] else "بدون"
                    students.append(f"- {row[2] or 'بدون اسم'} | {username} | {row[0]}")
            lines.append(f"{subject['title']} ({len(students)} طالب)")
            lines.extend(students[:20] if students else ["- لا يوجد"])
            if len(students) > 20:
                lines.append(f"- ... وباقي {len(students) - 20} طالب")
            lines.append("")
        await query.message.reply_text("\n".join(lines))
        return

    if query.data == "admin_lookup_user":
        clear_admin_flow(admin_id)
        set_state(admin_state_key(admin_id, "step"), "await_lookup_user")
        await query.message.reply_text("🔎 أرسل ID الطالب أو اليوزر مع أو بدون @ للبحث عنه.")
        return

    if query.data == "admin_sales":
        cursor.execute(
            """
            SELECT user_id, order_id, subjects, payment_method, amount, status, approved_at
            FROM sales ORDER BY id DESC LIMIT 10
            """
        )
        rows = cursor.fetchall()
        if not rows:
            await query.message.reply_text("لا توجد عمليات مسجلة بعد.")
            return
        lines = ["💰 آخر 10 عمليات:"]
        for row in rows:
            lines.append(f"👤 {row[0]} | 🧾 {row[1]} | 📚 {row[2]} | 💳 {row[3]} | 💵 {row[4]}$ | 📌 {row[5]} | 🕒 {row[6]}")
        await query.message.reply_text("\n".join(lines))
        return

    if query.data == "admin_pending":
        cursor.execute(
            """
            SELECT user_id, order_id, selected_payment, selected_subjects, request_at, payment_status
            FROM users WHERE payment_status IN ('pending', 'reviewing')
            ORDER BY request_at DESC
            """
        )
        rows = cursor.fetchall()
        if not rows:
            await query.message.reply_text("لا توجد طلبات معلقة حالياً.")
            return
        lines = ["📥 الطلبات المعلقة:"]
        for row in rows:
            payment_label = get_payment_label(row[2])
            subject_text = get_subjects_text(parse_subjects(row[3]))
            lines.append(
                f"🧾 {row[1] or '-'} | 👤 {row[0]} | 💳 {payment_label} | 📌 {row[5]} | 🕒 {row[4]}\n"
                f"📚 {subject_text}"
            )
        await query.message.reply_text("\n\n".join(lines))
        return

    if query.data == "admin_export_excel":
        file_path = export_sales_to_excel()
        with open(file_path, "rb") as f:
            await context.bot.send_document(
                chat_id=admin_id,
                document=f,
                filename=os.path.basename(file_path),
                caption="📁 تم تصدير العمليات إلى ملف Excel"
            )
        return

    if query.data == "admin_list_subjects":
        years = get_years()
        lines = ["📚 المواد الحالية:"]
        for year_key, year in years.items():
            lines.append(year["title"])
            for subject_key, subject in year.get("subjects", {}).items():
                lines.append(
                    f"• المفتاح: {subject_key}\n"
                    f"  الاسم: {subject['title']}\n"
                    f"  السعر: {subject.get('price', 0)}$\n"
                    f"  عدد المحاضرات: {len(subject.get('lectures', []))}"
                )
            lines.append("")
        await query.message.reply_text("\n".join(lines))
        return

    if query.data == "admin_add_subject":
        clear_admin_flow(admin_id)
        set_state(admin_state_key(admin_id, "step"), "await_year_key")
        years_text = "\n".join([f"• {k} = {v['title']}" for k, v in get_years().items()])
        await query.message.reply_text(f"➕ إضافة مادة\n\nأرسل مفتاح السنة أولاً.\n\n{years_text}")
        return

    if query.data == "admin_delete_subject":
        clear_admin_flow(admin_id)
        set_state(admin_state_key(admin_id, "step"), "await_delete_subject_key")
        await query.message.reply_text("🗑 أرسل مفتاح المادة التي تريد حذفها.")
        return

    if query.data == "admin_edit_price":
        clear_admin_flow(admin_id)
        set_state(admin_state_key(admin_id, "step"), "await_edit_price")
        await query.message.reply_text("💵 أرسل بالشكل التالي:\nمفتاح_المادة السعر_الجديد\n\nمثال:\nhigh_math 35")
        return

    if query.data == "admin_add_lecture":
        clear_admin_flow(admin_id)
        set_state(admin_state_key(admin_id, "step"), "await_lecture_subject_key")
        await query.message.reply_text("🎥 أرسل مفتاح المادة التي تريد إضافة المحاضرة إليها.")
        return

    if query.data == "admin_delete_lecture":
        clear_admin_flow(admin_id)
        set_state(admin_state_key(admin_id, "step"), "await_delete_lecture")
        await query.message.reply_text("🗑 أرسل بالشكل التالي:\nمفتاح_المادة مفتاح_المحاضرة\n\nمثال:\nhigh_math lec2")
        return

    if query.data == "admin_broadcast":
        set_state("broadcast_pending", "1")
        await query.message.reply_text("📢 أرسل الآن نص الإعلان الذي تريد إرساله لكل الطلاب المقبولين.")
        return

    if query.data == "admin_back":
        await query.message.reply_text("🏠 رجعت من لوحة الأدمن.")
        return


async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    text = update.message.text.strip()
    step = get_state(admin_state_key(user_id, "step"))

    if step == "await_lookup_user":
        result = _find_user_brief(text)
        if not result:
            await update.message.reply_text("❌ لم أجد هذا الطالب.")
            return

        if isinstance(result, list):
            lines = ["🔎 نتائج البحث:"]
            for row in result:
                username = f"@{row[1]}" if row[1] else "بدون"
                lines.append(f"• {row[2] or 'بدون اسم'} | {username} | {row[0]}")
            await update.message.reply_text("\n".join(lines))
            clear_admin_flow(user_id)
            return

        target_id = result[0]
        username = f"@{result[1]}" if result[1] else "بدون"
        first_name = result[2] or "بدون اسم"
        data = get_user_row(target_id)
        await update.message.reply_text(
            f"👤 بطاقة الطالب\n\n"
            f"الاسم: {first_name}\n"
            f"اليوزر: {username}\n"
            f"ID: {target_id}\n"
            f"حالة الطلب: {data['payment_status']}\n"
            f"رقم الطلب: {data['order_id'] or 'لا يوجد'}\n"
            f"طريقة الدفع: {get_payment_label(data['selected_payment'])}\n\n"
            f"🛒 المواد المختارة:\n{get_subjects_text(data['selected_subjects'])}\n\n"
            f"🎓 المواد المفعلة:\n{get_subjects_text(data['approved_subjects'])}"
        )
        clear_admin_flow(user_id)
        return

    if step == "await_year_key":
        years = get_years()
        if text not in years:
            await update.message.reply_text("❌ مفتاح السنة غير صحيح.")
            return
        set_state(admin_state_key(user_id, "year_key"), text)
        set_state(admin_state_key(user_id, "step"), "await_subject_key")
        await update.message.reply_text("أرسل الآن مفتاح المادة بالإنكليزي بدون فراغات.\nمثال: calculus_1")
        return

    if step == "await_subject_key":
        if " " in text:
            await update.message.reply_text("❌ المفتاح يجب أن يكون بدون فراغات.")
            return
        if get_subject(text):
            await update.message.reply_text("❌ هذا المفتاح مستخدم مسبقاً.")
            return
        set_state(admin_state_key(user_id, "subject_key"), text)
        set_state(admin_state_key(user_id, "step"), "await_subject_title")
        await update.message.reply_text("أرسل الآن اسم المادة.")
        return

    if step == "await_subject_title":
        set_state(admin_state_key(user_id, "subject_title"), text)
        set_state(admin_state_key(user_id, "step"), "await_subject_description")
        await update.message.reply_text("أرسل الآن وصف المادة.")
        return

    if step == "await_subject_description":
        set_state(admin_state_key(user_id, "subject_description"), text)
        set_state(admin_state_key(user_id, "step"), "await_subject_price")
        await update.message.reply_text("أرسل الآن سعر المادة بالأرقام فقط.")
        return

    if step == "await_subject_price":
        try:
            price = float(text)
        except ValueError:
            await update.message.reply_text("❌ السعر غير صحيح.")
            return
        year_key = get_state(admin_state_key(user_id, "year_key"))
        subject_key = get_state(admin_state_key(user_id, "subject_key"))
        subject_title = get_state(admin_state_key(user_id, "subject_title"))
        subject_description = get_state(admin_state_key(user_id, "subject_description"))
        add_subject(year_key, subject_key, subject_title, subject_description, price)
        clear_admin_flow(user_id)
        await update.message.reply_text(
            f"✅ تم إضافة المادة بنجاح.\nالسنة: {year_key}\nالمفتاح: {subject_key}\nالاسم: {subject_title}\nالسعر: {price}$"
        )
        return

    if step == "await_delete_subject_key":
        if not delete_subject(text):
            await update.message.reply_text("❌ لم أجد هذه المادة.")
            return
        clear_admin_flow(user_id)
        await update.message.reply_text(f"✅ تم حذف المادة: {text}")
        return

    if step == "await_edit_price":
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("❌ الصيغة غير صحيحة.")
            return
        subject_key, price_text = parts
        try:
            new_price = float(price_text)
        except ValueError:
            await update.message.reply_text("❌ السعر غير صحيح.")
            return
        if not edit_subject_price(subject_key, new_price):
            await update.message.reply_text("❌ لم أجد هذه المادة.")
            return
        clear_admin_flow(user_id)
        await update.message.reply_text(f"✅ تم تعديل سعر المادة {subject_key} إلى {new_price}$")
        return

    if step == "await_lecture_subject_key":
        subject = get_subject(text)
        if not subject:
            await update.message.reply_text("❌ المادة غير موجودة.")
            return
        set_state(admin_state_key(user_id, "lecture_subject_key"), text)
        set_state(admin_state_key(user_id, "step"), "await_lecture_title")
        await update.message.reply_text(f"✅ المادة المختارة: {subject['title']}\nأرسل الآن عنوان المحاضرة.")
        return

    if step == "await_lecture_title":
        set_state(admin_state_key(user_id, "lecture_title"), text)
        set_state(admin_state_key(user_id, "step"), "await_lecture_video")
        await update.message.reply_text("📹 أرسل الآن ملف الفيديو نفسه.")
        return

    if step == "await_delete_lecture":
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("❌ الصيغة غير صحيحة.")
            return
        subject_key, lecture_key = parts
        if not delete_lecture(subject_key, lecture_key):
            await update.message.reply_text("❌ لم أجد هذه المحاضرة.")
            return
        clear_admin_flow(user_id)
        await update.message.reply_text(f"✅ تم حذف المحاضرة {lecture_key} من المادة {subject_key}")
        return


async def admin_video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.video:
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    step = get_state(admin_state_key(user_id, "step"))
    if step != "await_lecture_video":
        return

    subject_key = get_state(admin_state_key(user_id, "lecture_subject_key"))
    lecture_title = get_state(admin_state_key(user_id, "lecture_title"))
    file_id = update.message.video.file_id

    if not subject_key or not lecture_title:
        clear_admin_flow(user_id)
        await update.message.reply_text("⚠️ حدث خلل في البيانات. أعد العملية.")
        return

    lecture_key = add_lecture(subject_key, lecture_title, file_id, is_new=True)
    clear_admin_flow(user_id)
    await update.message.reply_text(
        f"✅ تم إضافة المحاضرة بنجاح.\nالمادة: {get_subject(subject_key)['title']}\nمفتاح المحاضرة: {lecture_key}\nالعنوان: {lecture_title}"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM sales WHERE status='approved'")
    total_profit = cursor.fetchone()[0]
    await update.message.reply_text(f"👥 المستخدمون: {total_users}\n💵 إجمالي الأرباح: {total_profit}$")


async def sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cursor.execute("SELECT user_id, order_id, subjects, payment_method, amount, status, approved_at FROM sales ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("لا توجد عمليات مسجلة بعد.")
        return
    lines = ["💰 آخر 10 عمليات:"]
    for row in rows:
        lines.append(f"👤 {row[0]} | 🧾 {row[1]} | 📚 {row[2]} | 💳 {row[3]} | 💵 {row[4]}$ | 📌 {row[5]} | 🕒 {row[6]}")
    await update.message.reply_text("\n".join(lines))


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("استخدم الأمر هكذا:\n/broadcast نص الرسالة")
        return
    message = " ".join(context.args)
    cursor.execute("SELECT user_id FROM users WHERE approved_subjects IS NOT NULL AND approved_subjects != ''")
    users = [row[0] for row in cursor.fetchall()]
    sent = 0
    for user_id in users:
        try:
            await context.bot.send_message(user_id, f"📢 إعلان جديد\n\n{message}")
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ تم إرسال الإعلان إلى {sent} مستخدم.")
