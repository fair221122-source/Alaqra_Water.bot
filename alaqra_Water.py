import json
import os
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from reportlab.pdfgen import canvas


BOT_TOKEN = "8090667485:AAGCgIlZPEB069W_bhpIr0HBdp20GpfCCPI"
DATA_FILE = "data.json"
INITIAL_ADMIN_ID = 986199874


# ───────────── البيانات ─────────────

def load_data():
    if not os.path.exists(DATA_FILE):
        data = {
            "admin": {"admin_id": None},
            "settings": {"price_per_unit": 250},
            "clients": {},
            "subscribers": {},
            "readings": {},
            "payments": {},
        }
        save_data(data)
        return data

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return {
                "admin": {"admin_id": None},
                "settings": {"price_per_unit": 250},
                "clients": {},
                "subscribers": {},
                "readings": {},
                "payments": {},
            }


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


data = load_data()

AREAS = [
    "الحمراء",
    "الجبوبة",
    "عرض الجبل",
    "شمضات",
    "حظي",
    "الوادي",
    "بيع مباشر",
]


# ───────────── دوال مساعدة ─────────────

def get_user_id_by_serial(serial):
    for tg_id, info in data["clients"].items():
        if info.get("serial") == serial:
            return int(tg_id)
    return None


def get_last_reading(serial):
    readings = data["readings"].get(serial, [])
    return readings[-1] if readings else {"curr": 0, "amount": 0, "date": "—"}


def get_last_payment(serial):
    payments = data["payments"].get(serial, [])
    return payments[-1] if payments else {"amount": 0, "date": "—"}


def create_pdf(filename, text):
    c = canvas.Canvas(filename)
    y = 800
    for line in text.split("\n"):
        c.drawString(40, y, line)
        y -= 20
        if y < 40:
            c.showPage()
            y = 800
    c.save()


# ───────────── الحالات ─────────────

CLIENT_ENTER_SERIAL, CLIENT_ENTER_SUB = range(2)
CLIENT_PERIOD_FROM, CLIENT_PERIOD_TO = range(2, 4)

ADMIN_ENTER_ID = 10
ADMIN_STAT_SINGLE = 11
ADMIN_AREA_CHOOSE, ADMIN_AREA_FROM, ADMIN_AREA_TO = range(20, 23)
ADMIN_GLOBAL_FROM, ADMIN_GLOBAL_TO = range(30, 32)
ADMIN_ADD_READING_SERIAL, ADMIN_ADD_READING_VALUE = range(40, 42)
ADMIN_ADD_PAYMENT_SERIAL, ADMIN_ADD_PAYMENT_VALUE = range(50, 52)
ADMIN_MSG_MODE, ADMIN_MSG_TEXT = range(60, 62)


# ───────────── لوحات المفاتيح ─────────────

def client_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📌 استعلام"), KeyboardButton("📄 كشف حساب")],
        ],
        resize_keyboard=True,
    )


def admin_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📊 كشف مشترك"), KeyboardButton("📍 كشف منطقة")],
            [KeyboardButton("📋 كشف رئيسي")],
            [KeyboardButton("📥 تسجيل قراءة"), KeyboardButton("💰 تسجيل دفع")],
            [KeyboardButton("📢 إرسال رسالة")],
        ],
        resize_keyboard=True,
    )


# ───────────── العميل ─────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if user_id in data["clients"]:
        await update.message.reply_text("مرحباً بك", reply_markup=client_keyboard())
        return ConversationHandler.END

    await update.message.reply_text("أدخل الرقم التسلسلي:")
    return CLIENT_ENTER_SERIAL


async def client_enter_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["serial"] = update.message.text.strip()
    await update.message.reply_text("أدخل رقم العداد:")
    return CLIENT_ENTER_SUB


async def client_enter_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = context.user_data["serial"]

    data["clients"][str(update.effective_user.id)] = {
        "serial": serial,
        "sub_number": update.message.text.strip(),
    }

    save_data(data)

    await update.message.reply_text("تم الربط.", reply_markup=client_keyboard())
    return ConversationHandler.END


async def client_inquiry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    client = data["clients"].get(user_id)

    if not client:
        await update.message.reply_text("أرسل /start أولاً")
        return

    serial = client["serial"]

    r = get_last_reading(serial)
    p = get_last_payment(serial)

    msg = (
        f"التسلسلي: {serial}\n"
        f"آخر قراءة: {r['curr']} بتاريخ {r['date']} مبلغ {r['amount']}\n"
        f"آخر دفعة: {p['amount']} بتاريخ {p['date']}"
    )

    await update.message.reply_text(msg, reply_markup=client_keyboard())


# ───────────── المدير ─────────────

async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):

    admin_id = data["admin"].get("admin_id")

    if admin_id is None:
        await update.message.reply_text("أدخل ID المدير:")
        return ADMIN_ENTER_ID

    if update.effective_user.id != admin_id:
        await update.message.reply_text("لا تملك صلاحية")
        return ConversationHandler.END

    await update.message.reply_text("لوحة المدير", reply_markup=admin_keyboard())
    return ConversationHandler.END


async def admin_enter_id(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.text.strip() == str(INITIAL_ADMIN_ID):

        data["admin"]["admin_id"] = update.effective_user.id
        save_data(data)

        await update.message.reply_text("تم تفعيل المدير", reply_markup=admin_keyboard())
        return ConversationHandler.END

    await update.message.reply_text("خطأ")
    return ADMIN_ENTER_ID


# ───────────── قراءة ─────────────

async def admin_add_reading_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل التسلسلي:")
    return ADMIN_ADD_READING_SERIAL


async def admin_add_reading_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["serial"] = update.message.text.strip()
    await update.message.reply_text("أدخل القراءة:")
    return ADMIN_ADD_READING_VALUE


async def admin_add_reading_value(update: Update, context: ContextTypes.DEFAULT_TYPE):

    serial = context.user_data["serial"]
    curr = int(update.message.text)

    last = get_last_reading(serial)
    prev = last["curr"]

    units = curr - prev
    amount = units * data["settings"]["price_per_unit"]

    data["readings"].setdefault(serial, []).append(
        {
            "prev": prev,
            "curr": curr,
            "units": units,
            "amount": amount,
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
    )

    save_data(data)

    await update.message.reply_text("تم تسجيل القراءة", reply_markup=admin_keyboard())
    return ConversationHandler.END


# ───────────── دفع ─────────────

async def admin_add_payment_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل التسلسلي:")
    return ADMIN_ADD_PAYMENT_SERIAL


async def admin_add_payment_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["serial"] = update.message.text.strip()
    await update.message.reply_text("أدخل المبلغ:")
    return ADMIN_ADD_PAYMENT_VALUE


async def admin_add_payment_value(update: Update, context: ContextTypes.DEFAULT_TYPE):

    serial = context.user_data["serial"]
    amount = int(update.message.text)

    data["payments"].setdefault(serial, []).append(
        {
            "amount": amount,
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
    )

    save_data(data)

    await update.message.reply_text("تم تسجيل السداد", reply_markup=admin_keyboard())
    return ConversationHandler.END


# ───────────── MAIN ─────────────

def main():

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    client_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CLIENT_ENTER_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_enter_serial)],
            CLIENT_ENTER_SUB: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_enter_sub)],
        },
        fallbacks=[],
    )

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_entry)],
        states={
            ADMIN_ENTER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_enter_id)],
            ADMIN_ADD_READING_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_reading_serial)],
            ADMIN_ADD_READING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_reading_value)],
            ADMIN_ADD_PAYMENT_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_payment_serial)],
            ADMIN_ADD_PAYMENT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_payment_value)],
        },
        fallbacks=[],
    )

    app.add_handler(client_conv)
    app.add_handler(admin_conv)

    app.add_handler(MessageHandler(filters.Regex("^📌 استعلام$"), client_inquiry))
    app.add_handler(MessageHandler(filters.Regex("^📥 تسجيل قراءة$"), admin_add_reading_start))
    app.add_handler(MessageHandler(filters.Regex("^💰 تسجيل دفع$"), admin_add_payment_start))

    app.run_polling()


if __name__ == "__main__":
    main()
