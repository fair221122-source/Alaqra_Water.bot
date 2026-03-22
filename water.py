# -*- coding: utf-8 -*-
import os
import sqlite3
from datetime import datetime
from telegram import (
    Update, ReplyKeyboardMarkup, InlineKeyboardMarkup,
    InlineKeyboardButton, InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from reportlab.platypus import SimpleDocTemplate, Table, Paragraph
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

# ================== CONFIG ==================
TOKEN = "8090667485:AAGCgIlZPEB069W_bhpIr0HBdp20GpfCCPI"
UNIT_PRICE = 500
STATE_KEY = "state"
ANNUAL_PASSWORD = "09092009"

# ================== DATABASE ==================
def get_conn():
    return sqlite3.connect("water_project.db")

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS areas(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS subscribers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        serial INTEGER,
        account_no TEXT,
        name TEXT,
        area_id INTEGER,
        chat_id INTEGER
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS readings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sub_id INTEGER,
        prev_read INTEGER,
        curr_read INTEGER,
        units INTEGER,
        amount INTEGER,
        date TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sub_id INTEGER,
        amount INTEGER,
        date TEXT
    )""")

    conn.commit()
    conn.close()

# ================== PDF ==================
def generate_pdf(filename, title, data):
    doc = SimpleDocTemplate(filename, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = [Paragraph(title, styles["Title"])]
    table = Table(data)
    table.setStyle([("GRID",(0,0),(-1,-1),1,colors.black),
                     ("BACKGROUND",(0,0),(-1,0),colors.grey)])
    elements.append(table)
    doc.build(elements)

# ================== KEYBOARDS ==================
def admin_keyboard():
    return ReplyKeyboardMarkup([
        ["مشترك جديد", "تعديل مشترك"],
        ["تسجيل قراءة", "تسجيل دفع"],
        ["كشف مشترك", "كشف منطقة"],
        ["كشف رئيسي", "إرسال رسالة"],
        ["إغلاق سنوي"]
    ], resize_keyboard=True)

def subscriber_keyboard():
    return ReplyKeyboardMarkup([
        ["استعلام", "كشف حساب"]
    ], resize_keyboard=True)

# ================== HELPERS ==================
def find_subscriber(account_no=None, chat_id=None, serial=None):
    conn = get_conn()
    c = conn.cursor()
    query = "SELECT * FROM subscribers WHERE 1=1"
    params = []
    if account_no: query += " AND account_no=?"; params.append(account_no)
    if chat_id: query += " AND chat_id=?"; params.append(chat_id)
    if serial: query += " AND serial=?"; params.append(serial)
    c.execute(query, tuple(params))
    sub = c.fetchone()
    conn.close()
    return sub

def format_subscriber(sub):
    return f"الاسم: {sub[3]}\nرقم المشترك: {sub[2]}\nالمنطقة: {sub[4] or '-'}"

# ================== ADMIN HANDLER ==================
async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    data = context.user_data

    # ====== إضافة مشترك جديد ======
    if text == "مشترك جديد":
        await update.message.reply_text("أدخل اسم المشترك:")
        data["step"] = "new_name"
        return

    if data.get("step") == "new_name":
        data["name"] = text
        await update.message.reply_text("أدخل رقم المشترك:")
        data["step"] = "new_account"
        return

    if data.get("step") == "new_account":
        data["account_no"] = text
        conn = get_conn(); c = conn.cursor()
        serial = int(datetime.now().timestamp())
        c.execute("INSERT INTO subscribers(serial,account_no,name) VALUES(?,?,?)",
                  (serial, data["account_no"], data["name"]))
        conn.commit(); conn.close()
        await update.message.reply_text("تم إضافة المشترك بنجاح", reply_markup=admin_keyboard())
        data.clear()
        return

    # ====== تسجيل قراءة ======
    if text == "تسجيل قراءة":
        await update.message.reply_text("أدخل رقم المشترك:")
        data["step"] = "read_account"
        return

    if data.get("step") == "read_account":
        sub = find_subscriber(account_no=text)
        if not sub: await update.message.reply_text("غير موجود"); return
        data["sub_id"] = sub[0]; data["sub_name"] = sub[3]
        await update.message.reply_text(f"أدخل القراءة الجديدة للمشترك: {sub[3]}")
        data["step"] = "read_value"
        return

    if data.get("step") == "read_value":
        curr = int(text); sub_id = data["sub_id"]
        conn = get_conn(); c = conn.cursor()
        c.execute("SELECT curr_read FROM readings WHERE sub_id=? ORDER BY id DESC LIMIT 1", (sub_id,))
        prev = c.fetchone()[0] if c.fetchone() else 0
        units = curr - prev; amount = units*UNIT_PRICE
        c.execute("INSERT INTO readings(sub_id,prev_read,curr_read,units,amount,date) VALUES(?,?,?,?,?,?)",
                  (sub_id, prev, curr, units, amount, str(datetime.now())))
        conn.commit(); conn.close()
        await update.message.reply_text(f"تم الحفظ. المبلغ: {amount}", reply_markup=admin_keyboard())
        data.clear(); return

    # ====== تسجيل دفع ======
    if text == "تسجيل دفع":
        await update.message.reply_text("أدخل رقم المشترك:")
        data["step"] = "pay_account"; return

    if data.get("step") == "pay_account":
        sub = find_subscriber(account_no=text)
        if not sub: await update.message.reply_text("غير موجود"); return
        data["sub_id"] = sub[0]; await update.message.reply_text("أدخل المبلغ:"); data["step"] = "pay_amount"; return

    if data.get("step") == "pay_amount":
        amount = int(text); sub_id = data["sub_id"]
        conn = get_conn(); c = conn.cursor()
        c.execute("INSERT INTO payments(sub_id,amount,date) VALUES(?,?,?)",(sub_id,amount,str(datetime.now())))
        conn.commit(); conn.close()
        await update.message.reply_text("تم الدفع", reply_markup=admin_keyboard())
        data.clear(); return

# ================== SUBSCRIBER HANDLER ==================
async def subscriber_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text; chat_id = update.effective_chat.id
    sub = find_subscriber(chat_id=chat_id)
    if text == "استعلام":
        if not sub: await update.message.reply_text("غير مربوط"); return
        conn=get_conn(); c=conn.cursor()
        c.execute("SELECT SUM(amount) FROM readings WHERE sub_id=?",(sub[0],))
        total=c.fetchone()[0] or 0
        c.execute("SELECT SUM(amount) FROM payments WHERE sub_id=?",(sub[0],))
        paid=c.fetchone()[0] or 0; conn.close()
        await update.message.reply_text(f"رصيدك الحالي: {total-paid}")
        return
    if text == "كشف حساب":
        if not sub: await update.message.reply_text("غير مربوط"); return
        filename=f"sub_{sub[0]}.pdf"
        generate_pdf(filename,"كشف حساب", [["الاسم",sub[3]],["الرقم",sub[2]]])
        await update.message.reply_document(InputFile(filename))
        return

# ================== TEXT ROUTER ==================
async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == 123456789:  # ضع ID المدير هنا
        await admin_handler(update, context)
    else:
        await subscriber_handler(update, context)

# ================== MAIN ==================
def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", lambda u,c: u.message.reply_text("مرحباً")))
    app.add_handler(MessageHandler(filters.TEXT, text_router))
    app.run_polling()

if __name__ == "__main__":
    main()
