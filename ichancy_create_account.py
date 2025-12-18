import os
import random
import string
import db
from ichancy_api import IChancyAPI

api = IChancyAPI()

def _random_suffix(length=3):
    """إنشاء لاحقة عشوائية"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_available_username(raw_username: str) -> str:
    """
    توليد اسم مستخدم متاح مع إضافة لاحقة إذا كان الاسم غير متاح
    """
    # تنظيف الاسم
    clean_name = ''.join(c for c in raw_username if c.isalnum() or c in ['_', '-'])
    if not clean_name:
        clean_name = "user"
    
    # المحاولة بدون لاحقة أولاً
    if not api.check_player_exists(clean_name):
        return clean_name
    
    # إذا كان الاسم مستخدماً، إضافة لاحقات عشوائية حتى نجد اسم متاح
    for attempt in range(10):  # 10 محاولات كحد أقصى
        if attempt == 0:
            username = f"{clean_name}_{_random_suffix(3)}"
        elif attempt == 1:
            username = f"{clean_name}_{_random_suffix(4)}"
        elif attempt == 2:
            username = f"{clean_name}{random.randint(10, 99)}"
        elif attempt == 3:
            username = f"user_{clean_name}_{_random_suffix(3)}"
        else:
            username = f"player_{clean_name}_{_random_suffix(4)}_{random.randint(100, 999)}"
        
        if not api.check_player_exists(username):
            return username
    
    # إذا فشلنا في إيجاد اسم بعد 10 محاولات
    raise ValueError(f"❌ جميع الأسماء المشتقة من '{clean_name}' غير متاحة. يرجى اختيار اسم مختلف تماماً.")

def start_create_account(bot, call):
    bot.send_message(
        call.message.chat.id,
        "📝 **أرسل اسم المستخدم المطلوب:**\n\n"
        "- باللغة الإنجليزية فقط\n"
        "- يمكن استخدام أحرف، أرقام، وعلامة _\n"
        "- مثال: `john_doe` أو `player123`",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler_by_chat_id(
        call.message.chat.id, 
        lambda msg: process_username_step(bot, msg, call.from_user.id)
    )

def process_username_step(bot, message, telegram_id):
    raw_username = message.text.strip()
    
    if not raw_username:
        bot.send_message(message.chat.id, "❌ لم تقم بإدخال اسم. يرجى المحاولة مرة أخرى باستخدام /start")
        return
    
    # التحقق من طول الاسم
    if len(raw_username) < 3:
        bot.send_message(message.chat.id, "❌ الاسم قصير جداً. يجب أن يكون 3 أحرف على الأقل.")
        return
    
    if len(raw_username) > 20:
        bot.send_message(message.chat.id, "❌ الاسم طويل جداً. يجب أن لا يتجاوز 20 حرفاً.")
        return
    
    # التحقق من الأحروف المسموحة
    if not all(c.isalnum() or c in ['_', '-'] for c in raw_username):
        bot.send_message(
            message.chat.id,
            "❌ الاسم يحتوي على أحرف غير مسموحة.\n"
            "يُسمح فقط بـ:\n"
            "- أحرف إنجليزية (A-Z, a-z)\n"
            "- أرقام (0-9)\n"
            "- علامة _ أو -"
        )
        return
    
    try:
        # عرض رسالة "جاري التحقق"
        checking_msg = bot.send_message(message.chat.id, "🔍 **جاري التحقق من إمكانية الاسم...**")
        
        # توليد اسم متاح
        username = generate_available_username(raw_username)
        
        bot.edit_message_text(
            f"✅ **تم العثور على اسم متاح:**\n\n"
            f"📝 **الاسم المدخل:** `{raw_username}`\n"
            f"✨ **الاسم المتاح:** `{username}`\n\n"
            f"🔐 **الآن أرسل كلمة المرور:**\n"
            f"يجب أن تحتوي على:\n"
            f"• 8 أحرف على الأقل\n"
            f"• حرف كبير واحد على الأقل\n"
            f"• حرف صغير واحد على الأقل\n"
            f"• رقم واحد على الأقل\n\n"
            f"مثال: `MyPass123`",
            message.chat.id,
            checking_msg.message_id,
            parse_mode="Markdown"
        )
        
        bot.register_next_step_handler_by_chat_id(
            message.chat.id, 
            lambda msg: process_password_step(bot, msg, telegram_id, username)
        )
        
    except ValueError as e:
        bot.send_message(
            message.chat.id,
            f"❌ **خطأ:** {str(e)}\n\n"
            f"يرجى:\n"
            f"1. اختيار اسم مختلف\n"
            f"2. استخدام /start للمحاولة مرة أخرى\n"
            f"3. تجربة اسم أبسط مثل `user{random.randint(1000, 9999)}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"❌ **حدث خطأ غير متوقع:** {str(e)}\n\n"
            f"يرجى المحاولة مرة أخرى لاحقاً.",
            parse_mode="Markdown"
        )

def process_password_step(bot, message, telegram_id, username):
    password = message.text.strip()
    
    # التحقق من قوة كلمة المرور
    errors = []
    
    if len(password) < 8:
        errors.append("❌ كلمة المرور قصيرة جداً (8 أحرف على الأقل)")
    
    if not any(c.isupper() for c in password):
        errors.append("❌ يجب أن تحتوي على حرف كبير واحد على الأقل")
    
    if not any(c.islower() for c in password):
        errors.append("❌ يجب أن تحتوي على حرف صغير واحد على الأقل")
    
    if not any(c.isdigit() for c in password):
        errors.append("❌ يجب أن تحتوي على رقم واحد على الأقل")
    
    if errors:
        error_msg = "\n".join(errors)
        bot.send_message(
            message.chat.id,
            f"{error_msg}\n\n"
            f"🔐 **أعد إرسال كلمة مرور أقوى:**\n"
            f"مثال: `SecurePass123`",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler_by_chat_id(
            message.chat.id,
            lambda msg: process_password_step(bot, msg, telegram_id, username)
        )
        return
    
    try:
        # عرض رسالة "جاري الإنشاء"
        creating_msg = bot.send_message(message.chat.id, "⚙️ **جاري إنشاء الحساب...**")
        
        # إنشاء البريد الإلكتروني
        email = f"{username.lower()}@player.ichancy.com"
        
        # إنشاء الحساب في iChancy
        status, data, player_id, email_created = api.create_player_with_credentials(username, password)
        
        if status != 200:
            error_msg = "فشل إنشاء الحساب"
            if data and isinstance(data, dict):
                notifications = data.get("notification", [])
                if notifications and isinstance(notifications, list):
                    error_msg = notifications[0].get("content", error_msg)
                elif data.get("error"):
                    error_msg = data.get("error")
            raise ValueError(error_msg)
        
        if not player_id:
            # محاولة الحصول على player_id إذا لم يتم إرجاعه
            player_id = api.get_player_id(username)
            if not player_id:
                raise ValueError("لم يتم إنشاء معرف اللاعب")
        
        # تحديث البريد الإلكتروني إذا تم إنشاء واحد مختلف
        final_email = email_created if email_created else email
        
        # حفظ البيانات في قاعدة البيانات
        success = db.update_player_info(telegram_id, player_id, username, final_email, password)
        
        if not success:
            bot.edit_message_text(
                "⚠️ **تم إنشاء الحساب في iChancy ولكن حدث خطأ في حفظ البيانات المحلية.**\n\n"
                "يرجى التواصل مع الدعم.",
                message.chat.id,
                creating_msg.message_id,
                parse_mode="Markdown"
            )
            return
        
        # إرسال تفاصيل الحساب
        login_instructions = f"""
✅ **تم إنشاء الحساب بنجاح!**

🎮 **بيانات تسجيل الدخول إلى iChancy:**

👤 **اسم المستخدم:** `{username}`
🔐 **كلمة المرور:** `{password}`
📧 **البريد الإلكتروني:** `{final_email}`
🆔 **معرف اللاعب:** `{player_id}`

🔗 **رابط الموقع:** https://www.ichancy.com
🔗 **رابط الدخول المباشر:** https://www.ichancy.com/login

📌 **تعليمات هامة:**
1. استخدم نفس بيانات الدخول أعلاه
2. إذا لم تعمل، جرب تغيير كلمة المرور من أول دخول
3. للتأكد، يمكنك استخدام "نسيت كلمة المرور"

💾 **احفظ هذه البيانات في مكان آمن!**
        """
        
        bot.edit_message_text(
            login_instructions,
            message.chat.id,
            creating_msg.message_id,
            parse_mode="Markdown"
        )
        
        # إرسال نسخة مبسطة للنسخ
        bot.send_message(
            message.chat.id,
            f"📋 **نسخة للنسخ:**\n\n"
            f"المستخدم: {username}\n"
            f"كلمة المرور: {password}\n"
            f"الإيميل: {final_email}\n"
            f"الموقع: ichancy.com",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        error_message = str(e)
        bot.send_message(
            message.chat.id,
            f"❌ **فشل إنشاء الحساب:**\n\n{error_message}\n\n"
            f"يرجى:\n"
            f"1. المحاولة مرة أخرى باستخدام /start\n"
            f"2. تجربة اسم وكلمة مرور مختلفين\n"
            f"3. التواصل مع الدعم إذا تكررت المشكلة",
            parse_mode="Markdown"
    )
