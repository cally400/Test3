import random
import string
import db
from ichancy_api import IChancyAPI

api = IChancyAPI()

# =========================
# Helpers
# =========================

def _random_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def progress_bar(percent: int) -> str:
    filled = int(percent / 10)
    return f"[{'█' * filled}{'░' * (10 - filled)}] {percent}%"

def edit(bot, chat_id, message_id, text):
    bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode="Markdown")

def generate_username(raw_username: str) -> str:
    base = f"ZEUS_{raw_username}"
    for i in range(6):
        username = base if i == 0 else f"{base}_{_random_suffix()}"
        if not api.check_player_exists(username):
            return username
    raise ValueError("❌ اسم المستخدم غير متاح")

# =========================
# Entry
# =========================

def start_create_account(bot, call):
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    telegram_id = call.from_user.id

    user = db.get_user(telegram_id)
    if user and user.get("player_id"):
        edit(bot, chat_id, msg_id, "✅ لديك حساب مسبق بالفعل")
        return

    edit(
        bot,
        chat_id,
        msg_id,
        "📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):"
    )

    bot.register_next_step_handler_by_chat_id(
        chat_id,
        lambda m: process_username_step(bot, m, telegram_id)
    )

# =========================
# Username
# =========================

def process_username_step(bot, message, telegram_id):
    chat_id = message.chat.id
    raw = ''.join(c for c in message.text.strip() if c.isalnum() or c in ['_', '-'])

    if len(raw) < 3:
        bot.send_message(chat_id, "❌ الاسم قصير جداً")
        return

    progress = bot.send_message(
        chat_id,
        "⏳ التحقق من الاسم\n" + progress_bar(30)
    )

    try:
        username = generate_username(raw)

        edit(
            bot,
            chat_id,
            progress.message_id,
            f"""✅ الاسم متاح: `{username}`

🔐 الآن أرسل كلمة السر:
- 8 أحرف على الأقل
- أحرف كبيرة وصغيرة
- أرقام"""
        )

        bot.register_next_step_handler_by_chat_id(
            chat_id,
            lambda m: process_password_step(
                bot, m, telegram_id, username, progress.message_id
            )
        )

    except Exception as e:
        edit(bot, chat_id, progress.message_id, f"❌ {str(e)}")

# =========================
# Password
# =========================

def process_password_step(bot, message, telegram_id, username, progress_id):
    chat_id = message.chat.id
    password = message.text.strip()

    if (
        len(password) < 8 or
        not any(c.isupper() for c in password) or
        not any(c.islower() for c in password) or
        not any(c.isdigit() for c in password)
    ):
        bot.send_message(chat_id, "❌ كلمة المرور غير مطابقة للشروط")
        return

    try:
        edit(
            bot,
            chat_id,
            progress_id,
            "⏳ جاري إنشاء الحساب\n" + progress_bar(70)
        )

        status, data, player_id, email = api.create_player_with_credentials(username, password)
        if status != 200 or not player_id:
            raise ValueError("فشل إنشاء الحساب")

        db.update_player_info(
            telegram_id,
            player_id,
            username,
            email,
            password
        )

        edit(
            bot,
            chat_id,
            progress_id,
            f"""✅ تم إنشاء الحساب بنجاح!

👤 المستخدم: `{username}`
🔐 كلمة المرور: `{password}`
📧 الإيميل: `{email}`
🆔 Player ID: `{player_id}`

🔗 https://www.ichancy.com/login"""
        )

    except Exception as e:
        edit(bot, chat_id, progress_id, f"❌ {str(e)}")

