from ichancy_api import IChancyAPI
import telebot
from telebot import types
import os
import asyncio
import aiohttp
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import db  # استيراد قاعدة البيانات

# تهيئة API
api = IChancyAPI()

# تهيئة بوت التليجرام
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

# إعدادات القناة
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@your_channel_username")
CHANNEL_INVITE_LINK = os.getenv("CHANNEL_INVITE_LINK", "https://t.me/your_channel")

# قاموس لحفظ البيانات المؤقتة
user_data = {}

def check_channel_membership(chat_id, user_id):
    """التحقق من اشتراك المستخدم في القناة"""
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"خطأ في التحقق من العضوية: {e}")
        return False

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    # التحقق من وجود المستخدم في قاعدة البيانات
    user = db.get_user(user_id)
    
    if not user:
        # المستخدم جديد - التحقق من الإحالة
        referral_id = None
        if len(message.text.split()) > 1:
            referral_id = int(message.text.split()[1])
        
        # التحقق من اشتراكه في القناة أولاً
        if not check_channel_membership(CHANNEL_USERNAME, user_id):
            show_channel_requirement(message, referral_id)
            return
        
        # إذا كان مشتركاً - عرض شروط الخدمة
        show_terms(message, user_id, username, first_name, last_name, referral_id)
        return
    
    # المستخدم موجود - التحقق من قبول الشروط
    if not user.get('accepted_terms', False):
        show_terms(message, user_id, username, first_name, last_name)
        return
    
    # التحقق من اشتراكه في القناة
    if not user.get('joined_channel', False):
        if not check_channel_membership(CHANNEL_USERNAME, user_id):
            show_channel_requirement(message)
            return
        else:
            db.mark_channel_joined(user_id)
    
    # عرض القائمة الرئيسية
    show_main_menu(message)

def show_channel_requirement(message, referral_id=None):
    """عرض رسالة طلب الاشتراك في القناة"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("🔗 انضم للقناة", url=CHANNEL_INVITE_LINK),
        InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data=f"check_join:{referral_id}")
    )
    
    bot.send_message(
        message.chat.id,
        "📢 **مرحباً بك!**\n\n"
        "للاستفادة من خدمات البوت، يجب عليك الانضمام إلى قناتنا الرسمية أولاً.\n\n"
        "بعد الانضمام، اضغط على زر 'تحقق من الاشتراك' للمتابعة.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

def show_terms(message, user_id, username, first_name, last_name, referral_id=None):
    """عرض شروط الخدمة"""
    terms_text = """
    📜 **شروط الخدمة**

    **1. قبول الشروط:**
    - باستخدامك للبوت، فإنك توافق على جميع الشروط والأحكام المذكورة أدناه.

    **2. المسؤولية:**
    - المستخدم هو المسؤول الوحيد عن جميع الأنشطة التي تتم عبر حسابه.
    - البوت غير مسؤول عن أي خسائر مالية ناتجة عن سوء استخدام الخدمة.

    **3. الالتزام بالقوانين:**
    - يجب أن يكون عمر المستخدم 18 سنة أو أكثر.
    - يمنع استخدام البوت لأي أغراض غير قانونية.

    **4. الخصوصية:**
    - نحن نحترم خصوصيتك ولا نشارك بياناتك الشخصية مع أطراف ثالثة.
    - يتم تخزين البيانات لأغراض تشغيلية فقط.

    **5. التعديلات:**
    - نحتفظ بحق تعديل هذه الشروط في أي وقت.

    **6. إلغاء الخدمة:**
    - نحتفظ بحق إيقاف الخدمة لأي مستخدم يخالف الشروط.
    """
    
    keyboard = InlineKeyboardMarkup()
    keyboard.row_width = 2
    keyboard.add(
        InlineKeyboardButton("✅ أوافق على الشروط", callback_data=f"accept_terms:{user_id}:{referral_id}"),
        InlineKeyboardButton("❌ أرفض الشروط", callback_data=f"reject_terms:{user_id}")
    )
    
    bot.send_message(
        message.chat.id,
        terms_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_join:"))
def handle_check_join(call):
    """معالجة التحقق من الاشتراك في القناة"""
    try:
        data_parts = call.data.split(":")
        referral_id = data_parts[1] if len(data_parts) > 1 and data_parts[1] != "None" else None
        
        if check_channel_membership(CHANNEL_USERNAME, call.from_user.id):
            # تحديث حالة الاشتراك في قاعدة البيانات
            db.mark_channel_joined(call.from_user.id)
            
            # عرض شروط الخدمة
            show_terms(
                call.message,
                call.from_user.id,
                call.from_user.username,
                call.from_user.first_name,
                call.from_user.last_name,
                referral_id
            )
            
            bot.answer_callback_query(call.id, "✅ تم التحقق من اشتراكك!")
        else:
            bot.answer_callback_query(call.id, "❌ لم يتم العثور على اشتراكك، يرجى الانضمام أولاً")
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ حدث خطأ في التحقق")
        print(f"خطأ في handle_check_join: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("accept_terms:"))
def handle_accept_terms(call):
    """معالجة قبول شروط الخدمة"""
    try:
        data_parts = call.data.split(":")
        user_id = int(data_parts[1])
        referral_id = int(data_parts[2]) if len(data_parts) > 2 and data_parts[2].isdigit() else None
        
        # التحقق من أن المستخدم هو نفسه
        if call.from_user.id != user_id:
            bot.answer_callback_query(call.id, "❌ هذه الرسالة ليست لك!")
            return
        
        # إنشاء حساب المستخدم في قاعدة البيانات
        user_exists = db.get_user(user_id)
        
        if not user_exists:
            db.create_user(
                telegram_id=user_id,
                username=call.from_user.username,
                first_name=call.from_user.first_name,
                last_name=call.from_user.last_name
            )
        
        # قبول الشروط
        db.accept_terms(user_id)
        
        # معالجة الإحالة إذا وجدت
        if referral_id and referral_id != user_id:
            db.add_referral(referral_id, user_id)
        
        # إرسال رسالة التأكيد
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ **لقد وافقت على شروط الخدمة بنجاح!**\n\n"
                 "يمكنك الآن استخدام جميع ميزات البوت.\n"
                 "اضغط /start لعرض القائمة الرئيسية.",
            parse_mode="Markdown"
        )
        
        bot.answer_callback_query(call.id, "✅ تم حفظ موافقتك على الشروط")
        
        # عرض القائمة الرئيسية بعد 2 ثانية
        bot.send_message(call.message.chat.id, "⏳ جاري تحميل القائمة الرئيسية...")
        show_main_menu(call.message)
        
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ حدث خطأ، يرجى المحاولة مرة أخرى")
        print(f"خطأ في handle_accept_terms: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("reject_terms:"))
def handle_reject_terms(call):
    """معالجة رفض شروط الخدمة"""
    try:
        user_id = int(call.data.split(":")[1])
        
        # التحقق من أن المستخدم هو نفسه
        if call.from_user.id != user_id:
            bot.answer_callback_query(call.id, "❌ هذه الرسالة ليست لك!")
            return
        
        # حذف الرسالة
        bot.delete_message(call.message.chat.id, call.message.message_id)
        
        # إرسال رسالة الرفض
        bot.send_message(
            call.message.chat.id,
            "❌ **لقد رفضت شروط الخدمة**\n\n"
            "نأسف لأنك لا تستطيع استخدام خدمات البوت بدون قبول الشروط.\n"
            "إذا غيرت رأيك، يمكنك الضغط على /start في أي وقت.",
            parse_mode="Markdown"
        )
        
        bot.answer_callback_query(call.id, "❌ تم رفض الشروط")
        
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ حدث خطأ")
        print(f"خطأ في handle_reject_terms: {e}")

def show_main_menu(message):
    """عرض القائمة الرئيسية بعد قبول الشروط"""
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    if not user:
        send_welcome(message)
        return
    
    # الحصول على إحصائيات المستخدم
    stats = db.get_user_stats(user_id)
    
    keyboard = InlineKeyboardMarkup()
    keyboard.row_width = 2
    
    # الصف الأول
    keyboard.add(
        InlineKeyboardButton("👤 حسابي", callback_data="my_account"),
        InlineKeyboardButton("💰 إيداع", callback_data="deposit")
    )
    
    # الصف الثاني
    keyboard.add(
        InlineKeyboardButton("💸 سحب", callback_data="withdraw"),
        InlineKeyboardButton("📊 إحالات", callback_data="referrals")
    )
    
    # الصف الثالث
    keyboard.add(
        InlineKeyboardButton("📜 السجل", callback_data="transactions"),
        InlineKeyboardButton("🔗 رابط الإحالة", callback_data="referral_link")
    )
    
    # الصف الرابع (ميزات إضافية)
    keyboard.add(
        InlineKeyboardButton("🎰 رصيد اللاعب", callback_data="check_balance"),
        InlineKeyboardButton("🆘 الدعم", callback_data="support")
    )
    
    welcome_msg = (
        f"👋 **مرحباً {user['first_name']}**\n\n"
        f"💰 **رصيدك:** {user['balance']:.2f} NSP\n"
        f"👥 **إحالاتك:** {user['referrals_count']} (نشطة: {user['active_referrals_count']})\n"
        f"🎁 **رصيد الإحالات:** {user['referral_balance']:.2f} NSP\n\n"
        "📌 **اختر من القائمة:**"
    )
    
    bot.send_message(
        message.chat.id,
        welcome_msg,
        reply_markup=keyboard,
        parse_mode="Markdown"
        )
