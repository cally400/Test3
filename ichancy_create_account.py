# ichancy_create_account.py - الإصدار المتكامل
import os
import random
import string
import time
import logging
import db
from ichancy_api_selenium import IChancySeleniumAPI

# إعدادات التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API instance
api = None

def get_api():
    """الحصول على نسخة من API"""
    global api
    if api is None:
        logger.info("🚀 تهيئة IChancy API...")
        api = IChancySeleniumAPI(headless=True)
        try:
            success, _ = api.login()
            if success:
                logger.info("✅ تم تسجيل الدخول إلى API")
            else:
                logger.warning("⚠️ فشل تسجيل الدخول التلقائي")
        except Exception as e:
            logger.error(f"❌ خطأ في تهيئة API: {e}")
    return api

def generate_username(raw_username: str) -> str:
    """إنشاء اسم مستخدم فريد"""
    # تنظيف الاسم
    clean_name = ''.join(c for c in raw_username if c.isalnum() or c == '_')
    clean_name = clean_name[:15]
    
    if len(clean_name) < 3:
        clean_name = clean_name + str(random.randint(100, 999))
    
    # اقتراحات أسماء
    prefixes = ['PLAYER', 'USER', 'AGENT', 'GAMER']
    timestamp = int(time.time()) % 10000
    
    attempts = [
        f"{clean_name}_{timestamp:04d}",
        f"{random.choice(prefixes)}_{clean_name}",
        f"{clean_name}_{random.randint(1000, 9999)}",
        f"IC_{clean_name}_{random.randint(100, 999)}"
    ]
    
    api_instance = get_api()
    
    for username in attempts:
        try:
            exists, extra_data = api_instance.check_player_exists(username)
            
            # تخطي إذا كان هناك خطأ
            if extra_data and 'error' in extra_data:
                logger.warning(f"⚠️ خطأ في التحقق من {username}: {extra_data.get('error')}")
                continue
                
            if not exists:
                logger.info(f"✅ اسم متاح: {username}")
                return username
                
        except Exception as e:
            logger.error(f"❌ استثناء في التحقق من {username}: {str(e)[:100]}")
            time.sleep(1)
            continue
    
    # إذا فشلت جميع المحاولات
    return f"IC_{clean_name}_{int(time.time())}"

def start_create_account(bot, call):
    """بدء عملية إنشاء حساب"""
    logger.info(f"👤 بدء إنشاء حساب للمستخدم: {call.from_user.id}")
    
    bot.send_message(
        call.message.chat.id,
        "📝 **أرسل اسم المستخدم المطلوب:**\n\n"
        "• استخدم الإنجليزية فقط\n"
        "• بدون مسافات\n"
        "• 3-15 حرف\n"
        "• يمكن استخدام _\n\n"
        "مثال: `john_doe` أو `player123`",
        parse_mode="Markdown"
    )
    
    bot.register_next_step_handler_by_chat_id(
        call.message.chat.id,
        lambda msg: process_username_step(bot, msg, call.from_user.id)
    )

def process_username_step(bot, message, telegram_id):
    """معالجة خطوة اسم المستخدم"""
    raw_username = message.text.strip()
    
    # التحقق الأساسي
    if len(raw_username) < 3:
        bot.send_message(
            message.chat.id,
            "❌ **الاسم قصير جداً**\n\nيجب أن يكون 3 أحرف على الأقل.\n\n"
            "استخدم /start للبدء من جديد."
        )
        return
    
    if not all(c.isalnum() or c == '_' for c in raw_username):
        bot.send_message(
            message.chat.id,
            "❌ **أحرف غير مسموحة**\n\n"
            "استخدم:\n• أحرف إنجليزية\n• أرقام\n• _\n\n"
            "استخدم /start للبدء من جديد."
        )
        return
    
    # إضافة مؤشر الكتابة
    bot.send_chat_action(message.chat.id, 'typing')
    
    try:
        # توليد اسم فريد
        username = generate_username(raw_username)
        
        bot.send_message(
            message.chat.id,
            f"✅ **الاسم المتاح:** `{username}`\n\n"
            f"🔐 **الآن أرسل كلمة المرور:**\n\n"
            f"📌 **المتطلبات:**\n"
            f"• 8 أحرف على الأقل\n"
            f"• أحرف كبيرة وصغيرة\n"
            f"• أرقام\n"
            f"• رموز خاصة (اختياري)\n\n"
            f"💡 **مثال جيد:** `MyPass123!`",
            parse_mode="Markdown"
        )
        
        # تسجيل الخطوة التالية
        bot.register_next_step_handler_by_chat_id(
            message.chat.id,
            lambda msg: process_password_step(bot, msg, telegram_id, username)
        )
        
    except Exception as e:
        logger.error(f"❌ خطأ في توليد الاسم: {e}")
        bot.send_message(
            message.chat.id,
            f"❌ **حدث خطأ:**\n\n{str(e)}\n\n"
            f"يرجى المحاولة مرة أخرى لاحقاً."
        )

def validate_password(password):
    """التحقق من قوة كلمة المرور"""
    if len(password) < 8:
        return False, "❌ كلمة المرور قصيرة جداً (8 أحرف على الأقل)"
    
    if not any(c.isupper() for c in password):
        return False, "❌ أضف حرفاً كبيراً واحداً على الأقل"
    
    if not any(c.islower() for c in password):
        return False, "❌ أضف حرفاً صغيراً واحداً على الأقل"
    
    if not any(c.isdigit() for c in password):
        return False, "❌ أضف رقماً واحداً على الأقل"
    
    return True, "✅ كلمة المرور قوية"

def process_password_step(bot, message, telegram_id, username):
    """معالجة خطوة كلمة المرور"""
    password = message.text.strip()
    
    # التحقق من قوة كلمة المرور
    is_valid, validation_msg = validate_password(password)
    if not is_valid:
        bot.send_message(message.chat.id, validation_msg)
        return
    
    # إضافة مؤشر الكتابة
    bot.send_chat_action(message.chat.id, 'typing')
    
    # إرسال رسالة الانتظار
    processing_msg = bot.send_message(
        message.chat.id,
        "⏳ **جاري إنشاء الحساب...**\n\n"
        "قد يستغرق هذا 30-60 ثانية.\n"
        "يرجى الانتظار..."
    )
    
    try:
        api_instance = get_api()
        
        # التحقق النهائي من وجود اللاعب
        logger.info(f"🔍 التحقق النهائي من: {username}")
        exists, extra_data = api_instance.check_player_exists(username)
        
        if exists:
            bot.edit_message_text(
                f"❌ **الاسم مستخدم بالفعل!**\n\n"
                f"اللاعب `{username}` موجود مسبقاً.\n"
                f"يرجى اختيار اسم آخر.",
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                parse_mode="Markdown"
            )
            return
        
        # إنشاء الحساب
        logger.info(f"👤 إنشاء حساب: {username}")
        status, data, player_id = api_instance.create_player(username, password)
        
        if status != 200:
            error_msg = data.get('error', 'فشل إنشاء الحساب')
            logger.error(f"❌ فشل إنشاء الحساب: {error_msg}")
            
            bot.edit_message_text(
                f"❌ **فشل إنشاء الحساب:**\n\n{error_msg}\n\n"
                f"يرجى المحاولة مرة أخرى لاحقاً.",
                chat_id=message.chat.id,
                message_id=processing_msg.message_id
            )
            return
        
        # حفظ البيانات
        email = f"{username}@player.ichancy.com"
        
        # تحديث بيانات المستخدم في قاعدة البيانات
        db.update_player_info(telegram_id, player_id or "N/A", username, email, password)
        
        # إعداد رسالة النجاح
        success_text = f"""
✅ **تم إنشاء الحساب بنجاح!**

━━━━━━━━━━━━━━━━━━━━
👤 **معلومات الحساب:**

• **اسم المستخدم:** `{username}`
• **كلمة المرور:** `{password}`
• **البريد الإلكتروني:** `{email}`
• **معرف اللاعب:** `{player_id or 'N/A'}`

━━━━━━━━━━━━━━━━━━━━
🔗 **روابط مهمة:**

• تسجيل الدخول: https://www.ichancy.com/login
• تطبيق الهاتف: https://www.ichancy.com/app
• الدعم الفني: https://www.ichancy.com/support

━━━━━━━━━━━━━━━━━━━━
📌 **تعليمات مهمة:**

1. احفظ هذه المعلومات في مكان آمن
2. يمكنك تغيير كلمة المرور بعد أول دخول
3. للاستفسارات، راجع قسم الدعم
4. لا تشارك بيانات الدخول مع أي شخص

⚠️ **تحذير:** البوت غير مسؤول عن أمان حسابك.
━━━━━━━━━━━━━━━━━━━━
🎮 **تمتع باللعب!**
        """
        
        # إرسال الرسالة الرئيسية
        bot.edit_message_text(
            success_text,
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            parse_mode="Markdown"
        )
        
        # إرسال نسخة مبسطة للنسخ
        bot.send_message(
            message.chat.id,
            f"📋 **للنسخ واللصق:**\n\n"
            f"**الموقع:** ichancy.com\n"
            f"**المستخدم:** {username}\n"
            f"**كلمة المرور:** {password}\n"
            f"**الإيميل:** {email}",
            parse_mode="Markdown"
        )
        
        logger.info(f"✅ تم إنشاء حساب بنجاح للمستخدم: {telegram_id}")
        
    except Exception as e:
        logger.error(f"❌ استثناء في إنشاء الحساب: {e}")
        bot.edit_message_text(
            f"❌ **حدث خطأ غير متوقع:**\n\n{str(e)}\n\n"
            f"يرجى المحاولة مرة أخرى لاحقاً أو التواصل مع الدعم.",
            chat_id=message.chat.id,
            message_id=processing_msg.message_id
        )
