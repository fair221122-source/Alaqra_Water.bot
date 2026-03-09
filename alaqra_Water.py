# -*- coding: utf-8 -*-
import json
import os
from datetime import datetime
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet

# =========================================
# ضع التوكن والادمن هنا
# =========================================

TOKEN = "8090667485:AAGCgIlZPEB069W_bhpIr0HBdp20GpfCCPI"
ADMIN_ID = 986199874

UNIT_PRICE = 500

DATA_DIR = "data"
SUBS_FILE = os.path.join(DATA_DIR, "subscribers.json")
READ_FILE = os.path.join(DATA_DIR, "readings.json")
PAY_FILE = os.path.join(DATA_DIR, "payments.json")
LINK_FILE = os.path.join(DATA_DIR, "links.json")

REGIONS = [
    "الحمراء",
    "الجبوبة",
    "عرض الجبل",
    "شمضات",
    "حظي",
    "الوادي",
    "بيع مباشر",
]

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# =========================================
# تحميل / حفظ البيانات
# =========================================

def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_subscribers():
    return load_json(SUBS_FILE)


def save_subscribers(data):
    save_json(SUBS_FILE, data)


def get_readings():
    return load_json(READ_FILE)


def save_readings(data):
    save_json(READ_FILE, data)


def get_payments():
    return load_json(PAY_FILE)


def save_payments(data):
    save_json(PAY_FILE, data)


def get_links():
    return load_json(LINK_FILE)


def save_links(data):
    save_json(LINK_FILE, data)


# =========================================
# لوحات المفاتيح
# =========================================

def admin_keyboard():
    kb = [
        ["💰 تسجيل دفع", "📥 تسجيل قراءة", "📨 إرسال رسالة"],
        ["📊 كشف رئيسي", "📍 كشف منطقة", "👤 كشف مشترك"],
        ["➕ مشترك جديد", "✏️ تعديل مشترك"],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


def subscriber_keyboard():
    kb = [["📌 استعلام", "📄 كشف حساب"]]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


# =========================================
# حساب المتأخرات
# =========================================

def subscriber_balance(serial):
    readings = get_readings()
    payments = get_payments()

    total = sum(r["amount"] for r in readings if r["serial"] == serial)
    paid = sum(p["amount"] for p in payments if p["serial"] == serial)

    return total - paid


# =========================================
# /start
# =========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id

    if user == ADMIN_ID:
        await update.message.reply_text(
            "لوحة المدير", reply_markup=admin_keyboard()
        )
    else:
        await update.message.reply_text("أدخل الرقم التسلسلي للمشترك:")


# =========================================
# تسجيل دفع
# =========================================

PAY_SERIAL, PAY_AMOUNT = range(2)


async def pay_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك:")
    return PAY_SERIAL


async def pay_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = update.message.text.strip()

    subs = get_subscribers()
    sub = next((s for s in subs if s["serial"] == serial), None)

    if not sub:
        await update.message.reply_text("المشترك غير موجود")
        return ConversationHandler.END

    context.user_data["serial"] = serial
    context.user_data["name"] = sub["name"]

    await update.message.reply_text(f"اسم المشترك: {sub['name']}\nأدخل المبلغ:")
    return PAY_AMOUNT


async def pay_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = float(update.message.text)

    serial = context.user_data["serial"]

    payments = get_payments()
    payments.append(
        {
            "serial": serial,
            "amount": amount,
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
    )

    save_payments(payments)

    links = get_links()
    chat = next((l["chat_id"] for l in links if l["serial"] == serial), None)

    msg = f"""
سند قبض

تم استلام مبلغ وقدره {amount} ريال يمني
وذلك جزء من استهلاك المياه الخاصة بكم

إدارة المشروع
"""

    if chat:
        await context.bot.send_message(chat_id=chat, text=msg)

    await update.message.reply_text("تم تسجيل الدفع", reply_markup=admin_keyboard())
    return ConversationHandler.END


# =========================================
# تسجيل قراءة
# =========================================

READ_SERIAL, READ_VALUE = range(2)


async def read_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك:")
    return READ_SERIAL


async def read_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = update.message.text

    subs = get_subscribers()
    sub = next((s for s in subs if s["serial"] == serial), None)

    if not sub:
        await update.message.reply_text("غير موجود")
        return ConversationHandler.END

    context.user_data["serial"] = serial

    readings = get_readings()
    prev = 0
    user_reads = [r for r in readings if r["serial"] == serial]

    if user_reads:
        prev = user_reads[-1]["current"]

    context.user_data["prev"] = prev

    await update.message.reply_text(f"القراءة السابقة: {prev}\nأدخل القراءة الحالية:")
    return READ_VALUE


async def read_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = int(update.message.text)

    prev = context.user_data["prev"]
    serial = context.user_data["serial"]

    diff = current - prev
    amount = diff * UNIT_PRICE

    readings = get_readings()

    readings.append(
        {
            "serial": serial,
            "prev": prev,
            "current": current,
            "usage": diff,
            "amount": amount,
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
    )

    save_readings(readings)

    balance = subscriber_balance(serial)

    msg = f"""
عزيزي المشترك ...

تم تسجيل قراءة العداد

الاستهلاك: {diff} وحدة
سعر الوحدة: {UNIT_PRICE} ريال يمني
عليكم فاتورة ب {amount} ريال يمني
المبلغ المستحق {balance} ريال يمني

إدارة المشروع
"""

    links = get_links()
    chat = next((l["chat_id"] for l in links if l["serial"] == serial), None)

    if chat:
        await context.bot.send_message(chat_id=chat, text=msg)

    await update.message.reply_text("تم تسجيل القراءة", reply_markup=admin_keyboard())

    return ConversationHandler.END


# =========================================
# إضافة مشترك
# =========================================

NEW_NAME, NEW_REGION, NEW_METER = range(3)


async def new_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل اسم المشترك:")
    return NEW_NAME


async def new_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text("أدخل المنطقة:")
    return NEW_REGION


async def new_region(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["region"] = update.message.text
    await update.message.reply_text("أدخل رقم العداد:")
    return NEW_METER


async def new_meter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meter = update.message.text

    subs = get_subscribers()

    serial = str(len(subs) + 1)

    subs.append(
        {
            "serial": serial,
            "name": context.user_data["name"],
            "region": context.user_data["region"],
            "meter": meter,
        }
    )

    save_subscribers(subs)

    await update.message.reply_text(
        f"تم إضافة مشترك برقم تسلسلي {serial}", reply_markup=admin_keyboard()
    )

    return ConversationHandler.END


# =========================================
# استعلام المشترك
# =========================================

async def subscriber_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = update.message.text

    subs = get_subscribers()
    sub = next((s for s in subs if s["serial"] == serial), None)

    if not sub:
        await update.message.reply_text("الرقم غير موجود")
        return

    links = get_links()
    links.append({"serial": serial, "chat_id": update.effective_user.id})
    save_links(links)

    await update.message.reply_text(
        f"""
تم ربط الحساب

الاسم: {sub['name']}
المنطقة: {sub['region']}
رقم العداد: {sub['meter']}
""",
        reply_markup=subscriber_keyboard(),
    )


# =========================================
# كشف PDF
# =========================================

async def statement(update: Update, context: ContextTypes.DEFAULT_TYPE):

    links = get_links()
    chat = update.effective_user.id
    link = next((l for l in links if l["chat_id"] == chat), None)

    if not link:
        await update.message.reply_text("لم يتم ربط الحساب")
        return

    serial = link["serial"]

    readings = [r for r in get_readings() if r["serial"] == serial]
    payments = [p for p in get_payments() if p["serial"] == serial]

    file = f"statement_{serial}.pdf"

    styles = getSampleStyleSheet()

    elements = []

    elements.append(Paragraph("كشف حساب المشترك", styles["Title"]))
    elements.append(Spacer(1, 20))

    data = [["التاريخ", "القراءة", "الاستهلاك", "المبلغ"]]

    for r in readings:
        data.append([r["date"], r["current"], r["usage"], r["amount"]])

    table = Table(data)
    elements.append(table)

    elements.append(Spacer(1, 20))

    pay_data = [["التاريخ", "المبلغ"]]

    for p in payments:
        pay_data.append([p["date"], p["amount"]])

    elements.append(Table(pay_data))

    doc = SimpleDocTemplate(file)
    doc.build(elements)

    await update.message.reply_document(open(file, "rb"))


# =========================================
# main
# =========================================

def main():

    app = Application.builder().token(TOKEN).build()

    pay_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 تسجيل دفع$"), pay_start)],
        states={
            PAY_SERIAL: [MessageHandler(filters.TEXT, pay_serial)],
            PAY_AMOUNT: [MessageHandler(filters.TEXT, pay_amount)],
        },
        fallbacks=[],
    )

    read_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📥 تسجيل قراءة$"), read_start)],
        states={
            READ_SERIAL: [MessageHandler(filters.TEXT, read_serial)],
            READ_VALUE: [MessageHandler(filters.TEXT, read_value)],
        },
        fallbacks=[],
    )

    new_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ مشترك جديد$"), new_sub)],
        states={
            NEW_NAME: [MessageHandler(filters.TEXT, new_name)],
            NEW_REGION: [MessageHandler(filters.TEXT, new_region)],
            NEW_METER: [MessageHandler(filters.TEXT, new_meter)],
        },
        fallbacks=[],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(pay_conv)
    app.add_handler(read_conv)
    app.add_handler(new_conv)

    app.add_handler(MessageHandler(filters.Regex("^📄 كشف حساب$"), statement))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, subscriber_link))

    print("BOT STARTED")

    app.run_polling()


if __name__ == "__main__":
    main()
