import os
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

def update_progress(bot, chat_id, message_id, title, percent):
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=f"⏳ {title}\n{progress_bar(percent)}"
    )

def generate_username(raw_username: str) -> str:
    base = f"ZEUS_{raw_username}"
    for i in range(6):
        username = base if i == 0 else f"{base}_{_random_suffix()}"
        if not api.check_player_exists(username):
            return username
    raise ValueError("❌ اسم المستخدم غير متاح، جرّب اسمًا آخر")

# =========================
# Entry Point
# =========================

def start_create_account(bot, call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    telegram_id = call.from_user.id

    user = db.get_user(telegram_id)

    # ✅ يعتبر لديه حساب فقط إذا كانت كل بيانات ichancy موجودة
    has_account = False
    if user:
        if (
            user.get("player_id") and
            user.get("player_username") and
            user.get("player_email") and
            user.get("player_password")
        ):
            has_account = True

    if has_account:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="✅ لديك حساب مسبق بالفعل"
        )
        return

    # ❌ لا يملك حساب
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text="📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):"
    )

    bot.register_next_step_handler_by_chat_id(
        chat_id,
        lambda msg: process_username_step(bot, msg, telegram_id)
    )

# =========================
# Username Step
# =========================

def process_username_step(bot, message, telegram_id):
    chat_id = message.chat.id
    raw_username = ''.join(
        c for c in message.text.strip()
        if c.isalnum() or c in ['_', '-']
    )

    if len(raw_username) < 3:
        bot.send_message(chat_id, "❌ الاسم قصير جداً (3 أحرف على الأقل)")
        return

    # إرسال رسالة التحقق
    progress_msg = bot.send_message(
        chat_id,
        "⏳ التحقق من الاسم\n" + progress_bar(30)
    )

    try:
        username = generate_username(raw_username)

        # ✅ تعديل نفس رسالة التحقق لطلب كلمة السر
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_msg.message_id,
            text=(
                f"✅ الاسم متاح: `{username}`\n\n"
                f"🔐 الآن أرسل كلمة السر:\n"
                f"- 8 أحرف على الأقل\n"
                f"- أحرف كبيرة وصغيرة\n"
                f"- أرقام"
            ),
            parse_mode="Markdown"
        )

        bot.register_next_step_handler_by_chat_id(
            chat_id,
            lambda msg: process_password_step(
                bot, msg, telegram_id, username
            )
        )

    except Exception as e:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_msg.message_id,
            text=f"❌ خطأ: {str(e)}"
        )

# =========================
# Password Step
# =========================

def process_password_step(bot, message, telegram_id, username):
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
        # 🔹 إرسال رسالة جديدة (70%)
        progress_msg = bot.send_message(
            chat_id,
            "⏳ جاري إنشاء الحساب\n" + progress_bar(70)
        )

        status, data, player_id, email = api.create_player_with_credentials(
            username, password
        )

        if status != 200 or not player_id:
            raise ValueError("فشل إنشاء الحساب")

        db.update_player_info(
            telegram_id,
            player_id,
            username,
            email,
            password
        )

        # ✅ تعديل نفس رسالة 70% إلى النجاح
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_msg.message_id,
            text=f"""✅ تم إنشاء الحساب بنجاح!

👤 المستخدم: `{username}`
🔐 كلمة المرور: `{password}`
📧 الإيميل: `{email}`
🆔 Player ID: `{player_id}`

🔗 https://www.ichancy.com/login
""",
            parse_mode="Markdown"
        )

    except Exception as e:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_msg.message_id,
            text=f"❌ فشل إنشاء الحساب:\n{str(e)}"
        )

