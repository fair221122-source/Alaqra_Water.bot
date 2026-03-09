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

BOT_TOKEN = "8090667485:AAGCgIlZPEB069W_bhpIr0HBdp20GpfCCPI"
DATA_FILE = "data.json"
INITIAL_ADMIN_ID = 986199874


# ───────── البيانات ─────────

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
        return json.load(f)


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


# ───────── حالات ─────────

CLIENT_ENTER_SERIAL, CLIENT_ENTER_SUB = range(2)

ADMIN_ENTER_ID = 10

ADMIN_ADD_READING_SERIAL, ADMIN_ADD_READING_VALUE = range(20, 22)
ADMIN_ADD_PAYMENT_SERIAL, ADMIN_ADD_PAYMENT_VALUE = range(30, 32)

ADMIN_ADD_SUB_NAME, ADMIN_ADD_SUB_METER, ADMIN_ADD_SUB_AREA = range(40, 43)

ADMIN_EDIT_SERIAL, ADMIN_EDIT_AREA = range(50, 52)


# ───────── لوحات المفاتيح ─────────

def client_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📌 استعلام")],
        ],
        resize_keyboard=True,
    )


def admin_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📥 تسجيل قراءة"), KeyboardButton("💰 تسجيل دفع")],
            [KeyboardButton("➕ مشترك جديد"), KeyboardButton("✏️ تعديل")],
        ],
        resize_keyboard=True,
    )


# ───────── دوال مساعدة ─────────

def get_last_reading(serial):
    readings = data["readings"].get(serial, [])
    return readings[-1] if readings else {"curr": 0, "date": "—"}


def get_last_payment(serial):
    payments = data["payments"].get(serial, [])
    return payments[-1] if payments else {"amount": 0, "date": "—"}


def get_next_serial():
    if not data["subscribers"]:
        return "1"

    nums = [int(x) for x in data["subscribers"].keys() if x.isdigit()]
    return str(max(nums) + 1)


# ───────── العميل ─────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if user_id in data["clients"]:
        await update.message.reply_text("مرحباً بك", reply_markup=client_keyboard())
        return ConversationHandler.END

    await update.message.reply_text("أدخل الرقم التسلسلي:")
    return CLIENT_ENTER_SERIAL


async def client_enter_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["serial"] = update.message.text
    await update.message.reply_text("أدخل رقم العداد:")
    return CLIENT_ENTER_SUB


async def client_enter_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):

    serial = context.user_data["serial"]

    data["clients"][str(update.effective_user.id)] = {
        "serial": serial,
        "sub_number": update.message.text,
    }

    save_data(data)

    await update.message.reply_text("تم الربط.", reply_markup=client_keyboard())

    return ConversationHandler.END


async def client_inquiry(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = str(update.effective_user.id)

    client = data["clients"].get(user_id)

    if not client:
        await update.message.reply_text("أرسل /start")
        return

    serial = client["serial"]

    r = get_last_reading(serial)
    p = get_last_payment(serial)

    msg = (
        f"التسلسلي: {serial}\n"
        f"آخر قراءة: {r.get('curr')} بتاريخ {r.get('date')}\n"
        f"آخر دفعة: {p.get('amount')} بتاريخ {p.get('date')}"
    )

    await update.message.reply_text(msg, reply_markup=client_keyboard())


# ───────── المدير ─────────

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

    if update.message.text == str(INITIAL_ADMIN_ID):

        data["admin"]["admin_id"] = update.effective_user.id
        save_data(data)

        await update.message.reply_text("تم التفعيل", reply_markup=admin_keyboard())
        return ConversationHandler.END

    await update.message.reply_text("خطأ")
    return ADMIN_ENTER_ID


# ───────── تسجيل قراءة ─────────

async def admin_add_reading_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل الرقم التسلسلي:")
    return ADMIN_ADD_READING_SERIAL


async def admin_add_reading_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["serial"] = update.message.text
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


# ───────── تسجيل دفع ─────────

async def admin_add_payment_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل الرقم التسلسلي:")
    return ADMIN_ADD_PAYMENT_SERIAL


async def admin_add_payment_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["serial"] = update.message.text
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


# ───────── إضافة مشترك ─────────

async def admin_add_sub_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    serial = get_next_serial()
    context.user_data["serial"] = serial

    await update.message.reply_text(f"التسلسلي الجديد {serial}\nأدخل اسم المشترك:")

    return ADMIN_ADD_SUB_NAME


async def admin_add_sub_name(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["name"] = update.message.text

    await update.message.reply_text("أدخل رقم العداد:")

    return ADMIN_ADD_SUB_METER


async def admin_add_sub_meter(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["meter"] = update.message.text

    await update.message.reply_text("أدخل المنطقة:")

    return ADMIN_ADD_SUB_AREA


async def admin_add_sub_area(update: Update, context: ContextTypes.DEFAULT_TYPE):

    serial = context.user_data["serial"]

    data["subscribers"][serial] = {
        "name": context.user_data["name"],
        "meter": context.user_data["meter"],
        "area": update.message.text,
    }

    save_data(data)

    await update.message.reply_text("تم إضافة المشترك", reply_markup=admin_keyboard())

    return ConversationHandler.END


# ───────── تعديل المنطقة ─────────

async def admin_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك:")

    return ADMIN_EDIT_SERIAL


async def admin_edit_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):

    serial = update.message.text

    if serial not in data["subscribers"]:
        await update.message.reply_text("المشترك غير موجود")
        return ConversationHandler.END

    context.user_data["serial"] = serial

    await update.message.reply_text("أدخل المنطقة الجديدة:")

    return ADMIN_EDIT_AREA


async def admin_edit_area(update: Update, context: ContextTypes.DEFAULT_TYPE):

    serial = context.user_data["serial"]

    data["subscribers"][serial]["area"] = update.message.text

    save_data(data)

    await update.message.reply_text("تم تعديل المنطقة", reply_markup=admin_keyboard())

    return ConversationHandler.END


# ───────── MAIN ─────────

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
            ADMIN_ADD_SUB_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_sub_name)],
            ADMIN_ADD_SUB_METER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_sub_meter)],
            ADMIN_ADD_SUB_AREA: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_sub_area)],
            ADMIN_EDIT_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_serial)],
            ADMIN_EDIT_AREA: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_area)],
        },
        fallbacks=[],
    )

    app.add_handler(client_conv)
    app.add_handler(admin_conv)

    app.add_handler(MessageHandler(filters.Regex("^📌 استعلام$"), client_inquiry))

    app.add_handler(MessageHandler(filters.Regex("^📥 تسجيل قراءة$"), admin_add_reading_start))
    app.add_handler(MessageHandler(filters.Regex("^💰 تسجيل دفع$"), admin_add_payment_start))

    app.add_handler(MessageHandler(filters.Regex("^➕ مشترك جديد$"), admin_add_sub_start))
    app.add_handler(MessageHandler(filters.Regex("^✏️ تعديل$"), admin_edit_start))

    app.run_polling()


if __name__ == "__main__":
    main()
