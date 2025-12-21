# ichancy_create_account.py
import os
import random
import string
import time
import db
from telebot import types
from ichancy_api import IChancyAPI

api = IChancyAPI()

def _random_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_username(raw_username: str) -> str:
    """إنشاء اسم مستخدم فريد"""
    base = f"ZEUS_{raw_username}"
    for i in range(6):
        username = base if i == 0 else f"{base}_{_random_suffix()}"
        player_id = api.get_player_id(username)
        if not player_id:
            return username
    raise ValueError("❌ اسم المستخدم غير متاح، جرّب اسمًا آخر")

def show_progress(bot, chat_id, message, duration=2):
    """شريط تقدم وهمي متحرك حسب مدة محددة"""
    msg = bot.send_message(chat_id, f"{message}\n[----------] 0%")
    steps = 10
    for i in range(1, steps + 1):
        time.sleep(duration / steps)
        progress_bar = "█" * i + "-" * (steps - i)
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg.message_id,
            text=f"{message}\n[{progress_bar}] {i*10}%"
        )
    return msg

def start_create_account(bot, call):
    telegram_id = call.from_user.id

    # التحقق من وجود حساب مسبق في DB
    existing_player = db.get_user(telegram_id)
    if existing_player and existing_player.get("player_id"):
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ لديك حساب مسبق بالفعل!"
        )
        return

    # إذا لم يكن لديه حساب مسبق
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):"
    )
    bot.register_next_step_handler_by_chat_id(
        call.message.chat.id,
        lambda msg: process_username_step(bot, msg, telegram_id)
    )

def process_username_step(bot, message, telegram_id):
    if not message.text:
        bot.send_message(message.chat.id, "❌ يجب إرسال اسم مستخدم نصي")
        return

    raw_username = ''.join(c for c in message.text.strip() if c.isalnum() or c in ['_', '-'])
    if len(raw_username) < 3:
        bot.send_message(message.chat.id, "❌ الاسم قصير جداً، يجب أن يكون 3 أحرف على الأقل")
        return

    # شريط تقدم وهمي أثناء التحقق من الاسم
    progress_msg = show_progress(bot, message.chat.id, "⏳ جاري التحقق من الاسم:")

    try:
        username = generate_username(raw_username)
        bot.delete_message(message.chat.id, progress_msg.message_id)
        bot.send_message(
            message.chat.id,
            f"✅ الاسم متاح: `{username}`\n\n🔐 الآن أرسل كلمة السر:",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler_by_chat_id(
            message.chat.id,
            lambda msg: process_password_step(bot, msg, telegram_id, username)
        )
    except Exception as e:
        try:
            bot.delete_message(message.chat.id, progress_msg.message_id)
        except:
            pass
        bot.send_message(message.chat.id, f"❌ خطأ: {str(e)}")

def process_password_step(bot, message, telegram_id, username):
    password = message.text.strip()
    if len(password) < 8 or not any(c.isupper() for c in password) \
        or not any(c.islower() for c in password) or not any(c.isdigit() for c in password):
        bot.send_message(message.chat.id, "❌ كلمة المرور غير صالحة، يجب أن تحتوي على أحرف كبيرة وصغيرة وأرقام وطولها 8 أحرف على الأقل")
        return

    # شريط تقدم وهمي أثناء إنشاء الحساب
    progress_msg = show_progress(bot, message.chat.id, "⏳ جارِ إنشاء الحساب...")

    try:
        # إنشاء الحساب عبر API
        status, data, username_created, password_created, player_id = api.create_player(login=username, password=password)
        if status != 200 or not player_id:
            raise ValueError("فشل إنشاء الحساب")

        email = f"{username_created.lower()}@player.ichancy.com"
        db.update_player_info(telegram_id, player_id, username_created, email, password_created)
        bot.delete_message(message.chat.id, progress_msg.message_id)

        # رسالة النجاح
        bot.send_message(
            message.chat.id,
            f"✅ تم إنشاء الحساب بنجاح!\n\n"
            f"👤 اسم المستخدم: `{username_created}`\n"
            f"🔐 كلمة المرور: `{password_created}`\n"
            f"📧 البريد الإلكتروني: `{email}`\n"
            f"🆔 معرف اللاعب: `{player_id}`\n\n"
            f"🔗 رابط تسجيل الدخول: https://www.ichancy.com/login",
            parse_mode="Markdown"
        )

    except Exception as e:
        try:
            bot.delete_message(message.chat.id, progress_msg.message_id)
        except:
            pass
        bot.send_message(message.chat.id, f"❌ فشل إنشاء الحساب: {str(e)}", parse_mode="Markdown")

