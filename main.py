
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from config import TOKEN
from handlers_content import (
    start, menu_router, year_open, subject_toggle, subject_info, payment, paid,
    receive_proof, review_payment, approve, reject, open_subject, lecture_video,
    continue_last, text_handler,
)
from handlers_admin import (
    admin_panel, admin_router, admin_text_handler, admin_video_handler,
    stats, sales, broadcast,
)

if not TOKEN:
    raise ValueError("TOKEN is missing. Set it in Render Environment Variables.")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin_panel))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("sales", sales))
app.add_handler(CommandHandler("broadcast", broadcast))

app.add_handler(CallbackQueryHandler(admin_router, pattern=r"^admin_"))
app.add_handler(CallbackQueryHandler(menu_router, pattern=r"^(menu_|clear_selection$|continue_last$|lock_session$)"))
app.add_handler(CallbackQueryHandler(year_open, pattern=r"^year_open\|"))
app.add_handler(CallbackQueryHandler(subject_toggle, pattern=r"^subject_toggle\|"))
app.add_handler(CallbackQueryHandler(subject_info, pattern=r"^subject_info\|"))
app.add_handler(CallbackQueryHandler(payment, pattern=r"^pay_"))
app.add_handler(CallbackQueryHandler(paid, pattern=r"^paid$"))
app.add_handler(CallbackQueryHandler(review_payment, pattern=r"^review\|"))
app.add_handler(CallbackQueryHandler(approve, pattern=r"^approve\|"))
app.add_handler(CallbackQueryHandler(reject, pattern=r"^reject\|"))
app.add_handler(CallbackQueryHandler(open_subject, pattern=r"^open_subject\|"))
app.add_handler(CallbackQueryHandler(lecture_video, pattern=r"^lecture\|"))
app.add_handler(CallbackQueryHandler(continue_last, pattern=r"^continue_last$"))

app.add_handler(MessageHandler(filters.VIDEO, admin_video_handler))
app.add_handler(MessageHandler(filters.PHOTO, receive_proof))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

print("Bot Running as Render Background Worker...")
app.run_polling(allowed_updates=None, drop_pending_updates=False)
