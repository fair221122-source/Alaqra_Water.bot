#!/usr/bin/env python3
# -*- coding: utf-8 -*-

def keep_bot_alive():
    """
    دالة تمنع توقف البوت في GitHub.
    تعمل في Thread منفصل وتبقي السكربت صاحي.
    """
    import time
    while True:
        time.sleep(10)


def get_db_path():
    """
    دالة تثبّت مسار قاعدة البيانات حتى لا تضيع عند كل تشغيل.
    تمنع إنشاء ملف جديد في مسار مختلف.
    """
    import os
    return os.path.join(os.path.dirname(__file__), "water_project.db")


def force_save_pdf(c):
    """
    دالة تجبر ReportLab على حفظ ملف PDF بشكل كامل.
    تمنع ملفات PDF الفارغة أو التالفة في GitHub.
    """
    try:
        c.showPage()
    except:
        pass

    try:
        c.save()
    except:
        pass


import logging
import os
import sqlite3
from datetime import datetime, date

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ============ إعدادات أساسية ============
TOKEN = os.getenv("BOT_TOKEN", "8090667485:AAGCgIlZPEB069W_bhpIr0HBdp20GpfCCPI")

DB_PATH = os.path.join(os.path.dirname(__file__), "water_project.db")
UNIT_PRICE_DEFAULT = 500  # ريال يمني
ANNUAL_CLOSE_PASSWORD = os.getenv("ANNUAL_CLOSE_PASSWORD", "09092009")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# ============ قاعدة البيانات ============
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS areas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serial INTEGER UNIQUE NOT NULL,
            account_no TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            area_id INTEGER,
            chat_id INTEGER,
            created_at TEXT,
            FOREIGN KEY(area_id) REFERENCES areas(id)
        )
    """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            prev_read INTEGER NOT NULL,
            curr_read INTEGER NOT NULL,
            units INTEGER NOT NULL,
            unit_price INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            FOREIGN KEY(subscriber_id) REFERENCES subscribers(id)
        )
    """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            amount INTEGER NOT NULL,
            FOREIGN KEY(subscriber_id) REFERENCES subscribers(id)
        )
    """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS messages_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_type TEXT NOT NULL,
            target TEXT NOT NULL,
            text TEXT NOT NULL,
            date TEXT NOT NULL
        )
    """
    )

    # حفظ سعر الوحدة الافتراضي إن لم يكن موجوداً
    c.execute("SELECT value FROM settings WHERE key='unit_price'")
    if not c.fetchone():
        c.execute(
            "INSERT INTO settings(key, value) VALUES('unit_price', ?)",
            (str(UNIT_PRICE_DEFAULT),),
        )

    conn.commit()
    conn.close()


def get_conn():
    return sqlite3.connect(DB_PATH)


def get_unit_price():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='unit_price'")
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else UNIT_PRICE_DEFAULT


def set_admin_user_id(user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES('admin_user_id', ?)",
        (str(user_id),),
    )
    conn.commit()
    conn.close()


def get_admin_user_id():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='admin_user_id'")
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else None


def get_next_serial():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT MAX(serial) FROM subscribers")
    row = c.fetchone()
    max_serial = row[0] if row and row[0] is not None else 0
    conn.close()
    return max_serial + 1


def get_or_create_area(name: str):
    name = name.strip()
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM areas WHERE name=?", (name,))
    row = c.fetchone()
    if row:
        area_id = row[0]
    else:
        c.execute("INSERT INTO areas(name) VALUES(?)", (name,))
        area_id = c.lastrowid
        conn.commit()
    conn.close()
    return area_id


def get_all_areas():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, name FROM areas ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return rows


def find_subscriber_by_serial_and_account(serial: int, account_no: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT s.id, s.serial, s.account_no, s.name, s.area_id, s.chat_id, a.name
        FROM subscribers s
        LEFT JOIN areas a ON s.area_id = a.id
        WHERE s.serial=? AND s.account_no=?
    """,
        (serial, account_no),
    )
    row = c.fetchone()
    conn.close()
    return row


def find_subscriber_by_account(account_no: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT s.id, s.serial, s.account_no, s.name, s.area_id, s.chat_id, a.name
        FROM subscribers s
        LEFT JOIN areas a ON s.area_id = a.id
        WHERE s.account_no=?
    """,
        (account_no,),
    )
    row = c.fetchone()
    conn.close()
    return row


def find_subscriber_by_id(sub_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT s.id, s.serial, s.account_no, s.name, s.area_id, s.chat_id, a.name
        FROM subscribers s
        LEFT JOIN areas a ON s.area_id = a.id
        WHERE s.id=?
    """,
        (sub_id,),
    )
    row = c.fetchone()
    conn.close()
    return row


def find_subscriber_by_chat(chat_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT s.id, s.serial, s.account_no, s.name, s.area_id, s.chat_id, a.name
        FROM subscribers s
        LEFT JOIN areas a ON s.area_id = a.id
        WHERE s.chat_id=?
    """,
        (chat_id,),
    )
    row = c.fetchone()
    conn.close()
    return row


def link_subscriber_chat(serial: int, account_no: str, chat_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE subscribers SET chat_id=? WHERE serial=? AND account_no=?",
        (chat_id, serial, account_no),
    )
    conn.commit()
    conn.close()


def create_subscriber(serial: int, account_no: str, name: str, area_name: str):
    area_id = get_or_create_area(area_name)
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO subscribers(serial, account_no, name, area_id, chat_id, created_at)
        VALUES(?,?,?,?,?,?)
    """,
        (serial, account_no, name, area_id, None, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def update_subscriber(sub_id: int, name: str = None, area_name: str = None):
    conn = get_conn()
    c = conn.cursor()
    if name and area_name:
        area_id = get_or_create_area(area_name)
        c.execute(
            "UPDATE subscribers SET name=?, area_id=? WHERE id=?",
            (name, area_id, sub_id),
        )
    elif name:
        c.execute("UPDATE subscribers SET name=? WHERE id=?", (name, sub_id))
    elif area_name:
        area_id = get_or_create_area(area_name)
        c.execute("UPDATE subscribers SET area_id=? WHERE id=?", (area_id, sub_id))
    conn.commit()
    conn.close()


def get_last_reading(subscriber_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT prev_read, curr_read, units, unit_price, amount, date
        FROM readings
        WHERE subscriber_id=?
        ORDER BY id DESC
        LIMIT 1
    """,
        (subscriber_id,),
    )
    row = c.fetchone()
    conn.close()
    return row


def add_reading(subscriber_id: int, curr_read: int):
    unit_price = get_unit_price()
    last = get_last_reading(subscriber_id)
    prev_read = last[1] if last else 0
    units = max(0, curr_read - prev_read)
    amount = units * unit_price

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO readings(subscriber_id, date, prev_read, curr_read, units, unit_price, amount)
        VALUES(?,?,?,?,?,?,?)
    """,
        (
            subscriber_id,
            datetime.utcnow().isoformat(),
            prev_read,
            curr_read,
            units,
            unit_price,
            amount,
        ),
    )
    conn.commit()
    conn.close()
    return prev_read, units, unit_price, amount


def add_payment(subscriber_id: int, amount: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO payments(subscriber_id, date, amount)
        VALUES(?,?,?)
    """,
        (subscriber_id, datetime.utcnow().isoformat(), amount),
    )
    conn.commit()
    conn.close()


def get_subscriber_summary(subscriber_id: int):
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        SELECT SUM(amount) FROM readings WHERE subscriber_id=?
    """,
        (subscriber_id,),
    )
    total_consumption_amount = c.fetchone()[0] or 0

    c.execute(
        """
        SELECT SUM(amount) FROM payments WHERE subscriber_id=?
    """,
        (subscriber_id,),
    )
    total_payments = c.fetchone()[0] or 0

    balance = total_consumption_amount - total_payments

    c.execute(
        """
        SELECT prev_read, curr_read, units, unit_price, amount, date
        FROM readings
        WHERE subscriber_id=?
        ORDER BY id DESC
        LIMIT 1
    """,
        (subscriber_id,),
    )
    last_read = c.fetchone()

    conn.close()
    return {
        "total_consumption_amount": total_consumption_amount,
        "total_payments": total_payments,
        "balance": balance,
        "last_read": last_read,
    }


def get_subscriber_statement(subscriber_id: int, from_date: date, to_date: date):
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        SELECT date, prev_read, curr_read, units, unit_price, amount
        FROM readings
        WHERE subscriber_id=? AND date BETWEEN ? AND ?
        ORDER BY date
    """,
        (
            subscriber_id,
            from_date.isoformat(),
            (datetime.combine(to_date, datetime.max.time())).isoformat(),
        ),
    )
    readings = c.fetchall()

    c.execute(
        """
        SELECT date, amount
        FROM payments
        WHERE subscriber_id=? AND date BETWEEN ? AND ?
        ORDER BY date
    """,
        (
            subscriber_id,
            from_date.isoformat(),
            (datetime.combine(to_date, datetime.max.time())).isoformat(),
        ),
    )
    payments = c.fetchall()

    conn.close()
    return readings, payments


def get_area_summary(area_id: int, from_date: date, to_date: date):
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        SELECT id FROM subscribers WHERE area_id=?
    """,
        (area_id,),
    )
    subs = [row[0] for row in c.fetchall()]

    total_consumption = 0
    total_payments = 0

    for sid in subs:
        c.execute(
            """
            SELECT SUM(amount) FROM readings
            WHERE subscriber_id=? AND date BETWEEN ? AND ?
        """,
            (
                sid,
                from_date.isoformat(),
                (datetime.combine(to_date, datetime.max.time())).isoformat(),
            ),
        )
        total_consumption += c.fetchone()[0] or 0

        c.execute(
            """
            SELECT SUM(amount) FROM payments
            WHERE subscriber_id=? AND date BETWEEN ? AND ?
        """,
            (
                sid,
                from_date.isoformat(),
                (datetime.combine(to_date, datetime.max.time())).isoformat(),
            ),
        )
        total_payments += c.fetchone()[0] or 0

    conn.close()
    return total_consumption, total_payments, total_consumption - total_payments


def get_global_summary(from_date: date, to_date: date):
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        SELECT SUM(amount) FROM readings
        WHERE date BETWEEN ? AND ?
    """,
        (
            from_date.isoformat(),
            (datetime.combine(to_date, datetime.max.time())).isoformat(),
        ),
    )
    total_consumption = c.fetchone()[0] or 0

    c.execute(
        """
        SELECT SUM(amount) FROM payments
        WHERE date BETWEEN ? AND ?
    """,
        (
            from_date.isoformat(),
            (datetime.combine(to_date, datetime.max.time())).isoformat(),
        ),
    )
    total_payments = c.fetchone()[0] or 0

    conn.close()
    return total_consumption, total_payments, total_consumption - total_payments


def log_message(msg_type: str, target: str, text: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO messages_log(msg_type, target, text, date)
        VALUES(?,?,?,?)
    """,
        (msg_type, target, text, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    # ============ توليد ملفات PDF شاملة ============
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def generate_pdf(
    filename: str,
    report_type: str,   # subscriber | area | main
    from_date: date,
    to_date: date,
    data,
    totals=None,
):

    # تسجيل الخط العربي داخل الدالة فقط
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    try:
        pdfmetrics.registerFont(TTFont("Arabic", "Amiri-Regular.ttf"))
    except:
        pass

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(filename, pagesize=A4)
    
    """
    data:
        - subscriber report: (subscriber, readings, payments)
        - area report: list of rows [name, account_no, paid, due]
        - main report: list of rows [name, account_no, area, paid, due]

    totals:
        - {"paid": X, "due": Y}
    """

    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    y = height - 50

    # ============ الترويسة ============
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, y, "مشروع مياة قرية بيت الأقرع الأهلي")
    y -= 30

    title_map = {
        "subscriber": "كشف حساب مشترك",
        "area": "كشف حساب منطقة",
        "main": "كشف حساب رئيسي",
    }

    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(
        width / 2,
        y,
        f"{title_map.get(report_type, '')} للفترة من {from_date} إلى {to_date}"
    )
    y -= 40

    # ============ محتوى التقرير ============
    if report_type == "subscriber":
        subscriber, readings, payments = data

        c.setFont("Helvetica", 11)
        c.drawString(50, y, f"الاسم: {subscriber[3]}")
        y -= 20
        c.drawString(50, y, f"الرقم التسلسلي: {subscriber[1]}")
        y -= 20
        c.drawString(50, y, f"رقم المشترك: {subscriber[2]}")
        y -= 20
        c.drawString(50, y, f"المنطقة: {subscriber[6] or '-'}")
        y -= 30

        # القراءات
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "القراءات:")
        y -= 20

        c.setFont("Helvetica", 9)
        for r in readings:
            line = (
                f"تاريخ: {r[0][:10]} | سابقة: {r[1]} | حالية: {r[2]} | "
                f"وحدات: {r[3]} | سعر: {r[4]} | مبلغ: {r[5]}"
            )
            c.drawString(50, y, line)
            y -= 15
            if y < 80:
                c.showPage()
                y = height - 50
                c.setFont("Helvetica", 9)

        # المدفوعات
        y -= 20
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "المدفوعات:")
        y -= 20

        c.setFont("Helvetica", 9)
        for p in payments:
            line = f"تاريخ: {p[0][:10]} | مبلغ: {p[1]}"
            c.drawString(50, y, line)
            y -= 15
            if y < 80:
                c.showPage()
                y = height - 50
                c.setFont("Helvetica", 9)

    elif report_type == "area":
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, "م | الاسم | رقم المشترك | المدفوع | المتأخرات")
        y -= 15
        c.drawString(50, y, "-" * 90)
        y -= 20

        c.setFont("Helvetica", 9)
        counter = 1
        for row in data:
            name, acc, paid, due = row
            line = f"{counter} | {name} | {acc} | {paid} | {due}"
            c.drawString(50, y, line)
            y -= 15
            counter += 1

            if y < 80:
                c.showPage()
                y = height - 50
                c.setFont("Helvetica", 9)

        y -= 20
        c.setFont("Helvetica-Bold", 11)
        if totals:
            c.drawString(50, y, f"إجمالي المدفوعات: {totals.get('paid', 0)}")
            y -= 20
            c.drawString(50, y, f"إجمالي المتأخرات: {totals.get('due', 0)}")

    elif report_type == "main":
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, "م | الاسم | رقم المشترك | المنطقة | المدفوع | المتأخرات")
        y -= 15
        c.drawString(50, y, "-" * 110)
        y -= 20

        c.setFont("Helvetica", 9)
        counter = 1
        for row in data:
            name, acc, area, paid, due = row
            line = f"{counter} | {name} | {acc} | {area} | {paid} | {due}"
            c.drawString(50, y, line)
            y -= 15
            counter += 1

            if y < 80:
                c.showPage()
                y = height - 50
                c.setFont("Helvetica", 9)

        y -= 20
        c.setFont("Helvetica-Bold", 11)
        if totals:
            c.drawString(50, y, f"إجمالي المدفوعات: {totals.get('paid', 0)}")
            y -= 20
            c.drawString(50, y, f"إجمالي المتأخرات: {totals.get('due', 0)}")

    # ============ التذييل ============
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 50, "مدير المشروع/ صالح الطويل")
    c.drawString(50, 30, "التوقيع/ ____________________")

    c.showPage()
    c.save()


# ============ لوحات المفاتيح ============
def admin_keyboard():
    keyboard = [
        ["مشترك جديد", "تعديل مشترك"],
        ["تسجيل قراءة", "تسجيل دفع"],
        ["كشف مشترك", "كشف منطقة"],
        ["كشف رئيسي", "إرسال رسالة"],
        ["إغلاق سنوي"],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def subscriber_keyboard():
    keyboard = [["استعلام", "كشف حساب"]]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


# ============ حالات المستخدم ============
STATE_KEY = "state"

STATE_NONE = "NONE"

STATE_ADMIN_WAIT_USER_ID = "ADMIN_WAIT_USER_ID"

STATE_SUB_LINK_WAIT_SERIAL = "SUB_LINK_WAIT_SERIAL"
STATE_SUB_LINK_WAIT_ACCOUNT = "SUB_LINK_WAIT_ACCOUNT"

STATE_ADMIN_NEW_SUB_NAME = "ADMIN_NEW_SUB_NAME"
STATE_ADMIN_NEW_SUB_ACCOUNT = "ADMIN_NEW_SUB_ACCOUNT"
STATE_ADMIN_NEW_SUB_AREA = "ADMIN_NEW_SUB_AREA"

STATE_ADMIN_EDIT_SUB_WAIT_ACCOUNT = "ADMIN_EDIT_SUB_WAIT_ACCOUNT"
STATE_ADMIN_EDIT_SUB_CHOICE = "ADMIN_EDIT_SUB_CHOICE"
STATE_ADMIN_EDIT_SUB_NEW_NAME = "ADMIN_EDIT_SUB_NEW_NAME"
STATE_ADMIN_EDIT_SUB_NEW_AREA = "ADMIN_EDIT_SUB_NEW_AREA"

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
STATE_ADMIN_MSG_AREA_CHOOSE = "ADMIN_MSG_AREA_CHOOSE"
STATE_ADMIN_MSG_SUB_WAIT = "ADMIN_MSG_SUB_WAIT"
STATE_ADMIN_MSG_TEXT = "ADMIN_MSG_TEXT"

STATE_SUB_STATEMENT_WAIT_FROM = "SUB_STATEMENT_WAIT_FROM"
STATE_SUB_STATEMENT_WAIT_TO = "SUB_STATEMENT_WAIT_TO"

STATE_ADMIN_SUB_STATEMENT_WAIT_ACCOUNT = "ADMIN_SUB_STATEMENT_WAIT_ACCOUNT"
STATE_ADMIN_SUB_STATEMENT_WAIT_FROM = "ADMIN_SUB_STATEMENT_WAIT_FROM"
STATE_ADMIN_SUB_STATEMENT_WAIT_TO = "ADMIN_SUB_STATEMENT_WAIT_TO"

STATE_ADMIN_ANNUAL_CONFIRM = "ADMIN_ANNUAL_CONFIRM"
STATE_ADMIN_ANNUAL_PASSWORD = "ADMIN_ANNUAL_PASSWORD"


# ============ أدوات مساعدة ============
def is_admin(update: Update) -> bool:
    admin_id = get_admin_user_id()
    if not admin_id:
        return False
    return update.effective_user and update.effective_user.id == admin_id


def parse_date_str(text: str):
    try:
        parts = text.strip().split("/")
        if len(parts) != 3:
            return None
        d, m, y = map(int, parts)
        return date(y, m, d)
    except Exception:
        return None


def format_subscriber_info(sub):
    return (
        f"الرقم التسلسلي: {sub[1]}\n"
        f"رقم المشترك: {sub[2]}\n"
        f"الاسم: {sub[3]}\n"
        f"المنطقة: {sub[6] or '-'}\n"
    )


def format_subscriber_status(sub_id: int):
    sub = find_subscriber_by_id(sub_id)
    if not sub:
        return "لم يتم العثور على المشترك."
    summary = get_subscriber_summary(sub_id)
    last = summary["last_read"]
    text = format_subscriber_info(sub)
    text += "\n"
    if last:
        text += (
            f"آخر قراءة بتاريخ: {last[5][:10]}\n"
            f"القراءة السابقة: {last[0]}\n"
            f"القراءة الحالية: {last[1]}\n"
            f"فارق القراءات (وحدات): {last[2]}\n"
            f"سعر الوحدة: {last[3]}\n"
            f"قيمة الاستهلاك الأخير: {last[4]}\n"
        )
    else:
        text += "لا توجد قراءات مسجلة بعد.\n"
    text += "\n"
    text += f"إجمالي الاستهلاك (مبلغ): {summary['total_consumption_amount']}\n"
    text += f"إجمالي المدفوع: {summary['total_payments']}\n"
    text += f"إجمالي المتأخرات: {summary['balance']}\n"
    return text
    # ============ توجيه رسائل المدير ============
async def admin_text_router(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, state: str
):
    user_data = context.user_data

    # زر إلغاء العملية يعمل في أي وقت
    if text == "إلغاء العملية":
        user_data.clear()
        user_data[STATE_KEY] = STATE_NONE
        await update.message.reply_text(
            "تم إلغاء العملية والعودة إلى لوحة المدير.",
            reply_markup=admin_keyboard(),
        )
        return

    # ===================== الحالات العامة =====================
    if state == STATE_NONE:
        if text == "مشترك جديد":
            serial = get_next_serial()
            user_data["new_sub_serial"] = serial
            await update.message.reply_text(
                f"إنشاء مشترك جديد.\nالرقم التسلسلي المقترح: {serial}\n"
                "الرجاء إدخال اسم المشترك (رباعي أو خماسي):",
                reply_markup=ReplyKeyboardRemove(),
            )
            user_data[STATE_KEY] = STATE_ADMIN_NEW_SUB_NAME
            return

        if text == "تعديل مشترك":
            await update.message.reply_text(
                "الرجاء إدخال رقم المشترك الذي تريد تعديله:",
                reply_markup=ReplyKeyboardRemove(),
            )
            user_data[STATE_KEY] = STATE_ADMIN_EDIT_SUB_WAIT_ACCOUNT
            return

        if text == "تسجيل قراءة":
            await update.message.reply_text(
                "الرجاء إدخال رقم المشترك لتسجيل القراءة:",
                reply_markup=ReplyKeyboardRemove(),
            )
            user_data[STATE_KEY] = STATE_ADMIN_READ_WAIT_ACCOUNT
            return

        if text == "تسجيل دفع":
            await update.message.reply_text(
                "الرجاء إدخال رقم المشترك لتسجيل الدفع:",
                reply_markup=ReplyKeyboardRemove(),
            )
            user_data[STATE_KEY] = STATE_ADMIN_PAY_WAIT_ACCOUNT
            return

        if text == "كشف مشترك":
            await update.message.reply_text(
                "الرجاء إدخال رقم المشترك للاستعلام:",
                reply_markup=ReplyKeyboardRemove(),
            )
            user_data[STATE_KEY] = STATE_ADMIN_INQ_WAIT_ACCOUNT
            return

        if text == "كشف منطقة":
            areas = get_all_areas()
            if not areas:
                await update.message.reply_text(
                    "لا توجد مناطق مسجلة بعد.", reply_markup=admin_keyboard()
                )
                return
            buttons = [
                [InlineKeyboardButton(a[1], callback_data=f"area_{a[0]}")]
                for a in areas
            ]
            await update.message.reply_text(
                "اختر المنطقة:",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            user_data[STATE_KEY] = STATE_ADMIN_AREA_CHOOSE
            return

        if text == "كشف رئيسي":
            await update.message.reply_text(
                "أدخل تاريخ البداية بصيغة يوم/شهر/سنة (مثال: 01/01/2026):",
                reply_markup=ReplyKeyboardRemove(),
            )
            user_data[STATE_KEY] = STATE_ADMIN_MAIN_WAIT_FROM
            return

        if text == "إرسال رسالة":
            buttons = [
                [
                    InlineKeyboardButton("عامة", callback_data="msg_type_general"),
                    InlineKeyboardButton("منطقة", callback_data="msg_type_area"),
                    InlineKeyboardButton("مشترك", callback_data="msg_type_sub"),
                ]
            ]
            await update.message.reply_text(
                "اختر نوع الرسالة:", reply_markup=InlineKeyboardMarkup(buttons)
            )
            user_data[STATE_KEY] = STATE_ADMIN_MSG_TYPE
            return

        if text == "إغلاق سنوي":
            buttons = [
                [
                    InlineKeyboardButton("موافق", callback_data="annual_ok"),
                    InlineKeyboardButton("إلغاء", callback_data="annual_cancel"),
                ]
            ]
            await update.message.reply_text(
                "هل أنت متأكد من تنفيذ الإغلاق السنوي؟",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            user_data[STATE_KEY] = STATE_ADMIN_ANNUAL_CONFIRM
            return

        await update.message.reply_text(
            "اختر من لوحة المدير أو استخدم الأوامر المتاحة.",
            reply_markup=admin_keyboard(),
        )
        return

    # ===================== مشترك جديد =====================
    if state == STATE_ADMIN_NEW_SUB_NAME:
        user_data["new_sub_name"] = text
        await update.message.reply_text("الرجاء إدخال رقم المشترك (رقم العداد):")
        user_data[STATE_KEY] = STATE_ADMIN_NEW_SUB_ACCOUNT
        return

    if state == STATE_ADMIN_NEW_SUB_ACCOUNT:
        user_data["new_sub_account"] = text
        await update.message.reply_text("الرجاء إدخال اسم المنطقة:")
        user_data[STATE_KEY] = STATE_ADMIN_NEW_SUB_AREA
        return

    if state == STATE_ADMIN_NEW_SUB_AREA:
        serial = user_data.get("new_sub_serial")
        name = user_data.get("new_sub_name")
        account_no = user_data.get("new_sub_account")
        area_name = text
        create_subscriber(serial, account_no, name, area_name)
        await update.message.reply_text(
            "تم حفظ المشترك الجديد بنجاح.\n"
            f"الرقم التسلسلي: {serial}\n"
            f"رقم المشترك: {account_no}\n"
            f"الاسم: {name}\n"
            f"المنطقة: {area_name}",
            reply_markup=admin_keyboard(),
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    # ===================== تعديل مشترك =====================
    if state == STATE_ADMIN_EDIT_SUB_WAIT_ACCOUNT:
        sub = find_subscriber_by_account(text)
        if not sub:
            await update.message.reply_text(
                "لم يتم العثور على مشترك بهذا الرقم.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return
        user_data["edit_sub_id"] = sub[0]
        info = format_subscriber_info(sub)
        buttons = [
            [
                InlineKeyboardButton("تعديل الاسم", callback_data="edit_name"),
                InlineKeyboardButton("تعديل المنطقة", callback_data="edit_area"),
            ]
        ]
        await update.message.reply_text(
            "بيانات المشترك:\n\n" + info + "\nاختر ما تريد تعديله:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        user_data[STATE_KEY] = STATE_ADMIN_EDIT_SUB_CHOICE
        return

    if state == STATE_ADMIN_EDIT_SUB_NEW_NAME:
        sub_id = user_data.get("edit_sub_id")
        update_subscriber(sub_id, name=text)
        await update.message.reply_text(
            "تم تعديل الاسم بنجاح.", reply_markup=admin_keyboard()
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    if state == STATE_ADMIN_EDIT_SUB_NEW_AREA:
        sub_id = user_data.get("edit_sub_id")
        update_subscriber(sub_id, area_name=text)
        await update.message.reply_text(
            "تم تعديل المنطقة بنجاح.", reply_markup=admin_keyboard()
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    # ===================== تسجيل قراءة =====================
    if state == STATE_ADMIN_READ_WAIT_ACCOUNT:
        sub = find_subscriber_by_account(text)
        if not sub:
            await update.message.reply_text(
                "لم يتم العثور على مشترك بهذا الرقم.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return
        user_data["read_sub_id"] = sub[0]
        await update.message.reply_text("الرجاء إدخال آخر قراءة (رقم العداد الحالي):")
        user_data[STATE_KEY] = STATE_ADMIN_READ_WAIT_VALUE
        return

    if state == STATE_ADMIN_READ_WAIT_VALUE:
        try:
            curr_read = int(text)
        except ValueError:
            await update.message.reply_text("الرجاء إدخال رقم صحيح للقراءة.")
            return
        sub_id = user_data.get("read_sub_id")
        sub = find_subscriber_by_id(sub_id)
        prev_read, units, unit_price, amount = add_reading(sub_id, curr_read)
        user_data["read_curr"] = curr_read
        user_data["read_prev"] = prev_read
        user_data["read_units"] = units
        user_data["read_unit_price"] = unit_price
        user_data["read_amount"] = amount

        info = format_subscriber_info(sub)
        text_msg = (
            "تسجيل قراءة جديدة:\n\n"
            + info
            + f"القراءة السابقة: {prev_read}\n"
            f"القراءة الحالية: {curr_read}\n"
            f"فارق القراءات (وحدات): {units}\n"
            f"سعر الوحدة: {unit_price}\n"
            f"قيمة الاستهلاك: {amount}\n\n"
            "هل تريد حفظ هذه القراءة؟"
        )
        buttons = [
            [
                InlineKeyboardButton("حفظ", callback_data="read_save"),
                InlineKeyboardButton("تعديل", callback_data="read_edit"),
            ]
        ]
        await update.message.reply_text(
            text_msg, reply_markup=InlineKeyboardMarkup(buttons)
        )
        user_data[STATE_KEY] = STATE_ADMIN_READ_CONFIRM
        return

    # ===================== تسجيل دفع =====================
    if state == STATE_ADMIN_PAY_WAIT_ACCOUNT:
        sub = find_subscriber_by_account(text)
        if not sub:
            await update.message.reply_text(
                "لم يتم العثور على مشترك بهذا الرقم.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return
        user_data["pay_sub_id"] = sub[0]
        await update.message.reply_text("الرجاء إدخال مبلغ الدفع:")
        user_data[STATE_KEY] = STATE_ADMIN_PAY_WAIT_AMOUNT
        return

    if state == STATE_ADMIN_PAY_WAIT_AMOUNT:
        try:
            amount = int(text)
        except ValueError:
            await update.message.reply_text("الرجاء إدخال مبلغ صحيح (أرقام فقط).")
            return
        user_data["pay_amount"] = amount
        sub_id = user_data.get("pay_sub_id")
        sub = find_subscriber_by_id(sub_id)
        info = format_subscriber_info(sub)
        msg = (
            "تسجيل دفع جديد:\n\n"
            + info
            + f"المبلغ: {amount}\n\n"
            "هل تريد حفظ هذه العملية؟"
        )
        buttons = [
            [
                InlineKeyboardButton("حفظ", callback_data="pay_save"),
                InlineKeyboardButton("تعديل", callback_data="pay_edit"),
            ]
        ]
        await update.message.reply_text(
            msg, reply_markup=InlineKeyboardMarkup(buttons)
        )
        user_data[STATE_KEY] = STATE_ADMIN_PAY_CONFIRM
        return

    # ===================== كشف مشترك =====================
    if state == STATE_ADMIN_INQ_WAIT_ACCOUNT:
        sub = find_subscriber_by_account(text)
        if not sub:
            await update.message.reply_text(
                "لم يتم العثور على مشترك بهذا الرقم.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return
        sub_id = sub[0]
        info = format_subscriber_status(sub_id)
        buttons = [
            [
                InlineKeyboardButton("إرسال للمشترك", callback_data=f"inq_send_{sub_id}"),
                InlineKeyboardButton("تجاهل", callback_data="inq_ignore"),
            ]
        ]
        await update.message.reply_text(
            info, reply_markup=InlineKeyboardMarkup(buttons)
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    # ===================== كشف منطقة =====================
    if state == STATE_ADMIN_AREA_WAIT_FROM:
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. مثال صحيح: 01/01/2026"
            )
            return
        user_data["area_from_date"] = d
        await update.message.reply_text(
            "أدخل تاريخ النهاية بصيغة يوم/شهر/سنة (مثال: 10/03/2026):"
        )
        user_data[STATE_KEY] = STATE_ADMIN_AREA_WAIT_TO
        return

    if state == STATE_ADMIN_AREA_WAIT_TO:
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. مثال صحيح: 10/03/2026"
            )
            return
        if d < user_data["area_from_date"]:
            await update.message.reply_text("تاريخ النهاية يجب أن يكون بعد تاريخ البداية.")
            return

        from_date = user_data["area_from_date"]
        user_data["area_to_date"] = d
        area_id = user_data.get("area_id")
        total_c, total_p, bal = get_area_summary(area_id, from_date, d)

        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT name FROM areas WHERE id=?", (area_id,))
        area_name = c.fetchone()[0]
        conn.close()

        msg = (
            f"كشف منطقة: {area_name}\n"
            f"الفترة: من {from_date} إلى {d}\n\n"
            f"إجمالي الاستهلاك (مبلغ): {total_c}\n"
            f"إجمالي المدفوع: {total_p}\n"
            f"إجمالي المتأخرات: {bal}"
        )

        filename = f"area_{area_id}_{datetime.utcnow().timestamp()}.pdf"
        generate_pdf(
            filename,
            "area",
            from_date,
            d,
            [],
            totals={"paid": total_p, "due": bal},
        )

        await update.message.reply_text(msg, reply_markup=admin_keyboard())
        await update.message.reply_document(
            document=InputFile(filename, filename=os.path.basename(filename)),
            caption="ملف كشف المنطقة (PDF).",
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    # ===================== كشف رئيسي =====================
    if state == STATE_ADMIN_MAIN_WAIT_FROM:
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. مثال صحيح: 01/01/2026"
            )
            return
        user_data["main_from_date"] = d
        await update.message.reply_text(
            "أدخل تاريخ النهاية بصيغة يوم/شهر/سنة (مثال: 10/03/2026):"
        )
        user_data[STATE_KEY] = STATE_ADMIN_MAIN_WAIT_TO
        return

    if state == STATE_ADMIN_MAIN_WAIT_TO:
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. مثال صحيح: 10/03/2026"
            )
            return
        if d < user_data["main_from_date"]:
            await update.message.reply_text("تاريخ النهاية يجب أن يكون بعد تاريخ البداية.")
            return

        from_date = user_data["main_from_date"]
        user_data["main_to_date"] = d
        total_c, total_p, bal = get_global_summary(from_date, d)
        msg = (
            "كشف رئيسي لجميع المناطق:\n"
            f"الفترة: من {from_date} إلى {d}\n\n"
            f"إجمالي الاستهلاك (مبلغ): {total_c}\n"
            f"إجمالي المدفوع: {total_p}\n"
            f"إجمالي المتأخرات: {bal}"
        )

        filename = f"main_{datetime.utcnow().timestamp()}.pdf"
        generate_pdf(
            filename,
            "main",
            from_date,
            d,
            [],
            totals={"paid": total_p, "due": bal},
        )

        await update.message.reply_text(msg, reply_markup=admin_keyboard())
        await update.message.reply_document(
            document=InputFile(filename, filename=os.path.basename(filename)),
            caption="ملف الكشف الرئيسي (PDF).",
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    # ===================== إرسال رسالة: نص الرسالة =====================
    if state == STATE_ADMIN_MSG_TEXT:
        msg_type = user_data.get("msg_type")
        text_msg = text

        if msg_type == "general":
            conn = get_conn()
            c = conn.cursor()
            c.execute("SELECT chat_id FROM subscribers WHERE chat_id IS NOT NULL")
            chats = [row[0] for row in c.fetchall()]
            conn.close()
            for ch in chats:
                try:
                    await context.bot.send_message(chat_id=ch, text=text_msg)
                except Exception:
                    pass
            log_message("general", "all", text_msg)
            await update.message.reply_text(
                "تم إرسال الرسالة العامة لجميع المشتركين.",
                reply_markup=admin_keyboard(),
            )
            user_data[STATE_KEY] = STATE_NONE
            return

        if msg_type == "area":
            area_ids = user_data.get("msg_area_ids", [])
            if not area_ids:
                await update.message.reply_text(
                    "لم يتم اختيار أي منطقة.", reply_markup=admin_keyboard()
                )
                user_data[STATE_KEY] = STATE_NONE
                return
            conn = get_conn()
            c = conn.cursor()
            for aid in area_ids:
                c.execute(
                    "SELECT chat_id FROM subscribers WHERE area_id=? AND chat_id IS NOT NULL",
                    (aid,),
                )
                chats = [row[0] for row in c.fetchall()]
                for ch in chats:
                    try:
                        await context.bot.send_message(chat_id=ch, text=text_msg)
                    except Exception:
                        pass
            conn.close()
            log_message("area", ",".join(map(str, area_ids)), text_msg)
            await update.message.reply_text(
                "تم إرسال الرسالة للمناطق المحددة.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return

        if msg_type == "sub":
            sub_id = user_data.get("msg_sub_id")
            sub = find_subscriber_by_id(sub_id)
            if not sub or not sub[5]:
                await update.message.reply_text(
                    "لا يوجد قناة مرتبطة بهذا المشترك.", reply_markup=admin_keyboard()
                )
                user_data[STATE_KEY] = STATE_NONE
                return
            try:
                await context.bot.send_message(chat_id=sub[5], text=text_msg)
            except Exception:
                pass
            log_message("subscriber", str(sub_id), text_msg)
            await update.message.reply_text(
                "تم إرسال الرسالة للمشترك.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return

# ===================== كشف حساب مشترك من جهة المدير =====================
async def handle_admin_sub_statement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    text = update.message.text
    state = user_data.get(STATE_KEY, STATE_NONE)

    if state == STATE_ADMIN_SUB_STATEMENT_WAIT_ACCOUNT:
        sub = find_subscriber_by_account(text)
        if not sub:
            await update.message.reply_text(
                "لم يتم العثور على مشترك بهذا الرقم.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return

        user_data["stmt_sub_id"] = sub[0]

        await update.message.reply_text(
            "أدخل تاريخ البداية بصيغة يوم/شهر/سنة (مثال: 01/01/2026):"
        )

        user_data[STATE_KEY] = STATE_ADMIN_SUB_STATEMENT_WAIT_FROM
        return

    if state == STATE_ADMIN_SUB_STATEMENT_WAIT_FROM:
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. مثال صحيح: 01/01/2026"
            )
            return

        user_data["stmt_from_date"] = d
        await update.message.reply_text(
            "أدخل تاريخ النهاية بصيغة يوم/شهر/سنة (مثال: 10/03/2026):"
        )
        user_data[STATE_KEY] = STATE_ADMIN_SUB_STATEMENT_WAIT_TO
        return

    if state == STATE_ADMIN_SUB_STATEMENT_WAIT_TO:
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. مثال صحيح: 10/03/2026"
            )
            return

        if d < user_data["stmt_from_date"]:
            await update.message.reply_text(
                "تاريخ النهاية يجب أن يكون بعد تاريخ البداية."
            )
            return

        from_date = user_data["stmt_from_date"]
        user_data["stmt_to_date"] = d
        sub_id = user_data.get("stmt_sub_id")
        sub = find_subscriber_by_id(sub_id)
        readings, payments = get_subscriber_statement(sub_id, from_date, d)

        filename = f"statement_{sub_id}_{datetime.utcnow().timestamp()}.pdf"
        generate_pdf(
            filename,
            "subscriber",
            from_date,
            d,
            (sub, readings, payments),
        )

        await update.message.reply_document(
            document=InputFile(filename, filename=os.path.basename(filename)),
            caption="كشف حساب المشترك (PDF).",
        )

        await update.message.reply_text("تم إرسال كشف الحساب.")
    
# ============ توجيه رسائل المدير ============
async def admin_text_router(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, state: str
):
    user_data = context.user_data

    # زر إلغاء العملية يعمل في أي وقت
    if text == "إلغاء العملية":
        user_data.clear()
        user_data[STATE_KEY] = STATE_NONE
        await update.message.reply_text(
            "تم إلغاء العملية والعودة إلى لوحة المدير.",
            reply_markup=admin_keyboard(),
        )
        return

    # لوحات الأزرار الرئيسية
    if state == STATE_NONE:
        if text == "مشترك جديد":
            serial = get_next_serial()
            user_data["new_sub_serial"] = serial
            await update.message.reply_text(
                f"إنشاء مشترك جديد.\nالرقم التسلسلي المقترح: {serial}\n"
                "الرجاء إدخال اسم المشترك (رباعي أو خماسي):",
                reply_markup=ReplyKeyboardRemove(),
            )
            user_data[STATE_KEY] = STATE_ADMIN_NEW_SUB_NAME
            return

        if text == "تعديل مشترك":
            await update.message.reply_text(
                "الرجاء إدخال رقم المشترك الذي تريد تعديله:",
                reply_markup=ReplyKeyboardRemove(),
            )
            user_data[STATE_KEY] = STATE_ADMIN_EDIT_SUB_WAIT_ACCOUNT
            return

        if text == "تسجيل قراءة":
            await update.message.reply_text(
                "الرجاء إدخال رقم المشترك لتسجيل القراءة:",
                reply_markup=ReplyKeyboardRemove(),
            )
            user_data[STATE_KEY] = STATE_ADMIN_READ_WAIT_ACCOUNT
            return

        if text == "تسجيل دفع":
            await update.message.reply_text(
                "الرجاء إدخال رقم المشترك لتسجيل الدفع:",
                reply_markup=ReplyKeyboardRemove(),
            )
            user_data[STATE_KEY] = STATE_ADMIN_PAY_WAIT_ACCOUNT
            return

        if text == "كشف مشترك":
            await update.message.reply_text(
                "الرجاء إدخال رقم المشترك للاستعلام:",
                reply_markup=ReplyKeyboardRemove(),
            )
            user_data[STATE_KEY] = STATE_ADMIN_INQ_WAIT_ACCOUNT
            return

        if text == "كشف منطقة":
            areas = get_all_areas()
            if not areas:
                await update.message.reply_text(
                    "لا توجد مناطق مسجلة بعد.", reply_markup=admin_keyboard()
                )
                return
            buttons = [
                [InlineKeyboardButton(a[1], callback_data=f"area_{a[0]}")]
                for a in areas
            ]
            await update.message.reply_text(
                "اختر المنطقة:",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            user_data[STATE_KEY] = STATE_ADMIN_AREA_CHOOSE
            return

        if text == "كشف رئيسي":
            await update.message.reply_text(
                "أدخل تاريخ البداية بصيغة يوم/شهر/سنة (مثال: 01/01/2026):",
                reply_markup=ReplyKeyboardRemove(),
            )
            user_data[STATE_KEY] = STATE_ADMIN_MAIN_WAIT_FROM
            return

        if text == "إرسال رسالة":
            buttons = [
                [
                    InlineKeyboardButton("عامة", callback_data="msg_type_general"),
                    InlineKeyboardButton("منطقة", callback_data="msg_type_area"),
                    InlineKeyboardButton("مشترك", callback_data="msg_type_sub"),
                ]
            ]
            await update.message.reply_text(
                "اختر نوع الرسالة:", reply_markup=InlineKeyboardMarkup(buttons)
            )
            user_data[STATE_KEY] = STATE_ADMIN_MSG_TYPE
            return

        if text == "إغلاق سنوي":
            buttons = [
                [
                    InlineKeyboardButton("موافق", callback_data="annual_ok"),
                    InlineKeyboardButton("إلغاء", callback_data="annual_cancel"),
                ]
            ]
            await update.message.reply_text(
                "هل أنت متأكد من تنفيذ الإغلاق السنوي؟",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            user_data[STATE_KEY] = STATE_ADMIN_ANNUAL_CONFIRM
            return

        # أي نص آخر
        await update.message.reply_text(
            "اختر من لوحة المدير أو استخدم الأوامر المتاحة.",
            reply_markup=admin_keyboard(),
        )
        return

    # مشترك جديد: إدخال الاسم
    if state == STATE_ADMIN_NEW_SUB_NAME:
        user_data["new_sub_name"] = text
        await update.message.reply_text("الرجاء إدخال رقم المشترك (رقم العداد):")
        user_data[STATE_KEY] = STATE_ADMIN_NEW_SUB_ACCOUNT
        return

    # مشترك جديد: إدخال رقم المشترك
    if state == STATE_ADMIN_NEW_SUB_ACCOUNT:
        user_data["new_sub_account"] = text
        await update.message.reply_text("الرجاء إدخال اسم المنطقة:")
        user_data[STATE_KEY] = STATE_ADMIN_NEW_SUB_AREA
        return

    # مشترك جديد: إدخال المنطقة
    if state == STATE_ADMIN_NEW_SUB_AREA:
        serial = user_data.get("new_sub_serial")
        name = user_data.get("new_sub_name")
        account_no = user_data.get("new_sub_account")
        area_name = text
        create_subscriber(serial, account_no, name, area_name)
        await update.message.reply_text(
            "تم حفظ المشترك الجديد بنجاح.\n"
            f"الرقم التسلسلي: {serial}\n"
            f"رقم المشترك: {account_no}\n"
            f"الاسم: {name}\n"
            f"المنطقة: {area_name}",
            reply_markup=admin_keyboard(),
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    # تعديل مشترك: إدخال رقم المشترك
    if state == STATE_ADMIN_EDIT_SUB_WAIT_ACCOUNT:
        sub = find_subscriber_by_account(text)
        if not sub:
            await update.message.reply_text(
                "لم يتم العثور على مشترك بهذا الرقم.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return
        user_data["edit_sub_id"] = sub[0]
        info = format_subscriber_info(sub)
        buttons = [
            [
                InlineKeyboardButton("تعديل الاسم", callback_data="edit_name"),
                InlineKeyboardButton("تعديل المنطقة", callback_data="edit_area"),
            ]
        ]
        await update.message.reply_text(
            "بيانات المشترك:\n\n" + info + "\nاختر ما تريد تعديله:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        user_data[STATE_KEY] = STATE_ADMIN_EDIT_SUB_CHOICE
        return

    # تعديل مشترك: إدخال اسم جديد
    if state == STATE_ADMIN_EDIT_SUB_NEW_NAME:
        sub_id = user_data.get("edit_sub_id")
        update_subscriber(sub_id, name=text)
        await update.message.reply_text(
            "تم تعديل الاسم بنجاح.", reply_markup=admin_keyboard()
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    # تعديل مشترك: إدخال منطقة جديدة
    if state == STATE_ADMIN_EDIT_SUB_NEW_AREA:
        sub_id = user_data.get("edit_sub_id")
        update_subscriber(sub_id, area_name=text)
        await update.message.reply_text(
            "تم تعديل المنطقة بنجاح.", reply_markup=admin_keyboard()
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    # تسجيل قراءة: إدخال رقم المشترك
    if state == STATE_ADMIN_READ_WAIT_ACCOUNT:
        sub = find_subscriber_by_account(text)
        if not sub:
            await update.message.reply_text(
                "لم يتم العثور على مشترك بهذا الرقم.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return
        user_data["read_sub_id"] = sub[0]
        await update.message.reply_text("الرجاء إدخال آخر قراءة (رقم العداد الحالي):")
        user_data[STATE_KEY] = STATE_ADMIN_READ_WAIT_VALUE
        return

    # تسجيل قراءة: إدخال القراءة
    if state == STATE_ADMIN_READ_WAIT_VALUE:
        try:
            curr_read = int(text)
        except ValueError:
            await update.message.reply_text("الرجاء إدخال رقم صحيح للقراءة.")
            return
        sub_id = user_data.get("read_sub_id")
        sub = find_subscriber_by_id(sub_id)
        prev_read, units, unit_price, amount = add_reading(sub_id, curr_read)
        user_data["read_curr"] = curr_read
        user_data["read_prev"] = prev_read
        user_data["read_units"] = units
        user_data["read_unit_price"] = unit_price
        user_data["read_amount"] = amount

        info = format_subscriber_info(sub)
        text_msg = (
            "تسجيل قراءة جديدة:\n\n"
            + info
            + f"القراءة السابقة: {prev_read}\n"
            f"القراءة الحالية: {curr_read}\n"
            f"فارق القراءات (وحدات): {units}\n"
            f"سعر الوحدة: {unit_price}\n"
            f"قيمة الاستهلاك: {amount}\n\n"
            "هل تريد حفظ هذه القراءة؟"
        )
        buttons = [
            [
                InlineKeyboardButton("حفظ", callback_data="read_save"),
                InlineKeyboardButton("تعديل", callback_data="read_edit"),
            ]
        ]
        await update.message.reply_text(
            text_msg, reply_markup=InlineKeyboardMarkup(buttons)
        )
        user_data[STATE_KEY] = STATE_ADMIN_READ_CONFIRM
        return

    # تسجيل دفع: إدخال رقم المشترك
    if state == STATE_ADMIN_PAY_WAIT_ACCOUNT:
        sub = find_subscriber_by_account(text)
        if not sub:
            await update.message.reply_text(
                "لم يتم العثور على مشترك بهذا الرقم.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return
        user_data["pay_sub_id"] = sub[0]
        await update.message.reply_text("الرجاء إدخال مبلغ الدفع:")
        user_data[STATE_KEY] = STATE_ADMIN_PAY_WAIT_AMOUNT
        return

    # تسجيل دفع: إدخال المبلغ
    if state == STATE_ADMIN_PAY_WAIT_AMOUNT:
        try:
            amount = int(text)
        except ValueError:
            await update.message.reply_text("الرجاء إدخال مبلغ صحيح (أرقام فقط).")
            return
        user_data["pay_amount"] = amount
        sub_id = user_data.get("pay_sub_id")
        sub = find_subscriber_by_id(sub_id)
        info = format_subscriber_info(sub)
        msg = (
            "تسجيل دفع جديد:\n\n"
            + info
            + f"المبلغ: {amount}\n\n"
            "هل تريد حفظ هذه العملية؟"
        )
        buttons = [
            [
                InlineKeyboardButton("حفظ", callback_data="pay_save"),
                InlineKeyboardButton("تعديل", callback_data="pay_edit"),
            ]
        ]
        await update.message.reply_text(
            msg, reply_markup=InlineKeyboardMarkup(buttons)
        )
        user_data[STATE_KEY] = STATE_ADMIN_PAY_CONFIRM
        return

    # كشف مشترك: إدخال رقم المشترك
    if state == STATE_ADMIN_INQ_WAIT_ACCOUNT:
        sub = find_subscriber_by_account(text)
        if not sub:
            await update.message.reply_text(
                "لم يتم العثور على مشترك بهذا الرقم.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return
        sub_id = sub[0]
        info = format_subscriber_status(sub_id)
        buttons = [
            [
                InlineKeyboardButton("إرسال للمشترك", callback_data=f"inq_send_{sub_id}"),
                InlineKeyboardButton("تجاهل", callback_data="inq_ignore"),
            ]
        ]
        await update.message.reply_text(
            info, reply_markup=InlineKeyboardMarkup(buttons)
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    # كشف منطقة: إدخال تاريخ البداية/النهاية
    if state == STATE_ADMIN_AREA_WAIT_FROM:
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. مثال صحيح: 01/01/2026"
            )
            return
        user_data["area_from_date"] = d
        await update.message.reply_text(
            "أدخل تاريخ النهاية بصيغة يوم/شهر/سنة (مثال: 10/03/2026):"
        )
        user_data[STATE_KEY] = STATE_ADMIN_AREA_WAIT_TO
        return

    if state == STATE_ADMIN_AREA_WAIT_TO:
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. مثال صحيح: 10/03/2026"
            )
            return
        if d < user_data["area_from_date"]:
            await update.message.reply_text("تاريخ النهاية يجب أن يكون بعد تاريخ البداية.")
            return

        user_data["area_to_date"] = d
        area_id = user_data.get("area_id")
        total_c, total_p, bal = get_area_summary(
            area_id, user_data["area_from_date"], user_data["area_to_date"]
        )
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT name FROM areas WHERE id=?", (area_id,))
        area_name = c.fetchone()[0]
        conn.close()

        msg = (
            f"كشف منطقة: {area_name}\n"
            f"الفترة: من {user_data['area_from_date']} إلى {user_data['area_to_date']}\n\n"
            f"إجمالي الاستهلاك (مبلغ): {total_c}\n"
            f"إجمالي المدفوع: {total_p}\n"
            f"إجمالي المتأخرات: {bal}"
        )

        filename = f"area_{area_id}_{datetime.utcnow().timestamp()}.pdf"
        generate_area_or_global_pdf(
            filename,
            f"كشف منطقة: {area_name}",
            user_data["area_from_date"],
            user_data["area_to_date"],
            total_c,
            total_p,
            bal,
        )

        await update.message.reply_text(msg, reply_markup=admin_keyboard())
        await update.message.reply_document(
            document=InputFile(filename, filename=os.path.basename(filename)),
            caption="ملف كشف المنطقة (PDF).",
        )
        finalize_pdf_file(filename)
        user_data[STATE_KEY] = STATE_NONE
        return

    # كشف رئيسي: إدخال تاريخ البداية/النهاية
    if state == STATE_ADMIN_MAIN_WAIT_FROM:
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. مثال صحيح: 01/01/2026"
            )
            return
        user_data["main_from_date"] = d
        await update.message.reply_text(
            "أدخل تاريخ النهاية بصيغة يوم/شهر/سنة (مثال: 10/03/2026):"
        )
        user_data[STATE_KEY] = STATE_ADMIN_MAIN_WAIT_TO
        return

    if state == STATE_ADMIN_MAIN_WAIT_TO:
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. مثال صحيح: 10/03/2026"
            )
            return
        if d < user_data["main_from_date"]:
            await update.message.reply_text("تاريخ النهاية يجب أن يكون بعد تاريخ البداية.")
            return

        user_data["main_to_date"] = d
        total_c, total_p, bal = get_global_summary(
            user_data["main_from_date"], user_data["main_to_date"]
        )
        msg = (
            "كشف رئيسي لجميع المناطق:\n"
            f"الفترة: من {user_data['main_from_date']} إلى {user_data['main_to_date']}\n\n"
            f"إجمالي الاستهلاك (مبلغ): {total_c}\n"
            f"إجمالي المدفوع: {total_p}\n"
            f"إجمالي المتأخرات: {bal}"
        )

        filename = f"main_{datetime.utcnow().timestamp()}.pdf"
        generate_area_or_global_pdf(
            filename,
            "كشف رئيسي لجميع المناطق",
            user_data["main_from_date"],
            user_data["main_to_date"],
            total_c,
            total_p,
            bal,
        )

        await update.message.reply_text(msg, reply_markup=admin_keyboard())
        await update.message.reply_document(
            document=InputFile(filename, filename=os.path.basename(filename)),
            caption="ملف الكشف الرئيسي (PDF).",
        )
        finalize_pdf_file(filename)
        user_data[STATE_KEY] = STATE_NONE
        return

    # إرسال رسالة: إدخال نص الرسالة
    if state == STATE_ADMIN_MSG_TEXT:
        msg_type = user_data.get("msg_type")
        text_msg = text

        if msg_type == "general":
            conn = get_conn()
            c = conn.cursor()
            c.execute("SELECT chat_id FROM subscribers WHERE chat_id IS NOT NULL")
            chats = [row[0] for row in c.fetchall()]
            conn.close()
            for ch in chats:
                try:
                    await context.bot.send_message(chat_id=ch, text=text_msg)
                except Exception:
                    pass
            log_message("general", "all", text_msg)
            await update.message.reply_text(
                "تم إرسال الرسالة العامة لجميع المشتركين.",
                reply_markup=admin_keyboard(),
            )
            user_data[STATE_KEY] = STATE_NONE
            return

        if msg_type == "area":
            area_ids = user_data.get("msg_area_ids", [])
            if not area_ids:
                await update.message.reply_text(
                    "لم يتم اختيار أي منطقة.", reply_markup=admin_keyboard()
                )
                user_data[STATE_KEY] = STATE_NONE
                return
            conn = get_conn()
            c = conn.cursor()
            for aid in area_ids:
                c.execute(
                    "SELECT chat_id FROM subscribers WHERE area_id=? AND chat_id IS NOT NULL",
                    (aid,),
                )
                chats = [row[0] for row in c.fetchall()]
                for ch in chats:
                    try:
                        await context.bot.send_message(chat_id=ch, text=text_msg)
                    except Exception:
                        pass
            conn.close()
            log_message("area", ",".join(map(str, area_ids)), text_msg)
            await update.message.reply_text(
                "تم إرسال الرسالة للمناطق المحددة.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return

        if msg_type == "sub":
            sub_id = user_data.get("msg_sub_id")
            sub = find_subscriber_by_id(sub_id)
            if not sub or not sub[5]:
                await update.message.reply_text(
                    "لا يوجد قناة مرتبطة بهذا المشترك.", reply_markup=admin_keyboard()
                )
                user_data[STATE_KEY] = STATE_NONE
                return
            try:
                await context.bot.send_message(chat_id=sub[5], text=text_msg)
            except Exception:
                pass
            log_message("subscriber", str(sub_id), text_msg)
            await update.message.reply_text(
                "تم إرسال الرسالة للمشترك.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return

    # كشف حساب مشترك من جهة المدير
    if state == STATE_ADMIN_SUB_STATEMENT_WAIT_ACCOUNT:
        sub = find_subscriber_by_account(text)
        if not sub:
            await update.message.reply_text(
                "لم يتم العثور على مشترك بهذا الرقم.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return
        user_data["stmt_sub_id"] = sub[0]
        await update.message.reply_text(
            "أدخل تاريخ البداية بصيغة يوم/شهر/سنة (مثال: 01/01/2026):"
        )
        user_data[STATE_KEY] = STATE_ADMIN_SUB_STATEMENT_WAIT_FROM
        return

    if state == STATE_ADMIN_SUB_STATEMENT_WAIT_FROM:
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. مثال صحيح: 01/01/2026"
            )
            return
        user_data["stmt_from_date"] = d
        await update.message.reply_text(
            "أدخل تاريخ النهاية بصيغة يوم/شهر/سنة (مثال: 10/03/2026):"
        )
        user_data[STATE_KEY] = STATE_ADMIN_SUB_STATEMENT_WAIT_TO
        return

    if state == STATE_ADMIN_SUB_STATEMENT_WAIT_TO:
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. مثال صحيح: 10/03/2026"
            )
            return
        if d < user_data["stmt_from_date"]:
            await update.message.reply_text("تاريخ النهاية يجب أن يكون بعد تاريخ البداية.")
            return

        user_data["stmt_to_date"] = d
        sub_id = user_data.get("stmt_sub_id")
        sub = find_subscriber_by_id(sub_id)
        readings, payments = get_subscriber_statement(
            sub_id, user_data["stmt_from_date"], user_data["stmt_to_date"]
        )
        filename = f"statement_{sub_id}_{datetime.utcnow().timestamp()}.pdf"
        generate_statement_pdf(
            filename,
            sub,
            user_data["stmt_from_date"],
            user_data["stmt_to_date"],
            readings,
            payments,
        )
        await update.message.reply_document(
            document=InputFile(filename, filename=os.path.basename(filename)),
            caption="كشف حساب المشترك (PDF).",
        )
        finalize_pdf_file(filename)
        await update.message.reply_text(
            "تم إرسال كشف الحساب.", reply_markup=admin_keyboard()
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    # إغلاق سنوي: إدخال كلمة السر
    if state == STATE_ADMIN_ANNUAL_PASSWORD:
        if text != ANNUAL_CLOSE_PASSWORD:
            await update.message.reply_text(
                "كلمة السر غير صحيحة. تم إلغاء الإغلاق السنوي.",
                reply_markup=admin_keyboard(),
            )
            user_data[STATE_KEY] = STATE_NONE
            return

        filename = f"annual_{datetime.utcnow().timestamp()}.pdf"
        generate_annual_pdf(filename)

        await update.message.reply_document(
            document=InputFile(filename, filename=os.path.basename(filename)),
            caption="تقرير الإغلاق السنوي (PDF).",
        )
        finalize_pdf_file(filename)
        await update.message.reply_text(
            "تم تنفيذ الإغلاق السنوي بنجاح.", reply_markup=admin_keyboard()
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    # في حال لم تُطابق أي حالة
    await update.message.reply_text(
        "لم أفهم هذا الإدخال في هذه المرحلة.\nاستخدم الأزرار أو زر 'إلغاء العملية' للبدء من جديد.",
        reply_markup=admin_keyboard(),
    )


# ============ توجيه رسائل المشترك ============
async def subscriber_text_router(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, state: str
):
    user_data = context.user_data
    sub = find_subscriber_by_chat(update.effective_chat.id)
    if not sub:
        await update.message.reply_text(
            "حسابك غير مرتبط كمشترك.\nأرسل /start واتبع التعليمات للربط."
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    sub_id = sub[0]

    # كشف حساب من جهة المشترك
    if state == STATE_SUB_STATEMENT_WAIT_FROM:
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. استخدم يوم/شهر/سنة."
            )
            return
        user_data["sub_stmt_from"] = d
        await update.message.reply_text("أدخل تاريخ النهاية بصيغة يوم/شهر/سنة:")
        user_data[STATE_KEY] = STATE_SUB_STATEMENT_WAIT_TO
        return

    if state == STATE_SUB_STATEMENT_WAIT_TO:
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. استخدم يوم/شهر/سنة."
            )
            return
        from_date = user_data["sub_stmt_from"]
        if d < from_date:
            await update.message.reply_text("تاريخ النهاية يجب أن يكون بعد البداية.")
            return
        user_data["sub_stmt_to"] = d
        readings, payments = get_subscriber_statement(
            sub_id, from_date, d
        )
        filename = f"sub_stmt_{sub_id}_{datetime.utcnow().timestamp()}.pdf"
        generate_pdf(
            filename,
            "subscriber",
            from_date,
            d,
            (sub, readings, payments),
        )
        await update.message.reply_document(
            document=InputFile(filename, filename=os.path.basename(filename)),
            caption="كشف حسابك (PDF).",
        )
        await update.message.reply_text(
            "تم إرسال كشف الحساب.", reply_markup=subscriber_keyboard()
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    # الحالات العامة للمشترك
    if text == "استعلام":
        info = format_subscriber_status(sub_id)
        await update.message.reply_text(info, reply_markup=subscriber_keyboard())
        return

    if text == "كشف حساب":
        await update.message.reply_text(
            "أدخل تاريخ البداية بصيغة يوم/شهر/سنة:",
            reply_markup=ReplyKeyboardRemove(),
        )
        user_data[STATE_KEY] = STATE_SUB_STATEMENT_WAIT_FROM
        return

    await update.message.reply_text(
        "استخدم الأزرار المتاحة في حساب المشترك.",
        reply_markup=subscriber_keyboard(),
    )
    user_data[STATE_KEY] = STATE_NONE
    # ============ معالجة أزرار Inline ============
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_data = context.user_data
    state = user_data.get(STATE_KEY, STATE_NONE)

    # تعديل مشترك: اختيار نوع التعديل
    if state == STATE_ADMIN_EDIT_SUB_CHOICE:
        if data == "edit_name":
            await query.edit_message_text("الرجاء إدخال الاسم الجديد للمشترك:")
            user_data[STATE_KEY] = STATE_ADMIN_EDIT_SUB_NEW_NAME
            return
        if data == "edit_area":
            await query.edit_message_text("الرجاء إدخال اسم المنطقة الجديدة:")
            user_data[STATE_KEY] = STATE_ADMIN_EDIT_SUB_NEW_AREA
            return

    # تسجيل قراءة: تأكيد/تعديل
    if state == STATE_ADMIN_READ_CONFIRM:
        if data == "read_save":
            sub_id = user_data.get("read_sub_id")
            sub = find_subscriber_by_id(sub_id)
            amount = user_data.get("read_amount")
            units = user_data.get("read_units")
            unit_price = user_data.get("read_unit_price")
            prev_read = user_data.get("read_prev")
            curr_read = user_data.get("read_curr")

            if sub and sub[5]:
                msg = (
                    "فاتورة استهلاك جديدة:\n\n"
                    + format_subscriber_info(sub)
                    + f"القراءة السابقة: {prev_read}\n"
                    f"القراءة الحالية: {curr_read}\n"
                    f"فارق القراءات (وحدات): {units}\n"
                    f"سعر الوحدة: {unit_price}\n"
                    f"قيمة الاستهلاك: {amount}\n"
                )
                try:
                    await context.bot.send_message(chat_id=sub[5], text=msg)
                except Exception:
                    pass

            await query.edit_message_text("تم حفظ القراءة وإرسال الفاتورة للمشترك.")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="اختر من لوحة المدير:",
                reply_markup=admin_keyboard(),
            )
            user_data[STATE_KEY] = STATE_NONE
            return

        if data == "read_edit":
            await query.edit_message_text("الرجاء إدخال القراءة مرة أخرى:")
            user_data[STATE_KEY] = STATE_ADMIN_READ_WAIT_VALUE
            return

    # تسجيل دفع: تأكيد/تعديل
    if state == STATE_ADMIN_PAY_CONFIRM:
        if data == "pay_save":
            sub_id = user_data.get("pay_sub_id")
            amount = user_data.get("pay_amount")
            add_payment(sub_id, amount)
            sub = find_subscriber_by_id(sub_id)
            if sub and sub[5]:
                msg = (
                    "سند قبض جديد:\n\n"
                    + format_subscriber_info(sub)
                    + f"المبلغ المدفوع: {amount}\n"
                )
                try:
                    await context.bot.send_message(chat_id=sub[5], text=msg)
                except Exception:
                    pass
            await query.edit_message_text("تم حفظ الدفع وإرسال سند القبض للمشترك.")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="اختر من لوحة المدير:",
                reply_markup=admin_keyboard(),
            )
            user_data[STATE_KEY] = STATE_NONE
            return

        if data == "pay_edit":
            await query.edit_message_text("الرجاء إدخال مبلغ الدفع مرة أخرى:")
            user_data[STATE_KEY] = STATE_ADMIN_PAY_WAIT_AMOUNT
            return

    # كشف مشترك: إرسال للمشترك أو تجاهل
    if data.startswith("inq_send_"):
        sub_id = int(data.split("_")[-1])
        sub = find_subscriber_by_id(sub_id)
        if sub and sub[5]:
            info = format_subscriber_status(sub_id)
            try:
                await context.bot.send_message(chat_id=sub[5], text=info)
            except Exception:
                pass
            await query.edit_message_text("تم إرسال كشف المشترك إليه.")
        else:
            await query.edit_message_text("لا يوجد قناة مرتبطة بهذا المشترك.")
        return

    if data == "inq_ignore":
        await query.edit_message_text("تم تجاهل العملية.")
        return

    # كشف منطقة: اختيار المنطقة
    if state == STATE_ADMIN_AREA_CHOOSE and data.startswith("area_"):
        area_id = int(data.split("_")[1])
        user_data["area_id"] = area_id
        await query.edit_message_text(
            "أدخل تاريخ البداية بصيغة يوم/شهر/سنة:"
        )
        user_data[STATE_KEY] = STATE_ADMIN_AREA_WAIT_FROM
        return

    # إرسال رسالة: اختيار نوع الرسالة
    if state == STATE_ADMIN_MSG_TYPE:
        if data == "msg_type_general":
            user_data["msg_type"] = "general"
            await query.edit_message_text("اكتب نص الرسالة العامة:")
            user_data[STATE_KEY] = STATE_ADMIN_MSG_TEXT
            return

        if data == "msg_type_area":
            user_data["msg_type"] = "area"
            areas = get_all_areas()
            if not areas:
                await query.edit_message_text("لا توجد مناطق مسجلة.")
                user_data[STATE_KEY] = STATE_NONE
                return
            buttons = []
            for a in areas:
                buttons.append(
                    [InlineKeyboardButton(a[1], callback_data=f"msg_area_{a[0]}")]
                )
            buttons.append(
                [InlineKeyboardButton("تم الاختيار", callback_data="msg_area_done")]
            )
            await query.edit_message_text(
                "اختر منطقة أو أكثر (بالضغط على الأزرار)، ثم اضغط (تم الاختيار):",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            user_data["msg_area_ids"] = []
            return

        if data == "msg_type_sub":
            user_data["msg_type"] = "sub"
            await query.edit_message_text(
                "أدخل رقم المشترك أو اسم المشترك:"
            )
            user_data[STATE_KEY] = STATE_ADMIN_MSG_SUB_WAIT
            return

    # إرسال رسالة: اختيار مناطق متعددة
    if data.startswith("msg_area_") and not data.endswith("done"):
        area_id = int(data.split("_")[2])
        area_ids = user_data.get("msg_area_ids", [])
        if area_id not in area_ids:
            area_ids.append(area_id)
        user_data["msg_area_ids"] = area_ids
        await query.answer("تم اختيار المنطقة.")
        return

    if data == "msg_area_done":
        area_ids = user_data.get("msg_area_ids", [])
        if not area_ids:
            await query.edit_message_text("لم يتم اختيار أي منطقة.")
            user_data[STATE_KEY] = STATE_NONE
            return
        await query.edit_message_text("اكتب نص الرسالة لإرسالها للمناطق المحددة:")
        user_data[STATE_KEY] = STATE_ADMIN_MSG_TEXT
        return

    # إرسال رسالة: اختيار مشترك (النص يعالج في msg_sub_text_handler)
    if state == STATE_ADMIN_MSG_SUB_WAIT:
        return

    # إغلاق سنوي: موافق/إلغاء
    if state == STATE_ADMIN_ANNUAL_CONFIRM:
        if data == "annual_ok":
            await query.edit_message_text("الرجاء إدخال كلمة السر للإغلاق السنوي:")
            user_data[STATE_KEY] = STATE_ADMIN_ANNUAL_PASSWORD
            return
        if data == "annual_cancel":
            await query.edit_message_text("تم إلغاء الإغلاق السنوي.")
            user_data[STATE_KEY] = STATE_NONE
            return

    await query.edit_message_text("تمت معالجة الطلب أو انتهت الحالة.")
    user_data[STATE_KEY] = STATE_NONE


# ============ بحث عن مشترك بالاسم أو الرقم للرسائل ============
async def msg_sub_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    text = update.message.text.strip()
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        SELECT s.id, s.serial, s.account_no, s.name, s.area_id, s.chat_id, a.name
        FROM subscribers s
        LEFT JOIN areas a ON s.area_id = a.id
        WHERE s.account_no=?
    """,
        (text,),
    )
    row = c.fetchone()
    if not row:
        c.execute(
            """
            SELECT s.id, s.serial, s.account_no, s.name, s.area_id, s.chat_id, a.name
            FROM subscribers s
            LEFT JOIN areas a ON s.area_id = a.id
            WHERE s.name LIKE ?
        """,
            (f"%{text}%",),
        )
        row = c.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text(
            "لم يتم العثور على مشترك بهذا الاسم أو الرقم.",
            reply_markup=admin_keyboard(),
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    user_data["msg_sub_id"] = row[0]
    info = format_subscriber_info(row)
    await update.message.reply_text(
        "تم اختيار المشترك:\n\n" + info + "\nاكتب نص الرسالة:",
        reply_markup=ReplyKeyboardRemove(),
    )
    user_data[STATE_KEY] = STATE_ADMIN_MSG_TEXT


# ============ هاندلر النص مع دعم اختيار المشترك للرسائل ============
async def text_handler_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    state = user_data.get(STATE_KEY, STATE_NONE)
    if is_admin(update) and state == STATE_ADMIN_MSG_SUB_WAIT:
        await msg_sub_text_handler(update, context)
    else:
        await text_handler(update, context)


# ============ توليد تقرير الإغلاق السنوي PDF ============
def generate_annual_pdf(filename: str):
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    y = height - 60

    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, y, "تقرير الإغلاق السنوي لمشروع مياة قرية بيت الأقرع")
    y -= 40

    today = datetime.utcnow().date()
    c.setFont("Helvetica", 12)
    c.drawString(50, y, f"تاريخ التقرير: {today}")
    y -= 30

    # ملخص عام من قاعدة البيانات
    from_date = date(today.year, 1, 1)
    to_date = date(today.year, 12, 31)
    total_c, total_p, bal = get_global_summary(from_date, to_date)

    c.drawString(50, y, f"الفترة: من {from_date} إلى {to_date}")
    y -= 25
    c.drawString(50, y, f"إجمالي الاستهلاك (مبلغ): {total_c}")
    y -= 20
    c.drawString(50, y, f"إجمالي المدفوع: {total_p}")
    y -= 20
    c.drawString(50, y, f"إجمالي المتأخرات: {bal}")
    y -= 40

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 60, "مدير المشروع/ صالح الطويل")
    c.drawString(50, 40, "التوقيع/ ____________________")

    force_save_pdf(c)
    # ============ أوامر البداية والدخول ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    user_data.setdefault(STATE_KEY, STATE_NONE)
    chat_id = update.effective_chat.id

    # إن كان مديراً
    if is_admin(update):
        await update.message.reply_text(
            "مرحباً بك مدير المشروع.\nاستخدم لوحة المدير لإدارة المشتركين.",
            reply_markup=admin_keyboard(),
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    # إن كان مشتركاً مرتبطاً مسبقاً
    sub = find_subscriber_by_chat(chat_id)
    if sub:
        await update.message.reply_text(
            "مرحباً بك في نظام مشروع المياه.\nيمكنك استخدام الأزرار أدناه.",
            reply_markup=subscriber_keyboard(),
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    # ربط مشترك جديد
    await update.message.reply_text(
        "مرحباً بك في نظام مشروع المياه.\n"
        "لربط حسابك كمشترك، الرجاء إدخال الرقم التسلسلي (المكتوب في الدفتر):",
        reply_markup=ReplyKeyboardRemove(),
    )
    user_data[STATE_KEY] = STATE_SUB_LINK_WAIT_SERIAL


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    admin_id = get_admin_user_id()

    # تعيين المدير لأول مرة
    if not admin_id:
        set_admin_user_id(user.id)
        await update.message.reply_text(
            "تم تعيينك كمدير للمشروع.\nاستخدم لوحة المدير لإدارة النظام.",
            reply_markup=admin_keyboard(),
        )
        context.user_data[STATE_KEY] = STATE_NONE
        return

    # إن لم يكن هو المدير المسجل
    if user.id != admin_id:
        await update.message.reply_text(
            "هذا الأمر خاص بمدير المشروع فقط.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # مدير مسجل مسبقاً
    await update.message.reply_text(
        "مرحباً بك مدير المشروع.\nاختر من لوحة المدير:",
        reply_markup=admin_keyboard(),
    )
    context.user_data[STATE_KEY] = STATE_NONE


# ============ هاندلر النص الأساسي ============
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    state = user_data.get(STATE_KEY, STATE_NONE)
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    # إن كان مديراً
    if is_admin(update):
        await admin_text_router(update, context, text, state)
        return

    # ربط المشترك لأول مرة
    if state == STATE_SUB_LINK_WAIT_SERIAL:
        # حفظ الرقم التسلسلي مؤقتاً
        user_data["link_serial"] = text
        await update.message.reply_text(
            "الرجاء إدخال رقم المشترك (رقم العداد):"
        )
        user_data[STATE_KEY] = STATE_SUB_LINK_WAIT_ACCOUNT
        return

    if state == STATE_SUB_LINK_WAIT_ACCOUNT:
        serial = user_data.get("link_serial")
        account_no = text
        try:
            serial_int = int(serial)
        except Exception:
            await update.message.reply_text(
                "الرقم التسلسلي غير صحيح.\nأعد إرسال /start وحاول مرة أخرى."
            )
            user_data[STATE_KEY] = STATE_NONE
            return

        sub = find_subscriber_by_serial_and_account(serial_int, account_no)
        if not sub:
            await update.message.reply_text(
                "لم يتم العثور على مشترك بهذه البيانات.\n"
                "تأكد من الرقم التسلسلي ورقم المشترك ثم أعد إرسال /start.",
            )
            user_data[STATE_KEY] = STATE_NONE
            return

        # ربط هذا التليجرام بالمشترك
        link_subscriber_chat(serial_int, account_no, chat_id)
        await update.message.reply_text(
            "تم ربط حسابك كمشترك بنجاح.\nيمكنك الآن استخدام الأزرار أدناه.",
            reply_markup=subscriber_keyboard(),
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    # إن لم يكن مديراً ولا في حالة ربط، فهو مشترك عادي
    await subscriber_text_router(update, context, text, state)


# ============ نقطة الدخول وتشغيل البوت ============
def main():
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler_wrapper)
    )

    # تشغيل دالة منع توقف البوت في خيط منفصل
    import threading
    threading.Thread(target=keep_bot_alive, daemon=True).start()

    # تشغيل البوت
    app.run_polling()


if __name__ == "__main__":
    main()
    
