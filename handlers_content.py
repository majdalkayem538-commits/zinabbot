import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import ADMIN_ID, FAQ_TEXT, PAYMENT_TEXTS, WELCOME_TEXT, MIN_PIN_LENGTH
from database import cursor, conn
from helpers import (
    ensure_user, get_user_row, user_has_any_approved_subject, get_subjects_text,
    calc_total, generate_order_id, get_payment_label, now_str, is_admin,
    get_state, get_subject, subject_is_approved_for_user, find_lecture,
    get_subject_title, lecture_allowed_by_order, join_subjects, is_session_valid,
    require_security, hash_pin, start_session, lock_session, is_locked_out,
    record_failed_pin, clear_failed_pin, in_private_chat
)
from keyboards import (
    main_menu_keyboard, years_keyboard, year_subjects_keyboard, payment_keyboard,
    approved_subjects_keyboard, lectures_keyboard
)


def security_intro_text(user_id: int) -> str:
    row = get_user_row(user_id)
    if not row["security_pin"]:
        return (
            "🔐 لحماية المحتوى، يجب إنشاء PIN أمان قبل دخول المواد.\n\n"
            f"أرسل الآن PIN مكوّن من {MIN_PIN_LENGTH} أرقام أو أكثر.\n"
            "مثال: 2580"
        )
    return "🔑 أرسل PIN الأمان للدخول إلى المواد والمحاضرات."


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not in_private_chat(update):
        return
    user = update.effective_user
    ensure_user(user.id, user.username, user.first_name)
    await update.message.reply_text(
        WELCOME_TEXT,
        reply_markup=main_menu_keyboard(
            user_has_any_approved_subject(user.id),
            is_session_valid(user.id),
        ),
    )


async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not in_private_chat(update):
        await query.message.reply_text("❌ استخدم البوت ضمن محادثة خاصة فقط.")
        return

    user = query.from_user
    ensure_user(user.id, user.username, user.first_name)
    row = get_user_row(user.id)

    if query.data == "menu_home":
        approved_text = get_subjects_text(row["approved_subjects"])
        selected_text = get_subjects_text(row["selected_subjects"])
        secure_text = "مفعّلة" if is_session_valid(user.id) else "غير مفعّلة"
        await query.message.reply_text(
            f"✨ الرئيسية\n\n🔐 حالة الحماية: {secure_text}\n\n📚 المواد المقبولة لديك:\n{approved_text}\n\n🛒 المواد المختارة حالياً:\n{selected_text}",
            reply_markup=main_menu_keyboard(
                user_has_any_approved_subject(user.id),
                is_session_valid(user.id),
            ),
        )
        return

    if query.data == "menu_subjects":
        await query.message.reply_text(
            "📚 المواد مرتبة حسب السنوات\n\nاختر السنة لعرض المواد والأسعار:",
            reply_markup=years_keyboard(row["selected_subjects"]),
        )
        return

    if query.data == "menu_checkout":
        if not row["selected_subjects"]:
            await query.message.reply_text("⚠️ لم تختر أي مادة بعد.")
            return
        total = calc_total(row["selected_subjects"])
        await query.message.reply_text(
            f"🛒 المواد المختارة:\n{get_subjects_text(row['selected_subjects'])}\n\n💵 الإجمالي: {total}$\n\nاختر طريقة الدفع:",
            reply_markup=payment_keyboard(),
        )
        return

    if query.data == "clear_selection":
        cursor.execute("UPDATE users SET selected_subjects='' WHERE user_id=?", (user.id,))
        conn.commit()
        await query.message.reply_text(
            "🗑 تم إفراغ المواد المختارة.",
            reply_markup=years_keyboard([]),
        )
        return

    if query.data == "menu_my_subjects":
        if not row["approved_subjects"]:
            await query.message.reply_text("❌ لا يوجد لديك مواد مفعلة بعد.")
            return
        if require_security(user.id) and not is_session_valid(user.id):
            await query.message.reply_text(security_intro_text(user.id))
            return
        await query.message.reply_text(
            "🎓 المواد المفعلة لك:",
            reply_markup=approved_subjects_keyboard(row["approved_subjects"]),
        )
        return

    if query.data == "menu_security":
        if not row["approved_subjects"]:
            await query.message.reply_text("ℹ️ يتفعّل PIN الأمان بعد قبول أول مادة لك.")
            return
        await query.message.reply_text(security_intro_text(user.id))
        return

    if query.data == "lock_session":
        lock_session(user.id)
        await query.message.reply_text("🔐 تم قفل الجلسة. للدخول من جديد أرسل PIN الأمان.")
        return

    if query.data == "menu_faq":
        await query.message.reply_text(
            FAQ_TEXT,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🏠 رجوع", callback_data="menu_home")]]
            ),
        )
        return

    if query.data == "menu_support":
        cursor.execute("UPDATE users SET support_pending=1 WHERE user_id=?", (user.id,))
        conn.commit()
        await query.message.reply_text("📩 اكتب رسالتك الآن وسيتم إرسالها إلى الدعم.")
        return


async def year_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    row = get_user_row(user.id)
    _, year_key = query.data.split("|", 1)
    await query.message.reply_text(
        "اختر المواد من هذه السنة:",
        reply_markup=year_subjects_keyboard(year_key, row["selected_subjects"]),
    )


async def subject_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    ensure_user(user.id, user.username, user.first_name)

    _, subject_key = query.data.split("|", 1)
    subject = get_subject(subject_key)
    if not subject:
        await query.message.reply_text("⚠️ المادة غير موجودة.")
        return

    row = get_user_row(user.id)
    selected = row["selected_subjects"][:]
    if subject_key in selected:
        selected.remove(subject_key)
    else:
        selected.append(subject_key)

    cursor.execute("UPDATE users SET selected_subjects=? WHERE user_id=?", (join_subjects(selected), user.id))
    conn.commit()
    await query.message.reply_text(
        "✅ تم تحديث الاختيار.",
        reply_markup=year_subjects_keyboard(subject["year_key"], selected),
    )


async def subject_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, subject_key = query.data.split("|", 1)
    subject = get_subject(subject_key)
    if not subject:
        await query.message.reply_text("⚠️ المادة غير موجودة.")
        return
    await query.message.reply_text(
        f"{subject['year_title']}\n\n{subject['title']}\n{subject['description']}\n\n💵 السعر: {subject.get('price', 0)}$\n🎥 عدد المحاضرات الحالية: {len(subject.get('lectures', []))}"
    )


async def payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    row = get_user_row(user.id)

    if not row["selected_subjects"]:
        await query.message.reply_text("⚠️ اختر المواد أولاً.")
        return

    if row["payment_status"] in ("pending", "reviewing"):
        await query.message.reply_text(
            f"🟡 لديك طلب قيد المراجعة بالفعل.\n"
            f"🧾 رقم الطلب: {row['order_id'] or '-'}"
        )
        return

    order_id = generate_order_id()
    total = calc_total(row["selected_subjects"])
    method = query.data

    cursor.execute(
        """UPDATE users
           SET selected_payment=?,
               order_id=?,
               form_step='payer_full_name',
               support_pending=0,
               cash_full_name=NULL,
               cash_phone=NULL,
               cash_subject_names=NULL
           WHERE user_id=?""",
        (method, order_id, user.id),
    )
    conn.commit()

    await query.message.reply_text(
        f"💳 تم اختيار وسيلة الدفع: {get_payment_label(method)}\n\n"
        f"🧾 رقم الطلب: {order_id}\n"
        f"📚 المواد المختارة داخل البوت:\n{get_subjects_text(row['selected_subjects'])}\n"
        f"💵 الإجمالي: {total}$\n\n"
        f"أرسل الآن الاسم الثلاثي للطالب."
    )


async def paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("📸 أرسل صورة إشعار الدفع الآن.\n⚠️ يجب أن تكون واضحة وحديثة.")


async def receive_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not in_private_chat(update):
        return
    user = update.effective_user
    ensure_user(user.id, user.username, user.first_name)

    if not update.message.photo:
        return

    row = get_user_row(user.id)
    if not row["selected_subjects"]:
        await update.message.reply_text("⚠️ اختر المواد أولاً ثم ادفع.")
        return

    if row["payment_status"] in ("pending", "reviewing"):
        await update.message.reply_text(
            f"⏳ لديك طلب قيد المراجعة بالفعل.\n🧾 رقم الطلب: {row['order_id'] or '-'}"
        )
        return

    if time.time() - update.message.date.timestamp() > 120:
        await update.message.reply_text("❌ يرجى إرسال صورة إشعار جديدة من الكاميرا.")
        return

    order_id = row["order_id"] or generate_order_id()
    payment_method = get_payment_label(row["selected_payment"])
    photo = update.message.photo[-1].file_id
    total = calc_total(row["selected_subjects"])
    subjects_text = get_subjects_text(row["selected_subjects"])

    cursor.execute(
        "UPDATE users SET proof_message_id=?, payment_status='pending', request_at=?, order_id=? WHERE user_id=?",
        (update.message.message_id, now_str(), order_id, user.id),
    )
    conn.commit()

    keyboard = [
        [InlineKeyboardButton("👁 بدء المراجعة", callback_data=f"review|{user.id}")],
        [InlineKeyboardButton("✅ قبول الدفع", callback_data=f"approve|{user.id}")],
        [InlineKeyboardButton("❌ رفض الدفع", callback_data=f"reject|{user.id}")],
    ]

    sent = await context.bot.send_photo(
        ADMIN_ID,
        photo=photo,
        caption=(
            f"📥 طلب دفع جديد\n\n"
            f"🧾 رقم الطلب: {order_id}\n"
            f"👤 المستخدم: {user.first_name}\n"
            f"👤 الاسم الثلاثي: {row['cash_full_name'] or 'غير مُدخل'}\n"
            f"📞 الهاتف: {row['cash_phone'] or 'غير مُدخل'}\n"
            f"📝 أسماء المواد كما كتبها الطالب: {row['cash_subject_names'] or 'غير مُدخل'}\n"
            f"🆔 ID: {user.id}\n"
            f"👤 Username: @{user.username if user.username else 'بدون'}\n"
            f"💳 طريقة الدفع: {payment_method}\n"
            f"📚 المواد داخل البوت:\n{subjects_text}\n"
            f"💵 الإجمالي: {total}$\n"
            f"📌 الحالة: pending"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    cursor.execute("UPDATE users SET admin_message_id=? WHERE user_id=?", (sent.message_id, user.id))
    conn.commit()
    await update.message.reply_text(f"✅ تم إرسال الإشعار للمراجعة.\n🧾 رقم طلبك: {order_id}")


async def review_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("غير مسموح", show_alert=True)
        return

    user_id = int(query.data.split("|")[1])
    row = get_user_row(user_id)
    cursor.execute("UPDATE users SET payment_status='reviewing' WHERE user_id=?", (user_id,))
    conn.commit()

    await query.edit_message_caption(
        caption=(
            f"📥 طلب دفع قيد المراجعة\n\n"
            f"🧾 رقم الطلب: {row['order_id'] or '-'}\n"
            f"👤 الاسم الثلاثي: {row['cash_full_name'] or 'غير مُدخل'}\n"
            f"📞 الهاتف: {row['cash_phone'] or 'غير مُدخل'}\n"
            f"📝 أسماء المواد كما كتبها الطالب: {row['cash_subject_names'] or 'غير مُدخل'}\n"
            f"🆔 ID: {user_id}\n"
            f"💳 طريقة الدفع: {get_payment_label(row['selected_payment'])}\n"
            f"📚 المواد داخل البوت:\n{get_subjects_text(row['selected_subjects'])}\n"
            f"📌 الحالة: reviewing"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ قبول الدفع", callback_data=f"approve|{user_id}")],
            [InlineKeyboardButton("❌ رفض الدفع", callback_data=f"reject|{user_id}")],
        ]),
    )


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("غير مسموح", show_alert=True)
        return

    user_id = int(query.data.split("|")[1])
    user = await context.bot.get_chat(user_id)
    row = get_user_row(user_id)

    approved = row["approved_subjects"][:]
    for subject in row["selected_subjects"]:
        if subject not in approved:
            approved.append(subject)

    approved_at = now_str()
    total = calc_total(row["selected_subjects"])

    cursor.execute(
        """UPDATE users
           SET payment_status='approved',
               approved_at=?,
               approved_subjects=?,
               selected_subjects='',
               is_verified=0,
               session_expires_at=NULL
           WHERE user_id=?""",
        (approved_at, join_subjects(approved), user_id),
    )
    cursor.execute(
        """INSERT INTO sales (user_id, order_id, subjects, payment_method, amount, status, approved_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            row["order_id"],
            get_subjects_text(row["selected_subjects"]),
            get_payment_label(row["selected_payment"]),
            total,
            "approved",
            approved_at,
        ),
    )
    conn.commit()

    if row.get("proof_message_id"):
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=row["proof_message_id"])
        except Exception:
            pass

    pin_note = (
        "🔐 أول دخول للمحتوى سيتطلب منك إنشاء PIN أمان."
        if not row["security_pin"]
        else "🔐 استخدم PIN الأمان الخاص بك للدخول للمحتوى."
    )

    await context.bot.send_message(
        user_id,
        f"✅ تم الدفع بنجاح\n\n"
        f"🧾 رقم الطلب: {row['order_id']}\n"
        f"📚 المواد المفعلة لك:\n{get_subjects_text(row['selected_subjects'])}\n\n"
        f"يمكنك الآن الدخول إلى الفيديوهات.\n\n"
        f"{pin_note}",
        reply_markup=main_menu_keyboard(True, False),
    )

    try:
        if row.get("admin_message_id"):
            await context.bot.delete_message(chat_id=ADMIN_ID, message_id=row["admin_message_id"])
        else:
            await query.message.delete()
    except Exception:
        pass

    await context.bot.send_message(
        ADMIN_ID,
        f"✅ تم قبول الطلب\n\n"
        f"🧾 رقم الطلب: {row['order_id']}\n"
        f"👤 الاسم: {user.first_name}\n"
        f"🔗 اليوزر: @{user.username if user.username else 'لا يوجد'}\n"
        f"🆔 ID: {user_id}\n"
        f"💳 الطريقة: {get_payment_label(row['selected_payment'])}\n"
        f"📚 المواد المفعلة:\n{get_subjects_text(row['selected_subjects'])}\n\n"
        f"المستخدم صار بإمكانه الدخول إلى مكتبة الفيديوهات."
    )


async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("غير مسموح", show_alert=True)
        return

    user_id = int(query.data.split("|")[1])
    user = await context.bot.get_chat(user_id)
    row = get_user_row(user_id)
    total = calc_total(row["selected_subjects"])

    cursor.execute("UPDATE users SET payment_status='rejected' WHERE user_id=?", (user_id,))
    cursor.execute(
        """INSERT INTO sales (user_id, order_id, subjects, payment_method, amount, status, approved_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            row["order_id"],
            get_subjects_text(row["selected_subjects"]),
            get_payment_label(row["selected_payment"]),
            total,
            "rejected",
            now_str(),
        ),
    )
    conn.commit()

    await context.bot.send_message(
        user_id,
        f"❌ تم رفض الطلب.\n\n🧾 رقم الطلب: {row['order_id']}\nيرجى إعادة المحاولة أو التواصل مع الأدمن.",
    )
    try:
        if row.get("admin_message_id"):
            await context.bot.delete_message(chat_id=ADMIN_ID, message_id=row["admin_message_id"])
        else:
            await query.message.delete()
    except Exception:
        pass
    await context.bot.send_message(
        ADMIN_ID,
        f"❌ تم رفض الطلب\n\n🧾 رقم الطلب: {row['order_id']}\n👤 الاسم: {user.first_name}\n🔗 اليوزر: @{user.username if user.username else 'لا يوجد'}\n🆔 ID: {user_id}\n💳 الطريقة: {get_payment_label(row['selected_payment'])}",
    )


async def open_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, subject_key = query.data.split("|", 1)

    if not subject_is_approved_for_user(query.from_user.id, subject_key):
        await query.message.reply_text("❌ غير مسموح لك بالدخول إلى هذه المادة.")
        return
    if require_security(query.from_user.id) and not is_session_valid(query.from_user.id):
        await query.message.reply_text(security_intro_text(query.from_user.id))
        return

    subject = get_subject(subject_key)
    if not subject:
        await query.message.reply_text("⚠️ المادة غير موجودة.")
        return

    await query.message.reply_text(
        f"{subject['title']}\n\n{subject['description']}\n\n🔒 الترتيب الإجباري مفعّل: يجب فتح المحاضرات بالتسلسل.\nاختر المحاضرة:",
        reply_markup=lectures_keyboard(subject_key),
    )


async def lecture_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, subject_key, lecture_key = query.data.split("|", 2)

    if not subject_is_approved_for_user(query.from_user.id, subject_key):
        await query.message.reply_text("❌ غير مسموح لك بالدخول إلى هذه المحاضرة.")
        return
    if require_security(query.from_user.id) and not is_session_valid(query.from_user.id):
        await query.message.reply_text(security_intro_text(query.from_user.id))
        return
    if not lecture_allowed_by_order(query.from_user.id, subject_key, lecture_key):
        await query.message.reply_text("🔒 لا يمكن فتح هذه المحاضرة قبل مشاهدة المحاضرة السابقة.")
        return

    lecture = find_lecture(subject_key, lecture_key)
    if not lecture:
        await query.message.reply_text("⚠️ المحاضرة غير موجودة.")
        return

    file_id = lecture.get("file_id", "")
    if not file_id or "PLACEHOLDER" in file_id:
        await query.message.reply_text("⚠️ هذه المحاضرة لم يتم رفعها بعد.")
        return

    cursor.execute(
        "INSERT OR IGNORE INTO watched (user_id, subject_key, lecture_key, watched_at) VALUES (?, ?, ?, ?)",
        (query.from_user.id, subject_key, lecture_key, now_str()),
    )
    cursor.execute(
        "UPDATE users SET last_lecture_compound=? WHERE user_id=?",
        (f"{subject_key}|{lecture_key}", query.from_user.id),
    )
    conn.commit()

    note = f"📚 {get_subject_title(subject_key)}\n🎥 {lecture['title']}\n🔐 محتوى محمي"
    await context.bot.send_message(query.from_user.id, note, protect_content=True)
    await context.bot.send_video(chat_id=query.from_user.id, video=file_id, protect_content=True)


async def continue_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    row = get_user_row(query.from_user.id)
    if require_security(query.from_user.id) and not is_session_valid(query.from_user.id):
        await query.message.reply_text(security_intro_text(query.from_user.id))
        return

    compound = row["last_lecture_compound"]
    if not compound or "|" not in compound:
        await query.message.reply_text("ℹ️ لم تشاهد أي محاضرة بعد.")
        return

    subject_key, lecture_key = compound.split("|", 1)
    if not subject_is_approved_for_user(query.from_user.id, subject_key):
        await query.message.reply_text("⚠️ آخر محاضرة غير متاحة لك حالياً.")
        return

    lecture = find_lecture(subject_key, lecture_key)
    if not lecture:
        await query.message.reply_text("⚠️ آخر محاضرة غير موجودة حالياً.")
        return

    file_id = lecture.get("file_id", "")
    if not file_id or "PLACEHOLDER" in file_id:
        await query.message.reply_text("⚠️ آخر محاضرة لم يتم رفعها بعد.")
        return

    await context.bot.send_message(
        query.from_user.id,
        f"▶️ آخر محاضرة وصلت لها:\n{get_subject_title(subject_key)} - {lecture['title']}",
        protect_content=True,
    )
    await context.bot.send_video(chat_id=query.from_user.id, video=file_id, protect_content=True)


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text or not in_private_chat(update):
        return

    user = update.effective_user
    ensure_user(user.id, user.username, user.first_name)
    text = update.message.text.strip()
    row = get_user_row(user.id)

    if is_admin(user.id) and get_state("broadcast_pending") == "1":
        cursor.execute("SELECT user_id FROM users WHERE approved_subjects IS NOT NULL AND approved_subjects != ''")
        users = [r[0] for r in cursor.fetchall()]
        sent = 0
        for target_id in users:
            try:
                await context.bot.send_message(target_id, f"📢 إعلان جديد\n\n{text}")
                sent += 1
            except Exception:
                pass
        await update.message.reply_text(f"✅ تم إرسال الإعلان إلى {sent} مستخدم.")
        return

    if row["support_pending"] == 1 and not row["form_step"]:
        await context.bot.send_message(
            ADMIN_ID,
            f"📩 رسالة دعم جديدة\n\n"
            f"👤 المستخدم: {user.first_name}\n"
            f"🆔 ID: {user.id}\n"
            f"👤 Username: @{user.username if user.username else 'بدون'}\n\n"
            f"📝 الرسالة:\n{text}",
        )
        cursor.execute("UPDATE users SET support_pending=0 WHERE user_id=?", (user.id,))
        conn.commit()
        await update.message.reply_text("✅ تم إرسال رسالتك إلى الدعم.")
        return

    locked, until = is_locked_out(user.id)
    if locked:
        await update.message.reply_text(
            f"⛔ تم قفل الدخول مؤقتاً بسبب محاولات PIN خاطئة كثيرة.\nحاول مجدداً بعد {until}."
        )
        return

    if row["approved_subjects"] and text.isdigit() and len(text) >= MIN_PIN_LENGTH:
        if not row["security_pin"]:
            cursor.execute(
                "UPDATE users SET security_pin=?, pin_attempts=0, locked_until=NULL WHERE user_id=?",
                (hash_pin(text), user.id),
            )
            conn.commit()
            start_session(user.id)
            await update.message.reply_text(
                "✅ تم إنشاء PIN الأمان وتسجيل دخولك بنجاح.",
                reply_markup=main_menu_keyboard(True, True),
            )
            return

        if row["security_pin"] == hash_pin(text):
            clear_failed_pin(user.id)
            start_session(user.id)
            await update.message.reply_text(
                "✅ تم التحقق من PIN وفتح الجلسة.",
                reply_markup=main_menu_keyboard(True, True),
            )
            return

        attempts = record_failed_pin(user.id)
        await update.message.reply_text(
            f"❌ PIN غير صحيح.\nالمحاولات المتبقية قبل القفل: {max(0, 5 - attempts)}"
        )
        return

    if row["form_step"] == "payer_full_name":
        cursor.execute(
            "UPDATE users SET cash_full_name=?, form_step='payer_phone' WHERE user_id=?",
            (text, user.id),
        )
        conn.commit()
        await update.message.reply_text("📞 أرسل رقم هاتف الطالب.")
        return

    if row["form_step"] == "payer_phone":
        cursor.execute(
            "UPDATE users SET cash_phone=?, form_step='payer_subject_names' WHERE user_id=?",
            (text, user.id),
        )
        conn.commit()
        await update.message.reply_text("📝 أرسل أسماء المواد المسجل عليها الطالب.")
        return

    if row["form_step"] == "payer_subject_names":
        cursor.execute(
            """UPDATE users
               SET cash_subject_names=?, form_step=NULL
               WHERE user_id=?""",
            (text, user.id),
        )
        conn.commit()

        refreshed = get_user_row(user.id)
        order_id = refreshed["order_id"] or generate_order_id()
        total = calc_total(refreshed["selected_subjects"])
        payment_method = refreshed["selected_payment"]

        if payment_method == "pay_cash_in_person":
            cursor.execute(
                "UPDATE users SET payment_status='pending', request_at=? WHERE user_id=?",
                (now_str(), user.id),
            )
            conn.commit()

            keyboard = [
                [InlineKeyboardButton("👁 بدء المراجعة", callback_data=f"review|{user.id}")],
                [InlineKeyboardButton("✅ قبول الدفع", callback_data=f"approve|{user.id}")],
                [InlineKeyboardButton("❌ رفض الدفع", callback_data=f"reject|{user.id}")],
            ]

            sent = await context.bot.send_message(
                ADMIN_ID,
                f"📥 طلب تسجيل جديد\n\n"
                f"🧾 رقم الطلب: {order_id}\n"
                f"👤 اسم الطالب: {refreshed['cash_full_name']}\n"
                f"🆔 ID: {user.id}\n"
                f"👤 Username: @{user.username if user.username else 'بدون'}\n"
                f"📞 الهاتف: {refreshed['cash_phone']}\n"
                f"📝 أسماء المواد كما كتبها الطالب: {text}\n"
                f"📚 المواد المختارة داخل البوت:\n{get_subjects_text(refreshed['selected_subjects'])}\n"
                f"💰 الإجمالي المحسوب داخل البوت: {total}$\n"
                f"💳 طريقة الدفع: {get_payment_label(payment_method)}\n"
                f"📌 الحالة: pending",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

            cursor.execute(
                "UPDATE users SET admin_message_id=?, order_id=? WHERE user_id=?",
                (sent.message_id, order_id, user.id),
            )
            conn.commit()

            await update.message.reply_text(
                f"✅ تم إرسال طلبك إلى الأدمن للمراجعة.\n🧾 رقم طلبك: {order_id}"
            )
            return

        payment_text = PAYMENT_TEXTS.get(payment_method, "راسل الأدمن لمعرفة طريقة الدفع.")
        keyboard = [
            [InlineKeyboardButton("✅ أرسلت الدفع", callback_data="paid")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="menu_subjects")],
        ]

        await update.message.reply_text(
            f"✅ تم حفظ بياناتك.\n\n"
            f"👤 الاسم الثلاثي: {refreshed['cash_full_name']}\n"
            f"📞 الهاتف: {refreshed['cash_phone']}\n"
            f"📝 أسماء المواد: {text}\n\n"
            f"{payment_text}\n\n"
            f"🧾 رقم الطلب: {order_id}\n"
            f"📚 المواد المختارة داخل البوت:\n{get_subjects_text(refreshed['selected_subjects'])}\n"
            f"💵 الإجمالي: {total}$\n\n"
            f"بعد الدفع اضغط أرسلت الدفع وأرسل صورة إشعار الدفع.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if row["approved_subjects"] and not row["security_pin"]:
        await update.message.reply_text(security_intro_text(user.id))
        return
