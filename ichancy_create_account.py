import os
import random
import string
import time
import db
from ichancy_api import IChancyAPI

api = IChancyAPI()

def _random_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_username(raw_username: str) -> str:
    """إنشاء اسم مستخدم فريد"""
    base = f"ZEUS_{raw_username}"
    for i in range(6):
        username = base if i == 0 else f"{base}_{_random_suffix()}"
        if not api.check_player_exists(username):
            return username
    raise ValueError("❌ اسم المستخدم غير متاح، جرّب اسمًا آخر")

def start_create_account(bot, call):
    telegram_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    # التحقق إذا كان المستخدم لديه حساب مسبق
    player_data = db.get_player_by_telegram_id(telegram_id)
    if player_data:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="ℹ️ لديك حساب مسبقًا"
        )
        return

    # إذا لم يكن لديه حساب مسبق
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text="📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):"
    )

    bot.register_next_step_handler_by_chat_id(
        chat_id,
        lambda msg: process_username_step(bot, msg, telegram_id)
    )

def process_username_step(bot, message, telegram_id):
    raw_username = message.text.strip()
    raw_username = ''.join(c for c in raw_username if c.isalnum() or c in ['_', '-'])

    if len(raw_username) < 3:
        bot.send_message(message.chat.id, "❌ الاسم قصير جداً، يجب أن يكون 3 أحرف على الأقل")
        return

    # إرسال شريط تقدم وهمي
    progress_msg = bot.send_message(message.chat.id, "🔄 جاري التحقق: 0%")
    for i in range(1, 101):
        time.sleep(0.01)
        bot.edit_message_text(chat_id=message.chat.id, message_id=progress_msg.message_id, text=f"🔄 جاري التحقق: {i}%")
    bot.delete_message(chat_id=message.chat.id, message_id=progress_msg.message_id)

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
        bot.send_message(message.chat.id, "❌ كلمة المرور غير صالحة، يجب أن تحتوي على 8 أحرف على الأقل مع أحرف كبيرة وصغيرة وأرقام")
        return

    # إرسال شريط تقدم أثناء إنشاء الحساب
    progress_msg = bot.send_message(message.chat.id, "🔄 جاري إنشاء الحساب: 0%")
    for i in range(1, 101):
        time.sleep(0.02)
        bot.edit_message_text(chat_id=message.chat.id, message_id=progress_msg.message_id, text=f"🔄 جاري إنشاء الحساب: {i}%")
    bot.delete_message(chat_id=message.chat.id, message_id=progress_msg.message_id)

    try:
        email = f"{username.lower()}@player.ichancy.com"

        if api.check_player_exists(username):
            bot.send_message(message.chat.id, "❌ هذا الاسم مستخدم بالفعل، يرجى اختيار اسم آخر")
            return

        status, data, player_id, email_created = api.create_player_with_credentials(username, password)

        if status != 200:
            error_msg = "فشل إنشاء الحساب"
            if data and isinstance(data, dict):
                notifications = data.get("notification", [])
                if notifications and isinstance(notifications, list):
                    error_msg = notifications[0].get("content", error_msg)
            raise ValueError(error_msg)

        if not player_id:
            raise ValueError("لم يتم إنشاء معرف اللاعب")

        db.update_player_info(telegram_id, player_id, username, email_created or email, password)

        login_info = f"""
✅ **تم إنشاء الحساب بنجاح!**

👤 **اسم المستخدم:** `{username}`
🔐 **كلمة المرور:** `{password}`
📧 **البريد الإلكتروني:** `{email_created or email}`
🆔 **معرف اللاعب:** `{player_id}`

🔗 **رابط تسجيل الدخول:**
https://www.ichancy.com/login

⚠️ **احفظ هذه البيانات في مكان آمن!**
        """

        bot.send_message(message.chat.id, login_info, parse_mode="Markdown")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ **فشل إنشاء الحساب:** {str(e)}", parse_mode="Markdown")

