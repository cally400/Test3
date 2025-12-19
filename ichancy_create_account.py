import random
import string
from ichancy_api import IChancyAPI
from db import update_player_info
from admin_logger import send_admin_log

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

# ===============================
# خطوة إدخال اسم المستخدم
# ===============================
def start_create_account(bot, call):
    bot.send_message(call.message.chat.id, "📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):")
    bot.register_next_step_handler_by_chat_id(
        call.message.chat.id, 
        lambda msg: process_username_step(bot, msg, call.from_user.id)
    )

def process_username_step(bot, message, telegram_id):
    raw_username = ''.join(c for c in message.text.strip() if c.isalnum() or c in ['_', '-'])
    
    if len(raw_username) < 3:
        bot.send_message(message.chat.id, "❌ الاسم قصير جداً، يجب أن يكون 3 أحرف على الأقل")
        return

    try:
        username = generate_username(raw_username)
        bot.send_message(
            message.chat.id, 
            f"✅ الاسم متاح: `{username}`\n\n"
            f"🔐 أرسل كلمة السر:\n- يجب أن تحتوي على أحرف كبيرة وصغيرة وأرقام\n- 8 أحرف على الأقل",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler_by_chat_id(
            message.chat.id,
            lambda msg: process_password_step(bot, msg, telegram_id, username)
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ: {str(e)}\nيرجى المحاولة مرة أخرى باستخدام /start")

# ===============================
# خطوة إدخال كلمة المرور
# ===============================
def process_password_step(bot, message, telegram_id, username):
    password = message.text.strip()

    if len(password) < 8 or not any(c.isupper() for c in password) \
       or not any(c.islower() for c in password) or not any(c.isdigit() for c in password):
        bot.send_message(message.chat.id, "❌ كلمة المرور ضعيفة، يجب أن تحتوي على أحرف كبيرة وصغيرة وأرقام و8 أحرف على الأقل")
        return

    try:
        status, data, player_id, email = api.create_player_with_credentials(username, password)

        if status != 200 or not player_id:
            bot.send_message(message.chat.id, f"❌ فشل إنشاء الحساب: {data.get('notification', data)}")
            send_admin_log("❌ Create Account Failed", f"{username} / {telegram_id}\n{data}")
            return

        # حفظ البيانات في قاعدة البيانات
        update_player_info(telegram_id, player_id, username, email, password)

        # إرسال تعليمات تسجيل الدخول
        login_info = f"""
✅ **تم إنشاء الحساب بنجاح!**
👤 **اسم المستخدم:** `{username}`
🔐 **كلمة المرور:** `{password}`
📧 **البريد الإلكتروني:** `{email}`
🆔 **معرف اللاعب:** `{player_id}`

🔗 رابط تسجيل الدخول: https://www.ichancy.com/login

⚠️ احفظ هذه البيانات في مكان آمن!
"""
        bot.send_message(message.chat.id, login_info, parse_mode="Markdown")
        send_admin_log("✅ Account Created", f"{username} / {telegram_id}\nPlayer ID: {player_id}")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ أثناء إنشاء الحساب:\n{str(e)}")
        send_admin_log("❌ API Exception", f"{username} / {telegram_id}\n{str(e)}")

