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
    telegram_id = call.from_user.id

    # التحقق إذا كان لدى المستخدم حساب مسبقاً
    existing_player = db.get_player_by_telegram_id(telegram_id)
    if existing_player:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"⚠️ لديك حساب مسبقاً!\n\n"
                 f"👤 اسم المستخدم: `{existing_player['username']}`\n"
                 f"🆔 معرف اللاعب: `{existing_player['player_id']}`\n"
                 f"إذا أردت إنشاء حساب جديد، استخدم رابط آخر أو تواصل مع الدعم.",
            parse_mode="Markdown"
        )
        return

    # تعديل الرسالة لإعداد العملية
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=call.message.message_id,
        text="📝 جاري تحضير إنشاء الحساب، يرجى الانتظار..."
    )

    # رسائل مرحلية قصيرة
    for stage in ["🔄 التحقق من الاسم المطلوب...", "⏳ إعداد البيانات الأولية..."]:
        time.sleep(0.5)
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=stage)

    # طلب اسم المستخدم
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=call.message.message_id,
        text="📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):"
    )

    bot.register_next_step_handler_by_chat_id(
        chat_id,
        lambda msg: process_username_step(bot, msg, telegram_id, call.message.message_id)
    )

def process_username_step(bot, message, telegram_id, message_id):
    raw_username = ''.join(c for c in message.text.strip() if c.isalnum() or c in ['_', '-'])

    if len(raw_username) < 3:
        bot.edit_message_text(chat_id=message.chat.id, message_id=message_id,
                              text="❌ الاسم قصير جداً، يجب أن يكون 3 أحرف على الأقل")
        return

    try:
        username = generate_username(raw_username)

        # رسائل مرحلية قصيرة
        for stage in [f"✅ الاسم متاح: `{username}`", 
                      "🔐 الآن أرسل كلمة السر:\n- يجب أن تحتوي على أحرف كبيرة وصغيرة\n- يجب أن تحتوي على أرقام\n- يجب أن تكون 8 أحرف على الأقل\nمثال: `Pass1234`"]:
            time.sleep(0.5)
            bot.edit_message_text(chat_id=message.chat.id, message_id=message_id, text=stage, parse_mode="Markdown")

        bot.register_next_step_handler_by_chat_id(
            message.chat.id,
            lambda msg: process_password_step(bot, msg, telegram_id, username, message_id)
        )
    except Exception as e:
        bot.edit_message_text(chat_id=message.chat.id, message_id=message_id,
                              text=f"❌ خطأ: {str(e)}\n\nيرجى المحاولة مرة أخرى باستخدام /start")

def process_password_step(bot, message, telegram_id, username, message_id):
    password = message.text.strip()

    if len(password) < 8 or not any(c.isupper() for c in password) or not any(c.islower() for c in password) or not any(c.isdigit() for c in password):
        bot.edit_message_text(chat_id=message.chat.id, message_id=message_id,
                              text="❌ كلمة المرور غير صالحة.\nتأكد أنها تحتوي على أحرف كبيرة وصغيرة، أرقام، وطولها 8 أحرف على الأقل.")
        return

    # رسائل مرحلية قصيرة لمحاكاة النشاط
    for stage in ["🔄 جاري إنشاء الحساب، يرجى الانتظار...", "⏳ يتم التحقق من بياناتك وإنشاء الحساب..."]:
        time.sleep(0.5)
        bot.edit_message_text(chat_id=message.chat.id, message_id=message_id, text=stage)

    try:
        email = f"{username.lower()}@player.ichancy.com"

        if api.check_player_exists(username):
            bot.edit_message_text(chat_id=message.chat.id, message_id=message_id,
                                  text="❌ هذا الاسم مستخدم بالفعل، يرجى اختيار اسم آخر")
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

        # تعديل الرسالة النهائية
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
        bot.edit_message_text(chat_id=message.chat.id, message_id=message_id, text=final_text, parse_mode="Markdown")

    except Exception as e:
        bot.edit_message_text(chat_id=message.chat.id, message_id=message_id,
                              text=f"❌ **فشل إنشاء الحساب:**\n{str(e)}\n\nيرجى المحاولة لاحقاً أو التواصل مع الدعم.",
                              parse_mode="Markdown")

