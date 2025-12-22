import db
from ichancy_api import IChancyAPI
import logging

logger = logging.getLogger(__name__)

# لا تنشئ API عند الاستيراد
# api = IChancyAPI()  ← ❌ ممنوع

pending_withdraws = {}

def get_api():
    """إنشاء API فقط عند الحاجة"""
    return IChancyAPI()

def start_withdraw(bot, call):
    user = db.get_user(call.from_user.id)
    
    if not user:
        bot.send_message(call.message.chat.id, "❌ لا يوجد مستخدم مسجل")
        return
    
    player_id = user.get("player_id")
    
    if not player_id:
        bot.send_message(call.message.chat.id, "❌ لا يوجد حساب iChancy مرتبط")
        return
    
    player_id = str(player_id).strip()

    # تحقق من وجود اللاعب في iChancy
    try:
        api = get_api()
        status, data, balance = api.get_player_balance(player_id)

        if status != 200:
            bot.send_message(call.message.chat.id, f"❌ خطأ في التحقق من الحساب: {data.get('error', 'خطأ غير معروف')}")
            return
        
        bot.send_message(
            call.message.chat.id,
            f"💰 الرصيد الحالي في iChancy: {balance:.2f}"
        )
        
    except Exception as e:
        logger.error(f"خطأ في التحقق من حساب iChancy: {str(e)}")
        bot.send_message(call.message.chat.id, "❌ خطأ في التحقق من حساب iChancy")
        return
    
    pending_withdraws[call.from_user.id] = {
        "player_id": player_id,
        "chat_id": call.message.chat.id
    }
    
    bot.send_message(call.message.chat.id, "💸 أرسل مبلغ السحب (رقم موجب فقط):")
    bot.register_next_step_handler_by_chat_id(
        call.message.chat.id,
        lambda msg: process_withdraw(bot, msg, call.from_user.id)
    )

def process_withdraw(bot, message, telegram_id):
    if telegram_id not in pending_withdraws:
        bot.send_message(message.chat.id, "❌ انتهت الجلسة، الرجاء المحاولة مرة أخرى")
        return
    
    pending_data = pending_withdraws[telegram_id]
    player_id = pending_data["player_id"]
    chat_id = pending_data["chat_id"]
    
    amount_text = message.text.strip()
    logger.info(f"User {telegram_id} entered amount: '{amount_text}'")
    
    try:
        amount_text = amount_text.replace(" ", "").replace(",", "").replace("،", "")
        
        if not all(c.isdigit() or c == '.' for c in amount_text):
            bot.send_message(chat_id, "❌ يرجى إدخال أرقام فقط (مثال: 242 أو 100.50)")
            return
        
        amount = float(amount_text)
        
        if amount <= 0:
            bot.send_message(chat_id, "❌ المبلغ يجب أن يكون أكبر من صفر")
            return
        
        amount = round(amount, 2)
        
    except Exception as e:
        logger.error(f"خطأ في معالجة المبلغ: {str(e)}")
        bot.send_message(chat_id, "❌ خطأ في معالجة المبلغ")
        pending_withdraws.pop(telegram_id, None)
        return
    
    logger.info(f"Processing withdrawal: User {telegram_id}, Amount: {amount}, Player ID: {player_id}")
    
    loading_msg = bot.send_message(chat_id, "⏳ جاري التحقق من الرصيد...")
    
    try:
        api = get_api()
        status, data, balance_in_site = api.get_player_balance(player_id)
        
        bot.delete_message(chat_id, loading_msg.message_id)
        
        if status != 200:
            bot.send_message(chat_id, f"❌ فشل في التحقق من الرصيد. كود الخطأ: {status}")
            pending_withdraws.pop(telegram_id, None)
            return
        
        if balance_in_site < amount:
            bot.send_message(
                chat_id,
                f"❌ رصيدك في الموقع غير كافٍ\n"
                f"💰 الرصيد الحالي: {balance_in_site:.2f}\n"
                f"💸 المبلغ المطلوب: {amount:.2f}"
            )
            pending_withdraws.pop(telegram_id, None)
            return
            
    except Exception as e:
        bot.delete_message(chat_id, loading_msg.message_id)
        bot.send_message(chat_id, "❌ خطأ في التحقق من الرصيد")
        pending_withdraws.pop(telegram_id, None)
        return
    
    processing_msg = bot.send_message(chat_id, f"⏳ جاري سحب {amount:.2f}...")
    
    try:
        api = get_api()
        status, data = api.withdraw_from_player(player_id, amount)
        
        bot.delete_message(chat_id, processing_msg.message_id)
        
        if status == 200 and isinstance(data, dict) and data.get("result", False):
            user = db.get_user(telegram_id)
            old_balance = user.get("balance", 0)
            new_balance = old_balance + amount
            
            db.update_user(telegram_id, {"balance": new_balance})
            
            bot.send_message(
                chat_id,
                f"✅ تم سحب {amount:.2f} بنجاح\n"
                f"💰 رصيدك الجديد في البوت: {new_balance:.2f}"
            )
            
            db.log_transaction(
                telegram_id=telegram_id,
                player_id=player_id,
                amount=amount,
                ttype="ichancy_withdraw",
                status="completed",
                api_response=str(data)
            )
        
        else:
            error_msg = data.get("notification", [{}])[0].get("content", "فشل غير معروف")
            bot.send_message(chat_id, f"❌ فشل السحب:\n{error_msg}")
            
            db.log_transaction(
                telegram_id=telegram_id,
                player_id=player_id,
                amount=amount,
                ttype="ichancy_withdraw",
                status="failed",
                api_response=str(data)
            )
            
    except Exception as e:
        bot.delete_message(chat_id, processing_msg.message_id)
        bot.send_message(chat_id, f"❌ حدث خطأ غير متوقع:\n{str(e)}")
        
        db.log_transaction(
            telegram_id=telegram_id,
            player_id=player_id,
            amount=amount,
            ttype="ichancy_withdraw",
            status="error",
            error_msg=str(e)
        )
    
    finally:
        pending_withdraws.pop(telegram_id, None)
