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
        # التحقق أولاً إذا كان المستخدم موجود
        if not api.check_player_exists(username):
            return username
    raise ValueError("❌ اسم المستخدم غير متاح، جرّب اسمًا آخر")

def show_simple_progress(bot, chat_id, message):
    """عرض رسالة تقدم بسيطة"""
    progress_msg = bot.send_message(chat_id, f"⏳ {message}...")
    return progress_msg

def start_create_account(bot, call):
    telegram_id = call.from_user.id
    
    # التحقق من وجود حساب مسبق
    try:
        existing_account = db.get_player_info(telegram_id)
    except Exception as e:
        print(f"Error checking existing account: {e}")
        existing_account = None
    
    if existing_account:
        # إذا كان لديه حساب مسبق
        username = existing_account.get('username', 'غير معروف')
        
        message_text = f"""
✅ **لديك حساب مسبق بالفعل!**

👤 **اسم المستخدم:** `{username}`

🔗 **رابط تسجيل الدخول:**
https://www.ichancy.com/login

❓ **إذا كنت تريد إنشاء حساب جديد:**
اضغط /start واختر إنشاء حساب جديد
        """
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=message_text,
            parse_mode="Markdown"
        )
    else:
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
    
    raw_username = message.text.strip()
    
    if not raw_username:
        bot.send_message(message.chat.id, "❌ يجب إدخال اسم مستخدم")
        return
    
    # تنظيف الاسم
    raw_username = ''.join(c for c in raw_username if c.isalnum() or c in ['_', '-'])
    
    if len(raw_username) < 3:
        bot.send_message(message.chat.id, "❌ الاسم قصير جداً، يجب أن يكون 3 أحرف على الأقل")
        return
    
    # إظهار شريط تقدم بسيط
    progress_msg = bot.send_message(message.chat.id, "⏳ جارِ التحقق من اسم المستخدم...")
    
    try:
        username = generate_username(raw_username)
        
        # حذف رسالة التقدم
        bot.delete_message(message.chat.id, progress_msg.message_id)
        
        bot.send_message(
            message.chat.id, 
            f"✅ **الاسم متاح:** `{username}`\n\n"
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
        # حذف رسالة التقدم في حالة الخطأ
        try:
            bot.delete_message(message.chat.id, progress_msg.message_id)
        except:
            pass
        bot.send_message(message.chat.id, f"❌ خطأ: {str(e)}\n\nيرجى المحاولة مرة أخرى باستخدام /start")

def process_password_step(bot, message, telegram_id, username):
    if not message.text:
        bot.send_message(message.chat.id, "❌ يجب إرسال كلمة سر نصية")
        return
    
    password = message.text.strip()
    
    if not password:
        bot.send_message(message.chat.id, "❌ يجب إدخال كلمة مرور")
        return
    
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
    
    # إظهار شريط تقدم بسيط
    progress_msg = bot.send_message(message.chat.id, "⏳ جارِ إنشاء الحساب...")
    
    try:
        # إنشاء الحساب مع البريد الإلكتروني الصحيح
        email = f"{username.lower()}@player.ichancy.com"
        
        # تحقق أولاً إذا كان الحساب موجود بالفعل
        if api.check_player_exists(username):
            bot.delete_message(message.chat.id, progress_msg.message_id)
            bot.send_message(message.chat.id, "❌ هذا الاسم مستخدم بالفعل، يرجى اختيار اسم آخر")
            return
        
        # إنشاء الحساب
        status, data, player_id, email_created = api.create_player_with_credentials(username, password)
        
        if status != 200:
            error_msg = "فشل إنشاء الحساب"
            if data and isinstance(data, dict):
                notifications = data.get("notification", [])
                if notifications and isinstance(notifications, list):
                    error_msg = notifications[0].get("content", error_msg)
            raise ValueError(error_msg)
        
        if not player_id:
            raise ValueError("لم يتم إنشاء معرف اللاعب")
        
        # حفظ البيانات في قاعدة البيانات
        db.update_player_info(telegram_id, player_id, username, email_created or email, password)
        
        # حذف رسالة التقدم
        bot.delete_message(message.chat.id, progress_msg.message_id)
        
        # إرسال تعليمات تسجيل الدخول
        login_info = f"""
✅ **تم إنشاء الحساب بنجاح!**

👤 **اسم المستخدم:** `{username}`
🔐 **كلمة المرور:** `{password}`
📧 **البريد الإلكتروني:** `{email_created or email}`
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
            f"الإيميل: {email_created or email}",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        # حذف رسالة التقدم في حالة الخطأ
        try:
            bot.delete_message(message.chat.id, progress_msg.message_id)
        except:
            pass
        bot.send_message(
            message.chat.id, 
            f"❌ **فشل إنشاء الحساب:**\n\n{str(e)}\n\n"
            f"يرجى المحاولة مرة أخرى لاحقاً أو التواصل مع الدعم.",
            parse_mode="Markdown"
        )
