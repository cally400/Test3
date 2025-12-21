# ichancy_create_account.py
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
        if not api.check_player_exists(username):
            return username
    raise ValueError("❌ اسم المستخدم غير متاح، جرّب اسمًا آخر")

def update_progress_bar(bot, chat_id, message_id, prefix, progress):
    """تحديث شريط التقدم"""
    total_blocks = 10
    filled = int(progress * total_blocks / 100)
    bar = '█' * filled + '░' * (total_blocks - filled)
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=f"{prefix}\n[{bar}] {progress}%",
    )

def start_create_account(bot, call):
    telegram_id = call.from_user.id

    # التحقق من وجود حساب مسبق
    existing_account = db.get_user(telegram_id)
    
    if existing_account and existing_account.get("player_id"):
        # إذا كان لديه حساب مسبق
        username = existing_account.get('player_username', 'غير معروف')
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✅ لديك حساب مسبق بالفعل!\n\n👤 اسم المستخدم: `{username}`",
            parse_mode="Markdown"
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

    # إنشاء رسالة شريط تقدم أولية
    progress_msg = bot.send_message(message.chat.id, "⏳ جاري التحقق من الاسم:\n[░░░░░░░░░░] 0%")

    # تحديث الشريط تدريجيًا مع استدعاء API
    progress_steps = [10, 30, 60, 90, 100]
    for p in progress_steps[:-1]:
        time.sleep(0.5)  # لمحاكاة التقدم
        update_progress_bar(bot, message.chat.id, progress_msg.message_id, "⏳ جاري التحقق من الاسم:", p)

    # محاولة إنشاء اسم مستخدم متاح
    try:
        username = generate_username(raw_username)
    except Exception as e:
        update_progress_bar(bot, message.chat.id, progress_msg.message_id, "❌ فشل التحقق:", 100)
        bot.send_message(message.chat.id, f"❌ خطأ: {str(e)}\nيرجى المحاولة مرة أخرى")
        return

    update_progress_bar(bot, message.chat.id, progress_msg.message_id, "✅ الاسم متاح:", 100)
    time.sleep(0.5)

    bot.send_message(
        message.chat.id,
        f"✅ **الاسم متاح:** `{username}`\n\n🔐 الآن أرسل كلمة السر:",
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
        bot.send_message(message.chat.id, "❌ كلمة المرور غير قوية، يجب أن تحتوي على أحرف كبيرة وصغيرة وأرقام وطولها 8 أحرف على الأقل")
        return

    # شريط تقدم لإنشاء الحساب
    progress_msg = bot.send_message(message.chat.id, "⏳ جارِ إنشاء الحساب...\n[░░░░░░░░░░] 0%")
    progress_steps = [20, 40, 60, 80, 100]
    for p in progress_steps[:-1]:
        time.sleep(0.5)
        update_progress_bar(bot, message.chat.id, progress_msg.message_id, "⏳ جارِ إنشاء الحساب:", p)

    try:
        # تحقق أولًا إذا كان الحساب موجود
        if api.check_player_exists(username):
            update_progress_bar(bot, message.chat.id, progress_msg.message_id, "❌ الاسم مستخدم بالفعل:", 100)
            bot.send_message(message.chat.id, "❌ هذا الاسم مستخدم بالفعل، يرجى اختيار اسم آخر")
            return

        # إنشاء الحساب
        status, data, player_id, email_created = api.create_player_with_credentials(username, password)
        if status != 200 or not player_id:
            raise ValueError("فشل إنشاء الحساب، حاول مرة أخرى لاحقًا")

        # حفظ البيانات في DB
        db.update_player_info(telegram_id, player_id, username, email_created, password)

        update_progress_bar(bot, message.chat.id, progress_msg.message_id, "✅ تم إنشاء الحساب:", 100)
        time.sleep(0.5)

        bot.send_message(
            message.chat.id,
            f"✅ **تم إنشاء الحساب بنجاح!**\n👤 اسم المستخدم: `{username}`\n🔐 كلمة المرور: `{password}`\n📧 البريد الإلكتروني: `{email_created}`\n🆔 معرف اللاعب: `{player_id}`",
            parse_mode="Markdown"
        )

    except Exception as e:
        update_progress_bar(bot, message.chat.id, progress_msg.message_id, "❌ فشل إنشاء الحساب:", 100)
        bot.send_message(message.chat.id, f"❌ فشل إنشاء الحساب: {str(e)}")


