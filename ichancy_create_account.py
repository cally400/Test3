import os
import random
import string
import db
from ichancy_api import IChancyAPI

api = IChancyAPI()

def _random_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_username(raw_username: str) -> str:
    """إنشاء اسم مستخدم فريد"""
    base = f"ZEUS_{raw_username}"
    
    # تنظيف الاسم
    base = ''.join(c for c in base if c.isalnum() or c in ['_', '-']).lower()
    
    for i in range(10):  # زيادة المحاولات
        if i == 0:
            username = base
        elif i < 6:
            username = f"{base}_{_random_suffix(3)}"
        else:
            username = f"{base}_{i:02d}"
        
        # التحقق أولاً إذا كان المستخدم موجود
        try:
            if not api.check_player_exists(username):
                return username
        except Exception as e:
            # إذا فشل التحقق، حاول تجديد الجلسة ومحاولة أخرى
            print(f"تحذير في التحقق من المستخدم: {e}")
            continue
    
    # إذا لم ينجح، حاول اسم مختلف تماماً
    random_name = f"zeus_{_random_suffix(8)}"
    return random_name

def start_create_account(bot, call):
    """بدء إنشاء حساب مع تجديد الجلسة"""
    chat_id = call.message.chat.id
    
    # إرسال رسالة تحميل
    msg = bot.send_message(chat_id, "🔄 **جاري تجديد الجلسة وتجهيز النظام...**", parse_mode="Markdown")
    
    try:
        # محاولة تجديد الجلسة وإعادة تسجيل الدخول
        if api.ensure_login():
            bot.edit_message_text(
                "✅ **تم تجديد الجلسة بنجاح!**\n\n"
                "📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):",
                chat_id=chat_id,
                message_id=msg.message_id,
                parse_mode="Markdown"
            )
            
            bot.register_next_step_handler_by_chat_id(
                chat_id, 
                lambda message: process_username_step(bot, message, call.from_user.id)
            )
        else:
            bot.edit_message_text(
                "❌ **فشل تجديد الجلسة**\n\n"
                "يرجى المحاولة مرة أخرى بعد قليل أو التواصل مع الدعم.",
                chat_id=chat_id,
                message_id=msg.message_id,
                parse_mode="Markdown"
            )
            
    except Exception as e:
        bot.edit_message_text(
            f"❌ **حدث خطأ أثناء تجديد الجلسة:**\n\n{str(e)}\n\n"
            "يرجى المحاولة مرة أخرى.",
            chat_id=chat_id,
            message_id=msg.message_id,
            parse_mode="Markdown"
        )
        print(f"خطأ في تجديد الجلسة: {e}")

def process_username_step(bot, message, telegram_id):
    raw_username = message.text.strip()
    
    # تنظيف الاسم
    raw_username = ''.join(c for c in raw_username if c.isalnum() or c in ['_', '-'])
    
    if len(raw_username) < 3:
        bot.send_message(message.chat.id, "❌ الاسم قصير جداً، يجب أن يكون 3 أحرف على الأقل")
        return
    
    # التأكد من أن الجلسة لا تزال نشطة
    try:
        if not api.is_logged_in or not api._is_session_valid():
            bot.send_message(message.chat.id, "🔄 جلسة منتهية، جاري تجديدها...")
            api.ensure_login()
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ في تجديد الجلسة: {str(e)}")
        return
    
    try:
        username = generate_username(raw_username)
        bot.send_message(
            message.chat.id, 
            f"✅ **الاسم متاح:** `{username}`\n\n"
            f"🔐 **الآن أرسل كلمة السر:**\n"
            f"- يجب أن تحتوي على أحرف كبيرة وصغيرة\n"
            f"- يجب أن تحتوي على أرقام\n"
            f"- يجب أن تكون 8 أحرف على الأقل\n"
            f"- يمكن أن تحتوي على رموز خاصة: !@#$%^&*\n\n"
            f"**مثال:** `Pass@1234`",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler_by_chat_id(
            message.chat.id, 
            lambda msg: process_password_step(bot, msg, telegram_id, username)
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ: {str(e)}\n\nيرجى المحاولة مرة أخرى باستخدام /start")

def process_password_step(bot, message, telegram_id, username):
    password = message.text.strip()
    
    # التحقق من قوة كلمة المرور
    if len(password) < 8:
        bot.send_message(message.chat.id, "❌ كلمة المرور قصيرة جداً، يجب أن تكون 8 أحرف على الأقل")
        return
    
    if not any(c.isupper() for c in password) or not any(c.islower() for c in password):
        bot.send_message(message.chat.id, "❌ يجب أن تحتوي كلمة المرور على أحرف كبيرة وصغيرة")
        return
    
    if not any(c.isdigit() for c in password):
        bot.send_message(message.chat.id, "❌ يجب أن تحتوي كلمة المرور على أرقام")
        return
    
    # إظهار رسالة تحميل
    loading_msg = bot.send_message(message.chat.id, "🔄 **جاري إنشاء الحساب...**", parse_mode="Markdown")
    
    try:
        # التأكد من أن الجلسة نشطة قبل إنشاء الحساب
        api.ensure_login()
        
        # إنشاء الحساب
        status, data, player_id, email_created = api.create_player_with_credentials(username, password)
        
        if status != 200 or not data.get("result", False):
            error_msg = "فشل إنشاء الحساب"
            if data and isinstance(data, dict):
                notifications = data.get("notification", [])
                if notifications and isinstance(notifications, list):
                    error_msg = notifications[0].get("content", error_msg)
            
            bot.edit_message_text(
                f"❌ **فشل إنشاء الحساب:**\n\n{error_msg}",
                chat_id=message.chat.id,
                message_id=loading_msg.message_id,
                parse_mode="Markdown"
            )
            return
        
        if not player_id:
            # محاولة الحصول على معرف اللاعب مرة أخرى
            player_id = api.get_player_id(username)
            if not player_id:
                raise ValueError("لم يتم إنشاء معرف اللاعب")
        
        # استخدام البريد الإلكتروني من الاستجابة أو إنشاء واحد افتراضي
        email = email_created if email_created else f"{username.lower()}@player.nsp"
        
        # حفظ البيانات في قاعدة البيانات
        try:
            db.update_player_info(telegram_id, player_id, username, email, password)
        except Exception as db_error:
            print(f"تحذير: خطأ في قاعدة البيانات: {db_error}")
            # الاستمرار حتى لو فشلت قاعدة البيانات
        
        # إرسال تعليمات تسجيل الدخول
        login_info = f"""
✅ **تم إنشاء الحساب بنجاح!**

👤 **اسم المستخدم:** `{username}`
🔐 **كلمة المرور:** `{password}`
📧 **البريد الإلكتروني:** `{email}`
🆔 **معرف اللاعب:** `{player_id}`

🔗 **رابط تسجيل الدخول:**
https://www.ichancy.com/login

📌 **مهم:**
1. استخدم نفس بيانات الدخول أعلاه
2. يمكنك تسجيل الدخول مباشرة أو باستخدام الإيميل
3. للتأكد، يمكنك استخدام "نسيت كلمة المرور" على الموقع

⚠️ **احفظ هذه البيانات في مكان آمن!**
        """
        
        bot.edit_message_text(
            login_info,
            chat_id=message.chat.id,
            message_id=loading_msg.message_id,
            parse_mode="Markdown"
        )
        
        # إرسال نفس المعلومات في رسالة خاصة أيضاً للحفظ
        bot.send_message(
            message.chat.id,
            f"💾 **احفظ هذه البيانات:**\n\n"
            f"🌐 **الموقع:** https://www.ichancy.com\n"
            f"👤 **المستخدم:** `{username}`\n"
            f"🔐 **كلمة المرور:** `{password}`\n"
            f"📧 **الإيميل:** `{email}`\n"
            f"🆔 **المعرف:** `{player_id}`\n\n"
            f"📅 **تاريخ الإنشاء:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        bot.edit_message_text(
            f"❌ **فشل إنشاء الحساب:**\n\n{str(e)}\n\n"
            f"يرجى المحاولة مرة أخرى لاحقاً أو التواصل مع الدعم.",
            chat_id=message.chat.id,
            message_id=loading_msg.message_id,
            parse_mode="Markdown"
        )
        print(f"خطأ في إنشاء الحساب: {e}")
