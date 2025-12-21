import os
import random
import string
import time
import threading
import db
from telebot import types
from ichancy_api import IChancyAPI

api = IChancyAPI()

def _random_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_username(raw_username: str) -> str:
    base = f"ZEUS_{raw_username}"
    for i in range(10):
        username = base if i == 0 else f"{base}_{_random_suffix()}"
        try:
            if not api.check_player_exists(username):
                return username
        except Exception:
            time.sleep(0.5)
            continue
    raise ValueError("❌ اسم المستخدم غير متاح، جرّب اسمًا آخر")

def show_progress(bot, chat_id, message, stop_event):
    """شريط تقدم تفاعلي حسب API"""
    progress = 0
    msg = bot.send_message(chat_id, f"{message}\n⏳ التقدم: {progress}%")
    while not stop_event.is_set() and progress < 100:
        progress += random.randint(5, 15)
        if progress > 100:
            progress = 100
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg.message_id,
                text=f"{message}\n⏳ التقدم: {progress}%"
            )
        except:
            pass
        time.sleep(0.5)
    if not stop_event.is_set():
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg.message_id,
            text=f"{message}\n✅ تم الانتهاء"
        )
    return msg

def start_create_account(bot, call):
    telegram_id = call.from_user.id
    user = db.get_user(telegram_id)
    
    if user and user.get("player_id"):
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

    # شريط تقدم فعلي
    stop_event = threading.Event()
    progress_thread = threading.Thread(target=show_progress, args=(bot, message.chat.id, "⏳ جارِ التحقق من اسم المستخدم...", stop_event))
    progress_thread.start()
    
    try:
        username = generate_username(raw_username)
    finally:
        stop_event.set()
        progress_thread.join()
    
    bot.send_message(
        message.chat.id, 
        f"✅ الاسم متاح: `{username}`\n\n🔐 الآن أرسل كلمة السر:",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler_by_chat_id(
        message.chat.id, 
        lambda msg: process_password_step(bot, msg, telegram_id, username)
    )

def process_password_step(bot, message, telegram_id, username):
    if not message.text:
        bot.send_message(message.chat.id, "❌ يجب إرسال كلمة سر نصية")
        return
    
    password = message.text.strip()
    if len(password) < 8 or not any(c.isupper() for c in password) \
       or not any(c.islower() for c in password) or not any(c.isdigit() for c in password):
        bot.send_message(message.chat.id, "❌ كلمة المرور غير صالحة، تحقق من الشروط")
        return
    
    # شريط تقدم فعلي أثناء إنشاء الحساب
    stop_event = threading.Event()
    progress_thread = threading.Thread(target=show_progress, args=(bot, message.chat.id, "⏳ جارِ إنشاء الحساب...", stop_event))
    progress_thread.start()
    
    try:
        email = f"{username.lower()}@player.ichancy.com"
        for attempt in range(3):
            try:
                if api.check_player_exists(username):
                    stop_event.set()
                    progress_thread.join()
                    bot.send_message(message.chat.id, "❌ هذا الاسم مستخدم بالفعل، يرجى اختيار اسم آخر")
                    return
                status, data, player_id, email_created = api.create_player_with_credentials(username, password)
                if status == 200 and player_id:
                    break
            except Exception:
                time.sleep(1)
                continue
        else:
            raise ValueError("❌ فشل إنشاء الحساب بعد عدة محاولات")
        
        db.update_player_info(telegram_id, player_id, username, email_created or email, password)
    finally:
        stop_event.set()
        progress_thread.join()
    
    login_info = f"""
✅ تم إنشاء الحساب بنجاح!
👤 اسم المستخدم: `{username}`
🔐 كلمة المرور: `{password}`
📧 البريد الإلكتروني: `{email_created or email}`
🆔 معرف اللاعب: `{player_id}`
🔗 رابط تسجيل الدخول: https://www.ichancy.com/login
⚠️ احفظ هذه البيانات في مكان آمن!
    """
    bot.send_message(message.chat.id, login_info, parse_mode="Markdown")

