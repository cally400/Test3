import os
import random
import string
import db
import time
from datetime import datetime
from ichancy_api import IChancyAPI

api = IChancyAPI()

def _random_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_username(raw_username: str) -> str:
    """إنشاء اسم مستخدم فريد"""
    # تنظيف الاسم
    clean_name = ''.join(c for c in raw_username if c.isalnum() or c in ['_', '-'])
    if not clean_name:
        clean_name = "user"
    
    base = clean_name.lower()
    
    for i in range(10):
        if i == 0:
            username = base
        else:
            username = f"{base}_{_random_suffix(4)}"
        
        try:
            if not api.check_player_exists(username):
                return username
        except Exception:
            continue
    
    # إذا فشلت جميع المحاولات، استخدم اسم عشوائي
    return f"user_{int(time.time())}_{_random_suffix(4)}"

def start_create_account(bot, call):
    """بدء إنشاء حساب مع تجديد الجلسة"""
    chat_id = call.message.chat.id
    
    try:
        # إرسال رسالة تحميل
        msg = bot.send_message(chat_id, "🔄 **جاري الاتصال بالنظام...**", parse_mode="Markdown")
        
        # محاولة تسجيل الدخول
        try:
            success = api.ensure_login()
        except Exception as login_error:
            bot.edit_message_text(
                f"❌ **فشل الاتصال:**\n\n{str(login_error)}\n\n"
                "يرجى المحاولة مرة أخرى بعد قليل.",
                chat_id=chat_id,
                message_id=msg.message_id,
                parse_mode="Markdown"
            )
            return
        
        if success:
            bot.edit_message_text(
                "✅ **تم الاتصال بنجاح!**\n\n"
                "📝 **أرسل اسم المستخدم:**\n"
                "- الإنجليزية فقط\n"
                "- بدون مسافات\n"
                "- مثال: ali123",
                chat_id=chat_id,
                message_id=msg.message_id,
                parse_mode="Markdown"
            )
            
            # تسجيل الخطوة التالية
            bot.register_next_step_handler_by_chat_id(
                chat_id, 
                lambda message: process_username_step(bot, message, call.from_user.id, msg.message_id)
            )
            
    except Exception as e:
        bot.send_message(
            chat_id,
            f"❌ **حدث خطأ:**\n\n{str(e)[:100]}\n\n"
            "يرجى المحاولة مرة أخرى."
        )

def process_username_step(bot, message, telegram_id, prev_msg_id):
    raw_username = message.text.strip()
    
    if len(raw_username) < 2:
        bot.send_message(message.chat.id, "❌ الاسم قصير جداً")
        return
    
    try:
        username = generate_username(raw_username)
        
        bot.edit_message_text(
            f"✅ **الاسم:** `{username}`\n\n"
            "🔐 **أرسل كلمة المرور الآن:**\n"
            "- 8 أحرف على الأقل\n"
            "- أحرف كبيرة وصغيرة\n"
            "- أرقام\n"
            "- مثال: Password123",
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
    password = message.text.strip()
    
    # التحقق الأساسي
    if len(password) < 8:
        bot.send_message(message.chat.id, "❌ كلمة المرور قصيرة")
        return
    
    if not any(c.isupper() for c in password) or not any(c.islower() for c in password):
        bot.send_message(message.chat.id, "❌ يجب أن تحتوي على أحرف كبيرة وصغيرة")
        return
    
    if not any(c.isdigit() for c in password):
        bot.send_message(message.chat.id, "❌ يجب أن تحتوي على أرقام")
        return
    
    # إظهار رسالة التحميل
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
        
        if status != 200 or not data.get("result", False):
            error_msg = "فشل إنشاء الحساب"
            if isinstance(data, dict):
                if 'notification' in data and data['notification']:
                    error_msg = data['notification'][0].get('content', error_msg)
            
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
            db.update_player_info(telegram_id, player_id or "N/A", username, email, password)
        except:
            pass  # تجاهل خطأ قاعدة البيانات
        
        # رسالة النجاح
        success_msg = f"""
✅ **تم الإنشاء بنجاح!**

👤 **المستخدم:** `{username}`
🔐 **كلمة المرور:** `{password}`
📧 **الإيميل:** `{email}`
🆔 **المعرف:** `{player_id or 'N/A'}`

🌐 **الدخول:** https://www.ichancy.com
📅 **التاريخ:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
        """
        
        bot.edit_message_text(
            success_msg,
            chat_id=message.chat.id,
            message_id=prev_msg_id,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        bot.edit_message_text(
            f"❌ **خطأ:**\n\n{str(e)[:150]}",
            chat_id=message.chat.id,
            message_id=prev_msg_id,
            parse_mode="Markdown"
        )
