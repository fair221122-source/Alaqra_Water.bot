import json
import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
ApplicationBuilder,
CommandHandler,
MessageHandler,
ContextTypes,
filters,
ConversationHandler
)

BOT_TOKEN = os.getenv("8090667485:AAGCgIlZPEB069W_bhpIr0HBdp20GpfCCPI")
ADMIN_ID = 986199874

DATA_FILE = "data.json"

AREAS = [
"الحمراء",
"الجبوبة",
"عرض الجبل",
"شمضات",
"حظي",
"الوادي",
"بيع مباشر"
]

(
PAY_ID,
PAY_AMOUNT,
READ_ID,
READ_VALUE,
MESSAGE_TYPE,
MESSAGE_AREA,
MESSAGE_TEXT,
NEW_NAME,
NEW_AREA,
NEW_METER,
EDIT_ID,
EDIT_FIELD,
EDIT_VALUE
) = range(13)


def load_data():
    if not os.path.exists(DATA_FILE):
        return {"subscribers": {}, "last_id": 0}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)


def admin_keyboard():
    keyboard = [
        ["💰 تسجيل دفع", "📥 تسجيل قراءة", "📢 إرسال رسالة"],
        ["📋 كشف رئيسي", "📍 كشف منطقة", "📊 كشف مشترك"],
        ["➕ مشترك جديد", "✏️ تعديل"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(
            "لوحة المدير",
            reply_markup=admin_keyboard()
        )
    else:
        keyboard = [["استعلام", "كشف حساب"]]
        await update.message.reply_text(
            "مرحبا بك",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )


async def pay_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك")
    return PAY_ID


async def pay_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["pay_id"] = update.message.text
    await update.message.reply_text("أدخل المبلغ")
    return PAY_AMOUNT


async def pay_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = update.message.text
    sub_id = context.user_data["pay_id"]

    data = load_data()

    if sub_id in data["subscribers"]:
        name = data["subscribers"][sub_id]["name"]

        await context.bot.send_message(
            chat_id=data["subscribers"][sub_id]["chat_id"],
            text=f"سند قبض\nتم استلام مبلغ {amount} من المشترك {name}"
        )

    await update.message.reply_text("تم تسجيل الدفع", reply_markup=admin_keyboard())
    return ConversationHandler.END


async def read_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك")
    return READ_ID


async def read_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["read_id"] = update.message.text
    await update.message.reply_text("أدخل القراءة الحالية")
    return READ_VALUE


async def read_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = int(update.message.text)
    sub_id = context.user_data["read_id"]

    data = load_data()

    if sub_id in data["subscribers"]:
        prev = data["subscribers"][sub_id].get("last_read", 0)
        diff = value - prev

        data["subscribers"][sub_id]["last_read"] = value
        save_data(data)

        await context.bot.send_message(
            chat_id=data["subscribers"][sub_id]["chat_id"],
            text=f"تم تسجيل القراءة\nالاستهلاك {diff}"
        )

    await update.message.reply_text("تم تسجيل القراءة", reply_markup=admin_keyboard())
    return ConversationHandler.END


async def new_subscriber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل اسم المشترك")
    return NEW_NAME


async def new_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text("أدخل المنطقة")
    return NEW_AREA


async def new_area(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["area"] = update.message.text
    await update.message.reply_text("أدخل رقم العداد")
    return NEW_METER


async def new_meter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meter = update.message.text

    data = load_data()

    new_id = str(data["last_id"] + 1)

    data["subscribers"][new_id] = {
        "name": context.user_data["name"],
        "area": context.user_data["area"],
        "meter": meter,
        "chat_id": update.effective_user.id,
        "last_read": 0
    }

    data["last_id"] += 1

    save_data(data)

    await update.message.reply_text(
        f"تم إضافة مشترك رقم {new_id}",
        reply_markup=admin_keyboard()
    )

    return ConversationHandler.END


async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك")
    return EDIT_ID


async def edit_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["edit_id"] = update.message.text
    await update.message.reply_text("ماذا تريد تعديل؟ (المنطقة / رقم العداد)")
    return EDIT_FIELD


async def edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["field"] = update.message.text
    await update.message.reply_text("أدخل القيمة الجديدة")
    return EDIT_VALUE


async def edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = update.message.text
    sub_id = context.user_data["edit_id"]

    data = load_data()

    if context.user_data["field"] == "المنطقة":
        data["subscribers"][sub_id]["area"] = value

    if context.user_data["field"] == "رقم العداد":
        data["subscribers"][sub_id]["meter"] = value

    save_data(data)

    await update.message.reply_text("تم التعديل", reply_markup=admin_keyboard())
    return ConversationHandler.END


def main():

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    pay_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT("💰 تسجيل دفع"), pay_start)],
        states={
            PAY_ID: [MessageHandler(filters.TEXT, pay_id)],
            PAY_AMOUNT: [MessageHandler(filters.TEXT, pay_amount)],
        },
        fallbacks=[]
    )

    read_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT("📥 تسجيل قراءة"), read_start)],
        states={
            READ_ID: [MessageHandler(filters.TEXT, read_id)],
            READ_VALUE: [MessageHandler(filters.TEXT, read_value)],
        },
        fallbacks=[]
    )

    new_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT("➕ مشترك جديد"), new_subscriber)],
        states={
            NEW_NAME: [MessageHandler(filters.TEXT, new_name)],
            NEW_AREA: [MessageHandler(filters.TEXT, new_area)],
            NEW_METER: [MessageHandler(filters.TEXT, new_meter)],
        },
        fallbacks=[]
    )

    edit_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT("✏️ تعديل"), edit_start)],
        states={
            EDIT_ID: [MessageHandler(filters.TEXT, edit_id)],
            EDIT_FIELD: [MessageHandler(filters.TEXT, edit_field)],
            EDIT_VALUE: [MessageHandler(filters.TEXT, edit_value)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(pay_handler)
    app.add_handler(read_handler)
    app.add_handler(new_handler)
    app.add_handler(edit_handler)

    app.run_polling()


if __name__ == "__main__":
    main()
