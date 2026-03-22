# ================== إعدادات المدير والتوكن مباشرة ==================
import os
import sqlite3
from datetime import datetime, date
from typing import Optional, Tuple, List

# المتغيرات الخاصة بك (تم وضعها مباشرة هنا)
TOKEN = "8090667485:AAGCgIlZPEB069W_bhpIr0HBdp20GpfCCPI"
ADMIN_ID = 986199874  # هويتك كمدير للمشروع
DB_PATH = "water_project.db"
ANNUAL_CLOSE_PASSWORD = "09092009"

# ================== المكتبات المطلوبة ==================
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# مكتبة توليد ملفات PDF
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

# ================== الكيبوردات (Keyboards) ==================
def admin_keyboard():
    keyboard = [
        ["مشترك جديد", "تعديل مشترك"],
        ["تسجيل قراءة", "تسجيل دفع"],
        ["كشف مشترك", "كشف منطقة"],
        ["كشف رئيسي", "إرسال رسالة"],
        ["إغلاق سنوي", "تراجع عن آخر حفظ"],
        ["إلغاء العملية"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def subscriber_keyboard():
    keyboard = [["استعلام", "كشف حساب"]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================== الحالات (States) ==================
STATE_KEY = "state"
STATE_NONE = "NONE"
STATE_SUB_LINK_WAIT_SERIAL = "SUB_LINK_WAIT_SERIAL"
STATE_SUB_LINK_WAIT_ACCOUNT = "SUB_LINK_WAIT_ACCOUNT"
STATE_SUB_STMT_WAIT_FROM = "SUB_STMT_WAIT_FROM"
STATE_ADMIN_NEW_SUB_NAME = "ADMIN_NEW_SUB_NAME"
STATE_ADMIN_NEW_SUB_ACCOUNT = "ADMIN_NEW_SUB_ACCOUNT"
STATE_ADMIN_READ_WAIT_ACCOUNT = "ADMIN_READ_WAIT_ACCOUNT"
STATE_ADMIN_PAY_WAIT_ACCOUNT = "ADMIN_PAY_WAIT_ACCOUNT"
STATE_ADMIN_INQ_WAIT_ACCOUNT = "ADMIN_INQ_WAIT_ACCOUNT"
STATE_DATE_PICK_TARGET = "DATE_PICK_TARGET"

# ================== التعامل مع قاعدة البيانات ==================
def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    # إنشاء الجداول الأساسية
    c.execute("CREATE TABLE IF NOT EXISTS admin (id INTEGER PRIMARY KEY CHECK (id = 1), user_id INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS areas (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)")
    c.execute("""CREATE TABLE IF NOT EXISTS subscribers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, serial INTEGER NOT NULL, account_no TEXT NOT NULL,
        name TEXT NOT NULL, area_id INTEGER, chat_id INTEGER, FOREIGN KEY(area_id) REFERENCES areas(id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, subscriber_id INTEGER NOT NULL, prev_read INTEGER NOT NULL,
        curr_read INTEGER NOT NULL, units INTEGER NOT NULL, unit_price INTEGER NOT NULL,
        amount INTEGER NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(subscriber_id) REFERENCES subscribers(id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, subscriber_id INTEGER NOT NULL, amount INTEGER NOT NULL,
        created_at TEXT NOT NULL, FOREIGN KEY(subscriber_id) REFERENCES subscribers(id))""")
    
    # التأكد من وجود المناطق الافتراضية
    areas = ["الحمراء", "الجبوبة", "عرض الجبل", "شمضات", "حظي", "الوادي", "بيع مباشر"]
    for a in areas:
        try: c.execute("INSERT INTO areas(name) VALUES(?)", (a,))
        except sqlite3.IntegrityError: pass
    
    # تعيين الهوية مباشرة في قاعدة البيانات أيضاً
    c.execute("INSERT OR REPLACE INTO admin(id, user_id) VALUES(1, ?)", (ADMIN_ID,))
    
    conn.commit()
    conn.close()

def find_subscriber_by_chat(chat_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT s.*, a.name FROM subscribers s LEFT JOIN areas a ON s.area_id = a.id WHERE s.chat_id=?", (chat_id,))
    row = c.fetchone(); conn.close()
    return row

def get_subscriber_summary(sub_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(amount),0) FROM readings WHERE subscriber_id=?", (sub_id,))
    total_c = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE subscriber_id=?", (sub_id,))
    total_p = c.fetchone()[0]
    conn.close()
    return {"balance": total_c - total_p}

# ================== معالجة الأوامر والرسائل ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cid = update.effective_chat.id
    
    if uid == ADMIN_ID:
        await update.message.reply_text("أهلاً بك يا مدير المشروع. النظام تحت تصرفك الآن.", reply_markup=admin_keyboard())
        context.user_data[STATE_KEY] = STATE_NONE
    else:
        sub = find_subscriber_by_chat(cid)
        if sub:
            await update.message.reply_text(f"أهلاً {sub[3]}، يمكنك الاستعلام عن حسابك هنا.", reply_markup=subscriber_keyboard())
        else:
            await update.message.reply_text("أهلاً بك في بوت مشروع المياه. للبدء، أدخل الرقم التسلسلي للربط:")
            context.user_data[STATE_KEY] = STATE_SUB_LINK_WAIT_SERIAL

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    ud = context.user_data
    state = ud.get(STATE_KEY, STATE_NONE)
    uid = update.effective_user.id
    
    # منطق المدير
    if uid == ADMIN_ID:
        if text == "إلغاء العملية":
            ud.clear(); ud[STATE_KEY] = STATE_NONE
            await update.message.reply_text("تم إلغاء العملية الحالية.", reply_markup=admin_keyboard())
            return
        
        if state == STATE_NONE:
            if text == "مشترك جديد":
                ud[STATE_KEY] = STATE_ADMIN_NEW_SUB_NAME
                await update.message.reply_text("أدخل اسم المشترك الجديد:")
            elif text == "تسجيل قراءة":
                await update.message.reply_text("أدخل رقم عداد المشترك:")
                # هنا تكمل باقي المنطق الخاص بك...
            return

    # منطق المشترك
    else:
        if state == STATE_SUB_LINK_WAIT_SERIAL:
            # مثال لعملية الربط
            await update.message.reply_text(f"تم استقبال الرقم {text}. أدخل الآن رقم العداد للتحقق:")
            ud[STATE_KEY] = STATE_SUB_LINK_WAIT_ACCOUNT

# ================== التشغيل الرئيسي ==================
def main():
    init_db()
    print(f"تم التحقق من هوية المدير: {ADMIN_ID}")
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("البوت يعمل الآن على السيرفر...")
    app.run_polling()

if __name__ == "__main__":
    main()
