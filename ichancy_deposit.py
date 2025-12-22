import db
from ichancy_api import IChancyAPI

# لا تنشئ API عند الاستيراد
# api = IChancyAPI()  ← ❌ ممنوع

pending_deposits = {}

def get_api():
    """إنشاء API فقط عند الحاجة"""
    return IChancyAPI()

def start_deposit(bot, call):
    user = db.get_user(call.from_user.id)

    if not user or not user.get("player_id"):
        bot.send_message(call.message.chat.id, "❌ لا يوجد حساب iChancy مرتبط")
        return

    pending_deposits[call.from_user.id] = {"player_id": user["player_id"]}

    bot.send_message(call.message.chat.id, "💰 أرسل مبلغ الشحن:")
    bot.register_next_step_handler_by_chat_id(
        call.message.chat.id,
        lambda msg: process_amount(bot, msg, call.from_user.id)
    )

def process_amount(bot, message, telegram_id):
    if telegram_id not in pending_deposits:
        return

    try:
        amount = float(message.text.strip())
        if amount <= 0:
            raise ValueError
    except:
        bot.send_message(message.chat.id, "❌ أدخل رقمًا صحيحًا")
        return

    user = db.get_user(telegram_id)
    balance = user.get("balance", 0)

    if balance < amount:
        bot.send_message(message.chat.id, f"❌ رصيدك غير كافٍ\nرصيدك الحالي: {balance}")
        pending_deposits.pop(telegram_id, None)
        return

    player_id = pending_deposits[telegram_id]["player_id"]

    # خصم مبدئي
    db.update_user(telegram_id, {"balance": balance - amount})

    # شحن iChancy
    api = get_api()  # ← إنشاء API هنا فقط
    try:
        status, data = api.deposit_to_player(player_id, amount)
    except Exception as e:
        status, data = 500, {"notification":[{"content": str(e)}]}

    if status == 200 and data.get("result", False):
        db.log_transaction(
            telegram_id=telegram_id,
            player_id=player_id,
            amount=amount,
            ttype="ichancy_deposit",
            status="completed"
        )
        bot.send_message(message.chat.id, f"✅ تم شحن {amount} بنجاح في حساب iChancy")
    else:
        # rollback
        db.update_user(telegram_id, {"balance": balance})
        error_msg = data.get("notification", [{}])[0].get("content", "فشل غير معروف")
        db.log_transaction(
            telegram_id=telegram_id,
            player_id=player_id,
            amount=amount,
            ttype="ichancy_deposit",
            status="failed"
        )
        bot.send_message(
            message.chat.id,
            f"❌ فشل الشحن:\n{error_msg}\n\n🔄 تم إعادة الرصيد"
        )

    pending_deposits.pop(telegram_id, None)
