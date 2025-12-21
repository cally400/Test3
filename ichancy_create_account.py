import os
import random
import string
import db
from ichancy_api import IChancyAPI

api = IChancyAPI()

# =========================
# شريط التقدم
# =========================
def progress_bar(percent: int) -> str:
    filled = int(percent / 10)
    return f"[{'█' * filled}{'░' * (10 - filled)}] {percent}%"

def update_progress(bot, chat_id, message_id, title, percent):
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=f"⏳ {title}\n{progress_bar(percent)}"
    )

# =========================
# إنشاء اسم مستخدم فريد
# =========================
def _random_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_username(raw_username: str) -> str:
    base = f"ZEUS_{raw_username}"
    for i in range(6):
        username = base if i == 0 else f"{base}_{_random_suffix()}"
        if not api.check_player_exists(username):
            return username
    raise ValueError("❌ اسم المستخدم غير متاح، جرّب اسمًا آخر")

# =========================
# الخطوة الأولى: اسم المستخدم
# =========================
def start_create_account(bot, call):
    bot.send_message(call.message.chat.id, "📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):")
    bot.register_next_step_handler_by_chat_id(
        call.message.chat.id,
        lambda msg: process_username_step(bot, msg, call.from_user.id)
    )

def process_username_step(bot, message, telegram_id):
    chat_id = message.chat.id
    raw_username = ''.join(c for c in message.text.strip() if c.isalnum() or c in ['_', '-'])

    if len(raw_username) < 3:
        bot.send_message(chat_id, "❌ الاسم قصير جداً (3 أحرف على الأقل)")
        return

    # رسالة شريط التقدم
    progress_msg = bot.send_message(chat_id, "⏳ جاري التحقق من الاسم:\n[░░░░░░░░░░] 0%")

    try:
        # المرحلة 1: تحقق من وجود الحساب مسبقًا
        update_progress(bot, chat_id, progress_msg.message_id, "التحقق من وجود الاسم", 25)
        if api.check_player_exists(raw_username):
            bot.edit_message_text(chat_id=chat_id, message_id=progress_msg.message_id,
                                  text="✅ لديك حساب مسبقًا")
            return

        # المرحلة 2: إنشاء اسم مستخدم فريد
        update_progress(bot, chat_id, progress_msg.message_id, "إنشاء اسم مستخدم فريد", 50)
        username = generate_username(raw_username)

        # المرحلة 3: جاهز لاستلام كلمة المرور
        update_progress(bot, chat_id, progress_msg.message_id, "الاسم متاح، انتظر كلمة المرور", 75)

        bot.send_message(
            chat_id,
            f"✅ الاسم متاح: `{username}`\n\n"
            f"🔐 الآن أرسل كلمة السر:\n"
            f"- 8 أحرف على الأقل\n"
            f"- أحرف كبيرة وصغيرة\n"
            f"- أرقام",
            parse_mode="Markdown"
        )

        bot.register_next_step_handler_by_chat_id(
            chat_id,
            lambda msg: process_password_step(bot, msg, telegram_id, username, progress_msg.message_id)
        )

    except Exception as e:
        bot.edit_message_text(chat_id=chat_id, message_id=progress_msg.message_id, text=f"❌ خطأ: {str(e)}")

# =========================
# الخطوة الثانية: كلمة المرور
# =========================
def process_password_step(bot, message, telegram_id, username, progress_message_id):
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
        # المرحلة 4: إنشاء الحساب
        update_progress(bot, chat_id, progress_message_id, "جاري إنشاء الحساب", 80)
        status, data, player_id, email = api.create_player_with_credentials(username, password)

        if status != 200 or not player_id:
            raise ValueError("❌ فشل إنشاء الحساب")

        # المرحلة 5: حفظ البيانات
        update_progress(bot, chat_id, progress_message_id, "جاري حفظ البيانات", 90)
        db.update_player_info(telegram_id, player_id, username, email, password)

        # المرحلة 6: انتهى
        update_progress(bot, chat_id, progress_message_id, "✅ تم إنشاء الحساب بنجاح", 100)

        bot.send_message(
            chat_id,
            f"""✅ تم إنشاء الحساب بنجاح!

👤 المستخدم: `{username}`
🔐 كلمة المرور: `{password}`
📧 الإيميل: `{email}`
🆔 Player ID: `{player_id}`

🔗 https://www.ichancy.com/login
""",
            parse_mode="Markdown"
        )

    except Exception as e:
        bot.edit_message_text(chat_id=chat_id, message_id=progress_message_id, text=f"❌ فشل إنشاء الحساب:\n{str(e)}")

