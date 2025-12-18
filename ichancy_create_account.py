import os
import random
import string
import db
from ichancy_api import IChancyAPI

api = IChancyAPI()

def _random_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_username(raw_username: str) -> str:
    base = f"ZEUS_{raw_username}"
    for i in range(6):
        username = base if i == 0 else f"{base}_{_random_suffix()}"
        status, data, player_id, email = api.create_player_with_credentials(username, "TempPassword123!")
        if status == 200:
            return username
        if "username" not in str(data).lower():
            break
    raise ValueError("❌ اسم المستخدم غير متاح، جرّب اسمًا آخر")

def start_create_account(bot, call):
    bot.send_message(call.message.chat.id, "📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط):")
    bot.register_next_step_handler_by_chat_id(call.message.chat.id, process_username_step, call.from_user.id)

def process_username_step(message, telegram_id):
    raw_username = message.text.strip()
    try:
        username = generate_username(raw_username)
        bot.send_message(message.chat.id, f"✅ الاسم متاح: {username}\n🔐 أرسل كلمة السر:")
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_password_step, telegram_id, username)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ: {str(e)}")

def process_password_step(message, telegram_id, username):
    password = message.text.strip()
    try:
        status, data, player_id, email = api.create_player_with_credentials(username, password)
        if status != 200:
            error_msg = data.get("notification", [{}])[0].get("content", "فشل إنشاء الحساب")
            raise ValueError(error_msg)
        db.update_player_info(telegram_id, player_id, username, email, password)
        bot.send_message(message.chat.id, f"✅ تم إنشاء الحساب بنجاح\n👤 المستخدم: {username}\n🔐 كلمة السر: {password}\n📧 الإيميل: {email}\n🆔 معرف اللاعب: {player_id}")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ فشل إنشاء الحساب: {str(e)}")

