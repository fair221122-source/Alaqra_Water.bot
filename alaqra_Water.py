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

from reportlab.pdfgen import canvas  # لإنشاء PDF

BOT_TOKEN = "8090667485:AAGCgIlZPEB069W_bhpIr0HBdp20GpfCCPI"  # استبدلها بتوكن البوت
DATA_FILE = "data.json"

# ───────────── بيانات / JSON ─────────────

def load_data():
    if not os.path.exists(DATA_FILE):
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
INITIAL_ADMIN_ID = 986199874


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
    lines = ["📄 كشف حساب المشترك", f"الرقم التسلسلي: {serial}", ""]
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
    lines.append(f"\nإجمالي المستحق: {total_amount}\nالمدفوع: {total_paid}\nالرصيد: {total_amount - total_paid}")
    return "\n".join(lines)


def build_area_statement(area_name: str):
    lines = [f"📍 كشف حساب منطقة: {area_name}", ""]
    found = False
    for serial, info in data["subscribers"].items():
        if info.get("area") == area_name:
            found = True
            r_sum = sum(r["amount"] for r in data["readings"].get(serial, []))
            p_sum = sum(p["amount"] for p in data["payments"].get(serial, []))
            lines.append(f"👤 {info.get('name')}: رصيد {r_sum - p_sum}")
    return "\n".join(lines) if found else "لا توجد بيانات لهذه المنطقة."


def build_global_statement():
    lines = ["📋 كشف حساب رئيسي", ""]
    t_amt = t_paid = 0
    for serial, info in data["subscribers"].items():
        r_sum = sum(r["amount"] for r in data["readings"].get(serial, []))
        p_sum = sum(p["amount"] for p in data["payments"].get(serial, []))
        t_amt += r_sum
        t_paid += p_sum
        lines.append(f"{info.get('name')}: مستحق {r_sum} | مدفوع {p_sum}")
    lines.append(f"\nالإجمالي: مستحق {t_amt} | مدفوع {t_paid} | متبقي {t_amt - t_paid}")
    return "\n".join(lines)


# كشف حساب حسب فترة
def build_statement_by_period(serial: str, date_from_str: str, date_to_str: str):
    # العميل يدخل: يوم/شهر/سنة → نحولها إلى تاريخ
    df = datetime.strptime(date_from_str, "%d/%m/%Y")
    dt = datetime.strptime(date_to_str, "%d/%m/%Y")

    readings = data["readings"].get(serial, [])
    payments = data["payments"].get(serial, [])

    lines = [
        "📅 كشف حساب حسب الفترة",
        f"التسلسلي: {serial}",
        f"من: {date_from_str}",
        f"إلى: {date_to_str}",
        ""
    ]

    filtered_readings = [
        r for r in readings
        if df <= datetime.strptime(r["date"], "%Y-%m-%d") <= dt
    ]

    filtered_payments = [
        p for p in payments
        if df <= datetime.strptime(p["date"], "%Y-%m-%d") <= dt
    ]

    if not filtered_readings and not filtered_payments:
        return "لا توجد بيانات في هذه الفترة."

    lines.append("القراءات:")
    if filtered_readings:
        for r in filtered_readings:
            lines.append(f"- {r['date']}: من {r['prev']} إلى {r['curr']} | مبلغ {r['amount']}")
    else:
        lines.append("- لا توجد قراءات")

    lines.append("\nالدفعات:")
    if filtered_payments:
        for p in filtered_payments:
            lines.append(f"- {p['date']}: سداد {p['amount']}")
    else:
        lines.append("- لا توجد دفعات")

    total_amount = sum(r["amount"] for r in filtered_readings)
    total_paid = sum(p["amount"] for p in filtered_payments)

    lines.append(f"\nإجمالي المستحق: {total_amount}")
    lines.append(f"إجمالي المدفوع: {total_paid}")
    lines.append(f"الرصيد: {total_amount - total_paid}")

    return "\n".join(lines)


# إنشاء PDF من النص
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


# ───────────── حالات المحادثة ─────────────

(
    CLIENT_ENTER_SERIAL,
    CLIENT_ENTER_SUB,
    ADMIN_ENTER_ID,
    ADMIN_BROADCAST_AREA,
    ADMIN_BROADCAST_SINGLE,
    ADMIN_BROADCAST_MESSAGE,
    ADMIN_STAT_SINGLE,
    ADMIN_STAT_AREA,
    ADMIN_ADD_READING_SERIAL,
    ADMIN_ADD_READING_VALUE,
    ADMIN_ADD_PAYMENT_SERIAL,
    ADMIN_ADD_PAYMENT_VALUE,
) = range(12)

# حالات كشف الحساب حسب الفترة للعميل
CLIENT_PERIOD_FROM, CLIENT_PERIOD_TO = range(20, 22)


# ───────────── لوحات المفاتيح ─────────────

def get_client_keyboard():
    # زرين ثابتين فقط كما طلبت
    keyboard = [
        [KeyboardButton("📌 استعلام"), KeyboardButton("📄 كشف حساب")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_admin_keyboard():
    keyboard = [
        [KeyboardButton("📊 كشف مشترك"), KeyboardButton("📍 كشف منطقة"), KeyboardButton("📋 كشف رئيسي")],
        [KeyboardButton("📢 إرسال رسالة"), KeyboardButton("📥 تسجيل قراءة"), KeyboardButton("💰 تسجيل دفع")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ───────────── الدوال ─────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in data["clients"]:
        await update.message.reply_text("مرحباً بك مجدداً، اختر من القائمة:", reply_markup=get_client_keyboard())
        return ConversationHandler.END
    await update.message.reply_text("مرحباً، الرجاء إدخال الرقم التسلسلي:")
    return CLIENT_ENTER_SERIAL


async def client_enter_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["serial"] = update.message.text.strip()
    await update.message.reply_text("الرجاء إدخال رقم المشترك:")
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
    if client:
        serial = client["serial"]
        last_r = get_last_reading(serial)
        last_p = get_last_payment(serial)

        lines = [f"🔍 وضع المشترك {serial}", ""]
        if last_r:
            lines.append(f"آخر قراءة: {last_r['curr']} بتاريخ {last_r['date']} | مبلغ {last_r['amount']}")
        else:
            lines.append("لا توجد قراءات مسجلة.")
        if last_p:
            lines.append(f"آخر سداد: {last_p['amount']} بتاريخ {last_p['date']}")
        else:
            lines.append("لا توجد دفعات مسجلة.")

        await update.message.reply_text("\n".join(lines), reply_markup=get_client_keyboard())
    else:
        await update.message.reply_text("لم يتم الربط بعد. أرسل /start", reply_markup=get_client_keyboard())


# بداية كشف الحساب حسب الفترة
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
    date_from = context.user_data["date_from"]
    date_to = update.message.text.strip()

    user_id = str(update.effective_user.id)
    client = data["clients"].get(user_id)
    if not client:
        await update.message.reply_text("لم يتم الربط بعد. أرسل /start", reply_markup=get_client_keyboard())
        return ConversationHandler.END

    serial = client["serial"]

    # نص كشف الحساب
    msg = build_statement_by_period(serial, date_from, date_to)
    await update.message.reply_text(msg, reply_markup=get_client_keyboard())

    # إنشاء PDF وإرساله
    pdf_filename = f"statement_{serial}_{date_from.replace('/','-')}_{date_to.replace('/','-')}.pdf"
    create_pdf(pdf_filename, msg)
    try:
        with open(pdf_filename, "rb") as f:
            await update.message.reply_document(document=f, filename=pdf_filename)
    finally:
        if os.path.exists(pdf_filename):
            os.remove(pdf_filename)

    return ConversationHandler.END


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
        await update.message.reply_text("تم التفعيل.", reply_markup=get_admin_keyboard())
        return ConversationHandler.END
    await update.message.reply_text("ID غير صحيح، حاول مرة أخرى:")
    return ADMIN_ENTER_ID


# ───────────── دوال عمليات المدير ─────────────

async def admin_stat_single_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل الرقم التسلسلي:")
    return ADMIN_STAT_SINGLE


async def admin_stat_single_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_client_statement(update.message.text.strip()))
    return ConversationHandler.END


async def admin_stat_area_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل اسم المنطقة:")
    return ADMIN_STAT_AREA


async def admin_stat_area_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_area_statement(update.message.text.strip()))
    return ConversationHandler.END


async def admin_stat_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_global_statement())


async def admin_add_reading_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل التسلسلي:")
    return ADMIN_ADD_READING_SERIAL


async def admin_add_reading_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["r_serial"] = update.message.text.strip()
    await update.message.reply_text("أدخل القراءة:")
    return ADMIN_ADD_READING_VALUE


async def admin_add_reading_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = context.user_data["r_serial"]
    curr = int(update.message.text.strip())
    last = get_last_reading(serial)
    prev = last["curr"] if last else 0
    data["readings"].setdefault(serial, []).append({
        "prev": prev,
        "curr": curr,
        "units": curr - prev,
        "amount": (curr - prev) * data["settings"]["price_per_unit"],
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    save_data(data)
    await update.message.reply_text("تم تسجيل القراءة.", reply_markup=get_admin_keyboard())
    return ConversationHandler.END


async def admin_add_payment_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل التسلسلي:")
    return ADMIN_ADD_PAYMENT_SERIAL


async def admin_add_payment_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["p_serial"] = update.message.text.strip()
    await update.message.reply_text("أدخل المبلغ:")
    return ADMIN_ADD_PAYMENT_VALUE


async def admin_add_payment_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = context.user_data["p_serial"]
    data["payments"].setdefault(serial, []).append({
        "amount": int(update.message.text.strip()),
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    save_data(data)
    await update.message.reply_text("تم تسجيل السداد.", reply_markup=get_admin_keyboard())
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
            ADMIN_STAT_AREA: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_stat_area_done)],
            ADMIN_ADD_READING_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_reading_serial)],
            ADMIN_ADD_READING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_reading_value)],
            ADMIN_ADD_PAYMENT_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_payment_serial)],
            ADMIN_ADD_PAYMENT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_payment_value)],
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
    app.add_handler(MessageHandler(filters.Regex("^📍 كشف منطقة$"), admin_stat_area_start))
    app.add_handler(MessageHandler(filters.Regex("^📋 كشف رئيسي$"), admin_stat_all))
    app.add_handler(MessageHandler(filters.Regex("^📥 تسجيل قراءة$"), admin_add_reading_start))
    app.add_handler(MessageHandler(filters.Regex("^💰 تسجيل دفع$"), admin_add_payment_start))

    app.run_polling()


if __name__ == "__main__":
    main()
