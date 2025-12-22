from ichancy_api import IChancyAPI
import db
import random
import string
import re

# لا تنشئ API عند الاستيراد
# api = IChancyAPI()  ← ❌ ممنوع

def get_api():
    """إنشاء API فقط عند الحاجة"""
    return IChancyAPI()

def _random_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_username(base):
    api = get_api()  # ← إنشاء API هنا فقط

    base = base.replace(" ", "_")
    base = re.sub(r'[^A-Za-z0-9_-]', '', base)

    for _ in range(10):
        username = f"{base}_{_random_suffix()}"
        if not api.check_player_exists(username):
            return username

    raise ValueError("❌ لم أستطع إيجاد اسم متاح، حاول اسمًا آخر.")

def start_create_account(bot, call):
    chat_id = call.message.chat.id
    bot.send_message(chat_id, "📝 أرسل اسم المستخدم المطلوب (إنجليزي فقط):")
    bot.register_next_step_handler(call.message, lambda msg: ask_password(bot, msg))

def ask_password(bot, msg):
    username_raw = msg.text.strip()

    if not re.match(r'^[A-Za-z0-9_.-]+$', username_raw):
        return bot.send_message(msg.chat.id, "❌ استخدم أحرف إنجليزية فقط.")

    username = generate_username(username_raw)

    bot.send_message(
        msg.chat.id,
        f"✅ الاسم متاح: `{username}`\n\nأرسل كلمة المرور (8 أحرف على الأقل):",
        parse_mode="Markdown"
    )

    bot.register_next_step_handler(msg, lambda m: create_account(bot, m, username))

def create_account(bot, msg, username):
    password = msg.text.strip()

    if len(password) < 8:
        return bot.send_message(msg.chat.id, "❌ كلمة المرور قصيرة جدًا.")

    telegram_id = msg.from_user.id

    bot.send_message(msg.chat.id, "⏳ جاري إنشاء الحساب...")

    api = get_api()  # ← إنشاء API هنا فقط
    status, data, player_id, email = api.create_player_with_credentials(username, password)

    if status != 200 or not player_id:
        return bot.send_message(msg.chat.id, "❌ فشل إنشاء الحساب، حاول لاحقًا.")

    # حفظ في MongoDB
    db.update_player_info(
        telegram_id,
        player_id,
        username,
        email,
        password
    )

    bot.send_message(
        msg.chat.id,
        f"🎉 تم إنشاء الحساب بنجاح!\n\n"
        f"👤 المستخدم: `{username}`\n"
        f"📧 الإيميل: `{email}`\n"
        f"🔑 كلمة المرور: `{password}`\n"
        f"🆔 Player ID: `{player_id}`",
        parse_mode="Markdown"
    )
