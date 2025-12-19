import os
import random
import string
import db
from ichancy_api import IChancyAPI

# تهيئة API مع معالجة الأخطاء
try:
    api = IChancyAPI()
    print("✅ IChancyAPI initialized successfully")
except Exception as e:
    print(f"❌ Failed to initialize IChancyAPI: {e}")
    # سنقوم بإنشاء API فاشل للتعامل مع الأخطاء
    class FallbackAPI:
        def __init__(self):
            self.error = str(e)
        
        def check_player_exists(self, username):
            return False
        
        def create_player_with_credentials(self, username, password):
            return 500, {"error": f"API Initialization failed: {self.error}"}, None, None
    
    api = FallbackAPI()

def _random_suffix(length=3):
    """إنشاء لاحق عشوائي"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_username(raw_username: str) -> str:
    """إنشاء اسم مستخدم فريد"""
    base = f"ZEUS_{raw_username}"
    
    # محاولة 3 مرات فقط لتجنب التأخير
    for i in range(3):
        if i == 0:
            username = base
        else:
            username = f"{base}_{_random_suffix(2)}"
        
        try:
            if not api.check_player_exists(username):
                return username
        except:
            # إذا فشل التحقق، نستخدم الاسم مع لاحق عشوائي
            if i == 2:
                return f"{base}_{_random_suffix(4)}"
    
    return f"{base}_{_random_suffix(4)}"

def start_create_account(bot, call):
    """بدء عملية إنشاء حساب"""
    try:
        bot.send_message(
            call.message.chat.id, 
            "📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):"
        )
        bot.register_next_step_handler_by_chat_id(
            call.message.chat.id, 
            lambda msg: process_username_step(bot, msg, call.from_user.id)
        )
    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ خطأ في بدء العملية: {str(e)}"
        )

def process_username_step(bot, message, telegram_id):
    """معالجة اسم المستخدم"""
    try:
        raw_username = message.text.strip()
        
        # تنظيف الاسم
        cleaned = ''.join(c for c in raw_username if c.isalnum() or c in ['_', '-'])
        if not cleaned:
            bot.send_message(message.chat.id, "❌ الاسم غير صالح. يرجى استخدام أحرف إنجليزية وأرقام فقط.")
            return
        
        if len(cleaned) < 3:
            bot.send_message(message.chat.id, "❌ الاسم قصير جداً. يجب أن يكون 3 أحرف على الأقل.")
            return
        
        if len(cleaned) > 15:
            bot.send_message(message.chat.id, "❌ الاسم طويل جداً. يجب ألا يتجاوز 15 حرفاً.")
            return
        
        # إعلام المستخدم بأننا نعمل على توليد اسم
        processing_msg = bot.send_message(
            message.chat.id,
            "⏳ جاري التحقق من الأسماء المتاحة..."
        )
        
        # توليد اسم مستخدم فريد
        username = generate_username(cleaned)
        
        # حذف رسالة المعالجة
        bot.delete_message(message.chat.id, processing_msg.message_id)
        
        # طلب كلمة المرور
        bot.send_message(
            message.chat.id,
            f"✅ **تم اختيار اسم مستخدم لك:**\n\n"
            f"👤 `{username}`\n\n"
            f"🔐 **الآن أرسل كلمة المرور:**\n"
            f"• 8 أحرف على الأقل\n"
            f"• أحرف كبيرة وصغيرة\n"
            f"• أرقام\n\n"
            f"📝 **مثال:** `MyPass123`",
            parse_mode="Markdown"
        )
        
        bot.register_next_step_handler_by_chat_id(
            message.chat.id,
            lambda msg: process_password_step(bot, msg, telegram_id, username)
        )
        
    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"❌ خطأ في معالجة الاسم: {str(e)}\n\n"
            f"يرجى المحاولة مرة أخرى."
        )

def process_password_step(bot, message, telegram_id, username):
    """معالجة كلمة المرور"""
    try:
        password = message.text.strip()
        
        # تحقق بسيط من كلمة المرور
        if len(password) < 6:
            bot.send_message(message.chat.id, "❌ كلمة المرور قصيرة جداً. يجب أن تكون 6 أحرف على الأقل.")
            return
        
        # إعلام المستخدم بأننا نعمل على إنشاء الحساب
        creating_msg = bot.send_message(
            message.chat.id,
            "⏳ جاري إنشاء حسابك... يرجى الانتظار."
        )
        
        # محاولة إنشاء الحساب
        try:
            status, data, player_id, email = api.create_player_with_credentials(username, password)
            
            # حذف رسالة الانتظار
            bot.delete_message(message.chat.id, creating_msg.message_id)
            
            if status == 200 and player_id:
                # حفظ في قاعدة البيانات
                try:
                    db.update_player_info(telegram_id, player_id, username, email, password)
                except Exception as db_error:
                    print(f"Database error: {db_error}")
                    # نواصل حتى إذا فشلت قاعدة البيانات
                
                # إرسال النتيجة
                success_msg = f"""
✅ **تم إنشاء حسابك بنجاح!**

👤 **اسم المستخدم:** `{username}`
🔐 **كلمة المرور:** `{password}`
📧 **البريد الإلكتروني:** `{email}`
🆔 **معرف اللاعب:** `{player_id}`

🔗 **رابط الدخول:** https://www.ichancy.com/login

💡 **نصيحة:** احفظ هذه المعلومات في مكان آمن.
                """
                bot.send_message(message.chat.id, success_msg, parse_mode="Markdown")
                
            else:
                # تحديد رسالة الخطأ
                error_message = "فشل إنشاء الحساب"
                if isinstance(data, dict):
                    if "message" in data:
                        error_message = data["message"]
                    elif "error" in data:
                        error_message = data["error"]
                    elif "raw_response" in data:
                        error_message = "استجابة غير متوقعة من الخادم"
                
                bot.send_message(
                    message.chat.id,
                    f"❌ **{error_message}**\n\n"
                    f"كود الخطأ: {status}\n\n"
                    f"يرجى المحاولة مرة أخرى لاحقاً."
                )
                
        except Exception as api_error:
            bot.delete_message(message.chat.id, creating_msg.message_id)
            bot.send_message(
                message.chat.id,
                f"❌ **خطأ في الاتصال:**\n\n"
                f"{str(api_error)}\n\n"
                f"يرجى المحاولة مرة أخرى لاحقاً."
            )
            
    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"❌ **خطأ غير متوقع:**\n\n{str(e)}"
        )

def get_system_status(bot, call):
    """الحصول على حالة النظام"""
    try:
        # محاولة اختبار الاتصال
        test_status = "❓ غير معروف"
        
        if hasattr(api, '_ensure_login'):
            try:
                api._ensure_login()
                test_status = "✅ نشط"
            except:
                test_status = "❌ غير نشط"
        
        status_msg = f"""
📊 **حالة النظام:**

🔌 **الاتصال بالمنصة:** {test_status}
👤 **API جاهز:** {'✅' if hasattr(api, 'create_player_with_credentials') else '❌'}

📝 **لإنشاء حساب جديد:** /create
ℹ️ **للمساعدة:** /help
        """
        
        bot.send_message(call.message.chat.id, status_msg, parse_mode="Markdown")
        
    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ **خطأ في التحقق من الحالة:**\n{str(e)}"
        )
