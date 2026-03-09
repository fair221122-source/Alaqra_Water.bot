# -*- coding: utf-8 -*-

import sqlite3
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
Application,
CommandHandler,
MessageHandler,
ConversationHandler,
ContextTypes,
filters
)

TOKEN = "8090667485:AAGCgIlZPEB069W_bhpIr0HBdp20GpfCCPI"
ADMIN_ID = 986199874

UNIT_PRICE = 500
YEAR_PASSWORD = "09092009"

AREAS = [
"الحمراء",
"الجبوبة",
"عرض الجبل",
"شمضات",
"حظي",
"الوادي",
"بيع مباشر"
]

conn = sqlite3.connect("water.db",check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS subscribers(
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
meter TEXT,
area TEXT,
chat_id INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS readings(
id INTEGER PRIMARY KEY AUTOINCREMENT,
subscriber_id INTEGER,
reading INTEGER,
consumption INTEGER,
amount INTEGER,
date TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS payments(
id INTEGER PRIMARY KEY AUTOINCREMENT,
subscriber_id INTEGER,
amount INTEGER,
date TEXT
)
""")

conn.commit()

def admin_keyboard():

    kb = [
    ["💰 تسجيل دفع","📥 تسجيل قراءة","📨 إرسال رسالة"],
    ["📊 كشف رئيسي","📍 كشف منطقة","👤 كشف مشترك"],
    ["➕ مشترك جديد","✏️ تعديل مشترك","📅 إغلاق سنوي"]
    ]

    return ReplyKeyboardMarkup(kb,resize_keyboard=True)

def user_keyboard():

    kb = [
    ["📊 استعلام","📄 كشف حساب"]
    ]

    return ReplyKeyboardMarkup(kb,resize_keyboard=True)

async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):

    user = update.effective_user.id

    if user == ADMIN_ID:

        await update.message.reply_text(
        "لوحة المدير",
        reply_markup=admin_keyboard()
        )

        return

    await update.message.reply_text(
    "مرحبا بك في مشروع مياة قرية بيت الأقرع\n\nادخل الرقم التسلسلي"
    )

LINK_ID,LINK_METER = range(2)

async def link_id(update:Update,context:ContextTypes.DEFAULT_TYPE):

    context.user_data["sid"] = update.message.text

    await update.message.reply_text("ادخل رقم العداد")

    return LINK_METER

async def link_meter(update:Update,context:ContextTypes.DEFAULT_TYPE):

    sid = context.user_data["sid"]
    meter = update.message.text
    chat = update.effective_user.id

    cur.execute(
    "SELECT id,name,area FROM subscribers WHERE id=? AND meter=?",
    (sid,meter)
    )

    row = cur.fetchone()

    if not row:

        await update.message.reply_text("البيانات غير صحيحة")

        return ConversationHandler.END

    cur.execute(
    "UPDATE subscribers SET chat_id=? WHERE id=?",
    (chat,sid)
    )

    conn.commit()

    name=row[1]
    area=row[2]

    await update.message.reply_text(
f"""مرحبا بك في مشروع مياة قرية بيت الأقرع

بياناتك هي :

الرقم التسلسلي : {sid}
الاسم : {name}
رقم المشترك : {meter}
المنطقة : {area}
""",
reply_markup=user_keyboard()
)

    return ConversationHandler.END

NAME,AREA,METER = range(3)

async def new_subscriber(update:Update,context:ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text("ادخل اسم المشترك")

    return NAME

async def sub_name(update:Update,context:ContextTypes.DEFAULT_TYPE):

    context.user_data["name"]=update.message.text

    await update.message.reply_text("ادخل المنطقة")

    return AREA

async def sub_area(update:Update,context:ContextTypes.DEFAULT_TYPE):

    context.user_data["area"]=update.message.text

    await update.message.reply_text("ادخل رقم العداد")

    return METER

async def sub_meter(update:Update,context:ContextTypes.DEFAULT_TYPE):

    name=context.user_data["name"]
    area=context.user_data["area"]
    meter=update.message.text

    cur.execute(
    "INSERT INTO subscribers(name,meter,area) VALUES(?,?,?)",
    (name,meter,area)
    )

    conn.commit()

    await update.message.reply_text(
    "تم إضافة المشترك",
    reply_markup=admin_keyboard()
    )

    return ConversationHandler.END

RID,RVAL = range(2)

async def read_start(update:Update,context:ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id!=ADMIN_ID:
        return

    await update.message.reply_text("ادخل الرقم التسلسلي")

    return RID

async def read_id(update:Update,context:ContextTypes.DEFAULT_TYPE):

    context.user_data["sid"]=update.message.text

    await update.message.reply_text("ادخل القراءة الجديدة")

    return RVAL

async def read_value(update:Update,context:ContextTypes.DEFAULT_TYPE):

    sid=context.user_data["sid"]
    reading=int(update.message.text)

    cur.execute(
    "SELECT reading FROM readings WHERE subscriber_id=? ORDER BY id DESC LIMIT 1",
    (sid,)
    )

    row=cur.fetchone()

    last=row[0] if row else 0

    consumption=reading-last

    amount=consumption*UNIT_PRICE

    cur.execute(
    "INSERT INTO readings(subscriber_id,reading,consumption,amount,date) VALUES(?,?,?,?,?)",
    (sid,reading,consumption,amount,datetime.now())
    )

    conn.commit()

    cur.execute(
    "SELECT chat_id FROM subscribers WHERE id=?",
    (sid,)
    )

    user=cur.fetchone()

    if user and user[0]:

        try:

            await context.bot.send_message(
            user[0],
f"""تم تسجيل قراءة العداد

الاستهلاك : {consumption}
قيمة الفاتورة : {amount}

سعر الوحدة : {UNIT_PRICE}
"""
            )

        except:
            pass

    await update.message.reply_text(
    "تم تسجيل القراءة",
    reply_markup=admin_keyboard()
    )

    return ConversationHandler.END

PID,PAM = range(2)

async def pay_start(update:Update,context:ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id!=ADMIN_ID:
        return

    await update.message.reply_text("ادخل الرقم التسلسلي")

    return PID

async def pay_id(update:Update,context:ContextTypes.DEFAULT_TYPE):

    context.user_data["sid"]=update.message.text

    await update.message.reply_text("ادخل المبلغ")

    return PAM

async def pay_amount(update:Update,context:ContextTypes.DEFAULT_TYPE):

    sid=context.user_data["sid"]
    amount=int(update.message.text)

    cur.execute(
    "INSERT INTO payments(subscriber_id,amount,date) VALUES(?,?,?)",
    (sid,amount,datetime.now())
    )

    conn.commit()

    cur.execute(
    "SELECT chat_id FROM subscribers WHERE id=?",
    (sid,)
    )

    user=cur.fetchone()

    if user and user[0]:

        try:

            await context.bot.send_message(
            user[0],
f"""سند قبض

تم استلام مبلغ وقدره {amount}

شكرا لكم
"""
            )

        except:
            pass

    await update.message.reply_text(
    "تم تسجيل الدفع",
    reply_markup=admin_keyboard()
    )

    return ConversationHandler.END

async def inquiry(update:Update,context:ContextTypes.DEFAULT_TYPE):

    user=update.effective_user.id

    cur.execute(
    "SELECT id,name,area FROM subscribers WHERE chat_id=?",
    (user,)
    )

    row=cur.fetchone()

    if not row:

        await update.message.reply_text("الحساب غير مربوط")

        return

    sid=row[0]

    cur.execute(
    "SELECT SUM(amount) FROM readings WHERE subscriber_id=?",
    (sid,)
    )

    total=cur.fetchone()[0] or 0

    cur.execute(
    "SELECT SUM(amount) FROM payments WHERE subscriber_id=?",
    (sid,)
    )

    paid=cur.fetchone()[0] or 0

    remain=total-paid

    await update.message.reply_text(
f"""الاسم : {row[1]}
المنطقة : {row[2]}

إجمالي الفواتير : {total}
المدفوع : {paid}
المتبقي : {remain}
"""
)

async def area_report(update:Update,context:ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id!=ADMIN_ID:
        return

    await update.message.reply_text("اكتب اسم المنطقة")

    context.user_data["area"]=True

async def area_list(update:Update,context:ContextTypes.DEFAULT_TYPE):

    if "area" not in context.user_data:
        return

    area=update.message.text

    cur.execute(
    "SELECT id,name FROM subscribers WHERE area=?",
    (area,)
    )

    rows=cur.fetchall()

    text=f"كشف منطقة {area}\n\n"

    for r in rows:

        text+=f"{r[0]} - {r[1]}\n"

    await update.message.reply_text(text)

    context.user_data.pop("area")

async def main_report(update:Update,context:ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id!=ADMIN_ID:
        return

    cur.execute("SELECT id,name,area FROM subscribers")

    rows=cur.fetchall()

    text="كشف رئيسي\n\n"

    for r in rows:

        sid=r[0]

        cur.execute("SELECT SUM(amount) FROM readings WHERE subscriber_id=?",(sid,))
        total=cur.fetchone()[0] or 0

        cur.execute("SELECT SUM(amount) FROM payments WHERE subscriber_id=?",(sid,))
        paid=cur.fetchone()[0] or 0

        remain=total-paid

        text+=f"{r[0]} - {r[1]} - {r[2]} - المتبقي {remain}\n"

    await update.message.reply_text(text)

BROADCAST=0

async def msg_start(update:Update,context:ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id!=ADMIN_ID:
        return

    await update.message.reply_text("اكتب الرسالة")

    return BROADCAST

async def msg_send(update:Update,context:ContextTypes.DEFAULT_TYPE):

    text=update.message.text

    cur.execute("SELECT chat_id FROM subscribers")

    rows=cur.fetchall()

    for r in rows:

        if r[0]:

            try:

                await context.bot.send_message(r[0],text)

            except:
                pass

    await update.message.reply_text(
    "تم الإرسال",
    reply_markup=admin_keyboard()
    )

    return ConversationHandler.END

CLOSE=0

async def close_year(update:Update,context:ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id!=ADMIN_ID:
        return

    await update.message.reply_text("ادخل كلمة السر")

    return CLOSE

async def do_close(update:Update,context:ContextTypes.DEFAULT_TYPE):

    if update.message.text!=YEAR_PASSWORD:

        await update.message.reply_text("كلمة السر خطأ")

        return ConversationHandler.END

    cur.execute("DELETE FROM readings")

    conn.commit()

    await update.message.reply_text(
    "تم الإغلاق السنوي",
    reply_markup=admin_keyboard()
    )

    return ConversationHandler.END

def main():

    app=Application.builder().token(TOKEN).build()

    link_conv=ConversationHandler(
    entry_points=[CommandHandler("start",start)],
    states={
    LINK_ID:[MessageHandler(filters.TEXT,link_id)],
    LINK_METER:[MessageHandler(filters.TEXT,link_meter)]
    },
    fallbacks=[]
    )

    add_conv=ConversationHandler(
    entry_points=[MessageHandler(filters.TEXT("➕ مشترك جديد"),new_subscriber)],
    states={
    NAME:[MessageHandler(filters.TEXT,sub_name)],
    AREA:[MessageHandler(filters.TEXT,sub_area)],
    METER:[MessageHandler(filters.TEXT,sub_meter)]
    },
    fallbacks=[]
    )

    read_conv=ConversationHandler(
    entry_points=[MessageHandler(filters.TEXT("📥 تسجيل قراءة"),read_start)],
    states={
    RID:[MessageHandler(filters.TEXT,read_id)],
    RVAL:[MessageHandler(filters.TEXT,read_value)]
    },
    fallbacks=[]
    )

    pay_conv=ConversationHandler(
    entry_points=[MessageHandler(filters.TEXT("💰 تسجيل دفع"),pay_start)],
    states={
    PID:[MessageHandler(filters.TEXT,pay_id)],
    PAM:[MessageHandler(filters.TEXT,pay_amount)]
    },
    fallbacks=[]
    )

    msg_conv=ConversationHandler(
    entry_points=[MessageHandler(filters.TEXT("📨 إرسال رسالة"),msg_start)],
    states={
    BROADCAST:[MessageHandler(filters.TEXT,msg_send)]
    },
    fallbacks=[]
    )

    close_conv=ConversationHandler(
    entry_points=[MessageHandler(filters.TEXT("📅 إغلاق سنوي"),close_year)],
    states={
    CLOSE:[MessageHandler(filters.TEXT,do_close)]
    },
    fallbacks=[]
    )

    app.add_handler(link_conv)
    app.add_handler(add_conv)
    app.add_handler(read_conv)
    app.add_handler(pay_conv)
    app.add_handler(msg_conv)
    app.add_handler(close_conv)

    app.add_handler(MessageHandler(filters.TEXT("📊 كشف رئيسي"),main_report))
    app.add_handler(MessageHandler(filters.TEXT("📍 كشف منطقة"),area_report))
    app.add_handler(MessageHandler(filters.TEXT("📊 استعلام"),inquiry))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,area_list))

    print("BOT STARTED")

    app.run_polling()

if __name__=="__main__":
    main()
