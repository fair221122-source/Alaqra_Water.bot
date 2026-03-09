import json
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

BOT_TOKEN = "8090667485:AAGCgIlZPEB069W_bhpIr0HBdp20GpfCCPI"
ADMIN_ID = 986199874

DATA_FILE = "water_data.json"

ADD_NAME, ADD_METER, ADD_AREA = range(3)
EDIT_SERIAL, EDIT_AREA = range(3,5)
SEARCH_SERIAL = 10

def load_data():
    try:
        with open(DATA_FILE,"r",encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"subscribers":{}}

def save_data(data):
    with open(DATA_FILE,"w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)

data = load_data()

def admin_keyboard():
    keyboard = [
        [KeyboardButton("📊 كشف مشترك"), KeyboardButton("📍 كشف منطقة"), KeyboardButton("📋 كشف رئيسي")],
        [KeyboardButton("📢 إرسال رسالة"), KeyboardButton("📥 تسجيل قراءة"), KeyboardButton("💰 تسجيل دفع")],
        [KeyboardButton("🔍 بحث")],
        [KeyboardButton("➕ مشترك جديد"), KeyboardButton("✏️ تعديل")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("لوحة المدير", reply_markup=admin_keyboard())
    else:
        await update.message.reply_text("مرحبا بك في بوت المياه")

def get_next_serial():
    if not data["subscribers"]:
        return "1"
    nums=[int(x) for x in data["subscribers"].keys()]
    return str(max(nums)+1)

async def add_subscriber_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial=get_next_serial()
    context.user_data["serial"]=serial
    await update.message.reply_text(f"الرقم التسلسلي: {serial}\nاكتب اسم المشترك")
    return ADD_NAME

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"]=update.message.text
    await update.message.reply_text("اكتب رقم العداد")
    return ADD_METER

async def add_meter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["meter"]=update.message.text
    await update.message.reply_text("اكتب المنطقة")
    return ADD_AREA

async def add_area(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial=context.user_data["serial"]
    data["subscribers"][serial]={
        "name":context.user_data["name"],
        "meter":context.user_data["meter"],
        "area":update.message.text
    }
    save_data(data)
    await update.message.reply_text("تمت إضافة المشترك",reply_markup=admin_keyboard())
    return ConversationHandler.END

async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك")
    return EDIT_SERIAL

async def edit_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial=update.message.text
    if serial not in data["subscribers"]:
        await update.message.reply_text("المشترك غير موجود")
        return ConversationHandler.END
    context.user_data["serial"]=serial
    await update.message.reply_text("أدخل المنطقة الجديدة")
    return EDIT_AREA

async def edit_area(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial=context.user_data["serial"]
    data["subscribers"][serial]["area"]=update.message.text
    save_data(data)
    await update.message.reply_text("تم تعديل المنطقة",reply_markup=admin_keyboard())
    return ConversationHandler.END

async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك")
    return SEARCH_SERIAL

async def search_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial = update.message.text

    if serial not in data["subscribers"]:
        await update.message.reply_text("المشترك غير موجود",reply_markup=admin_keyboard())
        return ConversationHandler.END

    sub=data["subscribers"][serial]
    name=sub["name"]
    area=sub["area"]

    keyboard=[
        [KeyboardButton("📥 قراءة"),KeyboardButton("💰 دافع")],
        [KeyboardButton("📢 إرسال رسالة")],
        [KeyboardButton("⬅️ رجوع")]
    ]

    await update.message.reply_text(
        f"المشترك:\nالاسم: {name}\nالمنطقة: {area}\nالرقم: {serial}\n\nاختر العملية",
        reply_markup=ReplyKeyboardMarkup(keyboard,resize_keyboard=True)
    )

    return ConversationHandler.END

async def show_subscriber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text="قائمة المشتركين:\n\n"
    for s,v in data["subscribers"].items():
        text+=f"{s} - {v['name']} - {v['area']}\n"
    await update.message.reply_text(text)

async def show_area(update: Update, context: ContextTypes.DEFAULT_TYPE):
    areas={}
    for s,v in data["subscribers"].items():
        areas.setdefault(v["area"],[]).append(v["name"])

    text="كشف المناطق:\n"
    for a,n in areas.items():
        text+=f"\n{a}\n"
        for name in n:
            text+=f"- {name}\n"

    await update.message.reply_text(text)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):

    txt=update.message.text

    if txt=="📊 كشف مشترك":
        await show_subscriber(update,context)

    elif txt=="📍 كشف منطقة":
        await show_area(update,context)

    elif txt=="📋 كشف رئيسي":
        await show_subscriber(update,context)

    elif txt=="📢 إرسال رسالة":
        await update.message.reply_text("ميزة إرسال الرسائل يمكن ربطها لاحقاً")

    elif txt=="📥 تسجيل قراءة":
        await update.message.reply_text("ميزة تسجيل القراءة يمكن إضافتها لاحقاً")

    elif txt=="💰 تسجيل دفع":
        await update.message.reply_text("ميزة تسجيل الدفع يمكن إضافتها لاحقاً")

    elif txt=="⬅️ رجوع":
        await update.message.reply_text("لوحة المدير",reply_markup=admin_keyboard())

def main():

    app=ApplicationBuilder().token(BOT_TOKEN).build()

    add_conv=ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ مشترك جديد$"),add_subscriber_start)],
        states={
            ADD_NAME:[MessageHandler(filters.TEXT & ~filters.COMMAND,add_name)],
            ADD_METER:[MessageHandler(filters.TEXT & ~filters.COMMAND,add_meter)],
            ADD_AREA:[MessageHandler(filters.TEXT & ~filters.COMMAND,add_area)],
        },
        fallbacks=[]
    )

    edit_conv=ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^✏️ تعديل$"),edit_start)],
        states={
            EDIT_SERIAL:[MessageHandler(filters.TEXT & ~filters.COMMAND,edit_serial)],
            EDIT_AREA:[MessageHandler(filters.TEXT & ~filters.COMMAND,edit_area)],
        },
        fallbacks=[]
    )

    search_conv=ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔍 بحث$"),search_start)],
        states={
            SEARCH_SERIAL:[MessageHandler(filters.TEXT & ~filters.COMMAND,search_serial)]
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start",start))
    app.add_handler(add_conv)
    app.add_handler(edit_conv)
    app.add_handler(search_conv)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,main_menu))

    app.run_polling()

if __name__=="__main__":
    main()
