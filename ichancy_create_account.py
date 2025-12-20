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
    base = f"ZEUS_{raw_username}"
    for i in range(6):
        username = base if i == 0 else f"{base}_{_random_suffix()}"
        if not api.check_player_exists(username):
            return username
    raise ValueError("❌ اسم المستخدم غير متاح، جرّب اسمًا آخر")

def start_create_account(bot, call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    # تعديل الرسالة الأصلية مرة واحدة
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text="📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):"
    )

    # تسجيل خطوة إدخال اسم المستخدم
    bot.register_next_step_handler_by_chat_id(
        chat_id,
        lambda msg: process_username_step(bot, msg, call.from_user.id)
    )

def process_username_step(bot, message, telegram_id):
    raw_username = ''.join(c for c in message.text.strip() if c.isalnum() or c in ['_', '-'])

    if len(raw_username) < 3:
        bot.send_message(message.chat.id, "❌ الاسم قصير جداً، يجب أن يكون 3 أحرف على الأقل")
        return

    try:
        username = generate_username(raw_username)

        # إرسال شريط تقدم كرسالة جديدة
        progress_msg = bot.send_message(message.chat.id, "🔄 التحقق من الاسم وتجهيز الحساب...\n[░░░░░░░░░░] 0%")
        for i in range(1, 11):
            filled = '█' * i
            empty = '░' * (10 - i)
            percent = i * 10
            bot.edit_message_text(
                chat_id=progress_msg.chat.id,
                message_id=progress_msg.message_id,
                text=f"🔄 التحقق من الاسم وتجهيز الحساب...\n[{filled}{empty}] {percent}%"
            )
            time.sleep(0.2)

        # بعد شريط التقدم، طلب كلمة المرور
        bot.send_message(
            message.chat.id,
            f"✅ الاسم متاح: `{username}`\n\n🔐 الآن أرسل كلمة السر:\n"
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

    if len(password) < 8 or not any(c.isupper() for c in password) \
       or not any(c.islower() for c in password) or not any(c.isdigit() for c in password):
        bot.send_message(message.chat.id,
                         "❌ كلمة المرور غير صالحة.\nتأكد أنها تحتوي على أحرف كبيرة وصغيرة، أرقام، وطولها 8 أحرف على الأقل.")
        return

    # شريط تقدم جديد أثناء إنشاء الحساب
    progress_msg = bot.send_message(message.chat.id, "⏳ جاري إنشاء الحساب...\n[░░░░░░░░░░] 0%")
    for i in range(1, 11):
        filled = '█' * i
        empty = '░' * (10 - i)
        percent = i * 10
        bot.edit_message_text(
            chat_id=progress_msg.chat.id,
            message_id=progress_msg.message_id,
            text=f"⏳ جاري إنشاء الحساب...\n[{filled}{empty}] {percent}%"
        )
        time.sleep(0.2)

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
                if notifications and isinstance(notifications, list) and notifications:
                    error_msg = notifications[0].get("content", error_msg)
            raise ValueError(error_msg)

        if not player_id:
            raise ValueError("لم يتم إنشاء معرف اللاعب")

        db.update_player_info(telegram_id, player_id, username, email_created or email, password)

        # إرسال الحساب النهائي كرسالة جديدة
        final_text = f"""
✅ **تم إنشاء الحساب بنجاح!**

👤 **اسم المستخدم:** `{username}`
🔐 **كلمة المرور:** `{password}`
📧 **البريد الإلكتروني:** `{email_created or email}`
🆔 **معرف اللاعب:** `{player_id}`

🔗 **رابط تسجيل الدخول:**
https://www.ichancy.com/login

⚠️ **احفظ هذه البيانات في مكان آمن!**
"""
        bot.send_message(message.chat.id, final_text, parse_mode="Markdown")

    except Exception as e:
        bot.send_message(message.chat.id,
                         f"❌ **فشل إنشاء الحساب:**\n{str(e)}\n\nيرجى المحاولة لاحقاً أو التواصل مع الدعم.",
                         parse_mode="Markdown")

