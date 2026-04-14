import os

DEFAULT_RENDER_DATA_DIR = "/opt/render/project/data"
APP_DATA_DIR = os.getenv(
    "APP_DATA_DIR",
    DEFAULT_RENDER_DATA_DIR if os.path.isdir(DEFAULT_RENDER_DATA_DIR) else os.getcwd(),
)
os.makedirs(APP_DATA_DIR, exist_ok=True)

TOKEN = os.getenv("TOKEN")
ADMIN_ID = 728810082
DYNAMIC_CONTENT_FILE = os.getenv(
    "DYNAMIC_CONTENT_FILE",
    os.path.join(APP_DATA_DIR, "dynamic_content.json"),
)
SESSION_MINUTES = 30
MIN_PIN_LENGTH = 4

PAYMENT_TEXTS = {
    "pay_syriatel": "💰 الدفع عبر سيريتل كاش\n\nالرقم:\n31623094",
    "pay_sham": "💎 الدفع عبر شام كاش\n\nالمعرف:\n4d0c06e319a22353274375a58987f44b\n\nاسم الحساب:\nمجد غسان القيم",
    "pay_cash_transfer": "💵 الحوالة النقدية\n\nالاسم:\nمجد غسان القيم\nالهاتف:\n0937872522",
}

PAYMENT_LABELS = {
    "pay_syriatel": "سيريتل كاش",
    "pay_sham": "شام كاش",
    "pay_cash_transfer": "حوالة نقدية",
    "pay_cash_in_person": "نقداً",
}

WELCOME_TEXT = """✨أهلاً فيكم أصدقائي 🤍
معكم الآنسة زينب سلوم 

هون رح تلاقوا شرح بسيط وفيديوهات مرتبة تساعدكم تفهموا بسهولة 📚🎥

تابعوا بالترتيب وخلوها خفيفة ولطيفة 💌🤍

يلا نبلّش 🤍

داخل البوت تستطيع:
• مشاهدة المواد مرتبة حسب السنوات
• رؤية سعر كل مادة قبل الدفع
• التسجيل بمادة واحدة أو أكثر
• الدفع وإرسال الطلب للأدمن
• الدخول فقط إلى المواد المقبولة لك
• مشاهدة المحاضرات بشكل محمي داخل البوت

🔐 تمت إضافة حماية أقوى:
• الفيديوهات محمية داخل تيليغرام
• دخول المواد يتطلب PIN أمان
• الجلسة تنتهي تلقائياً بعد مدة
• لا يمكن فتح محاضرة لاحقة قبل السابقة

اختر من القائمة الرئيسية 👇"""

FAQ_TEXT = """❓ الأسئلة الشائعة

1) هل أستطيع التسجيل بأكثر من مادة؟
نعم، يمكنك اختيار أكثر من مادة.

2) هل أرى كل المواد بعد الدفع؟
لا، فقط المواد التي وافق الأدمن على تفعيلها لك.


DEFAULT_CATALOG = {
    "year1": {
        "title": "🎓 سنة أولى",
        "subjects": {
            "high_math": {
                "title": "📘 رياضيات عالية",
                "description": "مادة رياضيات عالية لطلاب السنة الأولى.",
                "price": 20,
                "lectures": [
                    {"key": "lec1", "title": "🎥 محاضرة 1", "file_id": "PLACEHOLDER_HIGH_MATH_1", "is_new": True},
                    {"key": "lec2", "title": "🎥 محاضرة 2", "file_id": "PLACEHOLDER_HIGH_MATH_2", "is_new": True},
                ],
            },
            "statistics_intro": {
                "title": "📘 مبادئ الاحصاء",
                "description": "مادة مبادئ الإحصاء لطلاب السنة الأولى.",
                "price": 20,
                "lectures": [
                    {"key": "lec1", "title": "🎥 محاضرة 1", "file_id": "PLACEHOLDER_STATISTICS_INTRO_1", "is_new": True},
                    {"key": "lec2", "title": "🎥 محاضرة 2", "file_id": "PLACEHOLDER_STATISTICS_INTRO_2", "is_new": True},
                ],
            },
        },
    },
    "year2": {
        "title": "🎓 سنة تانية",
        "subjects": {
            "economic_math": {
                "title": "📗 رياضيات اقتصادية",
                "description": "مادة الرياضيات الاقتصادية لطلاب السنة الثانية.",
                "price": 25,
                "lectures": [
                    {"key": "lec1", "title": "🎥 محاضرة 1", "file_id": "PLACEHOLDER_ECON_MATH_1", "is_new": True},
                    {"key": "lec2", "title": "🎥 محاضرة 2", "file_id": "PLACEHOLDER_ECON_MATH_2", "is_new": True},
                ],
            },
            "applied_statistics": {
                "title": "📗 الاحصاء التطبيقي",
                "description": "مادة الإحصاء التطبيقي لطلاب السنة الثانية.",
                "price": 25,
                "lectures": [
                    {"key": "lec1", "title": "🎥 محاضرة 1", "file_id": "PLACEHOLDER_APPLIED_STAT_1", "is_new": True},
                    {"key": "lec2", "title": "🎥 محاضرة 2", "file_id": "PLACEHOLDER_APPLIED_STAT_2", "is_new": True},
                ],
            },
        },
    },
    "year3": {
        "title": "🎓 سنة تالتة: اختصاص احصاء وبرمجة",
        "subjects": {
            "population_statistics": {
                "title": "📙 الاحصاء السكاني",
                "description": "مادة الإحصاء السكاني لطلاب السنة الثالثة اختصاص إحصاء وبرمجة.",
                "price": 30,
                "lectures": [
                    {"key": "lec1", "title": "🎥 محاضرة 1", "file_id": "PLACEHOLDER_POP_STAT_1", "is_new": True},
                    {"key": "lec2", "title": "🎥 محاضرة 2", "file_id": "PLACEHOLDER_POP_STAT_2", "is_new": True},
                ],
            },
            "mathematical_statistics": {
                "title": "📙 الاحصاء الرياضي",
                "description": "مادة الإحصاء الرياضي لطلاب السنة الثالثة اختصاص إحصاء وبرمجة.",
                "price": 30,
                "lectures": [
                    {"key": "lec1", "title": "🎥 محاضرة 1", "file_id": "PLACEHOLDER_MATH_STAT_1", "is_new": True},
                    {"key": "lec2", "title": "🎥 محاضرة 2", "file_id": "PLACEHOLDER_MATH_STAT_2", "is_new": True},
                ],
            },
        },
    },
}
