import db
from ichancy_api import IChancyAPI
import logging

api = IChancyAPI()
logger = logging.getLogger(__name__)

pending_withdraws = {}

def start_withdraw(bot, call):
    user = db.get_user(call.from_user.id)
    
    # تحقق محسّن من وجود المستخدم وبياناته
    if not user:
        bot.send_message(call.message.chat.id, "❌ لا يوجد مستخدم مسجل")
        return
    
    player_id = user.get("player_id")
    
    # تحقق محسّن من player_id
    if not player_id:
        bot.send_message(call.message.chat.id, "❌ لا يوجد حساب iChancy مرتبط")
        return
    
    # تنظيف وتأكيد صحة player_id
    player_id = str(player_id).strip()
    if not player_id or len(player_id) < 3:
        bot.send_message(call.message.chat.id, "❌ معرف اللاعب غير صالح")
        return
    
    # تحقق من وجود اللاعب فعليًا في iChancy
    try:
        status, data, balance = api.get_player_balance(player_id)
        if status != 200:
            bot.send_message(call.message.chat.id, "❌ لا يمكن الوصول إلى حساب iChancy، الرجاء التحقق من الربط")
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
    
    # حفظ البيانات مع معلومات إضافية
    pending_withdraws[call.from_user.id] = {
        "player_id": player_id,
        "user_balance": user.get("balance", 0),
        "initial_ichancy_balance": balance,
        "chat_id": call.message.chat.id,
        "username": user.get("username", ""),
        "timestamp": call.message.date
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
    
    try:
        # تحقق محسّن من المبلغ
        amount_str = message.text.strip()
        
        # إزالة أي مسافات أو فواصل
        amount_str = amount_str.replace(",", "").replace(" ", "")
        
        # تحقق من أن النص يحتوي فقط على أرقام ونقطة واحدة
        if not all(c.isdigit() or c == '.' for c in amount_str):
            raise ValueError("يجب إدخال أرقام فقط")
        
        # تحويل إلى عدد عشري
        amount = float(amount_str)
        
        # تحقق من أن المبلغ موجب
        if amount <= 0:
            raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
        
        # تحقق من أن المبلغ ليس كبيرًا جدًا
        if amount > 1000000:  # حد أقصى مليون
            raise ValueError("المبلغ كبير جدًا، الحد الأقصى 1,000,000")
        
        # تحقق من أن المبلغ لا يقل عن الحد الأدنى
        if amount < 1:  # حد أدنى 1
            raise ValueError("الحد الأدنى للسحب هو 1")
        
        # تحقق من أن المبلغ يحتوي على منزلتين عشريتين كحد أقصى
        if len(str(amount).split('.')[-1]) > 2:
            amount = round(amount, 2)
            bot.send_message(chat_id, f"⚠️ تم تقريب المبلغ إلى {amount} (منزلتان عشريتان كحد أقصى)")
        
    except ValueError as e:
        error_msg = str(e)
        if "could not convert" in error_msg:
            error_msg = "❌ أدخل رقمًا صحيحًا أو عشريًا صالحًا"
        bot.send_message(chat_id, error_msg)
        
        # إعادة تعيين الخطوة
        bot.send_message(chat_id, "💸 أرسل مبلغ السحب مرة أخرى:")
        bot.register_next_step_handler_by_chat_id(
            chat_id,
            lambda msg: process_withdraw(bot, msg, telegram_id)
        )
        return
    except Exception as e:
        logger.error(f"خطأ غير متوقع في معالجة المبلغ: {str(e)}")
        bot.send_message(chat_id, "❌ خطأ في معالجة المبلغ")
        pending_withdraws.pop(telegram_id, None)
        return
    
    # الحصول على أحدث بيانات المستخدم
    user = db.get_user(telegram_id)
    if not user:
        bot.send_message(chat_id, "❌ المستخدم غير موجود")
        pending_withdraws.pop(telegram_id, None)
        return
    
    # تحقق من رصيد iChancy
    loading_msg = bot.send_message(chat_id, "⏳ جاري التحقق من الرصيد...")
    
    try:
        status, data, balance_in_site = api.get_player_balance(player_id)
        
        bot.delete_message(chat_id, loading_msg.message_id)
        
        if status != 200:
            bot.send_message(chat_id, "❌ فشل التحقق من رصيد الموقع، الرجاء المحاولة لاحقًا")
            pending_withdraws.pop(telegram_id, None)
            return
        
        if balance_in_site < amount:
            bot.send_message(
                chat_id,
                f"❌ رصيدك في الموقع غير كافٍ\n"
                f"💰 الرصيد الحالي: {balance_in_site:.2f}\n"
                f"💸 المبلغ المطلوب: {amount:.2f}\n"
                f"🔻 الناقص: {(amount - balance_in_site):.2f}"
            )
            pending_withdraws.pop(telegram_id, None)
            return
            
    except Exception as e:
        bot.delete_message(chat_id, loading_msg.message_id)
        logger.error(f"خطأ في التحقق من الرصيد: {str(e)}")
        bot.send_message(chat_id, "❌ خطأ في التحقق من الرصيد")
        pending_withdraws.pop(telegram_id, None)
        return
    
    # إرسال رسالة تحميل للسحب
    processing_msg = bot.send_message(chat_id, "⏳ جاري معالجة السحب...")
    
    # سحب الرصيد من iChancy
    try:
        status, data = api.withdraw_from_player(player_id, amount)
        logger.info(f"Withdraw API Response - Status: {status}, Data: {data}")
        
        bot.delete_message(chat_id, processing_msg.message_id)
        
        if status == 200:
            # التحقق من الاستجابة بشكل أفضل
            if isinstance(data, dict) and data.get("result", False):
                # سحب ناجح
                transaction_id = data.get("id") or data.get("transactionId") or f"withdraw_{telegram_id}_{message.date}"
                
                # إضافة المبلغ إلى رصيد المستخدم في البوت
                user = db.get_user(telegram_id)  # إعادة الحصول على أحدث بيانات
                old_balance = user.get("balance", 0)
                new_balance = old_balance + amount
                
                success = db.update_user(telegram_id, {"balance": new_balance})
                
                if not success:
                    # إذا فشل تحديث قاعدة البيانات
                    bot.send_message(
                        chat_id,
                        f"⚠️ حدث خطأ في تحديث الرصيد\n"
                        f"تم سحب {amount:.2f} من iChancy ولكن لم يضف إلى رصيدك\n"
                        f"الرجاء التواصل مع الدعم"
                    )
                    
                    # تسجيل الخطأ
                    db.log_transaction(
                        telegram_id=telegram_id,
                        player_id=player_id,
                        amount=amount,
                        ttype="ichancy_withdraw",
                        status="db_error",
                        transaction_id=transaction_id,
                        error_msg="Failed to update user balance",
                        api_response=str(data)
                    )
                    
                    pending_withdraws.pop(telegram_id, None)
                    return
                
                # الحصول على الرصيد الجديد في iChancy للتأكيد
                try:
                    _, _, new_ichancy_balance = api.get_player_balance(player_id)
                    db.log_transaction(
                        telegram_id=telegram_id,
                        player_id=player_id,
                        amount=amount,
                        ttype="ichancy_withdraw",
                        status="completed",
                        transaction_id=transaction_id,
                        api_response=str(data)
                    )
                    
                    bot.send_message(
                        chat_id,
                        f"✅ تم سحب {amount:.2f} بنجاح\n\n"
                        f"📊 الرصيد الجديد في iChancy: {new_ichancy_balance:.2f}\n"
                        f"💰 رصيدك الجديد في البوت: {new_balance:.2f}\n"
                        f"📈 تمت إضافة {amount:.2f} إلى رصيدك"
                    )
                    
                except:
                    db.log_transaction(
                        telegram_id=telegram_id,
                        player_id=player_id,
                        amount=amount,
                        ttype="ichancy_withdraw",
                        status="completed",
                        transaction_id=transaction_id,
                        api_response=str(data)
                    )
                    
                    bot.send_message(
                        chat_id,
                        f"✅ تم سحب {amount:.2f} بنجاح\n\n"
                        f"💰 رصيدك الجديد في البوت: {new_balance:.2f}\n"
                        f"📈 تمت إضافة {amount:.2f} إلى رصيدك"
                    )
                
            else:
                # API عاد بنجاح ولكن العملية فشلت
                error_msg = "فشل غير معروف"
                notification = data.get("notification")
                
                if isinstance(notification, list) and len(notification) > 0:
                    error_msg = notification[0].get("content", "فشل غير معروف")
                elif isinstance(data.get("error"), str):
                    error_msg = data["error"]
                
                db.log_transaction(
                    telegram_id=telegram_id,
                    player_id=player_id,
                    amount=amount,
                    ttype="ichancy_withdraw",
                    status="failed",
                    error_msg=error_msg,
                    api_response=str(data)
                )
                
                bot.send_message(
                    chat_id,
                    f"❌ فشل السحب:\n{error_msg}\n\n"
                    f"🔄 لم يتم تعديل رصيدك"
                )
        
        else:
            # خطأ في الاتصال بالـAPI
            error_msg = f"خطأ في الاتصال: {status}"
            if isinstance(data, dict) and "error" in data:
                error_msg = data["error"]
            
            db.log_transaction(
                telegram_id=telegram_id,
                player_id=player_id,
                amount=amount,
                ttype="ichancy_withdraw",
                status="failed",
                error_msg=error_msg,
                api_response=str(data)
            )
            
            bot.send_message(
                chat_id,
                f"❌ فشل السحب:\n{error_msg}\n\n"
                f"🔄 لم يتم تعديل رصيدك"
            )
            
    except Exception as e:
        logger.error(f"خطأ غير متوقع في process_withdraw: {str(e)}")
        bot.delete_message(chat_id, processing_msg.message_id)
        
        db.log_transaction(
            telegram_id=telegram_id,
            player_id=player_id,
            amount=amount,
            ttype="ichancy_withdraw",
            status="error",
            error_msg=str(e)
        )
        
        bot.send_message(
            chat_id,
            f"❌ حدث خطأ غير متوقع:\n{str(e)}\n\n"
            f"🔄 لم يتم تعديل رصيدك"
        )
    
    finally:
        # تنظيف البيانات المؤقتة
        pending_withdraws.pop(telegram_id, None)
