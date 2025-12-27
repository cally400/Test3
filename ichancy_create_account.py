# ichancy_create_account.py - الإصدار المعدل
import os
import random
import string
import db
from ichancy_api import get_api_instance  # ⚠️ تغيير الاستيراد

# ⚠️ استخدام النسخة المشتركة من API
api = get_api_instance()

def _random_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_username(raw_username: str) -> str:
    """إنشاء اسم مستخدم فريد"""
    base = f"ZEUS_{raw_username}"
    
    # المحاولة 1-6: أسماء منظمة
    for i in range(6):
        username = base if i == 0 else f"{base}_{_random_suffix()}"
        try:
            exists = api.check_player_exists(username)
            if not exists:
                return username
        except Exception as e:
            # ⚠️ تسجيل الخطأ ومتابعة المحاولة
            print(f"⚠️ خطأ في التحقق من {username}: {e}")
            continue
    
    # المحاولة 7-12: أسماء عشوائية أكثر
    for i in range(6):
        username = f"ZEUS_{raw_username}_{_random_suffix(6)}"
        try:
            exists = api.check_player_exists(username)
            if not exists:
                return username
        except Exception:
            continue
    
    # ⚠️ إذا فشلت جميع المحاولات، أنشئ اسم عشوائي بدون تحقق
    return f"ZEUS_{raw_username}_{_random_suffix(8)}"

def start_create_account(bot, call):
    bot.send_message(call.message.chat.id, "📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):")
    bot.register_next_step_handler_by_chat_id(
        call.message.chat.id,
        lambda msg: process_username_step(bot, msg, call.from_user.id)
    )

def process_username_step(bot, message, telegram_id):
    raw_username = message.text.strip()
    # تنظيف الاسم
    raw_username = ''.join(c for c in raw_username if c.isalnum() or c in ['_', '-'])

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
        bot.send_message(message.chat.id, f"❌ خطأ: {str(e)}\n\nيرجى المحاولة مرة أخرى باستخدام /start")

def process_password_step(bot, message, telegram_id, username):
    password = message.text.strip()

    # التحقق من قوة كلمة المرور
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
        # إنشاء الحساب مع البريد الإلكتروني الصحيح
        email = f"{username.lower()}@player.ichancy.com"

        # تحقق أولاً إذا كان الحساب موجود بالفعل
        # ⚠️ يمكنك تعليق هذا السطر مؤقتاً للاختبار إذا كان check_player_exists يعطي خطأ
        exists = api.check_player_exists(username)
        if exists:
            bot.send_message(message.chat.id, "❌ هذا الاسم مستخدم بالفعل، يرجى اختيار اسم آخر")
            return

        # إنشاء الحساب
        status, data, player_id = api.create_player(username, password)  # ⚠️ التأكد من أن create_player تُرجع 3 قيم

        if status != 200:
            error_msg = "فشل إنشاء الحساب"
            if data and isinstance(data, dict):
                notifications = data.get("notification", [])
                if notifications and isinstance(notifications, list):
                    error_msg = notifications[0].get("content", error_msg)
            raise ValueError(error_msg)

        if not player_id:
            # ⚠️ محاولة الحصول على player_id يدوياً إذا لم يُرجع
            player_id = api.get_player_id(username)
            if not player_id:
                raise ValueError("لم يتم إنشاء معرف اللاعب")

        # حفظ البيانات في قاعدة البيانات
        db.update_player_info(telegram_id, player_id, username, email, password)

        # إرسال تعليمات تسجيل الدخول
        login_info = f"""
✅ **تم إنشاء الحساب بنجاح!**

👤 **اسم المستخدم:** `{username}`
🔐 **كلمة المرور:** `{password}`
📧 **البريد الإلكتروني:** `{email}`
🆔 **معرف اللاعب:** `{player_id}`

🔗 **رابط تسجيل الدخول:**
https://www.ichancy.com/login

📌 **مهم:**
1. استخدم نفس بيانات الدخول أعلاه
2. إذا لم تعمل، جرب تغيير كلمة المرور أول مرة
3. للتأكد، يمكنك استخدام "نسيت كلمة المرور" على الموقع

⚠️ **احفظ هذه البيانات في مكان آمن!**
        """

        bot.send_message(message.chat.id, login_info, parse_mode="Markdown")

        # إرسال نفس المعلومات في رسالة خاصة أيضاً للحفظ
        bot.send_message(
            message.chat.id,
            f"💾 **احفظ هذه البيانات:**\n\n"
            f"الموقع: https://www.ichancy.com\n"
            f"المستخدم: {username}\n"
            f"كلمة المرور: {password}\n"
            f"الإيميل: {email}",
            parse_mode="Markdown"
        )

    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"❌ **فشل إنشاء الحساب:**\n\n{str(e)}\n\n"
            f"يرجى المحاولة مرة أخرى لاحقاً أو التواصل مع الدعم.",
            parse_mode="Markdown"
        )
