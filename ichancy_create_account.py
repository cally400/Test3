# ichancy_create_account.py
import os
import random
import string
import time
import threading
from telebot import types
import db
from ichancy_api import IChancyAPI

api = IChancyAPI()

# -------------------------
def _random_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_username(raw_username: str) -> str:
    """إنشاء اسم مستخدم فريد"""
    base = f"ZEUS_{raw_username}"
    for i in range(6):
        username = base if i == 0 else f"{base}_{_random_suffix()}"
        try:
            # محاولة الحصول على player_id إذا كان موجود
            player_id = api.get_player_id(username)
            if not player_id:
                return username
        except Exception:
            continue
    raise ValueError("❌ اسم المستخدم غير متاح، جرّب اسمًا آخر")

# -------------------------
def start_create_account(bot, call):
    telegram_id = call.from_user.id

    # التحقق من وجود حساب مسبق
    player_info = db.get_player_info(telegram_id)
    
    if player_info and player_info.get("player_id"):
        # لديه حساب مسبق
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ لديك حساب مسبق بالفعل في Ichancy!"
        )
        return

    # إذا لم يكن لديه حساب مسبق
    msg = bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):"
    )
    
    bot.register_next_step_handler_by_chat_id(
        call.message.chat.id,
        lambda message: process_username_step(bot, message, telegram_id, msg)
    )

# -------------------------
def process_username_step(bot, message, telegram_id, progress_msg):
    raw_username = (message.text or "").strip()
    if not raw_username:
        bot.send_message(message.chat.id, "❌ يجب إدخال اسم مستخدم صحيح")
        return

    raw_username = ''.join(c for c in raw_username if c.isalnum() or c in ['_', '-'])
    if len(raw_username) < 3:
        bot.send_message(message.chat.id, "❌ الاسم قصير جداً، يجب أن يكون 3 أحرف على الأقل")
        return

    # إظهار شريط تقدم وهمي أثناء التحقق
    progress_thread = threading.Thread(target=show_progress, args=(bot, message.chat.id, "جارِ التحقق من الاسم"))
    progress_thread.start()

    try:
        username = generate_username(raw_username)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ: {str(e)}")
        return
    finally:
        # إيقاف شريط التقدم
        global stop_progress
        stop_progress = True
        progress_thread.join()

    bot.send_message(
        message.chat.id,
        f"✅ الاسم متاح: `{username}`\n\n🔐 الآن أرسل كلمة المرور المطلوبة:",
        parse_mode="Markdown"
    )

    bot.register_next_step_handler_by_chat_id(
        message.chat.id,
        lambda msg: process_password_step(bot, msg, telegram_id, username)
    )

# -------------------------
def process_password_step(bot, message, telegram_id, username):
    password = (message.text or "").strip()
    if len(password) < 8 or not any(c.isupper() for c in password) \
       or not any(c.islower() for c in password) or not any(c.isdigit() for c in password):
        bot.send_message(
            message.chat.id,
            "❌ كلمة المرور ضعيفة. يجب أن تحتوي على:\n- أحرف كبيرة وصغيرة\n- أرقام\n- 8 أحرف على الأقل"
        )
        return

    # شريط تقدم إنشاء الحساب
    progress_thread = threading.Thread(target=show_progress, args=(bot, message.chat.id, "جارِ إنشاء الحساب"))
    progress_thread.start()

    try:
        email = f"{username.lower()}@player.ichancy.com"

        status, data, created_username, created_password, player_id = api.create_player(username, password)
        if status != 200 or not player_id:
            raise ValueError("❌ فشل إنشاء الحساب، حاول لاحقاً")

        db.update_player_info(telegram_id, player_id, created_username, email, created_password)

        bot.send_message(
            message.chat.id,
            f"✅ تم إنشاء الحساب بنجاح!\n\n"
            f"👤 اسم المستخدم: `{created_username}`\n"
            f"🔐 كلمة المرور: `{created_password}`\n"
            f"📧 البريد الإلكتروني: `{email}`\n"
            f"🆔 معرف اللاعب: `{player_id}`\n\n"
            f"🔗 رابط تسجيل الدخول: https://www.ichancy.com/login",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ أثناء إنشاء الحساب: {str(e)}")
    finally:
        global stop_progress
        stop_progress = True
        progress_thread.join()

# -------------------------
stop_progress = False
def show_progress(bot, chat_id, message):
    """شريط تقدم وهمي """
    global stop_progress
    bar_length = 10
    percent = 0
    while not stop_progress:
        filled = int(bar_length * percent / 100)
        bar = "█" * filled + " " * (bar_length - filled)
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=None,  # تعديل حسب الحاجة إذا أردت تحديث رسالة موجودة
            text=f"⏳ {message}:\n[{bar}] {percent}%"
        )
        time.sleep(0.5)
        percent = min(percent + random.randint(5, 15), 100)

