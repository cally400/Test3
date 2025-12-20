import os
import random
import string
import db
import time
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

def show_progress_message(bot, chat_id, message, total_steps=5, delay=0.3):
    """عرض شريط تقدم"""
    progress_msg = bot.send_message(chat_id, f"⏳ {message}")
    
    for i in range(1, total_steps + 1):
        progress_bar = "█" * i + "░" * (total_steps - i)
        percentage = (i / total_steps) * 100
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg.message_id,
                text=f"⏳ {message}\n\n[{progress_bar}] {percentage:.0f}%"
            )
        except:
            pass
        time.sleep(delay)
    
    return progress_msg

def start_create_account(bot, call):
    telegram_id = call.from_user.id
    
    # التحقق من وجود حساب مسبق في قاعدة البيانات
    existing_account = db.get_player_info(telegram_id)
    
    if existing_account:
        # إذا كان لديه حساب مسبق
        username = existing_account.get('username', 'غير معروف')
        player_id = existing_account.get('player_id', 'غير معروف')
        
        message_text = f"""
✅ **لديك حساب مسبق!**

👤 **اسم المستخدم:** `{username}`
🆔 **معرف اللاعب:** `{player_id}`

📋 **خياراتك:**
1. /info - لعرض معلومات حسابك
2. /delete - لحذف حسابك
3. /change_password - لتغيير كلمة المرور

🔗 **رابط تسجيل الدخول:**
https://www.ichancy.com/login
        """
        
        # إرسال الرسالة مع زر خيارات
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        buttons = [
            types.InlineKeyboardButton("📋 معلومات الحساب", callback_data='account_info'),
            types.InlineKeyboardButton("✏️ تغيير كلمة السر", callback_data='change_password'),
            types.InlineKeyboardButton("🗑️ حذف الحساب", callback_data='delete_account'),
            types.InlineKeyboardButton("🔄 إنشاء حساب جديد", callback_data='new_account')
        ]
        
        # ترتيب الأزرار في صفين
        keyboard.add(buttons[0], buttons[1])
        keyboard.add(buttons[2], buttons[3])
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=message_text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
    else:
        # إذا لم يكن لديه حساب مسبق
        new_message_text = "📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):"
        
        # تعديل الرسالة الأصلية
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=new_message_text
        )
        
        # التسجيل للخطوة التالية
        bot.register_next_step_handler_by_chat_id(
            call.message.chat.id, 
            lambda msg: process_username_step(bot, msg, telegram_id)
        )

def process_username_step(bot, message, telegram_id):
    raw_username = message.text.strip()
    # تنظيف الاسم
    raw_username = ''.join(c for c in raw_username if c.isalnum() or c in ['_', '-'])
    
    if len(raw_username) < 3:
        bot.send_message(message.chat.id, "❌ الاسم قصير جداً، يجب أن يكون 3 أحرف على الأقل")
        return
    
    # إظهار شريط التقدم للتحقق من اسم المستخدم
    progress_msg = show_progress_message(
        bot, 
        message.chat.id, 
        "🔍 جارِ التحقق من إسم المستخدم..."
    )
    
    try:
        username = generate_username(raw_username)
        
        # تعديل رسالة التقدم لإظهار النجاح
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            text=f"✅ **تم العثور على اسم متاح!**\n\n👤 **اسم المستخدم:** `{username}`"
        )
        
        # إرسال رسالة طلب كلمة السر
        time.sleep(1)  # تأخير بسيط للقراءة
        bot.send_message(
            message.chat.id, 
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
        # في حالة الخطأ، تعديل رسالة التقدم
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            text=f"❌ **فشل في العثور على اسم متاح**\n\n{str(e)}\n\nيرجى المحاولة مرة أخرى باستخدام /start"
        )

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
    
    # إظهار شريط التقدم لإنشاء الحساب
    progress_msg = show_progress_message(
        bot, 
        message.chat.id, 
        "🚀 جارِ إنشاء الحساب...",
        total_steps=8,
        delay=0.4
    )
    
    try:
        # إنشاء الحساب مع البريد الإلكتروني الصحيح
        email = f"{username.lower()}@player.ichancy.com"
        
        # تحديث رسالة التقدم
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            text="🔄 جارِ التحقق من توفر الاسم..."
        )
        
        # تحقق أولاً إذا كان الحساب موجود بالفعل
        if api.check_player_exists(username):
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=progress_msg.message_id,
                text="❌ هذا الاسم مستخدم بالفعل، يرجى اختيار اسم آخر"
            )
            return
        
        # تحديث رسالة التقدم
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            text="🔄 جارِ إنشاء الحساب في النظام..."
        )
        
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
        
        # تحديث رسالة التقدم
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            text="🔄 جارِ حفظ البيانات في قاعدة البيانات..."
        )
        
        # حفظ البيانات في قاعدة البيانات
        db.update_player_info(telegram_id, player_id, username, email_created or email, password)
        
        # تحديث رسالة التقدم للإكمال
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            text="✅ **تم إنشاء الحساب بنجاح!**\n\nجارِ تجهيز البيانات..."
        )
        
        time.sleep(1)  # تأخير بسيط للقراءة
        
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
        
        # حذف رسالة التقدم القديمة
        bot.delete_message(message.chat.id, progress_msg.message_id)
        
        # إرسال المعلومات
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
        # في حالة الخطأ، تعديل رسالة التقدم
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            text=f"❌ **فشل إنشاء الحساب:**\n\n{str(e)}\n\n"
                 f"يرجى المحاولة مرة أخرى لاحقاً أو التواصل مع الدعم."
        )

# دالة جديدة للتعامل مع الأزرار الجديدة
def handle_account_options(bot, call):
    """التعامل مع أزرار خيارات الحساب"""
    data = call.data
    
    if data == 'account_info':
        telegram_id = call.from_user.id
        account_info = db.get_player_info(telegram_id)
        
        if account_info:
            username = account_info.get('username', 'غير معروف')
            player_id = account_info.get('player_id', 'غير معروف')
            email = account_info.get('email', 'غير معروف')
            
            info_text = f"""
📋 **معلومات حسابك:**

👤 **اسم المستخدم:** `{username}`
🆔 **معرف اللاعب:** `{player_id}`
📧 **البريد الإلكتروني:** `{email}`

🔗 **رابط تسجيل الدخول:**
https://www.ichancy.com/login
            """
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=info_text,
                parse_mode="Markdown"
            )
    
    elif data == 'change_password':
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🔐 أرسل كلمة السر الجديدة:",
            parse_mode="Markdown"
        )
        # هنا يمكنك إضافة منطق تغيير كلمة السر
    
    elif data == 'delete_account':
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="⚠️ هل أنت متأكد من حذف حسابك؟ هذه العملية لا يمكن التراجع عنها.",
            parse_mode="Markdown"
        )
        # هنا يمكنك إضافة منطق حذف الحساب
    
    elif data == 'new_account':
        # إعادة توجيه المستخدم لإنشاء حساب جديد
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="📝 أرسل اسم المستخدم المطلوب (بالإنجليزية فقط، بدون مسافات):"
        )
        bot.register_next_step_handler_by_chat_id(
            call.message.chat.id, 
            lambda msg: process_username_step(bot, msg, call.from_user.id)
        )
