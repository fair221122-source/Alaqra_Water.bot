# ================== imports & config ==================
import os
import sqlite3
from datetime import datetime, date
from typing import Optional, Tuple, List

from telegram import (
    Update,
    ReplyKeyboardMarkup,
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

# مكتبة توليد ملفات PDF
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

TOKEN = "8090667485:AAGCgIlZPEB069W_bhpIr0HBdp20GpfCCPI"
DB_PATH = "water_project.db"
ANNUAL_CLOSE_PASSWORD = "09092009"  # يمكنك تغييره

# ================== keyboards ==================
def admin_keyboard():
    keyboard = [
        ["مشترك جديد", "تعديل مشترك"],
        ["تسجيل قراءة", "تسجيل دفع"],
        ["كشف مشترك", "كشف منطقة"],
        ["كشف رئيسي", "إرسال رسالة"],
        ["إغلاق سنوي", "تراجع عن آخر حفظ"],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def subscriber_keyboard():
    keyboard = [["استعلام", "كشف حساب"]]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


# ================== states ==================
STATE_KEY = "state"

STATE_NONE = "NONE"

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

# حالات اختيار التاريخ (سنة/شهر/يوم) عبر الأزرار
STATE_DATE_PICK_TARGET = "DATE_PICK_TARGET"  # نستخدمه مع user_data["date_target_state"]


# ================== DB helpers ==================
def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            user_id INTEGER
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
            serial INTEGER NOT NULL,
            account_no TEXT NOT NULL,
            name TEXT NOT NULL,
            area_id INTEGER,
            chat_id INTEGER,
            FOREIGN KEY(area_id) REFERENCES areas(id)
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_id INTEGER NOT NULL,
            prev_read INTEGER NOT NULL,
            curr_read INTEGER NOT NULL,
            units INTEGER NOT NULL,
            unit_price INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(subscriber_id) REFERENCES subscribers(id)
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(subscriber_id) REFERENCES subscribers(id)
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS actions_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,
            ref_id INTEGER,
            created_at TEXT NOT NULL
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
            created_at TEXT NOT NULL
        )
        """
    )

    conn.commit()

    # إدخال المناطق الثابتة إن لم تكن موجودة
    areas = [
        "الحمراء",
        "الجبوبة",
        "عرض الجبل",
        "شمضات",
        "حظي",
        "الوادي",
        "بيع مباشر",
    ]
    for a in areas:
        try:
            c.execute("INSERT INTO areas(name) VALUES(?)", (a,))
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()


# ================== admin id helpers ==================
def get_admin_user_id() -> Optional[int]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id FROM admin WHERE id=1")
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return row[0]
    return None


def set_admin_user_id(user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO admin(id, user_id) VALUES(1, ?)", (user_id,))
    conn.commit()
    conn.close()


# ================== subscribers helpers ==================
def get_area_by_name(name: str) -> Optional[int]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM areas WHERE name=?", (name,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def get_all_areas():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, name FROM areas ORDER BY id")
    rows = c.fetchall()
    conn.close()
    return rows


def create_subscriber(serial: int, account_no: str, name: str, area_name: str):
    conn = get_conn()
    c = conn.cursor()
    try:
        area_id = get_area_by_name(area_name)
        if not area_id:
            return None, "المنطقة غير موجودة في القائمة."
        c.execute(
            """
            INSERT INTO subscribers(serial, account_no, name, area_id)
            VALUES(?,?,?,?)
            """,
            (serial, account_no, name, area_id),
        )
        sub_id = c.lastrowid
        conn.commit()
        return sub_id, None
    except Exception as e:
        conn.rollback()
        return None, str(e)
    finally:
        conn.close()


def update_subscriber(sub_id: int, name: str = None, area_name: str = None):
    conn = get_conn()
    c = conn.cursor()
    if name is not None:
        c.execute("UPDATE subscribers SET name=? WHERE id=?", (name, sub_id))
    if area_name is not None:
        area_id = get_area_by_name(area_name)
        if area_id:
            c.execute("UPDATE subscribers SET area_id=? WHERE id=?", (area_id, sub_id))
    conn.commit()
    conn.close()


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


def link_subscriber_chat(serial: int, account_no: str, chat_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE subscribers SET chat_id=? WHERE serial=? AND account_no=?",
        (chat_id, serial, account_no),
    )
    conn.commit()
    conn.close()


def get_all_subscribers():
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT s.id, s.serial, s.account_no, s.name, s.area_id, s.chat_id, a.name
        FROM subscribers s
        LEFT JOIN areas a ON s.area_id = a.id
        ORDER BY s.id
        """
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_subscribers_by_area(area_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT s.id, s.serial, s.account_no, s.name, s.area_id, s.chat_id, a.name
        FROM subscribers s
        LEFT JOIN areas a ON s.area_id = a.id
        WHERE s.area_id=?
        ORDER BY s.id
        """,
        (area_id,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_next_serial() -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT MAX(serial) FROM subscribers")
    row = c.fetchone()
    conn.close()
    max_serial = row[0] if row and row[0] else 0
    return max_serial + 1


# ================== readings & payments ==================
UNIT_PRICE_DEFAULT = 500  # مثال


def get_last_reading(sub_id: int) -> Optional[int]:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT curr_read FROM readings WHERE subscriber_id=? ORDER BY id DESC LIMIT 1",
        (sub_id,),
    )
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def add_reading(sub_id: int, curr_read: int):
    prev = get_last_reading(sub_id)
    if prev is None:
        prev = 0
    units = curr_read - prev
    if units < 0:
        units = 0
    unit_price = UNIT_PRICE_DEFAULT
    amount = units * unit_price
    now = datetime.utcnow().isoformat()

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO readings(subscriber_id, prev_read, curr_read, units, unit_price, amount, created_at)
        VALUES(?,?,?,?,?,?,?)
        """,
        (sub_id, prev, curr_read, units, unit_price, amount, now),
    )
    c.execute(
        "INSERT INTO actions_log(action_type, ref_id, created_at) VALUES(?,?,?)",
        ("reading", c.lastrowid, now),
    )
    conn.commit()
    conn.close()
    return prev, units, unit_price, amount


def add_payment(sub_id: int, amount: int):
    now = datetime.utcnow().isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO payments(subscriber_id, amount, created_at) VALUES(?,?,?)",
        (sub_id, amount, now),
    )
    c.execute(
        "INSERT INTO actions_log(action_type, ref_id, created_at) VALUES(?,?,?)",
        ("payment", c.lastrowid, now),
    )
    conn.commit()
    conn.close()


def undo_last_action():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, action_type, ref_id FROM actions_log ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    if not row:
        conn.close()
        return False, "لا يوجد عمليات للتراجع عنها."
    log_id, action_type, ref_id = row
    if action_type == "reading":
        c.execute("DELETE FROM readings WHERE id=?", (ref_id,))
    elif action_type == "payment":
        c.execute("DELETE FROM payments WHERE id=?", (ref_id,))
    c.execute("DELETE FROM actions_log WHERE id=?", (log_id,))
    conn.commit()
    conn.close()
    return True, "تم التراجع عن آخر عملية بنجاح."


# ================== summaries ==================
def get_subscriber_summary(sub_id: int):
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        SELECT prev_read, curr_read, units, unit_price, amount, created_at
        FROM readings
        WHERE subscriber_id=?
        ORDER BY id DESC LIMIT 1
        """,
        (sub_id,),
    )
    last = c.fetchone()

    c.execute(
        "SELECT COALESCE(SUM(amount),0) FROM readings WHERE subscriber_id=?",
        (sub_id,),
    )
    total_c = c.fetchone()[0]

    c.execute(
        "SELECT COALESCE(SUM(amount),0) FROM payments WHERE subscriber_id=?",
        (sub_id,),
    )
    total_p = c.fetchone()[0]

    conn.close()
    balance = total_c - total_p
    return {
        "last_read": last,
        "total_consumption_amount": total_c,
        "total_payments": total_p,
        "balance": balance,
    }


def get_subscriber_statement(sub_id: int, from_date: date, to_date: date):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT prev_read, curr_read, units, unit_price, amount, created_at
        FROM readings
        WHERE subscriber_id=? AND date(created_at) BETWEEN ? AND ?
        ORDER BY created_at
        """,
        (sub_id, from_date.isoformat(), to_date.isoformat()),
    )
    readings = c.fetchall()

    c.execute(
        """
        SELECT amount, created_at
        FROM payments
        WHERE subscriber_id=? AND date(created_at) BETWEEN ? AND ?
        ORDER BY created_at
        """,
        (sub_id, from_date.isoformat(), to_date.isoformat()),
    )
    payments = c.fetchall()
    conn.close()
    return readings, payments


def get_area_summary(area_id: int, from_date: date, to_date: date):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT s.id
        FROM subscribers s
        WHERE s.area_id=?
        """,
        (area_id,),
    )
    subs = [r[0] for r in c.fetchall()]
    total_c = 0
    total_p = 0
    for sid in subs:
        c.execute(
            """
            SELECT COALESCE(SUM(amount),0)
            FROM readings
            WHERE subscriber_id=? AND date(created_at) BETWEEN ? AND ?
            """,
            (sid, from_date.isoformat(), to_date.isoformat()),
        )
        total_c += c.fetchone()[0] or 0
        c.execute(
            """
            SELECT COALESCE(SUM(amount),0)
            FROM payments
            WHERE subscriber_id=? AND date(created_at) BETWEEN ? AND ?
            """,
            (sid, from_date.isoformat(), to_date.isoformat()),
        )
        total_p += c.fetchone()[0] or 0
    conn.close()
    bal = total_c - total_p
    return total_c, total_p, bal


def get_global_summary(from_date: date, to_date: date):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT COALESCE(SUM(amount),0)
        FROM readings
        WHERE date(created_at) BETWEEN ? AND ?
        """,
        (from_date.isoformat(), to_date.isoformat()),
    )
    total_c = c.fetchone()[0] or 0

    c.execute(
        """
        SELECT COALESCE(SUM(amount),0)
        FROM payments
        WHERE date(created_at) BETWEEN ? AND ?
        """,
        (from_date.isoformat(), to_date.isoformat()),
    )
    total_p = c.fetchone()[0] or 0
    conn.close()
    bal = total_c - total_p
    return total_c, total_p, bal


def log_message(msg_type: str, target: str, text: str):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute(
        "INSERT INTO messages_log(msg_type, target, text, created_at) VALUES(?,?,?,?)",
        (msg_type, target, text, now),
    )
    conn.commit()
    conn.close()


# ================== PDF helpers ==================
def _draw_header(c: canvas.Canvas, title: str, period: str):
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(105 * mm, 280 * mm, "مشروع مياة قرية بيت الأقرع الأهلي")
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(105 * mm, 272 * mm, title)
    c.setFont("Helvetica", 10)
    c.drawCentredString(105 * mm, 266 * mm, period)


def generate_statement_pdf(
    filename: str,
    sub_row,
    from_date: date,
    to_date: date,
    readings,
    payments,
):
    c = canvas.Canvas(filename, pagesize=A4)
    period = f"الفترة من {from_date} إلى {to_date}"
    _draw_header(c, "كشف حساب مشترك", period)

    x_margin = 20 * mm
    y = 250 * mm

    # بيانات المشترك
    c.setFont("Helvetica", 10)
    c.drawString(x_margin, y, f"الاسم: {sub_row[3]}")
    y -= 6 * mm
    c.drawString(x_margin, y, f"الرقم التسلسلي: {sub_row[1]}")
    y -= 6 * mm
    c.drawString(x_margin, y, f"رقم المشترك (رقم العدّاد): {sub_row[2]}")
    y -= 6 * mm
    c.drawString(x_margin, y, f"المنطقة: {sub_row[6] or '-'}")
    y -= 10 * mm

    # جدول القراءات
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x_margin, y, "القراءات:")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    c.drawString(x_margin, y, "التاريخ | السابقة | الحالية | الوحدات | سعر الوحدة | المبلغ")
    y -= 4 * mm
    c.line(x_margin, y, 190 * mm, y)
    y -= 4 * mm

    for r in readings:
        if y < 40 * mm:
            c.showPage()
            y = 270 * mm
        prev_read, curr_read, units, unit_price, amount, created_at = r
        line = f"{created_at[:10]} | {prev_read} | {curr_read} | {units} | {unit_price} | {amount}"
        c.drawString(x_margin, y, line)
        y -= 5 * mm

    y -= 6 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x_margin, y, "المدفوعات:")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    c.drawString(x_margin, y, "التاريخ | المبلغ")
    y -= 4 * mm
    c.line(x_margin, y, 190 * mm, y)
    y -= 4 * mm

    for p in payments:
        if y < 40 * mm:
            c.showPage()
            y = 270 * mm
        amount, created_at = p
        line = f"{created_at[:10]} | {amount}"
        c.drawString(x_margin, y, line)
        y -= 5 * mm

    # ملخص
    summary = get_subscriber_summary(sub_row[0])
    y -= 8 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(
        x_margin,
        y,
        f"إجمالي الاستهلاك (مبلغ): {summary['total_consumption_amount']}",
    )
    y -= 6 * mm
    c.drawString(x_margin, y, f"إجمالي المدفوع: {summary['total_payments']}")
    y -= 6 * mm
    c.drawString(x_margin, y, f"إجمالي المتأخرات: {summary['balance']}")

    c.showPage()
    c.save()


def generate_area_or_global_pdf(
    filename: str,
    title: str,
    from_date: date,
    to_date: date,
    total_c: int,
    total_p: int,
    bal: int,
    rows: List[tuple] = None,
    is_global: bool = False,
):
    c = canvas.Canvas(filename, pagesize=A4)
    period = f"الفترة من {from_date} إلى {to_date}"
    _draw_header(c, title, period)

    x_margin = 15 * mm
    y = 250 * mm
    c.setFont("Helvetica", 9)

    # رأس الجدول
    if is_global:
        header = "م | الاسم | رقم المشترك | المنطقة | المدفوع | المتأخرات"
    else:
        header = "م | الاسم | رقم المشترك | المدفوع | المتأخرات"

    c.drawString(x_margin, y, header)
    y -= 4 * mm
    c.line(x_margin, y, 190 * mm, y)
    y -= 4 * mm

    if rows:
        idx = 1
        for row in rows:
            if y < 40 * mm:
                c.showPage()
                y = 270 * mm
                c.setFont("Helvetica", 9)
                c.drawString(x_margin, y, header)
                y -= 4 * mm
                c.line(x_margin, y, 190 * mm, y)
                y -= 4 * mm

            if is_global:
                name, account_no, area_name, paid, debt = row
                line = f"{idx} | {name} | {account_no} | {area_name} | {paid} | {debt}"
            else:
                name, account_no, paid, debt = row
                line = f"{idx} | {name} | {account_no} | {paid} | {debt}"
            c.drawString(x_margin, y, line)
            y -= 5 * mm
            idx += 1

    y -= 6 * mm
    c.line(x_margin, y, 190 * mm, y)
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x_margin, y, f"إجمالي الاستهلاك (مبلغ): {total_c}")
    y -= 6 * mm
    c.drawString(x_margin, y, f"إجمالي المدفوعات: {total_p}")
    y -= 6 * mm
    c.drawString(x_margin, y, f"إجمالي المتأخرات: {bal}")
    y -= 10 * mm
    c.drawString(x_margin, y, "مدير المشروع/ صالح الطويل")
    y -= 6 * mm
    c.drawString(x_margin, y, "التوقيع/ ____________________")

    c.showPage()
    c.save()


def generate_annual_pdf(filename: str):
    # تقرير بسيط سنوي
    today = datetime.utcnow().date()
    from_date = date(today.year, 1, 1)
    to_date = date(today.year, 12, 31)
    total_c, total_p, bal = get_global_summary(from_date, to_date)

    c = canvas.Canvas(filename, pagesize=A4)
    period = f"الفترة من {from_date} إلى {to_date}"
    _draw_header(c, "تقرير الإغلاق السنوي", period)

    x_margin = 20 * mm
    y = 250 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_margin, y, f"إجمالي الاستهلاك (مبلغ): {total_c}")
    y -= 8 * mm
    c.drawString(x_margin, y, f"إجمالي المدفوع: {total_p}")
    y -= 8 * mm
    c.drawString(x_margin, y, f"إجمالي المتأخرات: {bal}")
    y -= 15 * mm
    c.drawString(x_margin, y, "مدير المشروع/ صالح الطويل")
    y -= 8 * mm
    c.drawString(x_margin, y, "التوقيع/ ____________________")

    c.showPage()
    c.save()


# ================== helpers ==================
def is_admin(update: Update) -> bool:
    admin_id = get_admin_user_id()
    if not admin_id:
        return False
    return update.effective_user and update.effective_user.id == admin_id


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
  # ================== date picker via inline ==================
# سنستخدمه بدل إدخال التاريخ يدوياً
def build_year_keyboard(current_year: int, years_back: int = 5):
    buttons = []
    for y in range(current_year, current_year - years_back - 1, -1):
        buttons.append([InlineKeyboardButton(str(y), callback_data=f"date_year_{y}")])
    return InlineKeyboardMarkup(buttons)


def build_month_keyboard():
    buttons = []
    for m in range(1, 13):
        buttons.append(
            [InlineKeyboardButton(str(m), callback_data=f"date_month_{m}")]
        )
    return InlineKeyboardMarkup(buttons)


def build_day_keyboard(year: int, month: int):
    import calendar

    days_in_month = calendar.monthrange(year, month)[1]
    buttons = []
    row = []
    for d in range(1, days_in_month + 1):
        row.append(InlineKeyboardButton(str(d), callback_data=f"date_day_{d}"))
        if len(row) == 7:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


async def start_date_pick(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    target_state: str,
    prompt_text: str,
):
    user_data = context.user_data
    user_data[STATE_KEY] = STATE_DATE_PICK_TARGET
    user_data["date_target_state"] = target_state
    user_data["date_pick_year"] = None
    user_data["date_pick_month"] = None
    user_data["date_pick_day"] = None

    now = datetime.utcnow()
    kb = build_year_keyboard(now.year)
    await update.message.reply_text(
        prompt_text + "\nاختر السنة:",
        reply_markup=kb,
    )


async def handle_date_pick_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    data = query.data
    user_data = context.user_data

    if user_data.get(STATE_KEY) != STATE_DATE_PICK_TARGET:
        return False

    year = user_data.get("date_pick_year")
    month = user_data.get("date_pick_month")
    day = user_data.get("date_pick_day")

    if data.startswith("date_year_"):
        year = int(data.split("_")[-1])
        user_data["date_pick_year"] = year
        kb = build_month_keyboard()
        await query.edit_message_text(
            f"السنة المختارة: {year}\nاختر الشهر:",
            reply_markup=kb,
        )
        return True

    if data.startswith("date_month_") and year:
        month = int(data.split("_")[-1])
        user_data["date_pick_month"] = month
        kb = build_day_keyboard(year, month)
        await query.edit_message_text(
            f"السنة: {year} - الشهر: {month}\nاختر اليوم:",
            reply_markup=kb,
        )
        return True

    if data.startswith("date_day_") and year and month:
        day = int(data.split("_")[-1])
        user_data["date_pick_day"] = day
        d = date(year, month, day)
        target_state = user_data.get("date_target_state")

        # تنظيف حالة اختيار التاريخ
        user_data[STATE_KEY] = target_state
        user_data["picked_date"] = d

        await query.edit_message_text(
            f"تم اختيار التاريخ: {d}",
        )
        return True

    return False


# ================== admin subscriber statement ==================
async def handle_admin_sub_statement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    state = user_data.get(STATE_KEY, STATE_NONE)

    if state == STATE_ADMIN_SUB_STATEMENT_WAIT_ACCOUNT:
        text = update.message.text.strip()
        sub = find_subscriber_by_account(text)
        if not sub:
            await update.message.reply_text(
                "لم يتم العثور على مشترك بهذا الرقم.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return

        user_data["stmt_sub_id"] = sub[0]
        await start_date_pick(
            update,
            context,
            STATE_ADMIN_SUB_STATEMENT_WAIT_FROM,
            "اختر تاريخ البداية:",
        )
        return

    if state == STATE_ADMIN_SUB_STATEMENT_WAIT_FROM:
        d = user_data.get("picked_date")
        if not d:
            await update.message.reply_text("لم يتم اختيار تاريخ صحيح.")
            return
        user_data["stmt_from_date"] = d
        await update.message.reply_text("الآن اختر تاريخ النهاية:")
        await start_date_pick(
            update,
            context,
            STATE_ADMIN_SUB_STATEMENT_WAIT_TO,
            "اختر تاريخ النهاية:",
        )
        return

    if state == STATE_ADMIN_SUB_STATEMENT_WAIT_TO:
        d = user_data.get("picked_date")
        if not d:
            await update.message.reply_text("لم يتم اختيار تاريخ صحيح.")
            return

        if d < user_data["stmt_from_date"]:
            await update.message.reply_text(
                "تاريخ النهاية يجب أن يكون بعد تاريخ البداية."
            )
            return

        from_date = user_data["stmt_from_date"]
        to_date = d
        user_data["stmt_to_date"] = to_date
        sub_id = user_data.get("stmt_sub_id")
        sub = find_subscriber_by_id(sub_id)
        readings, payments = get_subscriber_statement(sub_id, from_date, to_date)

        filename = f"statement_{sub_id}_{datetime.utcnow().timestamp()}.pdf"
        generate_statement_pdf(
            filename,
            sub,
            from_date,
            to_date,
            readings,
            payments,
        )

        summary_text = format_subscriber_info(sub)
        preview = (
            "معاينة كشف حساب المشترك:\n\n"
            + summary_text
            + f"الفترة: من {from_date} إلى {to_date}\n"
            "تم توليد ملف PDF بالتفاصيل.\n\n"
            "هل تريد إرسال الكشف للمشترك؟"
        )

        buttons = [
            [
                InlineKeyboardButton("إرسال للمشترك", callback_data=f"stmt_send_{sub_id}"),
                InlineKeyboardButton("تجاهل", callback_data="stmt_ignore"),
            ]
        ]

        await update.message.reply_text(preview, reply_markup=InlineKeyboardMarkup(buttons))
        await update.message.reply_document(
            document=InputFile(filename, filename=os.path.basename(filename)),
            caption="كشف حساب المشترك (PDF) - نسخة المدير.",
        )

        user_data["stmt_pdf_file"] = filename
        user_data[STATE_KEY] = STATE_NONE
        return


# ================== admin text router ==================
async def admin_text_router(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, state: str
):
    user_data = context.user_data

    if text == "إلغاء العملية":
        user_data.clear()
        user_data[STATE_KEY] = STATE_NONE
        await update.message.reply_text(
            "تم إلغاء العملية والعودة إلى لوحة المدير.",
            reply_markup=admin_keyboard(),
        )
        return

    if text == "تراجع عن آخر حفظ":
        ok, msg = undo_last_action()
        await update.message.reply_text(msg, reply_markup=admin_keyboard())
        user_data[STATE_KEY] = STATE_NONE
        return

    if state == STATE_NONE:
        if text == "مشترك جديد":
            serial = get_next_serial()
            user_data["new_sub_serial"] = serial
            await update.message.reply_text(
                f"إنشاء مشترك جديد.\nالرقم التسلسلي المقترح: {serial}\n"
                "الرجاء إدخال اسم المشترك:",
                reply_markup=admin_keyboard(),
            )
            user_data[STATE_KEY] = STATE_ADMIN_NEW_SUB_NAME
            return

        if text == "تعديل مشترك":
            await update.message.reply_text(
                "الرجاء إدخال رقم المشترك الذي تريد تعديله:",
                reply_markup=admin_keyboard(),
            )
            user_data[STATE_KEY] = STATE_ADMIN_EDIT_SUB_WAIT_ACCOUNT
            return

        if text == "تسجيل قراءة":
            await update.message.reply_text(
                "الرجاء إدخال رقم المشترك لتسجيل القراءة:",
                reply_markup=admin_keyboard(),
            )
            user_data[STATE_KEY] = STATE_ADMIN_READ_WAIT_ACCOUNT
            return

        if text == "تسجيل دفع":
            await update.message.reply_text(
                "الرجاء إدخال رقم المشترك لتسجيل الدفع:",
                reply_markup=admin_keyboard(),
            )
            user_data[STATE_KEY] = STATE_ADMIN_PAY_WAIT_ACCOUNT
            return

        if text == "كشف مشترك":
            await update.message.reply_text(
                "الرجاء إدخال رقم المشترك للاستعلام:",
                reply_markup=admin_keyboard(),
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
            await start_date_pick(
                update,
                context,
                STATE_ADMIN_MAIN_WAIT_FROM,
                "اختر تاريخ البداية للكشف الرئيسي:",
            )
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

    if state == STATE_ADMIN_NEW_SUB_NAME:
        user_data["new_sub_name"] = text
        await update.message.reply_text(
            "الرجاء إدخال رقم المشترك (رقم العداد):",
            reply_markup=admin_keyboard(),
        )
        user_data[STATE_KEY] = STATE_ADMIN_NEW_SUB_ACCOUNT
        return

    if state == STATE_ADMIN_NEW_SUB_ACCOUNT:
        user_data["new_sub_account"] = text
        # الآن نعرض قائمة المناطق للاختيار
        areas = get_all_areas()
        buttons = [
            [InlineKeyboardButton(a[1], callback_data=f"new_area_{a[0]}")]
            for a in areas
        ]
        await update.message.reply_text(
            "اختر منطقة المشترك:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        user_data[STATE_KEY] = STATE_ADMIN_NEW_SUB_AREA
        return

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
        # هنا نتوقع أن المدير يكتب اسم منطقة، لكننا نريدها من القائمة فقط
        # يمكن تجاهل الإدخال النصي أو إعادة توجيهه لاحقاً
        await update.message.reply_text(
            "تعديل المنطقة يتم من خلال قائمة المناطق فقط.",
            reply_markup=admin_keyboard(),
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    if state == STATE_ADMIN_READ_WAIT_ACCOUNT:
        sub = find_subscriber_by_account(text)
        if not sub:
            await update.message.reply_text(
                "لم يتم العثور على مشترك بهذا الرقم.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return
        user_data["read_sub_id"] = sub[0]
        await update.message.reply_text(
            "الرجاء إدخال آخر قراءة (رقم العداد الحالي):",
            reply_markup=admin_keyboard(),
        )
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

    if state == STATE_ADMIN_PAY_WAIT_ACCOUNT:
        sub = find_subscriber_by_account(text)
        if not sub:
            await update.message.reply_text(
                "لم يتم العثور على مشترك بهذا الرقم.", reply_markup=admin_keyboard()
            )
            user_data[STATE_KEY] = STATE_NONE
            return
        user_data["pay_sub_id"] = sub[0]
        await update.message.reply_text(
            "الرجاء إدخال مبلغ الدفع:",
            reply_markup=admin_keyboard(),
        )
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

    if state == STATE_ADMIN_AREA_WAIT_FROM:
        d = user_data.get("picked_date")
        if not d:
            await update.message.reply_text("لم يتم اختيار تاريخ صحيح.")
            return
        user_data["area_from_date"] = d
        await update.message.reply_text("الآن اختر تاريخ النهاية:")
        await start_date_pick(
            update,
            context,
            STATE_ADMIN_AREA_WAIT_TO,
            "اختر تاريخ النهاية:",
        )
        return

    if state == STATE_ADMIN_AREA_WAIT_TO:
        d = user_data.get("picked_date")
        if not d:
            await update.message.reply_text("لم يتم اختيار تاريخ صحيح.")
            return
        if d < user_data["area_from_date"]:
            await update.message.reply_text("تاريخ النهاية يجب أن يكون بعد تاريخ البداية.")
            return

        from_date = user_data["area_from_date"]
        to_date = d
        user_data["area_to_date"] = to_date
        area_id = user_data.get("area_id")
        total_c, total_p, bal = get_area_summary(area_id, from_date, to_date)

        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT name FROM areas WHERE id=?", (area_id,))
        area_name = c.fetchone()[0]
        conn.close()

        msg = (
            f"كشف منطقة: {area_name}\n"
            f"الفترة: من {from_date} إلى {to_date}\n\n"
            f"إجمالي الاستهلاك (مبلغ): {total_c}\n"
            f"إجمالي المدفوع: {total_p}\n"
            f"إجمالي المتأخرات: {bal}\n\n"
            "هل تريد إرسال كشف تفصيلي لكل مشترك في هذه المنطقة؟"
        )

        # تجهيز صفوف المنطقة للكشف PDF
        subs = get_subscribers_by_area(area_id)
        rows = []
        for s in subs:
            sid = s[0]
            summary = get_subscriber_summary(sid)
            paid = summary["total_payments"]
            debt = summary["balance"]
            rows.append((s[3], s[2], paid, debt))

        filename = f"area_{area_id}_{datetime.utcnow().timestamp()}.pdf"
        generate_area_or_global_pdf(
            filename,
            f"كشف منطقة: {area_name}",
            from_date,
            to_date,
            total_c,
            total_p,
            bal,
            rows=rows,
            is_global=False,
        )

        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("إرسال للمشتركين", callback_data=f"area_send_{area_id}"),
                InlineKeyboardButton("تجاهل", callback_data="area_ignore"),
            ]
        ]))
        await update.message.reply_document(
            document=InputFile(filename, filename=os.path.basename(filename)),
            caption="ملف كشف المنطقة (PDF) - نسخة المدير.",
        )
        user_data["area_pdf_file"] = filename
        user_data[STATE_KEY] = STATE_NONE
        return

    if state == STATE_ADMIN_MAIN_WAIT_FROM:
        d = user_data.get("picked_date")
        if not d:
            await update.message.reply_text("لم يتم اختيار تاريخ صحيح.")
            return
        user_data["main_from_date"] = d
        await update.message.reply_text("الآن اختر تاريخ النهاية:")
        await start_date_pick(
            update,
            context,
            STATE_ADMIN_MAIN_WAIT_TO,
            "اختر تاريخ النهاية:",
        )
        return

    if state == STATE_ADMIN_MAIN_WAIT_TO:
        d = user_data.get("picked_date")
        if not d:
            await update.message.reply_text("لم يتم اختيار تاريخ صحيح.")
            return
        if d < user_data["main_from_date"]:
            await update.message.reply_text("تاريخ النهاية يجب أن يكون بعد تاريخ البداية.")
            return

        from_date = user_data["main_from_date"]
        to_date = d
        user_data["main_to_date"] = to_date
        total_c, total_p, bal = get_global_summary(from_date, to_date)

        # تجهيز صفوف الكشف الرئيسي
        subs = get_all_subscribers()
        rows = []
        for s in subs:
            sid = s[0]
            summary = get_subscriber_summary(sid)
            paid = summary["total_payments"]
            debt = summary["balance"]
            rows.append((s[3], s[2], s[6] or "-", paid, debt))

        msg = (
            "كشف رئيسي لجميع المناطق:\n"
            f"الفترة: من {from_date} إلى {to_date}\n\n"
            f"إجمالي الاستهلاك (مبلغ): {total_c}\n"
            f"إجمالي المدفوع: {total_p}\n"
            f"إجمالي المتأخرات: {bal}\n\n"
            "هل تريد إرسال كشف لكل المشتركين؟"
        )

        filename = f"main_{datetime.utcnow().timestamp()}.pdf"
        generate_area_or_global_pdf(
            filename,
            "كشف رئيسي لجميع المناطق",
            from_date,
            to_date,
            total_c,
            total_p,
            bal,
            rows=rows,
            is_global=True,
        )

        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("إرسال للجميع", callback_data="main_send_all"),
                InlineKeyboardButton("تجاهل", callback_data="main_ignore"),
            ]
        ]))
        await update.message.reply_document(
            document=InputFile(filename, filename=os.path.basename(filename)),
            caption="ملف الكشف الرئيسي (PDF) - نسخة المدير.",
        )
        user_data["main_pdf_file"] = filename
        user_data[STATE_KEY] = STATE_NONE
        return

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

    if state in (
        STATE_ADMIN_SUB_STATEMENT_WAIT_ACCOUNT,
        STATE_ADMIN_SUB_STATEMENT_WAIT_FROM,
        STATE_ADMIN_SUB_STATEMENT_WAIT_TO,
    ):
        await handle_admin_sub_statement(update, context)
        return

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

        user_data[STATE_KEY] = STATE_NONE
        return
      # ================== callback handler ==================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_data = context.user_data
    state = user_data.get(STATE_KEY, STATE_NONE)

    # أولاً: معالجة اختيار التاريخ إن وجد
    handled = await handle_date_pick_callback(update, context)
    if handled:
        return

    # اختيار منطقة للمشترك الجديد
    if state == STATE_ADMIN_NEW_SUB_AREA and data.startswith("new_area_"):
        area_id = int(data.split("_")[-1])
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT name FROM areas WHERE id=?", (area_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            await query.edit_message_text("لم يتم العثور على المنطقة.")
            user_data[STATE_KEY] = STATE_NONE
            return
        area_name = row[0]
        user_data["new_sub_area"] = area_name

        serial = user_data.get("new_sub_serial")
        name = user_data.get("new_sub_name")
        account_no = user_data.get("new_sub_account")

        preview = (
            "معاينة بيانات المشترك الجديد:\n\n"
            f"الرقم التسلسلي: {serial}\n"
            f"رقم المشترك: {account_no}\n"
            f"الاسم: {name}\n"
            f"المنطقة: {area_name}\n\n"
            "هل تريد حفظ المشترك؟"
        )
        buttons = [
            [
                InlineKeyboardButton("حفظ", callback_data="newsub_save"),
                InlineKeyboardButton("إلغاء", callback_data="newsub_cancel"),
            ]
        ]
        await query.edit_message_text(preview, reply_markup=InlineKeyboardMarkup(buttons))
        user_data[STATE_KEY] = STATE_NONE
        return

    if data == "newsub_save":
        serial = user_data.get("new_sub_serial")
        name = user_data.get("new_sub_name")
        account_no = user_data.get("new_sub_account")
        area_name = user_data.get("new_sub_area")
        sub_id, err = create_subscriber(serial, account_no, name, area_name)
        if err:
            await query.edit_message_text(
                f"لم يتم الحفظ:\n{err}",
            )
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="اختر من لوحة المدير:",
                reply_markup=admin_keyboard(),
            )
            return
        await query.edit_message_text("تم حفظ المشترك الجديد بنجاح.")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="اختر من لوحة المدير:",
            reply_markup=admin_keyboard(),
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    if data == "newsub_cancel":
        await query.edit_message_text("تم إلغاء حفظ المشترك الجديد.")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="اختر من لوحة المدير:",
            reply_markup=admin_keyboard(),
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    if state == STATE_ADMIN_EDIT_SUB_CHOICE:
        if data == "edit_name":
            await query.edit_message_text("الرجاء إدخال الاسم الجديد للمشترك:")
            user_data[STATE_KEY] = STATE_ADMIN_EDIT_SUB_NEW_NAME
            return
        if data == "edit_area":
            # عرض قائمة المناطق لتعديل منطقة المشترك
            areas = get_all_areas()
            buttons = [
                [InlineKeyboardButton(a[1], callback_data=f"edit_area_{a[0]}")]
                for a in areas
            ]
            await query.edit_message_text(
                "اختر المنطقة الجديدة للمشترك:",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            return

    if data.startswith("edit_area_"):
        area_id = int(data.split("_")[-1])
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT name FROM areas WHERE id=?", (area_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            await query.edit_message_text("لم يتم العثور على المنطقة.")
            user_data[STATE_KEY] = STATE_NONE
            return
        area_name = row[0]
        sub_id = user_data.get("edit_sub_id")
        update_subscriber(sub_id, area_name=area_name)
        await query.edit_message_text("تم تعديل المنطقة بنجاح.")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="اختر من لوحة المدير:",
            reply_markup=admin_keyboard(),
        )
        user_data[STATE_KEY] = STATE_NONE
        return

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

    if data.startswith("stmt_send_"):
        sub_id = int(data.split("_")[-1])
        sub = find_subscriber_by_id(sub_id)
        filename = user_data.get("stmt_pdf_file")
        if not sub or not sub[5]:
            await query.edit_message_text("لا يوجد قناة مرتبطة بهذا المشترك.")
            return
        text_msg = (
            "كشف حسابك:\n\n"
            + format_subscriber_info(sub)
            + "تم إرفاق كشف الحساب بصيغة PDF."
        )
        try:
            await context.bot.send_message(chat_id=sub[5], text=text_msg)
            if filename and os.path.exists(filename):
                await context.bot.send_document(
                    chat_id=sub[5],
                    document=InputFile(filename, filename=os.path.basename(filename)),
                    caption="كشف حسابك (PDF).",
                )
        except Exception:
            pass
        await query.edit_message_text("تم إرسال كشف الحساب للمشترك.")
        return

    if data == "stmt_ignore":
        await query.edit_message_text("تم تجاهل كشف الحساب.")
        return

    if state == STATE_ADMIN_AREA_CHOOSE and data.startswith("area_"):
        area_id = int(data.split("_")[1])
        user_data["area_id"] = area_id
        await query.edit_message_text(
            "اختر تاريخ البداية:",
        )
        await start_date_pick(
            update,
            context,
            STATE_ADMIN_AREA_WAIT_FROM,
            "اختر تاريخ البداية:",
        )
        return

    if data.startswith("area_send_"):
        area_id = int(data.split("_")[-1])
        from_date = user_data.get("area_from_date")
        to_date = user_data.get("area_to_date")
        subs = get_subscribers_by_area(area_id)
        for sub in subs:
            sub_id = sub[0]
            chat_id = sub[5]
            if not chat_id:
                continue
            readings, payments = get_subscriber_statement(sub_id, from_date, to_date)
            stmt_file = f"area_stmt_{sub_id}_{datetime.utcnow().timestamp()}.pdf"
            generate_statement_pdf(stmt_file, sub, from_date, to_date, readings, payments)
            text_msg = (
                "كشف حسابك للفترة المحددة:\n\n"
                + format_subscriber_info(sub)
                + f"الفترة: من {from_date} إلى {to_date}\n"
            )
            try:
                await context.bot.send_message(chat_id=chat_id, text=text_msg)
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=InputFile(stmt_file, filename=os.path.basename(stmt_file)),
                    caption="كشف حسابك (PDF).",
                )
            except Exception:
                pass
        await query.edit_message_text("تم إرسال كشوف الحساب لجميع مشتركي المنطقة.")
        return

    if data == "area_ignore":
        await query.edit_message_text("تم تجاهل كشف المنطقة.")
        return

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
                "أدخل رقم المشترك أو اسم المشترك:",
            )
            user_data[STATE_KEY] = STATE_ADMIN_MSG_SUB_WAIT
            return

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

    if data == "main_send_all":
        from_date = user_data.get("main_from_date")
        to_date = user_data.get("main_to_date")
        subs = get_all_subscribers()
        for sub in subs:
            sub_id = sub[0]
            chat_id = sub[5]
            if not chat_id:
                continue
            readings, payments = get_subscriber_statement(sub_id, from_date, to_date)
            stmt_file = f"main_stmt_{sub_id}_{datetime.utcnow().timestamp()}.pdf"
            generate_statement_pdf(stmt_file, sub, from_date, to_date, readings, payments)
            text_msg = (
                "كشف حسابك للفترة المحددة:\n\n"
                + format_subscriber_info(sub)
                + f"الفترة: من {from_date} إلى {to_date}\n"
            )
            try:
                await context.bot.send_message(chat_id=chat_id, text=text_msg)
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=InputFile(stmt_file, filename=os.path.basename(stmt_file)),
                    caption="كشف حسابك (PDF).",
                )
            except Exception:
                pass
        await query.edit_message_text("تم إرسال كشوف الحساب لجميع المشتركين.")
        return

    if data == "main_ignore":
        await query.edit_message_text("تم تجاهل الكشف الرئيسي.")
        return

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


# ================== msg_sub_text_handler ==================
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
        reply_markup=admin_keyboard(),
    )
    user_data[STATE_KEY] = STATE_ADMIN_MSG_TEXT


async def text_handler_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    state = user_data.get(STATE_KEY, STATE_NONE)
    if is_admin(update) and state == STATE_ADMIN_MSG_SUB_WAIT:
        await msg_sub_text_handler(update, context)
    else:
        await text_handler(update, context)


# ================== subscriber side ==================
async def subscriber_text_router(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, state: str
):
    # حالة اختيار تاريخ البداية لكشف المشترك
    if state == "SUB_STMT_WAIT_FROM":
        d = context.user_data.get("picked_date")
        if not d:
            await update.message.reply_text("لم يتم اختيار تاريخ صحيح.")
            return

        context.user_data["sub_stmt_from"] = d

        await start_date_pick(
            update,
            context,
            "SUB_STMT_WAIT_TO",
            "اختر تاريخ النهاية لكشف الحساب:"
        )
        context.user_data[STATE_KEY] = "SUB_STMT_WAIT_TO"
        return

    # حالة اختيار تاريخ النهاية لكشف المشترك
    if state == "SUB_STMT_WAIT_TO":
        d = context.user_data.get("picked_date")
        if not d:
            await update.message.reply_text("لم يتم اختيار تاريخ صحيح.")
            return

        from_date = context.user_data["sub_stmt_from"]
        to_date = d

        if to_date < from_date:
            await update.message.reply_text("تاريخ النهاية يجب أن يكون بعد البداية.")
            return

        sub_id = context.user_data["sub_stmt_id"]
        sub = find_subscriber_by_id(sub_id)

        readings, payments = get_subscriber_statement(sub_id, from_date, to_date)

        filename = f"sub_stmt_{sub_id}_{datetime.utcnow().timestamp()}.pdf"
        generate_statement_pdf(filename, sub, from_date, to_date, readings, payments)

        text_msg = (
            "كشف حسابك:\n\n"
            + format_subscriber_info(sub)
            + f"الفترة: من {from_date} إلى {to_date}\n"
        )

        await update.message.reply_text(text_msg, reply_markup=subscriber_keyboard())
        await update.message.reply_document(
            document=InputFile(filename, filename=os.path.basename(filename)),
            caption="كشف حسابك (PDF).",
        )

        context.user_data[STATE_KEY] = STATE_NONE
        return

    # هنا يمكنك إضافة منطق "استعلام" و "كشف حساب" للمشترك
    if text == "استعلام":
        sub = find_subscriber_by_chat(update.effective_chat.id)
        if not sub:
            await update.message.reply_text(
                "لم يتم ربط حسابك بعد. أرسل /start للربط.",
                reply_markup=subscriber_keyboard(),
            )
            return
        info = format_subscriber_status(sub[0])
        await update.message.reply_text(info, reply_markup=subscriber_keyboard())
        return

    if text == "كشف حساب":
        sub = find_subscriber_by_chat(update.effective_chat.id)
        if not sub:
            await update.message.reply_text(
                "لم يتم ربط حسابك بعد. أرسل /start للربط.",
                reply_markup=subscriber_keyboard(),
            )
            return

        # بدء اختيار تاريخ البداية
        await start_date_pick(
            update,
            context,
            "SUB_STMT_WAIT_FROM",
            "اختر تاريخ البداية لكشف الحساب:"
        )
        context.user_data[STATE_KEY] = "SUB_STMT_WAIT_FROM"
        context.user_data["sub_stmt_id"] = sub[0]
        return

    await update.message.reply_text(
        "استخدم الأزرار المتاحة في الأسفل.",
        reply_markup=subscriber_keyboard(),
    )


# ================== start & admin commands ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    user_data.setdefault(STATE_KEY, STATE_NONE)
    chat_id = update.effective_chat.id

    if is_admin(update):
        await update.message.reply_text(
            "مرحباً بك مدير المشروع.\nاستخدم لوحة المدير لإدارة المشتركين.",
            reply_markup=admin_keyboard(),
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    sub = find_subscriber_by_chat(chat_id)
    if sub:
        await update.message.reply_text(
            "مرحباً بك في نظام مشروع المياه.\nيمكنك استخدام الأزرار أدناه.",
            reply_markup=subscriber_keyboard(),
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    await update.message.reply_text(
        "مرحباً بك في نظام مشروع المياه.\n"
        "لربط حسابك كمشترك، الرجاء إدخال الرقم التسلسلي (المكتوب في الدفتر):",
        reply_markup=subscriber_keyboard(),
    )
    user_data[STATE_KEY] = STATE_SUB_LINK_WAIT_SERIAL


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    admin_id = get_admin_user_id()

    if not admin_id:
        set_admin_user_id(user.id)
        await update.message.reply_text(
            "تم تعيينك كمدير للمشروع.\nاستخدم لوحة المدير لإدارة النظام.",
            reply_markup=admin_keyboard(),
        )
        context.user_data[STATE_KEY] = STATE_NONE
        return

    if user.id != admin_id:
        await update.message.reply_text(
            "هذا الأمر خاص بمدير المشروع فقط.",
            reply_markup=subscriber_keyboard(),
        )
        return

    await update.message.reply_text(
        "مرحباً بك مدير المشروع.\nاختر من لوحة المدير:",
        reply_markup=admin_keyboard(),
    )
    context.user_data[STATE_KEY] = STATE_NONE


# ================== text_handler ==================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    state = user_data.get(STATE_KEY, STATE_NONE)
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    if is_admin(update):
        await admin_text_router(update, context, text, state)
        return

    if state == STATE_SUB_LINK_WAIT_SERIAL:
        user_data["link_serial"] = text
        await update.message.reply_text(
            "الرجاء إدخال رقم المشترك (رقم العداد):",
            reply_markup=subscriber_keyboard(),
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
                "الرقم التسلسلي غير صحيح.\nأعد إرسال /start وحاول مرة أخرى.",
                reply_markup=subscriber_keyboard(),
            )
            user_data[STATE_KEY] = STATE_NONE
            return

        sub = find_subscriber_by_serial_and_account(serial_int, account_no)
        if not sub:
            await update.message.reply_text(
                "لم يتم العثور على مشترك بهذه البيانات.\n"
                "تأكد من الرقم التسلسلي ورقم المشترك ثم أعد إرسال /start.",
                reply_markup=subscriber_keyboard(),
            )
            user_data[STATE_KEY] = STATE_NONE
            return

        link_subscriber_chat(serial_int, account_no, chat_id)

        # رسالة الترحيب المعدلة
        msg = (
            "مرحباً بك في مشروع مياة قرية بيت الأقرع الأهلي\n"
            "بياناتك هي كالتالي:\n"
            f"الرقم التسلسلي: {sub[1]}\n"
            f"رقم المشترك (رقم العدّاد): {sub[2]}\n"
            f"الإسم: {sub[3]}\n"
            f"المنطقة: {sub[6] or '-'}\n"
        )
        await update.message.reply_text(
            msg,
            reply_markup=subscriber_keyboard(),
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    await subscriber_text_router(update, context, text, state)


# ================== keep alive dummy ==================
def keep_bot_alive():
    # يمكنك تركها فارغة أو إضافة منطق بسيط
    import time
    while True:
        time.sleep(60)


# ================== main ==================
def main():
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler_wrapper)
    )

    import threading
    threading.Thread(target=keep_bot_alive, daemon=True).start()

    app.run_polling()


if __name__ == "__main__":
    main()
