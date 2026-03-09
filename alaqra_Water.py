import json
import os
from datetime import datetime

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from reportlab.pdfgen import canvas

BOT_TOKEN = "8090667485:AAGCgIlZPEB069W_bhpIr0HBdp20GpfCCPI"
DATA_FILE = "data.json"
INITIAL_ADMIN_ID = 986199874

# ───────────── بيانات ─────────────

def load_data():
    if not os.path.exists(DATA_FILE):
        data = {
            "admin": {"admin_id": None},
            "settings": {
                "project_name": "مشروع مياة قرية بيت الأقرع",
                "price_per_unit": 250,
            },
            "clients": {},      # tg_id -> {serial, sub_number}
            "subscribers": {},  # serial -> {name, meter, area}
            "readings": {},     # serial -> [ {prev,curr,units,amount,date} ]
            "payments": {},     # serial -> [ {amount,date} ]
        }
        save_data(data)
        return data

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            data = {
                "admin": {"admin_id": None},
                "settings": {
                    "project_name": "مشروع مياة قرية بيت الأقرع",
                    "price_per_unit": 250,
                },
                "clients": {},
                "subscribers": {},
                "readings": {},
                "payments": {},
            }
            save_data(data)
            return data


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


data = load_data()

AREAS = [
    "الحمراء",
    "الجبوبة",
    "عرض الجبل",
    "شمضات",
    "حظي",
    "الوادي",
    "بيع مباشر",
]

# ───────────── دوال مساعدة ─────────────

def get_user_id_by_serial(serial: str):
    for tg_id, info in data["clients"].items():
        if info.get("serial") == serial:
            return int(tg_id)
    return None


def get_last_reading(serial: str):
    readings = data["readings"].get(serial, [])
    return readings[-1] if readings else None


def get_last_payment(serial: str):
    payments = data["payments"].get(serial, [])
    return payments[-1] if payments else None


def generate_invoice_number():
    return int(datetime.now().timestamp())


def build_client_statement(serial: str):
    readings = data["readings"].get(serial, [])
    payments = data["payments"].get(serial, [])
    sub = data["subscribers"].get(serial, {})
    name = sub.get("name", "غير معروف")
    lines = [
        "📄 كشف حساب المشترك",
        f"الاسم: {name}",
        f"الرقم التسلسلي: {serial}",
        ""
    ]
    if not readings and not payments:
        lines.append("لا توجد بيانات قراءات أو دفعات حتى الآن.")
        return "\n".join(lines)

    lines.append("القراءات:")
    for r in readings:
        lines.append(f"- {r['date']}: من {r['prev']} إلى {r['curr']} ({r['amount']} ريال)")

    lines.append("\nالدفعات:")
    for p in payments:
        lines.append(f"- {p['date']}: سداد {p['amount']} ريال")

    total_amount = sum(r["amount"] for r in readings)
    total_paid = sum(p["amount"] for p in payments)
    lines.append(f"\nإجمالي المستحق: {total_amount}")
    lines.append(f"المدفوع: {total_paid}")
    lines.append(f"الرصيد: {total_amount - total_paid}")
    return "\n".join(lines)


def build_area_statement_by_period(area: str, df: datetime, dt: datetime):
    lines = [
        f"📍 كشف منطقة: {area}",
        f"من: {df.strftime('%d/%m/%Y')} إلى: {dt.strftime('%d/%m/%Y')}",
        ""
    ]
    found = False
    total_amount = 0
    total_paid = 0

    for serial, info in data["subscribers"].items():
        if info.get("area") != area:
            continue
        readings = data["readings"].get(serial, [])
        payments = data["payments"].get(serial, [])

        fr = [
            r for r in readings
            if df <= datetime.strptime(r["date"], "%Y-%m-%d") <= dt
        ]
        fp = [
            p for p in payments
            if df <= datetime.strptime(p["date"], "%Y-%m-%d") <= dt
        ]

        if not fr and not fp:
            continue

        found = True
        r_sum = sum(r["amount"] for r in fr)
        p_sum = sum(p["amount"] for p in fp)
        total_amount += r_sum
        total_paid += p_sum

        lines.append(f"👤 {info.get('name','غير معروف')} (تسلسلي {serial})")
        lines.append(f"  مستحق: {r_sum} | مدفوع: {p_sum} | رصيد: {r_sum - p_sum}")
        lines.append("")

    if not found:
        return "لا توجد بيانات لهذه المنطقة في هذه الفترة."

    lines.append(f"الإجمالي للمنطقة: مستحق {total_amount} | مدفوع {total_paid} | رصيد {total_amount - total_paid}")
    return "\n".join(lines)


def build_global_statement_by_period(df: datetime, dt: datetime):
    lines = [
        "📋 كشف رئيسي لجميع المناطق",
        f"من: {df.strftime('%d/%m/%Y')} إلى: {dt.strftime('%d/%m/%Y')}",
        ""
    ]
    total_amount = 0
    total_paid = 0
    any_found = False

    for serial, info in data["subscribers"].items():
        readings = data["readings"].get(serial, [])
        payments = data["payments"].get(serial, [])

        fr = [
            r for r in readings
            if df <= datetime.strptime(r["date"], "%Y-%m-%d") <= dt
        ]
        fp = [
            p for p in payments
            if df <= datetime.strptime(p["date"], "%Y-%m-%d") <= dt
        ]

        if not fr and not fp:
            continue

        any_found = True
        r_sum = sum(r["amount"] for r in fr)
        p_sum = sum(p["amount"] for p in fp)
        total_amount += r_sum
        total_paid += p_sum

        lines.append(f"👤 {info.get('name','غير معروف')} (تسلسلي {serial})")
        lines.append(f"  مستحق: {r_sum} | مدفوع: {p_sum} | رصيد: {r_sum - p_sum}")
        lines.append("")

    if not any_found:
        return "لا توجد بيانات في هذه الفترة."

    lines.append(f"الإجمالي العام: مستحق {total_amount} | مدفوع {total_paid} | رصيد {total_amount - total_paid}")
    return "\n".join(lines)


def build_statement_by_period(serial: str, date_from_str: str, date_to_str: str):
    df = datetime.strptime(date_from_str, "%d/%m/%Y")
    dt = datetime.strptime(date_to_str, "%d/%m/%Y")

    readings = data["readings"].get(serial, [])
    payments = data["payments"].get(serial, [])
    sub = data["subscribers"].get(serial, {})
    name = sub.get("name", "غير معروف")

    lines = [
        "📅 كشف حساب حسب الفترة",
        f"الاسم: {name}",
        f"التسلسلي: {serial}",
        f"من: {date_from_str}",
        f"إلى: {date_to_str}",
        ""
    ]

    fr = [
        r for r in readings
        if df <= datetime.strptime(r["date"], "%Y-%m-%d") <= dt
    ]
    fp = [
        p for p in payments
        if df <= datetime.strptime(p["date"], "%Y-%m-%d") <= dt
    ]

    if not fr and not fp:
        return "لا توجد بيانات في هذه الفترة."

    lines.append("القراءات:")
    if fr:
        for r in fr:
            lines.append(f"- {r['date']}: من {r['prev']} إلى {r['curr']} | مبلغ {r['amount']}")
    else:
        lines.append("- لا توجد قراءات")

    lines.append("\nالدفعات:")
    if fp:
        for p in fp:
            lines.append(f"- {p['date']}: سداد {p['amount']}")
    else:
        lines.append("- لا توجد دفعات")

    total_amount = sum(r["amount"] for r in fr)
    total_paid = sum(p["amount"] for p in fp)

    lines.append(f"\nإجمالي المستحق: {total_amount}")
    lines.append(f"إجمالي المدفوع: {total_paid}")
    lines.append(f"الرصيد: {total_amount - total_paid}")

    return "\n".join(lines)


def create_pdf(filename: str, text: str):
    c = canvas.Canvas(filename)
    y = 800
    for line in text.split("\n"):
        c.drawString(40, y, line)
        y -= 20
        if y < 40:
            c.showPage()
            y = 800
    c.save()


def get_next_serial():
    if not data["subscribers"]:
        return "1"
    existing = [int(s) for s in data["subscribers"].keys() if s.isdigit()]
    if not existing:
        return "1"
    return str(max(existing) + 1)


# ───────────── حالات ─────────────

(
    CLIENT_ENTER_SERIAL,
    CLIENT_ENTER_SUB,
) = range(2)

(
    ADMIN_ENTER_ID,
    ADMIN_STAT_SINGLE,
    ADMIN_AREA_CHOOSE,
    ADMIN_AREA_FROM,
    ADMIN_AREA_TO,
    ADMIN_GLOBAL_FROM,
    ADMIN_GLOBAL_TO,
    ADMIN_ADD_READING_SERIAL,
    ADMIN_ADD_READING_VALUE,
    ADMIN_ADD_PAYMENT_SERIAL,
    ADMIN_ADD_PAYMENT_VALUE,
    ADMIN_MSG_MODE,
    ADMIN_MSG_AREA_CHOOSE,
    ADMIN_MSG_SINGLE_SERIAL,
    ADMIN_MSG_TEXT,
    ADMIN_ADD_SUB_NAME,
    ADMIN_ADD_SUB_METER,
    ADMIN_ADD_SUB_AREA,
    ADMIN_EDIT_MODE,
    ADMIN_EDIT_SERIAL,
    ADMIN_EDIT_NEW_NAME,
    ADMIN_EDIT_NEW_METER,
    ADMIN_EDIT_NEW_AREA,
) = range(2, 2 + 22)

CLIENT_PERIOD_FROM, CLIENT_PERIOD_TO = range(50, 52)

# ───────────── لوحات ─────────────

def get_client_keyboard():
    keyboard = [
        [KeyboardButton("📌 استعلام"), KeyboardButton("📄 كشف حساب")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_admin_keyboard():
    keyboard = [
        [KeyboardButton("📊 كشف مشترك"), KeyboardButton("📍 كشف منطقة"), KeyboardButton("📋 كشف رئيسي")],
        [KeyboardButton("📢 إرسال رسالة"), KeyboardButton("📥 تسجيل قراءة"), KeyboardButton("💰 تسجيل دفع")],
        [KeyboardButton("➕ إضافة مشترك جديد"), KeyboardButton("✏️ تعديل")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_areas_keyboard():
    keyboard = [[KeyboardButton(a)] for a in AREAS]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_msg_mode_keyboard():
    keyboard = [
        [KeyboardButton("عامة")],
        [KeyboardButton("منطقة")],
        [KeyboardButton("مشترك")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_edit_mode_keyboard():
    keyboard = [
        [KeyboardButton("تعديل المنطقة")],
        [KeyboardButton("تغيير اسم المشترك")],
        [KeyboardButton("تغيير رقم العداد")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ───────────── دوال العميل ─────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in data["clients"]:
        await update.message.reply_text("مرحباً بك مجدداً، اختر من القائمة:", reply_markup=get_client_keyboard())
        return ConversationHandler.END
    await update.message.reply_text("مرحباً، الرجاء إدخال الرقم التسلسلي:")
    return CLIENT_ENTER_SERIAL


async def client_enter_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["serial"] = update.message.text.strip()
    await update.message.reply_text("الرجاء إدخال رقم المشترك (رقم العداد):")
    return CLIENT_ENTER_SUB


async def client_enter_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = context.user_data["serial"]
    data["clients"][str(update.effective_user.id)] = {
        "serial": serial,
        "sub_number": update.message.text.strip()
    }
    save_data(data)
    await update.message.reply_text("تم الربط بنجاح.", reply_markup=get_client_keyboard())
    return ConversationHandler.END


async def client_inquiry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    client = data["clients"].get(user_id)
    if not client:
        await update.message.reply_text("لم يتم الربط بعد. أرسل /start", reply_markup=get_client_keyboard())
        return
    serial = client["serial"]
    last_r = get_last_reading(serial)
    last_p = get_last_payment(serial)
    sub = data["subscribers"].get(serial, {})
    name = sub.get("name", "غير معروف")

    lines = [f"🔍 وضع المشترك {serial}", f"الاسم: {name}", ""]
    if last_r:
        lines.append(f"آخر قراءة: {last_r['curr']} بتاريخ {last_r['date']} | مبلغ {last_r['amount']}")
    else:
        lines.append("لا توجد قراءات مسجلة.")
    if last_p:
        lines.append(f"آخر سداد: {last_p['amount']} بتاريخ {last_p['date']}")
    else:
        lines.append("لا توجد دفعات مسجلة.")

    await update.message.reply_text("\n".join(lines), reply_markup=get_client_keyboard())


async def client_period_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "حدد التاريخ:\nأدخل تاريخ البداية (يوم/شهر/سنة)\nمثال: 01/01/2024"
    )
    return CLIENT_PERIOD_FROM


async def client_period_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["date_from"] = update.message.text.strip()
    await update.message.reply_text(
        "أدخل تاريخ النهاية (يوم/شهر/سنة)\nمثال: 31/12/2024"
    )
    return CLIENT_PERIOD_TO


async def client_period_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_from = update.message.text.strip()
    date_from_saved = context.user_data.get("date_from")
    user_id = str(update.effective_user.id)
    client = data["clients"].get(user_id)
    if not client:
        await update.message.reply_text("لم يتم الربط بعد. أرسل /start", reply_markup=get_client_keyboard())
        return ConversationHandler.END

    serial = client["serial"]
    msg = build_statement_by_period(serial, date_from_saved, date_from)
    await update.message.reply_text(msg, reply_markup=get_client_keyboard())

    pdf_filename = f"statement_{serial}_{date_from_saved.replace('/','-')}_{date_from.replace('/','-')}.pdf"
    create_pdf(pdf_filename, msg)
    try:
        with open(pdf_filename, "rb") as f:
            await update.message.reply_document(document=f, filename=pdf_filename)
    finally:
        if os.path.exists(pdf_filename):
            os.remove(pdf_filename)

    return ConversationHandler.END


# ───────────── دوال المدير ─────────────

async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = data["admin"].get("admin_id")
    if admin_id is None:
        await update.message.reply_text("أدخل ID المدير للتحقق:")
        return ADMIN_ENTER_ID
    if update.effective_user.id != admin_id:
        await update.message.reply_text("ليس لديك صلاحية.")
        return ConversationHandler.END
    await update.message.reply_text("لوحة المدير:", reply_markup=get_admin_keyboard())
    return ConversationHandler.END


async def admin_enter_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == str(INITIAL_ADMIN_ID):
        data["admin"]["admin_id"] = update.effective_user.id
        save_data(data)
        await update.message.reply_text("تم تفعيل حساب المدير.", reply_markup=get_admin_keyboard())
        return ConversationHandler.END
    await update.message.reply_text("ID غير صحيح، حاول مرة أخرى:")
    return ADMIN_ENTER_ID


# كشف مشترك
async def admin_stat_single_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك:")
    return ADMIN_STAT_SINGLE


async def admin_stat_single_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = update.message.text.strip()
    await update.message.reply_text(build_client_statement(serial), reply_markup=get_admin_keyboard())
    return ConversationHandler.END


# كشف منطقة
async def admin_area_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اختر المنطقة:", reply_markup=get_areas_keyboard())
    return ADMIN_AREA_CHOOSE


async def admin_area_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    area = update.message.text.strip()
    if area not in AREAS:
        await update.message.reply_text("منطقة غير صحيحة، اختر من القائمة:", reply_markup=get_areas_keyboard())
        return ADMIN_AREA_CHOOSE
    context.user_data["area"] = area
    await update.message.reply_text(
        f"منطقة: {area}\nأدخل تاريخ البداية (يوم/شهر/سنة):"
    )
    return ADMIN_AREA_FROM


async def admin_area_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["area_from"] = update.message.text.strip()
    await update.message.reply_text("أدخل تاريخ النهاية (يوم/شهر/سنة):")
    return ADMIN_AREA_TO


async def admin_area_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    area = context.user_data["area"]
    df_str = context.user_data["area_from"]
    dt_str = update.message.text.strip()
    df = datetime.strptime(df_str, "%d/%m/%Y")
    dt = datetime.strptime(dt_str, "%d/%m/%Y")

    msg = build_area_statement_by_period(area, df, dt)
    await update.message.reply_text(msg, reply_markup=get_admin_keyboard())

    pdf_filename = f"area_{area}_{df_str.replace('/','-')}_{dt_str.replace('/','-')}.pdf"
    create_pdf(pdf_filename, msg)
    try:
        with open(pdf_filename, "rb") as f:
            await update.message.reply_document(document=f, filename=pdf_filename)
    finally:
        if os.path.exists(pdf_filename):
            os.remove(pdf_filename)

    return ConversationHandler.END


# كشف رئيسي
async def admin_global_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل تاريخ البداية (يوم/شهر/سنة):")
    return ADMIN_GLOBAL_FROM


async def admin_global_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["global_from"] = update.message.text.strip()
    await update.message.reply_text("أدخل تاريخ النهاية (يوم/شهر/سنة):")
    return ADMIN_GLOBAL_TO


async def admin_global_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    df_str = context.user_data["global_from"]
    dt_str = update.message.text.strip()
    df = datetime.strptime(df_str, "%d/%m/%Y")
    dt = datetime.strptime(dt_str, "%d/%m/%Y")

    msg = build_global_statement_by_period(df, dt)
    await update.message.reply_text(msg, reply_markup=get_admin_keyboard())

    pdf_filename = f"global_{df_str.replace('/','-')}_{dt_str.replace('/','-')}.pdf"
    create_pdf(pdf_filename, msg)
    try:
        with open(pdf_filename, "rb") as f:
            await update.message.reply_document(document=f, filename=pdf_filename)
    finally:
        if os.path.exists(pdf_filename):
            os.remove(pdf_filename)

    return ConversationHandler.END


# تسجيل قراءة
async def admin_add_reading_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك:")
    return ADMIN_ADD_READING_SERIAL


async def admin_add_reading_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["r_serial"] = update.message.text.strip()
    await update.message.reply_text("أدخل القراءة الحالية:")
    return ADMIN_ADD_READING_VALUE


async def admin_add_reading_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = context.user_data["r_serial"]
    try:
        curr = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("الرجاء إدخال رقم صحيح للقراءة:")
        return ADMIN_ADD_READING_VALUE

    last = get_last_reading(serial)
    prev = last["curr"] if last else 0
    units = curr - prev
    amount = units * data["settings"]["price_per_unit"]

    data["readings"].setdefault(serial, []).append({
        "prev": prev,
        "curr": curr,
        "units": units,
        "amount": amount,
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    save_data(data)

    await update.message.reply_text("تم تسجيل القراءة.", reply_markup=get_admin_keyboard())

    client_id = get_user_id_by_serial(serial)
    if client_id:
        msg = (
            "📥 تم تسجيل قراءة جديدة\n\n"
            f"التسلسلي: {serial}\n"
            f"القراءة السابقة: {prev}\n"
            f"القراءة الحالية: {curr}\n"
            f"الاستهلاك: {units} وحدة\n"
            f"المبلغ: {amount} ريال\n"
            f"التاريخ: {datetime.now().strftime('%Y-%m-%d')}"
        )
        await context.bot.send_message(chat_id=client_id, text=msg)

    return ConversationHandler.END


# تسجيل دفع
async def admin_add_payment_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك:")
    return ADMIN_ADD_PAYMENT_SERIAL


async def admin_add_payment_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["p_serial"] = update.message.text.strip()
    await update.message.reply_text("أدخل مبلغ السداد:")
    return ADMIN_ADD_PAYMENT_VALUE


async def admin_add_payment_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = context.user_data["p_serial"]
    try:
        amount = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("الرجاء إدخال رقم صحيح للمبلغ:")
        return ADMIN_ADD_PAYMENT_VALUE

    data["payments"].setdefault(serial, []).append({
        "amount": amount,
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    save_data(data)

    await update.message.reply_text("تم تسجيل السداد.", reply_markup=get_admin_keyboard())

    client_id = get_user_id_by_serial(serial)
    if client_id:
        total_amount = sum(r["amount"] for r in data["readings"].get(serial, []))
        total_paid = sum(p["amount"] for p in data["payments"].get(serial, []))
        balance = total_amount - total_paid

        msg = (
            "💰 تم تسجيل سداد جديد\n\n"
            f"التسلسلي: {serial}\n"
            f"المبلغ المدفوع: {amount} ريال\n"
            f"التاريخ: {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"الرصيد الجديد: {balance} ريال"
        )
        await context.bot.send_message(chat_id=client_id, text=msg)

    return ConversationHandler.END


# إرسال رسالة (عامة / منطقة / مشترك)
async def admin_msg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اختر نوع الرسالة:", reply_markup=get_msg_mode_keyboard())
    return ADMIN_MSG_MODE


async def admin_msg_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = update.message.text.strip()
    if mode not in ["عامة", "منطقة", "مشترك"]:
        await update.message.reply_text("اختر من الخيارات:", reply_markup=get_msg_mode_keyboard())
        return ADMIN_MSG_MODE

    context.user_data["msg_mode"] = mode

    if mode == "عامة":
        await update.message.reply_text("اكتب نص الرسالة العامة:")
        return ADMIN_MSG_TEXT
    elif mode == "منطقة":
        await update.message.reply_text("اختر المنطقة:", reply_markup=get_areas_keyboard())
        return ADMIN_MSG_AREA_CHOOSE
    else:  # مشترك
        await update.message.reply_text("أدخل الرقم التسلسلي للمشترك:")
        return ADMIN_MSG_SINGLE_SERIAL


async def admin_msg_area_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    area = update.message.text.strip()
    if area not in AREAS:
        await update.message.reply_text("منطقة غير صحيحة، اختر من القائمة:", reply_markup=get_areas_keyboard())
        return ADMIN_MSG_AREA_CHOOSE
    context.user_data["msg_area"] = area
    await update.message.reply_text(f"اكتب نص الرسالة لمشتركي منطقة {area}:")
    return ADMIN_MSG_TEXT


async def admin_msg_single_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["msg_serial"] = update.message.text.strip()
    await update.message.reply_text("اكتب نص الرسالة للمشترك:")
    return ADMIN_MSG_TEXT


async def admin_msg_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    mode = context.user_data["msg_mode"]

    if mode == "عامة":
        for tg_id in data["clients"].keys():
            await update.get_bot().send_message(chat_id=int(tg_id), text=text)
        await update.message.reply_text("تم إرسال الرسالة لجميع المشتركين.", reply_markup=get_admin_keyboard())

    elif mode == "منطقة":
        area = context.user_data["msg_area"]
        for serial, info in data["subscribers"].items():
            if info.get("area") != area:
                continue
            tg_id = get_user_id_by_serial(serial)
            if tg_id:
                await update.get_bot().send_message(chat_id=tg_id, text=text)
        await update.message.reply_text(f"تم إرسال الرسالة لمشتركي منطقة {area}.", reply_markup=get_admin_keyboard())

    else:  # مشترك
        serial = context.user_data["msg_serial"]
        tg_id = get_user_id_by_serial(serial)
        if tg_id:
            await update.get_bot().send_message(chat_id=tg_id, text=text)
            await update.message.reply_text("تم إرسال الرسالة للمشترك.", reply_markup=get_admin_keyboard())
        else:
            await update.message.reply_text("لم يتم العثور على هذا المشترك.", reply_markup=get_admin_keyboard())

    return ConversationHandler.END


# إضافة مشترك جديد
async def admin_add_sub_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = get_next_serial()
    context.user_data["new_serial"] = serial
    await update.message.reply_text(f"رقم المشترك الجديد هو: {serial}\nأدخل اسم المشترك كاملاً:")
    return ADMIN_ADD_SUB_NAME


async def admin_add_sub_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_name"] = update.message.text.strip()
    await update.message.reply_text("أدخل رقم العداد:")
    return ADMIN_ADD_SUB_METER


async def admin_add_sub_meter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_meter"] = update.message.text.strip()
    await update.message.reply_text("اختر المنطقة:", reply_markup=get_areas_keyboard())
    return ADMIN_ADD_SUB_AREA


async def admin_add_sub_area(update: Update, context: ContextTypes.DEFAULT_TYPE):
    area = update.message.text.strip()
    if area not in AREAS:
        await update.message.reply_text("منطقة غير صحيحة، اختر من القائمة:", reply_markup=get_areas_keyboard())
        return ADMIN_ADD_SUB_AREA

    serial = context.user_data["new_serial"]
    name = context.user_data["new_name"]
    meter = context.user_data["new_meter"]

    data["subscribers"][serial] = {
        "name": name,
        "meter": meter,
        "area": area,
    }
    save_data(data)

    await update.message.reply_text(
        f"تم إضافة المشترك:\nالاسم: {name}\nالتسلسلي: {serial}\nالعداد: {meter}\nالمنطقة: {area}",
        reply_markup=get_admin_keyboard()
    )
    return ConversationHandler.END


# تعديل مشترك
async def admin_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اختر نوع التعديل:", reply_markup=get_edit_mode_keyboard())
    return ADMIN_EDIT_MODE


async def admin_edit_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = update.message.text.strip()
    if mode not in ["تعديل المنطقة", "تغيير اسم المشترك", "تغيير رقم العداد"]:
        await update.message.reply_text("اختر من الخيارات:", reply_markup=get_edit_mode_keyboard())
        return ADMIN_EDIT_MODE

    context.user_data["edit_mode"] = mode
    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك:")
    return ADMIN_EDIT_SERIAL


async def admin_edit_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = update.message.text.strip()
    if serial not in data["subscribers"]:
        await update.message.reply_text("لا يوجد مشترك بهذا الرقم التسلسلي.", reply_markup=get_admin_keyboard())
        return ConversationHandler.END

    context.user_data["edit_serial"] = serial
    mode = context.user_data["edit_mode"]

    if mode == "تعديل المنطقة":
        await update.message.reply_text("اختر المنطقة الجديدة:", reply_markup=get_areas_keyboard())
        return ADMIN_EDIT_NEW_AREA
    elif mode == "تغيير اسم المشترك":
        await update.message.reply_text("أدخل الاسم الجديد:")
        return ADMIN_EDIT_NEW_NAME
    else:
        await update.message.reply_text("أدخل رقم العداد الجديد:")
        return ADMIN_EDIT_NEW_METER


async def admin_edit_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = context.user_data["edit_serial"]
    new_name = update.message.text.strip()
    data["subscribers"][serial]["name"] = new_name
    save_data(data)
    await update.message.reply_text("تم تعديل الاسم بنجاح.", reply_markup=get_admin_keyboard())
    return ConversationHandler.END


async def admin_edit_new_meter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = context.user_data["edit_serial"]
    new_meter = update.message.text.strip()
    data["subscribers"][serial]["meter"] = new_meter
    save_data(data)
    await update.message.reply_text("تم تعديل رقم العداد بنجاح.", reply_markup=get_admin_keyboard())
    return ConversationHandler.END


async def admin_edit_new_area(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = context.user_data["edit_serial"]
    area = update.message.text.strip()
    if area not in AREAS:
        await update.message.reply_text("منطقة غير صحيحة، اختر من القائمة:", reply_markup=get_areas_keyboard())
        return ADMIN_EDIT_NEW_AREA
    data["subscribers"][serial]["area"] = area
    save_data(data)
    await update.message.reply_text("تم تعديل المنطقة بنجاح.", reply_markup=get_admin_keyboard())
    return ConversationHandler.END


# ───────────── MAIN ─────────────

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    client_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CLIENT_ENTER_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_enter_serial)],
            CLIENT_ENTER_SUB: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_enter_sub)],
            CLIENT_PERIOD_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_period_from)],
            CLIENT_PERIOD_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_period_to)],
        },
        fallbacks=[],
    )

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_entry)],
        states={
            ADMIN_ENTER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_enter_id)],

            ADMIN_STAT_SINGLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_stat_single_done)],

            ADMIN_AREA_CHOOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_area_choose)],
            ADMIN_AREA_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_area_from)],
            ADMIN_AREA_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_area_to)],

            ADMIN_GLOBAL_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_global_from)],
            ADMIN_GLOBAL_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_global_to)],

            ADMIN_ADD_READING_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_reading_serial)],
            ADMIN_ADD_READING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_reading_value)],

            ADMIN_ADD_PAYMENT_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_payment_serial)],
            ADMIN_ADD_PAYMENT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_payment_value)],

            ADMIN_MSG_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_msg_mode)],
            ADMIN_MSG_AREA_CHOOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_msg_area_choose)],
            ADMIN_MSG_SINGLE_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_msg_single_serial)],
            ADMIN_MSG_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_msg_text)],

            ADMIN_ADD_SUB_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_sub_name)],
            ADMIN_ADD_SUB_METER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_sub_meter)],
            ADMIN_ADD_SUB_AREA: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_sub_area)],

            ADMIN_EDIT_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_mode)],
            ADMIN_EDIT_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_serial)],
            ADMIN_EDIT_NEW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_new_name)],
            ADMIN_EDIT_NEW_METER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_new_meter)],
            ADMIN_EDIT_NEW_AREA: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_new_area)],
        },
        fallbacks=[],
    )

    app.add_handler(client_conv)
    app.add_handler(admin_conv)
# أزرار العميل
if last_r:
    lines.append(
        f"آخر قراءة: {last_r['curr']} بتاريخ {last_r['date']} | مبلغ {last_r['amount']}"
    )
else:
    lines.append("لا توجد قراءات مسجلة.")

if last_p:
    lines.append(
        f"آخر سداد: {last_p['amount']} بتاريخ {last_p['date']}"
    )
else:
    lines.append("لا توجد دفعات مسجلة.")
await update.message.reply_text("\n".join(lines), reply_markup=get_client_keyboard())

async def client_period_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "حدد التاريخ:\nأدخل تاريخ البداية (يوم/شهر/سنة)\nمثال: 01/01/2024"
    )
    return CLIENT_PERIOD_FROM


async def client_period_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["date_from"] = update.message.text.strip()
    await update.message.reply_text(
        "أدخل تاريخ النهاية (يوم/شهر/سنة)\nمثال: 31/12/2024"
    )
    return CLIENT_PERIOD_TO


async def client_period_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_from_saved = update.message.text.strip()
    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك:")
    return ADMIN_STAT_SINGLE


async def admin_stat_single_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = update.message.text.strip()
    await update.message.reply_text(build_client_statement(serial), reply_markup=get_admin_keyboard())
    return ConversationHandler.END


# كشف منطقة
async def admin_area_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اختر المنطقة:", reply_markup=get_areas_keyboard())
    return ADMIN_AREA_CHOOSE


async def admin_area_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    area = update.message.text.strip()
    if area not in AREAS:
        await update.message.reply_text("منطقة غير صحيحة، اختر من القائمة:", reply_markup=get_areas_keyboard())
        return ADMIN_AREA_CHOOSE
    context.user_data["area"] = area
    await update.message.reply_text(
        f"منطقة: {area}\nأدخل تاريخ البداية (يوم/شهر/سنة):"
    )
    return ADMIN_AREA_FROM


async def admin_area_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["area_from"] = update.message.text.strip()
    await update.message.reply_text("أدخل تاريخ النهاية (يوم/شهر/سنة):")
    return ADMIN_AREA_TO


async def admin_area_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    area = context.user_data["area"]
    df_str = context.user_data["area_from"]
    dt_str = update.message.text.strip()
    df = datetime.strptime(df_str, "%d/%m/%Y")
    dt = datetime.strptime(dt_str, "%d/%m/%Y")

    msg = build_area_statement_by_period(area, df, dt)
    await update.message.reply_text(msg, reply_markup=get_admin_keyboard())

    pdf_filename = f"area_{area}_{df_str.replace('/','-')}_{dt_str.replace('/','-')}.pdf"
    create_pdf(pdf_filename, msg)
    try:
        with open(pdf_filename, "rb") as f:
            await update.message.reply_document(document=f, filename=pdf_filename)
    finally:
        if os.path.exists(pdf_filename):
            os.remove(pdf_filename)

    return ConversationHandler.END


# كشف رئيسي
async def admin_global_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل تاريخ البداية (يوم/شهر/سنة):")
    return ADMIN_GLOBAL_FROM


async def admin_global_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["global_from"] = update.message.text.strip()
    await update.message.reply_text("أدخل تاريخ النهاية (يوم/شهر/سنة):")
    return ADMIN_GLOBAL_TO


async def admin_global_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    df_str = context.user_data["global_from"]
    dt_str = update.message.text.strip()
    df = datetime.strptime(df_str, "%d/%m/%Y")
    dt = datetime.strptime(dt_str, "%d/%m/%Y")

    msg = build_global_statement_by_period(df, dt)
    await update.message.reply_text(msg, reply_markup=get_admin_keyboard())

    pdf_filename = f"global_{df_str.replace('/','-')}_{dt_str.replace('/','-')}.pdf"
    create_pdf(pdf_filename, msg)
    try:
        with open(pdf_filename, "rb") as f:
            await update.message.reply_document(document=f, filename=pdf_filename)
    finally:
        if os.path.exists(pdf_filename):
            os.remove(pdf_filename)

    return ConversationHandler.END


# تسجيل قراءة
async def admin_add_reading_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك:")
    return ADMIN_ADD_READING_SERIAL


async def admin_add_reading_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["r_serial"] = update.message.text.strip()
    await update.message.reply_text("أدخل القراءة الحالية:")
    return ADMIN_ADD_READING_VALUE


async def admin_add_reading_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = context.user_data["r_serial"]
    try:
        curr = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("الرجاء إدخال رقم صحيح للقراءة:")
        return ADMIN_ADD_READING_VALUE

    last = get_last_reading(serial)
    prev = last["curr"] if last else 0
    units = curr - prev
    amount = units * data["settings"]["price_per_unit"]

    data["readings"].setdefault(serial, []).append({
        "prev": prev,
        "curr": curr,
        "units": units,
        "amount": amount,
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    save_data(data)

    await update.message.reply_text("تم تسجيل القراءة.", reply_markup=get_admin_keyboard())

    client_id = get_user_id_by_serial(serial)
    if client_id:
        msg = (
            "📥 تم تسجيل قراءة جديدة\n\n"
            f"التسلسلي: {serial}\n"
            f"القراءة السابقة: {prev}\n"
            f"القراءة الحالية: {curr}\n"
            f"الاستهلاك: {units} وحدة\n"
            f"المبلغ: {amount} ريال\n"
            f"التاريخ: {datetime.now().strftime('%Y-%m-%d')}"
        )
        await context.bot.send_message(chat_id=client_id, text=msg)

    return ConversationHandler.END


# تسجيل دفع
async def admin_add_payment_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك:")
    return ADMIN_ADD_PAYMENT_SERIAL


async def admin_add_payment_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["p_serial"] = update.message.text.strip()
    await update.message.reply_text("أدخل مبلغ السداد:")
    return ADMIN_ADD_PAYMENT_VALUE


async def admin_add_payment_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = context.user_data["p_serial"]
    try:
        amount = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("الرجاء إدخال رقم صحيح للمبلغ:")
        return ADMIN_ADD_PAYMENT_VALUE

    data["payments"].setdefault(serial, []).append({
        "amount": amount,
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    save_data(data)

    await update.message.reply_text("تم تسجيل السداد.", reply_markup=get_admin_keyboard())

    client_id = get_user_id_by_serial(serial)
    if client_id:
        total_amount = sum(r["amount"] for r in data["readings"].get(serial, []))
        total_paid = sum(p["amount"] for p in data["payments"].get(serial, []))
        balance = total_amount - total_paid

        msg = (
            "💰 تم تسجيل سداد جديد\n\n"
            f"التسلسلي: {serial}\n"
            f"المبلغ المدفوع: {amount} ريال\n"
            f"التاريخ: {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"الرصيد الجديد: {balance} ريال"
        )
        await context.bot.send_message(chat_id=client_id, text=msg)

    return ConversationHandler.END


# إرسال رسالة (عامة / منطقة / مشترك)
async def admin_msg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اختر نوع الرسالة:", reply_markup=get_msg_mode_keyboard())
    return ADMIN_MSG_MODE


async def admin_msg_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = update.message.text.strip()
    if mode not in ["عامة", "منطقة", "مشترك"]:
        await update.message.reply_text("اختر من الخيارات:", reply_markup=get_msg_mode_keyboard())
        return ADMIN_MSG_MODE

    context.user_data["msg_mode"] = mode

    if mode == "عامة":
        await update.message.reply_text("اكتب نص الرسالة العامة:")
        return ADMIN_MSG_TEXT
    elif mode == "منطقة":
        await update.message.reply_text("اختر المنطقة:", reply_markup=get_areas_keyboard())
        return ADMIN_MSG_AREA_CHOOSE
    else:  # مشترك
        await update.message.reply_text("أدخل الرقم التسلسلي للمشترك:")
        return ADMIN_MSG_SINGLE_SERIAL


async def admin_msg_area_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    area = update.message.text.strip()
    if area not in AREAS:
        await update.message.reply_text("منطقة غير صحيحة، اختر من القائمة:", reply_markup=get_areas_keyboard())
        return ADMIN_MSG_AREA_CHOOSE
    context.user_data["msg_area"] = area
    await update.message.reply_text(f"اكتب نص الرسالة لمشتركي منطقة {area}:")
    return ADMIN_MSG_TEXT


async def admin_msg_single_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["msg_serial"] = update.message.text.strip()
    await update.message.reply_text("اكتب نص الرسالة للمشترك:")
    return ADMIN_MSG_TEXT


async def admin_msg_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    mode = context.user_data["msg_mode"]

    if mode == "عامة":
        for tg_id in data["clients"].keys():
            await update.get_bot().send_message(chat_id=int(tg_id), text=text)
        await update.message.reply_text("تم إرسال الرسالة لجميع المشتركين.", reply_markup=get_admin_keyboard())

    elif mode == "منطقة":
        area = context.user_data["msg_area"]
        for serial, info in data["subscribers"].items():
            if info.get("area") != area:
                continue
            tg_id = get_user_id_by_serial(serial)
            if tg_id:
                await update.get_bot().send_message(chat_id=tg_id, text=text)
        await update.message.reply_text(f"تم إرسال الرسالة لمشتركي منطقة {area}.", reply_markup=get_admin_keyboard())

else:  # مشترك
    serial = context.user_data["msg_serial"]
    tg_id = get_user_id_by_serial(serial)
    if tg_id:
        await update.get_bot().send_message(chat_id=tg_id, text=text)
    else:
        await update.message.reply_text("لم يتم العثور على هذا المشترك.", reply_markup=get_admin_keyboard())

return ConversationHandler.END


# إضافة مشترك جديد
async def admin_add_sub_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = get_next_serial()
    context.user_data["new_serial"] = serial
    await update.message.reply_text(f"رقم المشترك الجديد هو: {serial}\nأدخل اسم المشترك كاملاً:")
    return ADMIN_ADD_SUB_NAME


async def admin_add_sub_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_name"] = update.message.text.strip()
    await update.message.reply_text("أدخل رقم العداد:")
    return ADMIN_ADD_SUB_METER


async def admin_add_sub_meter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_meter"] = update.message.text.strip()
    await update.message.reply_text("اختر المنطقة:", reply_markup=get_areas_keyboard())
    return ADMIN_ADD_SUB_AREA


async def admin_add_sub_area(update: Update, context: ContextTypes.DEFAULT_TYPE):
    area = update.message.text.strip()
    if area not in AREAS:
        await update.message.reply_text("منطقة غير صحيحة، اختر من القائمة:", reply_markup=get_areas_keyboard())
        return ADMIN_ADD_SUB_AREA

    serial = context.user_data["new_serial"]
    name = context.user_data["new_name"]
    meter = context.user_data["new_meter"]

    data["subscribers"][serial] = {
        "name": name,
        "meter": meter,
        "area": area,
    }
    save_data(data)

    await update.message.reply_text(
        f"تم إضافة المشترك:\nالاسم: {name}\nالتسلسلي: {serial}\nالعداد: {meter}\nالمنطقة: {area}",
        reply_markup=get_admin_keyboard()
    )
    return ConversationHandler.END


# تعديل مشترك
async def admin_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اختر نوع التعديل:", reply_markup=get_edit_mode_keyboard())
    return ADMIN_EDIT_MODE


async def admin_edit_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = update.message.text.strip()
    if mode not in ["تعديل المنطقة", "تغيير اسم المشترك", "تغيير رقم العداد"]:
        await update.message.reply_text("اختر من الخيارات:", reply_markup=get_edit_mode_keyboard())
        return ADMIN_EDIT_MODE

    context.user_data["edit_mode"] = mode
    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك:")
    return ADMIN_EDIT_SERIAL


async def admin_edit_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = update.message.text.strip()
    if serial not in data["subscribers"]:
        await update.message.reply_text("لا يوجد مشترك بهذا الرقم التسلسلي.", reply_markup=get_admin_keyboard())
        return ConversationHandler.END

    context.user_data["edit_serial"] = serial
    mode = context.user_data["edit_mode"]

    if mode == "تعديل المنطقة":
        await update.message.reply_text("اختر المنطقة الجديدة:", reply_markup=get_areas_keyboard())
        return ADMIN_EDIT_NEW_AREA
    elif mode == "تغيير اسم المشترك":
        await update.message.reply_text("أدخل الاسم الجديد:")
        return ADMIN_EDIT_NEW_NAME
    else:
        await update.message.reply_text("أدخل رقم العداد الجديد:")
        return ADMIN_EDIT_NEW_METER


async def admin_edit_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = context.user_data["edit_serial"]
    new_name = update.message.text.strip()
    data["subscribers"][serial]["name"] = new_name
    save_data(data)
    await update.message.reply_text("تم تعديل الاسم بنجاح.", reply_markup=get_admin_keyboard())
    return ConversationHandler.END


async def admin_edit_new_meter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = context.user_data["edit_serial"]
    new_meter = update.message.text.strip()
    data["subscribers"][serial]["meter"] = new_meter
    save_data(data)
    await update.message.reply_text("تم تعديل رقم العداد بنجاح.", reply_markup=get_admin_keyboard())
    return ConversationHandler.END


async def admin_edit_new_area(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = context.user_data["edit_serial"]
    area = update.message.text.strip()
    if area not in AREAS:
        await update.message.reply_text("منطقة غير صحيحة، اختر من القائمة:", reply_markup=get_areas_keyboard())
        return ADMIN_EDIT_NEW_AREA
    data["subscribers"][serial]["area"] = area
    save_data(data)
    await update.message.reply_text("تم تعديل المنطقة بنجاح.", reply_markup=get_admin_keyboard())
    return ConversationHandler.END


# ───────────── MAIN ─────────────

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    client_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CLIENT_ENTER_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_enter_serial)],
            CLIENT_ENTER_SUB: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_enter_sub)],
            CLIENT_PERIOD_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_period_from)],
            CLIENT_PERIOD_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_period_to)],
        },
        fallbacks=[],
    )

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_entry)],
        states={
            ADMIN_ENTER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_enter_id)],

            ADMIN_STAT_SINGLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_stat_single_done)],

            ADMIN_AREA_CHOOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_area_choose)],
            ADMIN_AREA_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_area_from)],
            ADMIN_AREA_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_area_to)],

            ADMIN_GLOBAL_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_global_from)],
            ADMIN_GLOBAL_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_global_to)],

            ADMIN_ADD_READING_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_reading_serial)],
            ADMIN_ADD_READING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_reading_value)],

            ADMIN_ADD_PAYMENT_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_payment_serial)],
            ADMIN_ADD_PAYMENT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_payment_value)],

            ADMIN_MSG_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_msg_mode)],
            ADMIN_MSG_AREA_CHOOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_msg_area_choose)],
            ADMIN_MSG_SINGLE_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_msg_single_serial)],
            ADMIN_MSG_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_msg_text)],

            ADMIN_ADD_SUB_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_sub_name)],
            ADMIN_ADD_SUB_METER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_sub_meter)],
            ADMIN_ADD_SUB_AREA: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_sub_area)],

            ADMIN_EDIT_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_mode)],
            ADMIN_EDIT_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_serial)],
            ADMIN_EDIT_NEW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_new_name)],
            ADMIN_EDIT_NEW_METER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_new_meter)],
            ADMIN_EDIT_NEW_AREA: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_new_area)],
        },
        fallbacks=[],
    )

    app.add_handler(client_conv)
    app.add_handler(admin_conv)

    # أزرار العميل
    app.add_handler(MessageHandler(filters.Regex("^📌 استعلام$"), client_inquiry))
    app.add_handler(MessageHandler(filters.Regex("^📄 كشف حساب$"), client_period_start))

    # أزرار المدير
    app.add_handler(MessageHandler(filters.Regex("^📊 كشف مشترك$"), admin_stat_single_start))
    app.add_handler(MessageHandler(filters.Regex("^📍 كشف منطقة$"), admin_area_start))
    app.add_handler(MessageHandler(filters.Regex("^📋 كشف رئيسي$"), admin_global_start))
    app.add_handler(MessageHandler(filters.Regex("^📥 تسجيل قراءة$"), admin_add_reading_start))
    app.add_handler(MessageHandler(filters.Regex("^💰 تسجيل دفع$"), admin_add_payment_start))
    app.add_handler(MessageHandler(filters.Regex("^📢 إرسال رسالة$"), admin_msg_start))
    app.add_handler(MessageHandler(filters.Regex("^➕ إضافة مشترك جديد$"), admin_add_sub_start))
    app.add_handler(MessageHandler(filters.Regex("^✏️ تعديل$"), admin_edit_start))

    app.run_polling()


if __name__ == "__main__":
    main()
