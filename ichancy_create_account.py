import os
import random
import string
import db
from ichancy_api import IChancyAPI, IChancySession

api = IChancyAPI()

def _random_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_username(raw_username: str) -> str:
    """إنشاء اسم مستخدم فريد"""
    base = f"ZEUS_{raw_username}"
    session = IChancySession(api._headers())
    api._ensure_login(session)  # إنشاء جلسة مستقلة للتحقق

    for i in range(6):
        username = base if i == 0 else f"{base}_{_random_suffix()}"
        if not api.check_player_exists(session, username):
            return username
    raise ValueError("❌ اسم المستخدم غير متاح، جرّب اسمًا آخر")

def start_create_account(bot, call):
    bot.send_message(call.message.chat.id, "📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):")
    bot.register_next_step_handler_by_chat_id(
        call.message.chat.id, 
        lambda msg: process_username_step(bot, msg, call.from_user.id)
    )

def process_username_step(bot, message, telegram_id):
    raw_username = message.text.strip()
    raw_username = ''.join(c for c in raw_username if c.isalnum() or c in ['_', '-'])
    
    if len(raw_username) < 3:
        bot.send_message(message.chat.id, "❌ الاسم قصير جداً، يجب أن يكون 3 أحرف على الأقل")
        return
    
    try:
        username = generate_username(raw_username)
        bot.send_message(
            message.chat.id, 
            f"✅ الاسم متاح: `{username}`\n\n"
            f"🔐 **الآن أرسل كلمة السر:**\n"
            f"- يجب أن تحتوي على أحرف كبيرة وصغيرة\n"
            f"- يجب أن تحتوي على أرقام\n"
            f"- يجب أن تكون 8 أحرف على الأقل\n\n"
            f"مثال: `Pass1234`",
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
    
    if len(password) < 8 or not any(c.isupper() for c in password) or not any(c.islower() for c in password) or not any(c.isdigit() for c in password):
        bot.send_message(message.chat.id, "❌ كلمة المرور غير صالحة، تأكد من الشروط")
        return
    
    try:
        session = IChancySession(api._headers())
        api._ensure_login(session)

        # تحقق من وجود اللاعب
        if api.check_player_exists(session, username):
            bot.send_message(message.chat.id, "❌ هذا الاسم مستخدم بالفعل، يرجى اختيار اسم آخر")
            return
        
        # إنشاء الحساب
        status, data, player_id, email_created = api.create_player_with_credentials(session, username, password)
        
        if status != 200 or not player_id:
            error_msg = data.get("notification", [{}])[0].get("content", "فشل إنشاء الحساب") if isinstance(data, dict) else "فشل إنشاء الحساب"
            raise ValueError(error_msg)
        
        # حفظ البيانات في قاعدة البيانات
        db.update_player_info(telegram_id, player_id, username, email_created, password)
        
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

    except Exception as e:
        bot.send_message(
            message.chat.id, 
            f"❌ **فشل إنشاء الحساب:** {str(e)}\nيرجى المحاولة مرة أخرى لاحقاً.",
            parse_mode="Markdown"
        )

