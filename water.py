# ================== imports & config ==================
import os
import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()
ADMIN_ID = int(os.getenv("ADMIN_ID"))

from datetime import datetime, date
from typing import Optional, Tuple, List

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

TOKEN = "8090667485:AAGCgIlZPEB069W_bhpIr0HBdp20GpfCCPI"
DB_PATH = "water_project.db"
ANNUAL_CLOSE_PASSWORD = "09092009"
import os
from dotenv import load_dotenv

# ================== keyboards ==================
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

# ================== states ==================
STATE_KEY = "state"
STATE_NONE = "NONE"

# حالات المشترك
STATE_SUB_LINK_WAIT_SERIAL = "SUB_LINK_WAIT_SERIAL"
STATE_SUB_LINK_WAIT_ACCOUNT = "SUB_LINK_WAIT_ACCOUNT"
STATE_SUB_STMT_WAIT_FROM = "SUB_STMT_WAIT_FROM"
STATE_SUB_STMT_WAIT_TO = "SUB_STMT_WAIT_TO"

# حالات المدير
STATE_ADMIN_NEW_SUB_NAME = "ADMIN_NEW_SUB_NAME"
STATE_ADMIN_NEW_SUB_ACCOUNT = "ADMIN_NEW_SUB_ACCOUNT"
STATE_ADMIN_NEW_SUB_AREA = "ADMIN_NEW_SUB_AREA"
STATE_ADMIN_EDIT_SUB_WAIT_ACCOUNT = "ADMIN_EDIT_SUB_WAIT_ACCOUNT"
STATE_ADMIN_EDIT_SUB_CHOICE = "ADMIN_EDIT_SUB_CHOICE"
STATE_ADMIN_EDIT_SUB_NEW_NAME = "ADMIN_EDIT_SUB_NEW_NAME"
STATE_ADMIN_READ_WAIT_ACCOUNT = "ADMIN_READ_WAIT_ACCOUNT"
STATE_ADMIN_READ_WAIT_VALUE = "ADMIN_READ_WAIT_VALUE"
STATE_ADMIN_READ_CONFIRM = "ADMIN_READ_CONFIRM"
STATE_ADMIN_PAY_WAIT_ACCOUNT = "ADMIN_PAY_WAIT_ACCOUNT"
STATE_ADMIN_PAY_WAIT_AMOUNT = "ADMIN_PAY_WAIT_AMOUNT"
STATE_ADMIN_PAY_CONFIRM = "ADMIN_PAY_CONFIRM"
STATE_ADMIN_INQ_WAIT_ACCOUNT = "ADMIN_INQ_WAIT_ACCOUNT"
STATE_ADMIN_AREA_CHOOSE = "ADMIN_AREA_CHOOSE"
STATE_ADMIN_AREA_WAIT_FROM = "ADMIN_AREA_WAIT_FROM"
STATE_ADMIN_AREA_WAIT_TO = "ADMIN_AREA_WAIT_TO"
STATE_ADMIN_MAIN_WAIT_FROM = "ADMIN_MAIN_WAIT_FROM"
STATE_ADMIN_MAIN_WAIT_TO = "ADMIN_MAIN_WAIT_TO"
STATE_ADMIN_MSG_TYPE = "ADMIN_MSG_TYPE"
STATE_ADMIN_MSG_SUB_WAIT = "ADMIN_MSG_SUB_WAIT"
STATE_ADMIN_MSG_TEXT = "ADMIN_MSG_TEXT"
STATE_ADMIN_ANNUAL_CONFIRM = "ADMIN_ANNUAL_CONFIRM"
STATE_ADMIN_ANNUAL_PASSWORD = "ADMIN_ANNUAL_PASSWORD"
STATE_DATE_PICK_TARGET = "DATE_PICK_TARGET"

# ================== DB helpers ==================
def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_conn()
    c = conn.cursor()
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
    c.execute("CREATE TABLE IF NOT EXISTS actions_log (id INTEGER PRIMARY KEY AUTOINCREMENT, action_type TEXT NOT NULL, ref_id INTEGER, created_at TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS messages_log (id INTEGER PRIMARY KEY AUTOINCREMENT, msg_type TEXT NOT NULL, target TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL)")
    
    areas = ["الحمراء", "الجبوبة", "عرض الجبل", "شمضات", "حظي", "الوادي", "بيع مباشر"]
    for a in areas:
        try: c.execute("INSERT INTO areas(name) VALUES(?)", (a,))
        except sqlite3.IntegrityError: pass
    conn.commit()
    conn.close()

# ================== General Helpers ==================
def get_admin_user_id():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id FROM admin WHERE id=1")
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def set_admin_user_id(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO admin(id, user_id) VALUES(1, ?)", (user_id,))
    conn.commit()
    conn.close()

def find_subscriber_by_account(acc):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT s.*, a.name FROM subscribers s LEFT JOIN areas a ON s.area_id = a.id WHERE s.account_no=?", (acc,))
    row = c.fetchone()
    conn.close()
    return row

def find_subscriber_by_id(sid):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT s.*, a.name FROM subscribers s LEFT JOIN areas a ON s.area_id = a.id WHERE s.id=?", (sid,))
    row = c.fetchone()
    conn.close()
    return row

def find_subscriber_by_chat(chat_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT s.*, a.name FROM subscribers s LEFT JOIN areas a ON s.area_id = a.id WHERE s.chat_id=?", (chat_id,))
    row = c.fetchone()
    conn.close()
    return row

def get_all_areas():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, name FROM areas")
    rows = c.fetchall()
    conn.close()
    return rows

def get_subscriber_summary(sub_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT prev_read, curr_read, units, unit_price, amount, created_at FROM readings WHERE subscriber_id=? ORDER BY id DESC LIMIT 1", (sub_id,))
    last = c.fetchone()
    c.execute("SELECT COALESCE(SUM(amount),0) FROM readings WHERE subscriber_id=?", (sub_id,))
    total_c = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE subscriber_id=?", (sub_id,))
    total_p = c.fetchone()[0]
    conn.close()
    return {"last_read": last, "total_consumption_amount": total_c, "total_payments": total_p, "balance": total_c - total_p}

def get_subscriber_statement(sub_id, f_date, t_date):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT prev_read, curr_read, units, unit_price, amount, created_at FROM readings WHERE subscriber_id=? AND date(created_at) BETWEEN ? AND ? ORDER BY created_at", (sub_id, f_date.isoformat(), t_date.isoformat()))
    r = c.fetchall()
    c.execute("SELECT amount, created_at FROM payments WHERE subscriber_id=? AND date(created_at) BETWEEN ? AND ? ORDER BY created_at", (sub_id, f_date.isoformat(), t_date.isoformat()))
    p = c.fetchall()
    conn.close()
    return r, p

# ================== PDF Generation (Fixed) ==================
def generate_statement_pdf(filename, sub, f_date, t_date, readings, payments):
    try:
        c = canvas.Canvas(filename, pagesize=A4)
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(105 * mm, 280 * mm, "Water Project Statement")
        c.setFont("Helvetica", 10)
        c.drawString(20 * mm, 260 * mm, f"Subscriber: {sub[3]}")
        c.drawString(20 * mm, 255 * mm, f"Account No: {sub[2]}")
        c.drawString(20 * mm, 250 * mm, f"Period: {f_date} to {t_date}")
        
        y = 230 * mm
        c.drawString(20 * mm, y, "Date | Prev | Curr | Units | Price | Amount")
        y -= 5 * mm
        c.line(20 * mm, y, 190 * mm, y)
        y -= 7 * mm
        
        for r in readings:
            line = f"{r[5][:10]} | {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]}"
            c.drawString(20 * mm, y, line)
            y -= 5 * mm
            if y < 30 * mm: c.showPage(); y = 280 * mm
            
        c.save()
        return True
    except Exception as e:
        print(f"PDF Error: {e}")
        return False

# ================== Date Picker ==================
def build_year_kb():
    now = datetime.utcnow().year
    return InlineKeyboardMarkup([[InlineKeyboardButton(str(y), callback_data=f"date_year_{y}")] for y in range(now, now-3, -1)])

def build_month_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton(str(m), callback_data=f"date_month_{m}")] for m in range(1, 13)])

def build_day_kb(year, month):
    import calendar
    days = calendar.monthrange(year, month)[1]
    btns = [[InlineKeyboardButton(str(d), callback_data=f"date_day_{d}") for d in range(i, min(i+7, days+1))] for i in range(1, days+1, 7)]
    return InlineKeyboardMarkup(btns)

# ================== Handlers ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    uid = update.effective_user.id
    admin_id = get_admin_user_id()
    
    if uid == admin_id:
        await update.message.reply_text("مرحباً أيها المدير.", reply_markup=admin_keyboard())
        context.user_data[STATE_KEY] = STATE_NONE
    else:
        sub = find_subscriber_by_chat(cid)
        if sub:
            await update.message.reply_text(f"أهلاً {sub[3]}", reply_markup=subscriber_keyboard())
        else:
            await update.message.reply_text("أهلاً بك. أدخل الرقم التسلسلي للربط:")
            context.user_data[STATE_KEY] = STATE_SUB_LINK_WAIT_SERIAL

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    ud = context.user_data
    state = ud.get(STATE_KEY, STATE_NONE)
    uid = update.effective_user.id
    
    # تحكم المدير
    if uid == get_admin_user_id():
        if text == "إلغاء العملية":
            ud.clear(); ud[STATE_KEY] = STATE_NONE
            await update.message.reply_text("تم الإلغاء.", reply_markup=admin_keyboard())
            return

        if state == STATE_NONE:
            if text == "مشترك جديد":
                ud[STATE_KEY] = STATE_ADMIN_NEW_SUB_NAME
                await update.message.reply_text("أدخل اسم المشترك:")
            elif text == "تسجيل قراءة":
                ud[STATE_KEY] = STATE_ADMIN_READ_WAIT_ACCOUNT
                await update.message.reply_text("أدخل رقم عداد المشترك:")
            elif text == "تسجيل دفع":
                ud[STATE_KEY] = STATE_ADMIN_PAY_WAIT_ACCOUNT
                await update.message.reply_text("أدخل رقم عداد المشترك:")
            elif text == "كشف مشترك":
                ud[STATE_KEY] = STATE_ADMIN_INQ_WAIT_ACCOUNT
                await update.message.reply_text("أدخل رقم المشترك:")
            elif text == "كشف منطقة":
                areas = get_all_areas()
                btns = [[InlineKeyboardButton(a[1], callback_data=f"area_{a[0]}")] for a in areas]
                await update.message.reply_text("اختر المنطقة:", reply_markup=InlineKeyboardMarkup(btns))
            elif text == "كشف رئيسي":
                ud["date_target_state"] = STATE_ADMIN_MAIN_WAIT_FROM
                await update.message.reply_text("اختر سنة البداية:", reply_markup=build_year_kb())
                ud[STATE_KEY] = STATE_DATE_PICK_TARGET
            elif text == "إرسال رسالة":
                btns = [[InlineKeyboardButton("عامة", callback_data="msg_all"), InlineKeyboardButton("مشترك", callback_data="msg_one")]]
                await update.message.reply_text("نوع الرسالة:", reply_markup=InlineKeyboardMarkup(btns))
            return
        
        # معالجة إدخالات المدير المتسلسلة
        if state == STATE_ADMIN_NEW_SUB_NAME:
            ud["n_name"] = text
            ud[STATE_KEY] = STATE_ADMIN_NEW_SUB_ACCOUNT
            await update.message.reply_text("أدخل رقم العداد:")
        elif state == STATE_ADMIN_NEW_SUB_ACCOUNT:
            ud["n_acc"] = text
            conn = get_conn(); c = conn.cursor()
            c.execute("INSERT INTO subscribers (serial, account_no, name, area_id) VALUES (?,?,?,?)", (1, ud["n_acc"], ud["n_name"], 1))
            conn.commit(); conn.close()
            await update.message.reply_text("تمت الإضافة بنجاح.", reply_markup=admin_keyboard())
            ud[STATE_KEY] = STATE_NONE

    # تحكم المشترك
    else:
        if text == "كشف حساب":
            sub = find_subscriber_by_chat(update.effective_chat.id)
            if sub:
                ud["sub_stmt_id"] = sub[0]
                ud["date_target_state"] = STATE_SUB_STMT_WAIT_FROM
                ud[STATE_KEY] = STATE_DATE_PICK_TARGET
                await update.message.reply_text("اختر السنة:", reply_markup=build_year_kb())
        elif text == "استعلام":
            sub = find_subscriber_by_chat(update.effective_chat.id)
            if sub:
                summ = get_subscriber_summary(sub[0])
                await update.message.reply_text(f"رصيدك الحالي هو: {summ['balance']} ريال.")

        elif state == STATE_SUB_LINK_WAIT_SERIAL:
            ud["l_serial"] = text
            ud[STATE_KEY] = STATE_SUB_LINK_WAIT_ACCOUNT
            await update.message.reply_text("أدخل رقم العداد للتحقق:")
        elif state == STATE_SUB_LINK_WAIT_ACCOUNT:
            conn = get_conn(); c = conn.cursor()
            c.execute("UPDATE subscribers SET chat_id=? WHERE account_no=?", (update.effective_chat.id, text))
            conn.commit(); conn.close()
            await update.message.reply_text("تم ربط الحساب بنجاح!", reply_markup=subscriber_keyboard())
            ud[STATE_KEY] = STATE_NONE

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    ud = context.user_data
    await query.answer()

    if data.startswith("date_year_"):
        ud["pick_y"] = int(data.split("_")[2])
        await query.edit_message_text("اختر الشهر:", reply_markup=build_month_kb())
    elif data.startswith("date_month_"):
        ud["pick_m"] = int(data.split("_")[2])
        await query.edit_message_text("اختر اليوم:", reply_markup=build_day_kb(ud["pick_y"], ud["pick_m"]))
    elif data.startswith("date_day_"):
        d = date(ud["pick_y"], ud["pick_m"], int(data.split("_")[2]))
        target = ud.get("date_target_state")
        
        if target in [STATE_SUB_STMT_WAIT_FROM, STATE_ADMIN_MAIN_WAIT_FROM]:
            ud["f_date"] = d
            ud["date_target_state"] = target.replace("FROM", "TO")
            await query.edit_message_text(f"تاريخ البداية: {d}. اختر سنة النهاية:", reply_markup=build_year_kb())
        else:
            # توليد الكشف النهائي
            f_date = ud["f_date"]
            t_date = d
            sid = ud.get("sub_stmt_id")
            sub = find_subscriber_by_id(sid)
            readings, payments = get_subscriber_statement(sid, f_date, t_date)
            
            fname = f"stmt_{sid}.pdf"
            if generate_statement_pdf(fname, sub, f_date, t_date, readings, payments):
                await context.bot.send_document(chat_id=update.effective_chat.id, document=open(fname, 'rb'))
                os.remove(fname)
            else:
                await query.edit_message_text("عذراً، فشل توليد الملف.")
            ud[STATE_KEY] = STATE_NONE

# ================== Main ==================
def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", start)) # للتسهيل
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()
