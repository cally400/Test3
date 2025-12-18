# ichancy_withdraw.py
from ichancy_api import IChancyAPI
import db

api = IChancyAPI()

# المستخدمون الذين ينتظرون إدخال مبلغ
pending_withdraw = {}

def start_withdraw(bot, call):
    user = db.get_user(call.from_user.id)

    if not user or not user.get("player_id"):
        bot.answer_callback_query(call.id, "❌ لا يوجد حساب iChancy")
        return

    pending_withdraw[call.from_user.id] = True

    bot.edit_message_text(
        "💸 **سحب رصيد من موقع iChancy**\n\n✏️ أرسل الآن المبلغ المراد سحبه:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown"
    )


def process_withdraw(bot, message):
    telegram_id = message.from_user.id

    if telegram_id not in pending_withdraw:
        return

    user = db.get_user(telegram_id)

    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
    except:
        bot.send_message(message.chat.id, "❌ أدخل رقمًا صحيحًا")
        return

    try:
        # 1️⃣ جلب رصيد المستخدم من الموقع
        site_balance = api.get_balance(user["player_id"])

        if site_balance < amount:
            bot.send_message(
                message.chat.id,
                f"❌ رصيدك في الموقع غير كافٍ\n💰 رصيد الموقع: {site_balance}"
            )
            pending_withdraw.pop(telegram_id, None)
            return

        # 2️⃣ الخصم من الموقع (الأهم)
        success = api.withdraw(
            player_id=user["player_id"],
            amount=amount
        )

        if not success:
            bot.send_message(
                message.chat.id,
                "❌ فشل الخصم من الموقع، لم يتم تعديل رصيدك"
            )
            pending_withdraw.pop(telegram_id, None)
            return

        # 3️⃣ بعد النجاح فقط ➜ إضافة الرصيد للبوت
        db.update_balance(
            telegram_id=telegram_id,
            amount=amount
        )

        db.log_transaction(
            telegram_id=telegram_id,
            player_id=user["player_id"],
            amount=amount,
            ttype="ichancy_withdraw",
            status="completed"
        )

        bot.send_message(
            message.chat.id,
            f"""✅ **تم السحب بنجاح**

💸 من الموقع: `{amount}`
💳 أضيف إلى رصيدك في البوت
💰 رصيدك الحالي: `{user['balance'] + amount}`
""",
            parse_mode="Markdown"
        )

    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"❌ حدث خطأ أثناء السحب:\n`{str(e)}`",
            parse_mode="Markdown"
        )

    finally:
        pending_withdraw.pop(telegram_id, None)
      
