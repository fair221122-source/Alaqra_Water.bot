import os
import json
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes,
    ConversationHandler, filters
)

# PDF
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet

BOT_TOKEN = os.getenv("8090667485:AAGCgIlZPEB069W_bhpIr0HBdp20GpfCCPI")
ADMIN_ID = int(os.getenv("986199874", "123456789"))

DATA_FILE = "data.json"
UNIT_PRICE = 500

AREAS = [
    "الحمراء","الجبوبة","عرض الجبل","شمضات","حضي","الوادي","بيع مباشر"
]

# States
ASK_SERIAL = 1
PAY_ID, PAY_AMOUNT = 10, 11
READ_ID, READ_VALUE = 20, 21
MSG_TYPE, MSG_AREA, MSG_TEXT = 30, 31, 32
NEW_NAME, NEW_AREA, NEW_METER = 40, 41, 42
EDIT_ID, EDIT_FIELD, EDIT_VALUE = 50, 51, 52
FROM_DATE, TO_DATE = 60, 61

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"subscribers": {}, "last_id": 0}
    with open(DATA_FILE,"r",encoding="utf8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE,"w",encoding="utf8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)

# keyboards
def admin_keyboard():
    kb = [
        ["💰 تسجيل دفع","📥 تسجيل قراءة","📢 إرسال رسالة"],
        ["📋 كشف رئيسي","📍 كشف منطقة","📊 كشف مشترك"],
        ["➕ مشترك جديد","✏️ تعديل"]
    ]
    return ReplyKeyboardMarkup(kb,resize_keyboard=True)

def subscriber_keyboard():
    kb = [["📌 استعلام","📄 كشف حساب"]]
    return ReplyKeyboardMarkup(kb,resize_keyboard=True)

# start
async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("لوحة المدير",reply_markup=admin_keyboard())
        return ConversationHandler.END
    await update.message.reply_text("أدخل الرقم التسلسلي للمشترك لربط حسابك")
    return ASK_SERIAL

async def link_account(update:Update,context:ContextTypes.DEFAULT_TYPE):
    serial = update.message.text
    data = load_data()
    if serial not in data["subscribers"]:
        await update.message.reply_text("الرقم غير موجود")
        return ASK_SERIAL

    sub = data["subscribers"][serial]
    sub["chat_id"] = update.effective_user.id
    save_data(data)

    text=f"""
تم ربط الحساب

الاسم: {sub['name']}
المنطقة: {sub['area']}
رقم العداد: {sub['meter']}
"""
    await update.message.reply_text(text,reply_markup=subscriber_keyboard())
    return ConversationHandler.END

# تسجيل قراءة
async def read_start(update,context):
    await update.message.reply_text("أدخل الرقم التسلسلي")
    return READ_ID

async def read_id(update,context):
    context.user_data["sub_id"]=update.message.text
    await update.message.reply_text("أدخل القراءة الحالية")
    return READ_VALUE

async def read_value(update,context):
    value=int(update.message.text)
    sub_id=context.user_data["sub_id"]
    data=load_data()
    sub=data["subscribers"][sub_id]

    prev=sub.get("last_read",0)
    diff=value-prev
    amount=diff*UNIT_PRICE

    sub["last_read"]=value
    sub["arrears"]=sub.get("arrears",0)+amount

    if "readings" not in sub:
        sub["readings"]=[]
    sub["readings"].append({
        "date":str(datetime.now().date()),
        "consumption":diff,
        "amount":amount
    })

    save_data(data)

    msg=f"""
عزيزي المشترك

تم تسجيل قراءة العداد

الاستهلاك: {diff} وحدة
سعر الوحدة: {UNIT_PRICE} ريال يمني
قيمة الاستهلاك: {amount} ريال يمني

المبلغ المستحق: {sub['arrears']} ريال يمني
"""

    if "chat_id" in sub:
        await context.bot.send_message(sub["chat_id"],msg)

    await update.message.reply_text("تم تسجيل القراءة",reply_markup=admin_keyboard())
    return ConversationHandler.END

# تسجيل دفع
async def pay_start(update,context):
    await update.message.reply_text("أدخل الرقم التسلسلي")
    return PAY_ID

async def pay_id(update,context):
    context.user_data["sub_id"]=update.message.text
    await update.message.reply_text("أدخل المبلغ")
    return PAY_AMOUNT

async def pay_amount(update,context):
    amount=int(update.message.text)
    sub_id=context.user_data["sub_id"]

    data=load_data()
    sub=data["subscribers"][sub_id]

    prev=sub.get("arrears",0)
    new=max(prev-amount,0)
    sub["arrears"]=new

    if "payments" not in sub:
        sub["payments"]=[]
    sub["payments"].append({
        "date":str(datetime.now().date()),
        "amount":amount
    })

    save_data(data)

    msg=f"""
عزيزي المشترك

تم استلام مبلغ منكم

المبلغ المسدد: {amount}
المبلغ السابق: {prev}

المتبقي: {new}
"""

    if "chat_id" in sub:
        await context.bot.send_message(sub["chat_id"],msg)

    await update.message.reply_text("تم تسجيل الدفع",reply_markup=admin_keyboard())
    return ConversationHandler.END

# استعلام المشترك
async def subscriber_status(update,context):
    data=load_data()
    uid=update.effective_user.id

    for sub in data["subscribers"].values():
        if sub.get("chat_id")==uid:
            text=f"""
آخر وضع مالي

الاسم: {sub['name']}
المنطقة: {sub['area']}
رقم العداد: {sub['meter']}

المتأخرات: {sub.get('arrears',0)} ريال
"""
            await update.message.reply_text(text)
            return

# كشف حساب
async def statement_start(update,context):
    await update.message.reply_text("أدخل الفترة من (يوم/شهر/سنة)")
    return FROM_DATE

async def statement_from(update,context):
    context.user_data["from"]=update.message.text
    await update.message.reply_text("إلى")
    return TO_DATE

async def statement_to(update,context):
    from_date=context.user_data["from"]
    to_date=update.message.text

    data=load_data()
    uid=update.effective_user.id

    for sid,sub in data["subscribers"].items():
        if sub.get("chat_id")==uid:
            file=f"statement_{sid}.pdf"

            styles=getSampleStyleSheet()
            story=[]
            story.append(Paragraph("كشف حساب المشترك",styles['Title']))
            story.append(Spacer(1,20))

            story.append(Paragraph(f"الاسم: {sub['name']}",styles['Normal']))
            story.append(Paragraph(f"المنطقة: {sub['area']}",styles['Normal']))
            story.append(Paragraph(f"رقم العداد: {sub['meter']}",styles['Normal']))
            story.append(Spacer(1,20))

            story.append(Paragraph(f"الفترة من {from_date} إلى {to_date}",styles['Normal']))
            story.append(Spacer(1,20))

            readings=sub.get("readings",[])
            payments=sub.get("payments",[])

            r_table=[["التاريخ","الاستهلاك","القيمة"]]
            for r in readings:
                r_table.append([r["date"],r["consumption"],r["amount"]])

            p_table=[["التاريخ","المبلغ"]]
            for p in payments:
                p_table.append([p["date"],p["amount"]])

            story.append(Paragraph("القراءات",styles['Heading2']))
            story.append(Table(r_table))
            story.append(Spacer(1,20))

            story.append(Paragraph("السداد",styles['Heading2']))
            story.append(Table(p_table))
            story.append(Spacer(1,20))

            story.append(Paragraph(f"المتأخرات الكلية: {sub.get('arrears',0)} ريال",styles['Heading2']))

            pdf=SimpleDocTemplate(file)
            pdf.build(story)

            await update.message.reply_document(open(file,"rb"))
            return ConversationHandler.END

# إضافة مشترك
async def new_sub(update,context):
    await update.message.reply_text("أدخل اسم المشترك")
    return NEW_NAME

async def new_name(update,context):
    context.user_data["name"]=update.message.text
    await update.message.reply_text("أدخل المنطقة")
    return NEW_AREA

async def new_area(update,context):
    context.user_data["area"]=update.message.text
    await update.message.reply_text("أدخل رقم العداد")
    return NEW_METER

async def new_meter(update,context):
    meter=update.message.text
    data=load_data()

    new_id=str(data["last_id"]+1)

    data["subscribers"][new_id]={
        "name":context.user_data["name"],
        "area":context.user_data["area"],
        "meter":meter,
        "arrears":0,
        "last_read":0
    }

    data["last_id"]+=1
    save_data(data)

    await update.message.reply_text(f"تم إضافة مشترك رقم {new_id}",reply_markup=admin_keyboard())
    return ConversationHandler.END

def main():
    app=ApplicationBuilder().token(BOT_TOKEN).build()

    # start + ربط
    start_handler=ConversationHandler(
        entry_points=[CommandHandler("start",start)],
        states={ASK_SERIAL:[MessageHandler(filters.TEXT,link_account)]},
        fallbacks=[]
    )

    # قراءة
    read_handler=ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT("📥 تسجيل قراءة"),read_start)],
        states={
            READ_ID:[MessageHandler(filters.TEXT,read_id)],
            READ_VALUE:[MessageHandler(filters.TEXT,read_value)]
        },
        fallbacks=[]
    )

    # دفع
    pay_handler=ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT("💰 تسجيل دفع"),pay_start)],
        states={
            PAY_ID:[MessageHandler(filters.TEXT,pay_id)],
            PAY_AMOUNT:[MessageHandler(filters.TEXT,pay_amount)]
        },
        fallbacks=[]
    )

    # كشف
    statement_handler=ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT("📄 كشف حساب"),statement_start)],
        states={
            FROM_DATE:[MessageHandler(filters.TEXT,statement_from)],
            TO_DATE:[MessageHandler(filters.TEXT,statement_to)]
        },
        fallbacks=[]
    )

    # إضافة مشترك
    new_handler=ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT("➕ مشترك جديد"),new_sub)],
        states={
            NEW_NAME:[MessageHandler(filters.TEXT,new_name)],
            NEW_AREA:[MessageHandler(filters.TEXT,new_area)],
            NEW_METER:[MessageHandler(filters.TEXT,new_meter)]
        },
        fallbacks=[]
    )

    app.add_handler(start_handler)
    app.add_handler(read_handler)
    app.add_handler(pay_handler)
    app.add_handler(statement_handler)
    app.add_handler(new_handler)

    app.add_handler(MessageHandler(filters.TEXT("📌 استعلام"),subscriber_status))

    app.run_polling()

if __name__=="__main__":
    main()
