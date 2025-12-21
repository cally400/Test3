import os
import random
import string
import time
import db
from ichancy_api import IChancyAPI

api = IChancyAPI()

def _random_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def ensure_session():
    """تجديد الجلسة إذا انتهت أو غير موجودة"""
    if not api.is_session_valid():
        api.login()
        print("🔄 تم تجديد الجلسة بنجاح")

def generate_username(raw_username: str) -> str:
    """إنشاء اسم مستخدم فريد"""
    base = f"ZEUS_{raw_username}"
    for i in range(6):
        username = base if i == 0 else f"{base}_{_random_suffix()}"
        ensure_session()
        if not api.check_player_exists(username):
            return username
    raise ValueError("❌ اسم المستخدم غير متاح، جرّب اسمًا آخر")

def start_create_account(bot, call):
    telegram_id = call.from_user.id
    # تحقق أولاً إذا كان لديه حساب مسبق
    ensure_session()
    player = db.get_player_by_telegram_id(telegram_id)
    if player:
        bot.send_message(call.message.chat.id, "❌ لديك حساب مسبق بالفعل!")
        return

    bot.send_message(call.message.chat.id, "📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):")
    bot.register_next_step_handler_by_chat_id(
        call.message.chat.id,
        lambda msg: process_username_step(bot, msg, telegram_id)
    )

def process_username_step(bot, message, telegram_id):
    raw_username = ''.join(c for c in message.text.strip() if c.isalnum() or c in ['_', '-'])
    if len(raw_username) < 3:
        bot.send_message(message.chat.id, "❌ الاسم قصير جداً، يجب أن يكون 3 أحرف على الأقل")
        return

    try:
        username = generate_username(raw_username)
        bot.send_message(message.chat.id, f"✅ الاسم متاح: `{username}`\n\n🔐 الآن أرسل كلمة السر:", parse_mode="Markdown")
        bot.register_next_step_handler_by_chat_id(
            message.chat.id,
            lambda msg: process_password_step(bot, msg, telegram_id, username)
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ: {str(e)}")

def process_password_step(bot, message, telegram_id, username):
    password = message.text.strip()
    if len(password) < 8 or not any(c.isupper() for c in password) or not any(c.islower() for c in password) or not any(c.isdigit() for c in password):
        bot.send_message(message.chat.id, "❌ كلمة المرور ضعيفة، تأكد من الشروط")
        return

    try:
        ensure_session()
        # شريط التقدم
        progress_msg = bot.send_message(message.chat.id, "⏳ جاري إنشاء الحساب: 0%")
        for i in range(1, 101, 10):
            time.sleep(0.2)
            bot.edit_message_text(f"⏳ جاري إنشاء الحساب: {i}%", message.chat.id, progress_msg.message_id)

        status, data, player_id, email_created = api.create_player_with_credentials(username, password)
        if status != 200 or not player_id:
            raise ValueError("فشل إنشاء الحساب")

        email = email_created or f"{username.lower()}@player.ichancy.com"
        db.update_player_info(telegram_id, player_id, username, email, password)

        bot.edit_message_text("✅ تم إنشاء الحساب بنجاح!", message.chat.id, progress_msg.message_id)
        bot.send_message(message.chat.id, f"👤 اسم المستخدم: `{username}`\n🔐 كلمة المرور: `{password}`\n📧 الإيميل: {email}\n🆔 معرف اللاعب: `{player_id}`", parse_mode="Markdown")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ فشل إنشاء الحساب: {str(e)}")

