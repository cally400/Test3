
# ichancy_create_account.py

import random
import string
import logging
import db
from ichancy_api import IChancyAPI

# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("CreateAccount")

api = IChancyAPI()

# =========================
# Helpers
# =========================
def _random_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def generate_username(raw_username: str) -> str:
    """إنشاء اسم مستخدم فريد"""
    raw_username = ''.join(c for c in raw_username if c.isalnum() or c in ['_', '-'])
    base = f"ZEUS_{raw_username}"

    for i in range(6):
        username = base if i == 0 else f"{base}_{_random_suffix()}"
        try:
            exists = api.ensure_login() and api.create_player(login=username, password="Temp1234")[0] == 409
        except Exception:
            continue
        if not exists:
            return username

    raise ValueError("❌ اسم المستخدم غير متاح، جرّب اسمًا آخر")


# =========================
# Bot steps
# =========================
def start_create_account(bot, call):
    bot.send_message(
        call.message.chat.id,
        "📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):"
    )
    bot.register_next_step_handler_by_chat_id(
        call.message.chat.id,
        lambda msg: process_username_step(bot, msg, call.from_user.id)
    )


def process_username_step(bot, message, telegram_id):
    logger.info("DEBUG: process_username_step called")
    if not message.text:
        bot.send_message(message.chat.id, "❌ الرجاء إرسال نص فقط")
        return start_create_account(bot, message)

    raw_username = ''.join(c for c in message.text.strip() if c.isalnum() or c in ['_', '-'])
    logger.info(f"DEBUG: cleaned username = {raw_username}")

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
        logger.error(f"Error generating username: {str(e)}")
        bot.send_message(
            message.chat.id,
            f"❌ خطأ: {str(e)}\n\nيرجى المحاولة مرة أخرى باستخدام /start"
        )


def process_password_step(bot, message, telegram_id, username):
    if not message.text:
        bot.send_message(message.chat.id, "❌ الرجاء إرسال كلمة مرور نصية")
        return

    password = message.text.strip()

    if len(password) < 8:
        bot.send_message(message.chat.id, "❌ كلمة المرور قصيرة جداً، يجب أن تكون 8 أحرف على الأقل")
        return

    if not any(c.isupper() for c in password) or not any(c.islower() for c in password):
        bot.send_message(message.chat.id, "❌ يجب أن تحتوي كلمة المرور على أحرف كبيرة وصغيرة")
        return

    if not any(c.isdigit() for c in password):
        bot.send_message(message.chat.id, "❌ يجب أن تحتوي كلمة المرور على أرقام")
        return

    try:
        status, data = api.create_player(login=username, password=password)
        if status != 200:
            raise ValueError(f"فشل إنشاء الحساب: {data}")

        # تحديث قاعدة البيانات
        email = f"{username}@agent.nsp"
        db.update_player_info(telegram_id, username=username, email=email, password=password)

        login_info = f"""
✅ **تم إنشاء الحساب بنجاح!**

👤 **اسم المستخدم:** `{username}`
🔐 **كلمة المرور:** `{password}`
📧 **البريد الإلكتروني:** `{email}`

🔗 **رابط تسجيل الدخول:**
https://www.ichancy.com/login

⚠️ **احفظ هذه البيانات في مكان آمن!**
        """

        bot.send_message(message.chat.id, login_info, parse_mode="Markdown")
        logger.info(f"Player created: {username}")

    except Exception as e:
        logger.error(f"Error creating player: {str(e)}")
        bot.send_message(
            message.chat.id,
            f"❌ **فشل إنشاء الحساب:**\n\n{str(e)}\n\nيرجى المحاولة مرة أخرى لاحقاً أو التواصل مع الدعم.",
            parse_mode="Markdown"
        )
