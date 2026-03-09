import logging
import sqlite3
import io
import random
import string
from datetime import datetime
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, 
    ConversationHandler, ContextTypes, CallbackQueryHandler
)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

# --- الإعدادات ---
# ضع هنا الـ ID الخاص بحسابك (تحصل عليه من بوت @userinfobot)
ADMIN_USER_ID = "986199874"  
ANNUAL_PASSWORD = "root" 
UNIT_PRICE = 500         

# --- قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('water_system.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (serial_id TEXT PRIMARY KEY, meter_num TEXT, name TEXT, area TEXT, 
                  chat_id INTEGER, prev_reading REAL DEFAULT 0, balance REAL DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, meter_num TEXT, type TEXT, 
                  value REAL, reading REAL, date TEXT)''')
    conn.commit()
    conn.close()

# --- حالات الحوار ---
(AUTH_STEP, MAIN_MENU, ADD_NAME, ADD_METER, ADD_AREA, 
 REG_READ_NUM, REG_READ_VAL, CONFIRM_READ, 
 REG_PAY_NUM, REG_PAY_VAL, CONFIRM_PAY,
 USER_LINK, USER_STMT_DATE, ANNUAL_AUTH) = range(14)

# --- لوحات المفاتيح ---
ADMIN_KB = [
    ['إرسال رسالة 📩', 'تسجيل قراءة 📥', 'تسجيل دفع 💰'],
    ['كشف مشترك 👤', 'كشف منطقة 📍', 'كشف رئيسي 📊'],
    ['تعديل مشترك ✏️', 'مشترك جديد ➕', 'إغلاق سنوي 🔒']
]

USER_KB = [['استعلام 🔍', 'كشف حساب 📑']]

# --- الوظائف ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('water_system.db')
    user = conn.execute("SELECT name FROM users WHERE chat_id=?", (user_id,)).fetchone()
    conn.close()

    if user:
        await update.message.reply_text(f"مرحباً بك مجدداً {user[0]}", 
                                       reply_markup=ReplyKeyboardMarkup(USER_KB, resize_keyboard=True))
        return MAIN_MENU

    if context.user_data.get('asked_once'):
        await update.message.reply_text("يرجى إدخال (الرقم التسلسلي-رقم المشترك) للربط:")
        return USER_LINK
    
    context.user_data['asked_once'] = True
    await update.message.reply_text("مرحباً بك. إذا كنت المدير أرسل (admin)، وللمشترك أرسل /start مرة ثانية.")
    return AUTH_STEP

async def auth_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "admin":
        await update.message.reply_text("أدخل USER_ID المدير:")
        return AUTH_STEP
    elif text == str(ADMIN_USER_ID):
        await update.message.reply_text("لوحة المدير جاهزة:", 
                                       reply_markup=ReplyKeyboardMarkup(ADMIN_KB, resize_keyboard=True))
        return MAIN_MENU
    return AUTH_STEP

async def user_linking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        serial, meter = update.message.text.split('-')
        conn = sqlite3.connect('water_system.db')
        c = conn.cursor()
        user = c.execute("SELECT name FROM users WHERE serial_id=? AND meter_num=?", (serial, meter)).fetchone()
        if user:
            c.execute("UPDATE users SET chat_id=? WHERE meter_num=?", (update.effective_user.id, meter))
            conn.commit()
            await update.message.reply_text(f"تم الربط بنجاح! أهلاً بك {user[0]}", 
                                           reply_markup=ReplyKeyboardMarkup(USER_KB, resize_keyboard=True))
        else:
            await update.message.reply_text("بيانات غير صحيحة.")
        conn.close()
    except:
        await update.message.reply_text("الصيغة: التسلسلي-المشترك")
    return MAIN_MENU

async def user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = sqlite3.connect('water_system.db')
    u = conn.execute("SELECT name, prev_reading, balance FROM users WHERE chat_id=?", (uid,)).fetchone()
    conn.close()
    if u:
        await update.message.reply_text(f"👤 الاسم: {u[0]}\n📟 آخر قراءة: {u[1]}\n💰 الرصيد/المتأخرات: {u[2]} ريال")

async def new_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = ''.join(random.choices(string.digits, k=6))
    context.user_data['sn'] = serial
    await update.message.reply_text(f"الرقم التسلسلي المولد: {serial}\nأدخل الاسم كاملاً:")
    return ADD_NAME

async def save_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("أدخل رقم المشترك (العداد):")
    return ADD_METER

async def save_meter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['meter'] = update.message.text
    await update.message.reply_text("أدخل المنطقة:")
    return ADD_AREA

async def save_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    area = update.message.text
    conn = sqlite3.connect('water_system.db')
    conn.execute("INSERT INTO users (serial_id, meter_num, name, area) VALUES (?, ?, ?, ?)",
                 (context.user_data['sn'], context.user_data['meter'], context.user_data['name'], area))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ تم الحفظ.", reply_markup=ReplyKeyboardMarkup(ADMIN_KB, resize_keyboard=True))
    return MAIN_MENU

# --- تشغيل البوت ---

def main():
    init_db()
    
    # ************************************************
    # هنا تضع التوكن الخاص بك بدلاً من الكلمة الموجودة بالأسفل
    # ************************************************
    TOKEN = "8090667485:AAGCgIlZPEB069W_bhpIr0HBdp20GpfCCPI"
    
    app = Application.builder().token(TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AUTH_STEP: [MessageHandler(filters.TEXT & ~filters.COMMAND, auth_step)],
            USER_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_linking)],
            MAIN_MENU: [
                MessageHandler(filters.Regex('^مشترك جديد ➕$'), new_user_start),
                MessageHandler(filters.Regex('^استعلام 🔍$'), user_query),
                # يمكن إضافة باقي الوظائف هنا بنفس الطريقة
            ],
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_name)],
            ADD_METER: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_meter)],
            ADD_AREA: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_final)],
        },
        fallbacks=[CommandHandler('start', start)]
    )
    
    app.add_handler(conv)
    print("البوت يعمل الآن... اذهب لتليجرام واضغط Start")
    app.run_polling()

if __name__ == '__main__':
    main()
