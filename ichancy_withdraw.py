import db
from ichancy_api import IChancyAPI

api = IChancyAPI()

# حالات مؤقتة
pending_withdraws = {}

def start_withdraw(bot, call):
    user = db.get_user(call.from_user.id)

    if not user or not user.get("player_id"):
        bot.send_message(call.message.chat.id, "❌ لا يوجد حساب iChancy مرتبط")
        return

    pending_withdraws[call.from_user.id] = {
        "player_id": user["player_id"]
    }

    bot.send_message(
        call.message.chat.id,
        "💸 أرسل مبلغ السحب:"
    )

    bot.register_next_step_handler_by_chat_id(
        call.message.chat.id,
        lambda msg: process_withdraw(bot, msg, call.from_user.id)
    )


def process_withdraw(bot, message, telegram_id):
    if telegram_id not in pending_withdraws:
        return

    # تحقق من المبلغ
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            raise ValueError
    except:
        bot.send_message(message.chat.id, "❌ أدخل رقمًا صحيحًا")
        return

    player_id = pending_withdraws[telegram_id]["player_id"]

    # ========================
    # 1️⃣ التحقق من رصيد iChancy
    # ========================
    status, data, balance_in_site = api.get_player_balance(player_id)
    if status != 200:
        bot.send_message(message.chat.id, "❌ فشل التحقق من رصيد الموقع")
        pending_withdraws.pop(telegram_id, None)
        return

    if balance_in_site < amount:
        bot.send_message(
            message.chat.id,
            f"❌ رصيدك في الموقع غير كافٍ\nرصيدك الحالي: {balance_in_site}"
        )
        pending_withdraws.pop(telegram_id, None)
        return

    # ========================
    # 2️⃣ سحب الرصيد من iChancy
    # ========================
    status, data = api.withdraw_from_player(player_id, amount)

    if status == 200 and data.get("result", False):
        # ========================
        # 3️⃣ إضافة الرصيد إلى DB
        # ========================
        db.update_balance(telegram_id, amount)

        db.log_transaction(
            telegram_id=telegram_id,
            player_id=player_id,
            amount=amount,
            ttype="ichancy_withdraw",
            status="completed"
        )

        bot.send_message(
            message.chat.id,
            f"✅ تم سحب {amount} من حساب iChancy وإضافته إلى رصيدك"
        )

    else:
        error_msg = (
            data.get("notification", [{}])[0].get("content")
            if isinstance(data, dict)
            else "فشل غير معروف"
        )

        db.log_transaction(
            telegram_id=telegram_id,
            player_id=player_id,
            amount=amount,
            ttype="ichancy_withdraw",
            status="failed"
        )

        bot.send_message(
            message.chat.id,
            f"❌ فشل السحب:\n{error_msg}\n\n🔄 لم يتم تعديل رصيدك"
        )

    pending_withdraws.pop(telegram_id, None)

