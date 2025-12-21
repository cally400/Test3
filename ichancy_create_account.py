        )import os
import random
import string
import db
import time
from datetime import datetime
from ichancy_api import IChancyAPI

# إنشاء مثول API واحد فقط (Singleton)
api_instance = None

def get_api():
    """الحصول على مثول واحد من API"""
    global api_instance
    if api_instance is None:
        api_instance = IChancyAPI()
    return api_instance

def _random_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_username(raw_username: str) -> str:
    """إنشاء اسم مستخدم فريد"""
    api = get_api()
    
    # تنظيف الاسم
    clean_name = ''.join(c for c in raw_username if c.isalnum() or c in ['_', '-'])
    if not clean_name or len(clean_name) < 2:
        clean_name = "user"
    
    base = clean_name.lower()
    
    for i in range(8):
        if i == 0:
            username = base
        elif i < 5:
            username = f"{base}_{_random_suffix(3)}"
        else:
            username = f"{base}_{i:02d}"
        
        try:
            if not api.check_player_exists(username):
                return username
            time.sleep(0.1)  # تأخير بسيط بين المحاولات
        except Exception:
            continue
    
    # اسم عشوائي إذا فشلت جميع المحاولات
    return f"user_{int(time.time())}_{_random_suffix(4)}"

def start_create_account(bot, call):
    """بدء إنشاء حساب مع تجديد الجلسة"""
    chat_id = call.message.chat.id
    api = get_api()
    
    try:
        # إرسال رسالة تحميل
        msg = bot.send_message(chat_id, "🔄 **جاري الاتصال بالنظام...**", parse_mode="Markdown")
        
        try:
            # محاولة تسجيل الدخول
            success = api.ensure_login()
            
            if success:
                bot.edit_message_text(
                    "✅ **تم الاتصال بنجاح!**\n\n"
                    "📝 **أرسل اسم المستخدم المطلوب:**\n"
                    "(بالإنجليزية، بدون مسافات، 3 أحرف على الأقل)",
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    parse_mode="Markdown"
                )
                
                bot.register_next_step_handler_by_chat_id(
                    chat_id, 
                    lambda message: process_username_step(bot, message, call.from_user.id, msg.message_id)
                )
            else:
                bot.edit_message_text(
                    "❌ **فشل الاتصال بالنظام**\n\n"
                    "يرجى المحاولة مرة أخرى بعد قليل.",
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    parse_mode="Markdown"
                )
                
        except Exception as login_error:
            error_msg = str(login_error)
            
            # معالجة خاصة لـ Duplicate login
            if "duplicate" in error_msg.lower() or "already" in error_msg.lower():
                bot.edit_message_text(
                    "⚠️ **الجلسة نشطة بالفعل**\n\n"
                    "📝 **أرسل اسم المستخدم المطلوب:**\n"
                    "(بالإنجليزية، بدون مسافات، 3 أحرف على الأقل)",
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    parse_mode="Markdown"
                )
                
                bot.register_next_step_handler_by_chat_id(
                    chat_id, 
                    lambda message: process_username_step(bot, message, call.from_user.id, msg.message_id)
                )
            else:
                bot.edit_message_text(
                    f"❌ **خطأ في الاتصال:**\n\n{error_msg[:100]}",
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    parse_mode="Markdown"
                )
                
    except Exception as e:
        bot.send_message(
            chat_id,
            f"❌ **حدث خطأ غير متوقع:**\n\n{str(e)[:100]}"
        )

def process_username_step(bot, message, telegram_id, prev_msg_id):
    """معالجة اسم المستخدم"""
    raw_username = message.text.strip()
    
    if len(raw_username) < 2:
        bot.send_message(message.chat.id, "❌ الاسم قصير جداً، يجب أن يكون حرفين على الأقل")
        return
    
    try:
        username = generate_username(raw_username)
        
        bot.edit_message_text(
            f"✅ **الاسم المتاح:** `{username}`\n\n"
            "🔐 **أرسل كلمة المرور الآن:**\n"
            "- 8 أحرف على الأقل\n"
            "- أحرف كبيرة وصغيرة\n"
            "- أرقام\n"
            "- مثال: `MyPass123`",
            chat_id=message.chat.id,
            message_id=prev_msg_id,
            parse_mode="Markdown"
        )
        
        bot.register_next_step_handler_by_chat_id(
            message.chat.id, 
            lambda msg: process_password_step(bot, msg, telegram_id, username, prev_msg_id)
        )
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ: {str(e)}")

def process_password_step(bot, message, telegram_id, username, prev_msg_id):
    """معالجة كلمة المرور وإنشاء الحساب"""
    password = message.text.strip()
    api = get_api()
    
    # التحقق الأساسي
    if len(password) < 6:
        bot.send_message(message.chat.id, "❌ كلمة المرور قصيرة جداً")
        return
    
    bot.edit_message_text(
        "🔄 **جاري إنشاء الحساب...**",
        chat_id=message.chat.id,
        message_id=prev_msg_id,
        parse_mode="Markdown"
    )
    
    try:
        # التأكد من الجلسة
        api.ensure_login()
        
        # إنشاء الحساب
        status, data, player_id, email = api.create_player_with_credentials(username, password)
        
        if status != 200:
            error_msg = "خطأ في الشبكة"
            if isinstance(data, dict):
                if 'notification' in data and data['notification']:
                    error_msg = data['notification'][0].get('content', error_msg)
                elif 'error' in data:
                    error_msg = data['error']
            
            bot.edit_message_text(
                f"❌ **{error_msg}**",
                chat_id=message.chat.id,
                message_id=prev_msg_id,
                parse_mode="Markdown"
            )
            return
        
        # إذا لم نحصل على player_id، نحاول مرة أخرى
        if not player_id:
            time.sleep(1)
            player_id = api.get_player_id(username)
        
        # حفظ في قاعدة البيانات
        try:
            db.update_player_info(
                telegram_id, 
                player_id or "N/A", 
                username, 
                email, 
                password
            )
        except Exception as db_error:
            print(f"ملاحظة: خطأ في قاعدة البيانات: {db_error}")
        
        # رسالة النجاح
        success_msg = f"""
✅ **تم إنشاء الحساب بنجاح!**

📋 **البيانات:**
👤 **المستخدم:** `{username}`
🔐 **كلمة المرور:** `{password}`
📧 **الإيميل:** `{email}`
🆔 **المعرف:** `{player_id or 'N/A'}`

🌐 **الدخول:** https://www.ichancy.com/login

💾 **احفظ هذه البيانات في مكان آمن!**
        """
        
        bot.edit_message_text(
            success_msg,
            chat_id=message.chat.id,
            message_id=prev_msg_id,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        error_msg = str(e)
        bot.edit_message_text(
            f"❌ **خطأ:**\n\n{error_msg[:150]}",
            chat_id=message.chat.id,
            message_id=prev_msg_id,
            parse_mode="Markdown"
        )
