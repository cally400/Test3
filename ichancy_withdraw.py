import db
from ichancy_api import IChancyAPI
import logging

api = IChancyAPI()
logger = logging.getLogger(__name__)

pending_withdraws = {}

def start_withdraw(bot, call):
    user = db.get_user(call.from_user.id)
    
    if not user:
        bot.send_message(call.message.chat.id, "❌ لا يوجد مستخدم مسجل")
        return
    
    player_id = user.get("player_id")
    
    if not player_id:
        bot.send_message(call.message.chat.id, "❌ لا يوجد حساب iChancy مرتبط")
        return
    
    # تنظيف player_id
    player_id = str(player_id).strip()
    
    # تحقق من وجود اللاعب في iChancy
    try:
        status, data, balance = api.get_player_balance(player_id)
        if status != 200:
            bot.send_message(call.message.chat.id, f"❌ خطأ في التحقق من الحساب: {data.get('error', 'خطأ غير معروف')}")
            return
        
        # عرض الرصيد الحالي
        bot.send_message(
            call.message.chat.id,
            f"💰 الرصيد الحالي في iChancy: {balance:.2f}"
        )
        
    except Exception as e:
        logger.error(f"خطأ في التحقق من حساب iChancy: {str(e)}")
        bot.send_message(call.message.chat.id, "❌ خطأ في التحقق من حساب iChancy")
        return
    
    # حفظ البيانات
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
    
    # الحصول على النص وتحويله
    amount_text = message.text.strip()
    
    # تسجيل البيانات للمساعدة في التصحيح
    logger.info(f"User {telegram_id} entered amount: '{amount_text}'")
    
    try:
        # إزالة المسافات والفاصلة العربية/الإنجليزية
        amount_text = amount_text.replace(" ", "").replace(",", "").replace("،", "")
        
        # تحقق إذا كان النص يحتوي على أرقام فقط (مع نقطة عشرية)
        if not all(c.isdigit() or c == '.' for c in amount_text):
            bot.send_message(chat_id, "❌ يرجى إدخال أرقام فقط (مثال: 242 أو 100.50)")
            return
        
        # تحويل إلى float
        amount = float(amount_text)
        
        # تحقق من أن المبلغ موجب
        if amount <= 0:
            bot.send_message(chat_id, "❌ المبلغ يجب أن يكون أكبر من صفر")
            return
        
        # تقريب إلى منزلتين عشريتين
        amount = round(amount, 2)
        
    except ValueError as e:
        logger.error(f"خطأ في تحويل المبلغ '{amount_text}': {str(e)}")
        bot.send_message(chat_id, f"❌ لا يمكن تحويل '{amount_text}' إلى رقم. يرجى إدخال رقم صالح.")
        return
    except Exception as e:
        logger.error(f"خطأ غير متوقع في معالجة المبلغ: {str(e)}")
        bot.send_message(chat_id, "❌ خطأ في معالجة المبلغ")
        pending_withdraws.pop(telegram_id, None)
        return
    
    logger.info(f"Processing withdrawal: User {telegram_id}, Amount: {amount}, Player ID: {player_id}")
    
    # التحقق من رصيد iChancy
    loading_msg = bot.send_message(chat_id, "⏳ جاري التحقق من الرصيد...")
    
    try:
        status, data, balance_in_site = api.get_player_balance(player_id)
        
        bot.delete_message(chat_id, loading_msg.message_id)
        
        if status != 200:
            logger.error(f"Failed to get balance: Status {status}, Data: {data}")
            bot.send_message(chat_id, f"❌ فشل في التحقق من الرصيد. كود الخطأ: {status}")
            pending_withdraws.pop(telegram_id, None)
            return
        
        logger.info(f"Balance check successful: {balance_in_site}")
        
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
        logger.error(f"خطأ في التحقق من الرصيد: {str(e)}")
        bot.send_message(chat_id, "❌ خطأ في التحقق من الرصيد")
        pending_withdraws.pop(telegram_id, None)
        return
    
    # بدء عملية السحب
    processing_msg = bot.send_message(chat_id, f"⏳ جاري سحب {amount:.2f}...")
    
    try:
        # سحب الرصيد من iChancy
        logger.info(f"Calling withdraw_from_player with: player_id={player_id}, amount={amount}")
        status, data = api.withdraw_from_player(player_id, amount)
        
        logger.info(f"Withdraw API Response - Status: {status}, Data: {data}")
        
        bot.delete_message(chat_id, processing_msg.message_id)
        
        if status == 200:
            if isinstance(data, dict) and data.get("result", False):
                # سحب ناجح
                transaction_id = data.get("id") or f"withdraw_{telegram_id}_{message.date}"
                
                # إضافة المبلغ إلى رصيد المستخدم في البوت
                user = db.get_user(telegram_id)
                if not user:
                    bot.send_message(chat_id, "❌ لم يتم العثور على بيانات المستخدم")
                    pending_withdraws.pop(telegram_id, None)
                    return
                
                old_balance = user.get("balance", 0)
                new_balance = old_balance + amount
                
                # تحديث الرصيد في قاعدة البيانات
                success = db.update_user(telegram_id, {"balance": new_balance})
                
                if not success:
                    bot.send_message(
                        chat_id,
                        f"⚠️ تم سحب المبلغ ولكن حدث خطأ في تحديث الرصيد\n"
                        f"الرجاء التواصل مع الدعم"
                    )
                else:
                    # الحصول على الرصيد الجديد في iChancy للتأكيد
                    try:
                        _, _, new_ichancy_balance = api.get_player_balance(player_id)
                        bot.send_message(
                            chat_id,
                            f"✅ تم سحب {amount:.2f} بنجاح\n\n"
                            f"📊 الرصيد الجديد في iChancy: {new_ichancy_balance:.2f}\n"
                            f"💰 رصيدك الجديد في البوت: {new_balance:.2f}"
                        )
                    except:
                        bot.send_message(
                            chat_id,
                            f"✅ تم سحب {amount:.2f} بنجاح\n\n"
                            f"💰 رصيدك الجديد في البوت: {new_balance:.2f}"
                        )
                
                # تسجيل المعاملة
                db.log_transaction(
                    telegram_id=telegram_id,
                    player_id=player_id,
                    amount=amount,
                    ttype="ichancy_withdraw",
                    status="completed" if success else "db_error",
                    transaction_id=transaction_id,
                    api_response=str(data)
                )
                
            else:
                # API عاد بنجاح ولكن العملية فشلت
                error_msg = "فشل غير معروف"
                if isinstance(data, dict):
                    notification = data.get("notification")
                    if isinstance(notification, list) and len(notification) > 0:
                        error_msg = notification[0].get("content", "فشل غير معروف")
                    elif data.get("error"):
                        error_msg = data["error"]
                
                logger.error(f"Withdraw failed: {error_msg}")
                bot.send_message(chat_id, f"❌ فشل السحب:\n{error_msg}")
                
                db.log_transaction(
                    telegram_id=telegram_id,
                    player_id=player_id,
                    amount=amount,
                    ttype="ichancy_withdraw",
                    status="failed",
                    error_msg=error_msg,
                    api_response=str(data)
                )
        
        else:
            # خطأ في الاتصال بالـAPI
            error_msg = f"خطأ في الاتصال: {status}"
            if isinstance(data, dict) and "error" in data:
                error_msg = data["error"]
            
            logger.error(f"API connection error: {error_msg}")
            bot.send_message(chat_id, f"❌ فشل السحب:\n{error_msg}")
            
            db.log_transaction(
                telegram_id=telegram_id,
                player_id=player_id,
                amount=amount,
                ttype="ichancy_withdraw",
                status="failed",
                error_msg=error_msg,
                api_response=str(data)
            )
            
    except Exception as e:
        logger.error(f"خطأ غير متوقع في process_withdraw: {str(e)}", exc_info=True)
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
        # تنظيف البيانات المؤقتة
        pending_withdraws.pop(telegram_id, None)
