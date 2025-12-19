import os
import random
import string
import db
from ichancy_api import IChancyAPI

# تهيئة API
api = IChancyAPI()

def _random_suffix(length=3):
    """إنشاء لاحق عشوائي"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_username(raw_username: str) -> str:
    """إنشاء اسم مستخدم فريد"""
    base = f"ZEUS_{raw_username}"
    
    # محاولة 6 مرات مع لاحق عشوائي
    for i in range(6):
        if i == 0:
            username = base
        else:
            username = f"{base}_{_random_suffix()}"
        
        # التحقق من عدم وجود الاسم
        if not api.check_player_exists(username):
            return username
    
    raise ValueError("❌ جميع الأسماء غير متاحة، يرجى تجربة اسم مختلف")

def start_create_account(bot, call):
    """بدء عملية إنشاء حساب"""
    bot.send_message(
        call.message.chat.id, 
        "📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):"
    )
    bot.register_next_step_handler_by_chat_id(
        call.message.chat.id, 
        lambda msg: process_username_step(bot, msg, call.from_user.id)
    )

def process_username_step(bot, message, telegram_id):
    """معالجة اسم المستخدم"""
    raw_username = message.text.strip()
    
    # تنظيف الاسم من المسافات والرموز غير المسموح بها
    raw_username = ''.join(c for c in raw_username if c.isalnum() or c in ['_', '-'])
    
    # التحقق من الطول
    if len(raw_username) < 3:
        bot.send_message(
            message.chat.id, 
            "❌ الاسم قصير جداً، يجب أن يكون 3 أحرف على الأقل"
        )
        return
    
    if len(raw_username) > 20:
        bot.send_message(
            message.chat.id,
            "❌ الاسم طويل جداً، يجب ألا يتجاوز 20 حرفاً"
        )
        return
    
    try:
        # توليد اسم مستخدم فريد
        username = generate_username(raw_username)
        
        # طلب كلمة المرور
        bot.send_message(
            message.chat.id, 
            f"✅ الاسم متاح: `{username}`\n\n"
            f"🔐 **الآن أرسل كلمة السر:**\n"
            f"📌 **الشروط:**\n"
            f"• 8 أحرف على الأقل\n"
            f"• تحتوي على أحرف كبيرة وصغيرة\n"
            f"• تحتوي على أرقام\n"
            f"• يمكن أن تحتوي على رموز خاصة\n\n"
            f"📋 **مثال:** `Pass@1234`",
            parse_mode="Markdown"
        )
        
        bot.register_next_step_handler_by_chat_id(
            message.chat.id, 
            lambda msg: process_password_step(bot, msg, telegram_id, username)
        )
        
    except ValueError as e:
        bot.send_message(
            message.chat.id, 
            f"❌ {str(e)}\n\nيرجى المحاولة مرة أخرى باستخدام /start"
        )
    except Exception as e:
        bot.send_message(
            message.chat.id, 
            f"❌ حدث خطأ غير متوقع: {str(e)}\n\nيرجى المحاولة مرة أخرى لاحقاً."
        )

def process_password_step(bot, message, telegram_id, username):
    """معالجة كلمة المرور وإنشاء الحساب"""
    password = message.text.strip()
    
    # التحقق من قوة كلمة المرور
    errors = []
    
    if len(password) < 8:
        errors.append("• يجب أن تكون 8 أحرف على الأقل")
    
    if not any(c.isupper() for c in password):
        errors.append("• يجب أن تحتوي على حرف كبير واحد على الأقل")
    
    if not any(c.islower() for c in password):
        errors.append("• يجب أن تحتوي على حرف صغير واحد على الأقل")
    
    if not any(c.isdigit() for c in password):
        errors.append("• يجب أن تحتوي على رقم واحد على الأقل")
    
    if errors:
        error_message = "❌ كلمة المرور غير صالحة:\n" + "\n".join(errors)
        bot.send_message(message.chat.id, error_message)
        return
    
    try:
        # التحقق النهائي من توفر الاسم
        if api.check_player_exists(username):
            bot.send_message(
                message.chat.id,
                "❌ هذا الاسم مستخدم بالفعل، يرجى اختيار اسم آخر"
            )
            return
        
        # إنشاء الحساب
        status, data, player_id, email_created = api.create_player_with_credentials(username, password)
        
        # تحليل الاستجابة
        if status == 200 and player_id:
            # حفظ البيانات في قاعدة البيانات
            try:
                db.update_player_info(telegram_id, player_id, username, email_created, password)
            except Exception as db_error:
                send_admin_log("⚠️ Database Error", f"Failed to save player info: {str(db_error)}")
            
            # إرسال معلومات الحساب
            login_info = f"""
✅ **تم إنشاء الحساب بنجاح!**

👤 **اسم المستخدم:** `{username}`
🔐 **كلمة المرور:** `{password}`
📧 **البريد الإلكتروني:** `{email_created}`
🆔 **معرف اللاعب:** `{player_id}`

🔗 **رابط تسجيل الدخول:**
https://www.ichancy.com/login

⚠️ **احفظ هذه البيانات في مكان آمن!**
"""
            bot.send_message(message.chat.id, login_info, parse_mode="Markdown")
            
            # إرسال رسالة تأكيد إضافية
            bot.send_message(
                message.chat.id,
                "🎉 **تم إنشاء حسابك بنجاح!**\n\n"
                "يمكنك الآن استخدام الحساب للعب على المنصة.\n"
                "لأي استفسار، لا تتردد في التواصل مع الدعم."
            )
            
        else:
            # استخراج رسالة الخطأ
            error_msg = "فشل إنشاء الحساب"
            if isinstance(data, dict):
                if "notification" in data and isinstance(data["notification"], list) and data["notification"]:
                    error_msg = data["notification"][0].get("content", error_msg)
                elif "message" in data:
                    error_msg = data["message"]
                elif "error" in data:
                    error_msg = data["error"]
            
            raise ValueError(f"{error_msg} (كود: {status})")
            
    except ValueError as e:
        bot.send_message(
            message.chat.id, 
            f"❌ **فشل إنشاء الحساب:**\n{str(e)}\n\n"
            f"يرجى المحاولة مرة أخرى باستخدام بيانات مختلفة."
        )
    except Exception as e:
        bot.send_message(
            message.chat.id, 
            f"❌ **حدث خطأ غير متوقع:**\n{str(e)}\n\n"
            f"يرجى المحاولة مرة أخرى لاحقاً."
        )

# ======================
# دوال إضافية للبوت
# ======================

def handle_deposit(bot, call, player_id):
    """معالجة طلب الإيداع"""
    try:
        bot.send_message(
            call.message.chat.id,
            "💰 **الإيداع**\n\n"
            "أرسل المبلغ الذي تريد إيداعه:"
        )
        
        bot.register_next_step_handler_by_chat_id(
            call.message.chat.id,
            lambda msg: process_deposit_amount(bot, msg, player_id)
        )
        
    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ خطأ في طلب الإيداع: {str(e)}"
        )

def process_deposit_amount(bot, message, player_id):
    """معالجة مبلغ الإيداع"""
    try:
        amount_text = message.text.strip()
        
        # التحقق من أن المبلغ رقم
        try:
            amount = float(amount_text)
            if amount <= 0:
                raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
        except ValueError:
            bot.send_message(
                message.chat.id,
                "❌ المبلغ غير صالح. يرجى إرسال رقم صحيح"
            )
            return
        
        # تنفيذ الإيداع
        status, data = api.deposit_to_player(player_id, amount)
        
        if status == 200:
            bot.send_message(
                message.chat.id,
                f"✅ **تم الإيداع بنجاح!**\n\n"
                f"المبلغ: {amount} NSP\n"
                f"للاعب: {player_id}"
            )
        else:
            error_msg = data.get("error", "فشل الإيداع")
            bot.send_message(
                message.chat.id,
                f"❌ **فشل الإيداع:** {error_msg}"
            )
            
    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"❌ حدث خطأ أثناء الإيداع: {str(e)}"
        )

def handle_balance(bot, call, player_id):
    """التحقق من الرصيد"""
    try:
        status, data = api.get_player_balance(player_id)
        
        if status == 200:
            balance = data.get("balance", "غير متاح")
            bot.send_message(
                call.message.chat.id,
                f"💰 **رصيد اللاعب:**\n\n"
                f"🆔 المعرف: `{player_id}`\n"
                f"💵 الرصيد: `{balance}` NSP",
                parse_mode="Markdown"
            )
        else:
            error_msg = data.get("error", "فشل جلب الرصيد")
            bot.send_message(
                call.message.chat.id,
                f"❌ **خطأ:** {error_msg}"
            )
            
    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ حدث خطأ: {str(e)}"
        )
