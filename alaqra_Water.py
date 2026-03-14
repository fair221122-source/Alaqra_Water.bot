#!/usr/bin/env python3
# -*- coding: utf-8 -*-
def safe_finalize_pdf(c, filename):
    """
    تغلق ملف PDF بشكل آمن وتضمن أنه صالح للفتح.
    """
    try:
        c.showPage()
    except:
        pass

    try:
        c.save()
    except:
        pass

    # إصلاح الملفات الفارغة أو التالفة
    try:
        if not os.path.exists(filename) or os.path.getsize(filename) < 500:
            with open(filename, "wb") as f:
                f.write(b"%PDF-1.4\n%EOF")
    except:
        pass
        
import logging
import os
import sqlite3
import json
from datetime import datetime, date

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
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

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ================== أدوات مساعدة عامة ==================


def keep_bot_alive():
    import time
    while True:
        time.sleep(10)


def get_db_path():
    return os.path.join(os.path.dirname(__file__), "water_project.db")


def force_save_pdf(c: canvas.Canvas):
    try:
        c.showPage()
    except Exception:
        pass
    try:
        c.save()
    except Exception:
        pass


def finalize_pdf_file(filename: str):
    try:
        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            c = canvas.Canvas(filename, pagesize=A4)
            c.setFont("Helvetica", 12)
            c.drawString(50, 800, "ملف PDF تم إنشاؤه تلقائياً.")
            force_save_pdf(c)
    except Exception:
        pass


def register_arabic_font():
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        pdfmetrics.registerFont(TTFont("Arabic", "Amiri-Regular.ttf"))
        return "Arabic"
    except Exception:
        return "Helvetica"


# ============ إعدادات أساسية ============
TOKEN = os.getenv("BOT_TOKEN", "......")

DB_PATH = get_db_path()
UNIT_PRICE_DEFAULT = 500
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

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS undo_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,
            table_name TEXT NOT NULL,
            row_id INTEGER NOT NULL,
            date TEXT NOT NULL
        )
    """
    )

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
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT id FROM subscribers WHERE serial=?", (serial,))
    if c.fetchone():
        conn.close()
        return None, "الرقم التسلسلي مستخدم من قبل."

    c.execute("SELECT id FROM subscribers WHERE account_no=?", (account_no,))
    if c.fetchone():
        conn.close()
        return None, "رقم المشترك مستخدم من قبل."

    area_id = get_or_create_area(area_name)
    c.execute(
        """
        INSERT INTO subscribers(serial, account_no, name, area_id, chat_id, created_at)
        VALUES(?,?,?,?,?,?)
    """,
        (serial, account_no, name, area_id, None, datetime.utcnow().isoformat()),
    )
    sub_id = c.lastrowid

    c.execute(
        """
        INSERT INTO undo_log(action_type, table_name, row_id, date)
        VALUES(?,?,?,?)
    """,
        ("create", "subscribers", sub_id, datetime.utcnow().isoformat()),
    )

    conn.commit()
    conn.close()
    return sub_id, None


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
    row_id = c.lastrowid
    c.execute(
        """
        INSERT INTO undo_log(action_type, table_name, row_id, date)
        VALUES(?,?,?,?)
    """,
        ("create", "readings", row_id, datetime.utcnow().isoformat()),
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
    row_id = c.lastrowid
    c.execute(
        """
        INSERT INTO undo_log(action_type, table_name, row_id, date)
        VALUES(?,?,?,?)
    """,
        ("create", "payments", row_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def undo_last_action():
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, action_type, table_name, row_id
        FROM undo_log
        ORDER BY id DESC
        LIMIT 1
    """
    )
    row = c.fetchone()
    if not row:
        conn.close()
        return False, "لا توجد عملية سابقة للتراجع عنها."

    log_id, action_type, table_name, row_id = row
    if action_type == "create":
        c.execute(f"DELETE FROM {table_name} WHERE id=?", (row_id,))
        c.execute("DELETE FROM undo_log WHERE id=?", (log_id,))
        conn.commit()
        conn.close()
        return True, f"تم التراجع عن آخر عملية حفظ في جدول {table_name}."
    conn.close()
    return False, "لا يمكن التراجع عن هذه العملية."


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


# ============ توليد ملفات PDF ============
def generate_pdf(
    filename: str,
    report_type: str,
    from_date: date,
    to_date: date,
    data,
    totals=None,
):
    font_name = register_arabic_font()
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    y = height - 50

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
        f"{title_map.get(report_type, '')} للفترة من {from_date} إلى {to_date}",
    )
    y -= 40

    if report_type == "subscriber":
        subscriber, readings, payments = data

        c.setFont(font_name, 11)
        c.drawString(50, y, f"الاسم: {subscriber[3]}")
        y -= 20
        c.drawString(50, y, f"الرقم التسلسلي: {subscriber[1]}")
        y -= 20
        c.drawString(50, y, f"رقم المشترك: {subscriber[2]}")
        y -= 20
        c.drawString(50, y, f"المنطقة: {subscriber[6] or '-'}")
        y -= 30

        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "القراءات:")
        y -= 20

        c.setFont("Helvetica", 9)
        if readings:
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
        else:
            c.drawString(50, y, "لا توجد قراءات في هذه الفترة.")
            y -= 20

        y -= 20
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "المدفوعات:")
        y -= 20

        c.setFont("Helvetica", 9)
        if payments:
            for p in payments:
                line = f"تاريخ: {p[0][:10]} | مبلغ: {p[1]}"
                c.drawString(50, y, line)
                y -= 15
                if y < 80:
                    c.showPage()
                    y = height - 50
                    c.setFont("Helvetica", 9)
        else:
            c.drawString(50, y, "لا توجد مدفوعات في هذه الفترة.")
            y -= 20

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

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 50, "مدير المشروع/ صالح الطويل")
    c.drawString(50, 30, "التوقيع/ ____________________")

    force_save_pdf(c)
    finalize_pdf_file(filename)


def generate_statement_pdf(filename: str, sub_row, from_date: date, to_date: date, readings, payments):
    generate_pdf(
        filename,
        "subscriber",
        from_date,
        to_date,
        (sub_row, readings, payments),
    )


def generate_area_or_global_pdf(
    filename: str,
    title: str,
    from_date: date,
    to_date: date,
    total_c: int,
    total_p: int,
    bal: int,
):
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    y = height - 60

    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, y, "مشروع مياة قرية بيت الأقرع الأهلي")
    y -= 30
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(width / 2, y, title)
    y -= 30

    c.setFont("Helvetica", 11)
    c.drawString(50, y, f"الفترة: من {from_date} إلى {to_date}")
    y -= 20
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
    finalize_pdf_file(filename)


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
    finalize_pdf_file(filename)


# ============ لوحات المفاتيح ============
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


# ============ حالات ============
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


# ============ كشف مشترك من جهة المدير ============
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


# ============ توجيه رسائل المدير ============
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
            await update.message.reply_text(
                "أدخل تاريخ البداية بصيغة يوم/شهر/سنة (مثال: 01/01/2026):",
                reply_markup=admin_keyboard(),
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
        await update.message.reply_text(
            "الرجاء إدخال اسم المنطقة:",
            reply_markup=admin_keyboard(),
        )
        user_data[STATE_KEY] = STATE_ADMIN_NEW_SUB_AREA
        return

    if state == STATE_ADMIN_NEW_SUB_AREA:
        user_data["new_sub_area"] = text
        serial = user_data.get("new_sub_serial")
        name = user_data.get("new_sub_name")
        account_no = user_data.get("new_sub_account")
        area_name = user_data.get("new_sub_area")

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
        await update.message.reply_text(
            preview, reply_markup=InlineKeyboardMarkup(buttons)
        )
        user_data[STATE_KEY] = STATE_NONE
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
        sub_id = user_data.get("edit_sub_id")
        update_subscriber(sub_id, area_name=text)
        await update.message.reply_text(
            "تم تعديل المنطقة بنجاح.", reply_markup=admin_keyboard()
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
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. مثال صحيح: 01/01/2026"
            )
            return
        user_data["area_from_date"] = d
        await update.message.reply_text(
            "أدخل تاريخ النهاية بصيغة يوم/شهر/سنة (مثال: 10/03/2026):",
            reply_markup=admin_keyboard(),
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

        filename = f"area_{area_id}_{datetime.utcnow().timestamp()}.pdf"
        generate_area_or_global_pdf(
            filename,
            f"كشف منطقة: {area_name}",
            from_date,
            to_date,
            total_c,
            total_p,
            bal,
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
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. مثال صحيح: 01/01/2026"
            )
            return
        user_data["main_from_date"] = d
        await update.message.reply_text(
            "أدخل تاريخ النهاية بصيغة يوم/شهر/سنة (مثال: 10/03/2026):",
            reply_markup=admin_keyboard(),
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
        to_date = d
        user_data["main_to_date"] = to_date
        total_c, total_p, bal = get_global_summary(from_date, to_date)
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

        subs = get_all_subscribers()
        today = datetime.utcnow().date()
        from_date = date(today.year, 1, 1)
        to_date = date(today.year, 12, 31)
        for sub in subs:
            sub_id = sub[0]
            chat_id = sub[5]
            if not chat_id:
                continue
            readings, payments = get_subscriber_statement(sub_id, from_date, to_date)
            stmt_file = f"annual_stmt_{sub_id}_{datetime.utcnow().timestamp()}.pdf"
            generate_statement_pdf(stmt_file, sub, from_date, to_date, readings, payments)
            text_msg = (
                "كشف حسابك السنوي:\n\n"
                + format_subscriber_info(sub)
                + f"الفترة: من {from_date} إلى {to_date}\n"
            )
            try:
                await context.bot.send_message(chat_id=chat_id, text=text_msg)
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=InputFile(stmt_file, filename=os.path.basename(stmt_file)),
                    caption="كشف حسابك السنوي (PDF).",
                )
            except Exception:
                pass

        await update.message.reply_text(
            "تم تنفيذ الإغلاق السنوي وإرسال كشوف الحساب للمشتركين.",
            reply_markup=admin_keyboard(),
        )
        user_data[STATE_KEY] = STATE_NONE
        return

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
            "حسابك غير مرتبط كمشترك.\nأرسل /start واتبع التعليمات للربط.",
            reply_markup=subscriber_keyboard(),
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    sub_id = sub[0]

    if state == STATE_SUB_STATEMENT_WAIT_FROM:
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. استخدم يوم/شهر/سنة.",
                reply_markup=subscriber_keyboard(),
            )
            return
        user_data["sub_stmt_from"] = d
        await update.message.reply_text(
            "أدخل تاريخ النهاية بصيغة يوم/شهر/سنة:",
            reply_markup=subscriber_keyboard(),
        )
        user_data[STATE_KEY] = STATE_SUB_STATEMENT_WAIT_TO
        return

    if state == STATE_SUB_STATEMENT_WAIT_TO:
        d = parse_date_str(text)
        if not d:
            await update.message.reply_text(
                "صيغة التاريخ غير صحيحة. استخدم يوم/شهر/سنة.",
                reply_markup=subscriber_keyboard(),
            )
            return
        from_date = user_data["sub_stmt_from"]
        if d < from_date:
            await update.message.reply_text(
                "تاريخ النهاية يجب أن يكون بعد البداية.",
                reply_markup=subscriber_keyboard(),
            )
            return
        to_date = d
        user_data["sub_stmt_to"] = to_date
        readings, payments = get_subscriber_statement(
            sub_id, from_date, to_date
        )
        filename = f"sub_stmt_{sub_id}_{datetime.utcnow().timestamp()}.pdf"
        generate_pdf(
            filename,
            "subscriber",
            from_date,
            to_date,
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

    if text == "استعلام":
        info = format_subscriber_status(sub_id)
        await update.message.reply_text(info, reply_markup=subscriber_keyboard())
        return

    if text == "كشف حساب":
        await update.message.reply_text(
            "أدخل تاريخ البداية بصيغة يوم/شهر/سنة:",
            reply_markup=subscriber_keyboard(),
        )
        user_data[STATE_KEY] = STATE_SUB_STATEMENT_WAIT_FROM
        return

    await update.message.reply_text(
        "استخدم الأزرار المتاحة في حساب المشترك.",
        reply_markup=subscriber_keyboard(),
    )
    user_data[STATE_KEY] = STATE_NONE


# ============ أزرار Inline ============
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_data = context.user_data
    state = user_data.get(STATE_KEY, STATE_NONE)

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
            await query.edit_message_text("الرجاء إدخال اسم المنطقة الجديدة:")
            user_data[STATE_KEY] = STATE_ADMIN_EDIT_SUB_NEW_AREA
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
            "أدخل تاريخ البداية بصيغة يوم/شهر/سنة:",
        )
        user_data[STATE_KEY] = STATE_ADMIN_AREA_WAIT_FROM
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


# ============ بحث مشترك للرسائل ============
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


# ============ أوامر البداية ============
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


# ============ هاندلر النص ============
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
        await update.message.reply_text(
            "تم ربط حسابك كمشترك بنجاح.\nيمكنك الآن استخدام الأزرار أدناه.",
            reply_markup=subscriber_keyboard(),
        )
        user_data[STATE_KEY] = STATE_NONE
        return

    await subscriber_text_router(update, context, text, state)


# ============ نقطة الدخول ============
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
