# main.py - النسخة المحسنة
import os
import threading
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request, jsonify

import db
from config import BOT_TOKEN, CHANNEL_ID, CHANNEL_INVITE_LINK
from ichancy_api_selenium import IChancySeleniumAPI

# =========================
# إعدادات التسجيل
# =========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =========================
# تهيئة البوت
# =========================
if not BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN غير موجود")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =========================
# تهيئة API
# =========================
ichancy_api = None
api_executor = ThreadPoolExecutor(max_workers=2)

def init_ichancy_api():
    """تهيئة API بشكل متزامن"""
    global ichancy_api
    try:
        logger.info("🚀 تهيئة IChancy API...")
        ichancy_api = IChancySeleniumAPI(headless=True)
        
        # محاولة تسجيل الدخول
        success, _ = ichancy_api.login()
        if success:
            logger.info("✅ تم تهيئة IChancy API بنجاح")
        else:
            logger.warning("⚠️ لم يتمكن API من تسجيل الدخول تلقائياً")
            
    except Exception as e:
        logger.error(f"❌ فشل تهيئة IChancy API: {e}")
        ichancy_api = None

# =========================
# Web server (مهم لـ Railway)
# =========================
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 Bot is running | IChancy Account Creator"

@app.route("/health")
def health_check():
    """فحص صحة النظام"""
    status = {
        "bot": "running",
        "api": "ready" if ichancy_api else "not_ready",
        "redis": "connected" if db.check_redis_connection() else "disconnected"
    }
    return jsonify(status)

@app.route("/webhook", methods=["POST"])
def webhook():
    """للاستخدام المستقبلي مع webhooks"""
    return jsonify({"status": "ok"})

# =========================
# التحقق من الاشتراك
# =========================
def check_channel_membership(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"❌ خطأ في التحقق من العضوية: {e}")
        return False

# =========================
# القائمة الرئيسية
# =========================
def build_main_menu():
    kb = InlineKeyboardMarkup(row_width=2)

    kb.add(InlineKeyboardButton("🎮 IChancy حساب", callback_data="ichancy"))

    kb.row(
        InlineKeyboardButton("💰 شحن رصيد", callback_data="deposit"),
        InlineKeyboardButton("💸 سحب رصيد", callback_data="withdraw")
    )

    kb.add(InlineKeyboardButton("👥 الإحالات", callback_data="referrals"))

    kb.row(
        InlineKeyboardButton("🎁 كود هدية", callback_data="gift_code"),
        InlineKeyboardButton("💝 إهداء رصيد", callback_data="gift_balance")
    )

    kb.row(
        InlineKeyboardButton("📞 تواصل معنا", callback_data="contact"),
        InlineKeyboardButton("✉️ رسالة للإدارة", callback_data="admin_msg")
    )

    kb.row(
        InlineKeyboardButton("📚 الشروحات", callback_data="tutorials"),
        InlineKeyboardButton("📜 السجل", callback_data="transactions")
    )

    kb.add(InlineKeyboardButton("📱 تحميل التطبيق", callback_data="download_app"))

    kb.add(InlineKeyboardButton("📄 الشروط", callback_data="terms"))

    return kb

def show_main_menu(chat_id, message_id=None):
    text = "🏠 **القائمة الرئيسية**\n\nاختر الخدمة التي تريدها:"
    
    if message_id:
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_main_menu()
        )
    else:
        bot.send_message(chat_id, text, reply_markup=build_main_menu())

# =========================
# /start
# =========================
@bot.message_handler(commands=["start", "menu"])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""
    
    logger.info(f"👤 مستخدم جديد: {user_id} - {username}")

    # التحقق من الاشتراك في القناة
    if CHANNEL_ID and CHANNEL_INVITE_LINK:
        if not check_channel_membership(CHANNEL_ID, user_id):
            show_channel_requirement(message)
            return
    
    # التحقق من وجود المستخدم
    user = db.get_user(user_id)
    
    if not user:
        # إنشاء مستخدم جديد
        db.create_user(
            telegram_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name
        )
        logger.info(f"✅ تم إنشاء مستخدم جديد: {user_id}")
    
    # التحقق من قبول الشروط
    if not user or not user.get("accepted_terms"):
        show_terms(message, user_id)
        return
    
    # عرض القائمة الرئيسية
    show_main_menu(message.chat.id)

# =========================
# رسالة الاشتراك
# =========================
def show_channel_requirement(message):
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("🔗 انضم للقناة", url=CHANNEL_INVITE_LINK),
        InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_join")
    )
    
    bot.send_message(
        message.chat.id,
        "📢 **مرحباً!**\n\n"
        "للبدء في استخدام البوت، يجب الانضمام إلى قناتنا أولاً:\n\n"
        "✅ اشترك في القناة\n"
        "✅ اضغط على زر 'تحقق من الاشتراك'",
        reply_markup=kb
    )

# =========================
# الشروط
# =========================
def show_terms(message, user_id):
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ أوافق على الشروط", callback_data=f"accept_terms:{user_id}"),
        InlineKeyboardButton("❌ لا أوافق", callback_data=f"reject_terms:{user_id}")
    )

    terms_text = """
📜 **شروط وأحكام استخدام البوت**

باستخدامك لهذا البوت، فإنك توافق على الشروط التالية:

1. **الغرض:** البوت مخصص لإنشاء حسابات iChancy فقط.
2. **المسؤولية:** أنت المسؤول عن حساباتك ومدفوعاتك.
3. **الاستخدام:** يجب استخدام البوت بطريقة قانونية وأخلاقية.
4. **الحظر:** يحق للإدارة حظر أي مستخدم يخالف الشروط.
5. **التغييرات:** قد تتغير الشروط دون إشعار مسبق.

بالنقر على "أوافق" فإنك تقر بأنك قد قرأت وفهمت هذه الشروط.
    """

    bot.send_message(message.chat.id, terms_text, reply_markup=kb)

# =========================
# تحقق الاشتراك
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def handle_check_join(call):
    if check_channel_membership(CHANNEL_ID, call.from_user.id):
        db.mark_channel_joined(call.from_user.id)
        bot.answer_callback_query(call.id, "✅ تم التحقق من الاشتراك!")
        
        # الانتقال إلى الشروط
        show_terms(call.message, call.from_user.id)
        
    else:
        bot.answer_callback_query(
            call.id, 
            "❌ لم نراك في القناة بعد!\nانضم أولاً ثم اضغط على الزر مرة أخرى.",
            show_alert=True
        )

# =========================
# قبول الشروط
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("accept_terms"))
def handle_accept_terms(call):
    try:
        user_id = int(call.data.split(":")[1])
        
        if call.from_user.id != user_id:
            bot.answer_callback_query(call.id, "❌ هذا الزر ليس لك!")
            return
        
        # قبول الشروط
        db.accept_terms(user_id)
        
        bot.edit_message_text(
            "✅ **تم قبول الشروط بنجاح!**\n\n"
            "يمكنك الآن استخدام جميع ميزات البوت.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        
        # عرض القائمة الرئيسية بعد ثانيتين
        bot.answer_callback_query(call.id, "تم قبول الشروط!")
        threading.Timer(2, lambda: show_main_menu(call.message.chat.id)).start()
        
    except Exception as e:
        logger.error(f"❌ خطأ في قبول الشروط: {e}")
        bot.answer_callback_query(call.id, "❌ حدث خطأ!")

# =========================
# رفض الشروط
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("reject_terms"))
def handle_reject_terms(call):
    bot.answer_callback_query(
        call.id,
        "❌ لا يمكنك استخدام البوت بدون قبول الشروط.\n\n"
        "إذا غيرت رأيك، استخدم /start مرة أخرى.",
        show_alert=True
    )

# =========================
# IChancy Menu
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "ichancy")
def handle_ichancy(call):
    user = db.get_user(call.from_user.id)

    if not user:
        bot.answer_callback_query(call.id, "❌ المستخدم غير موجود!")
        return

    has_account = all([
        user.get("player_id"),
        user.get("player_email"),
        user.get("player_username"),
        user.get("player_password")
    ])

    keyboard = InlineKeyboardMarkup(row_width=1)

    if has_account:
        text = "🎮 **حساب iChancy**\n\n✅ تم العثور على حسابك:\n\n"
        text += f"👤 **المستخدم:** `{user.get('player_username')}`\n"
        text += f"📧 **الإيميل:** `{user.get('player_email')}`\n"
        text += f"🆔 **المعرف:** `{user.get('player_id')}`\n\n"
        text += "اختر الخدمة التي تريدها:"
        
        keyboard.add(
            InlineKeyboardButton("➕ إنشاء حساب آخر", callback_data="ichancy_create"),
            InlineKeyboardButton("💰 شحن للحساب", callback_data="ichancy_deposit"),
            InlineKeyboardButton("💸 سحب من الحساب", callback_data="ichancy_withdraw"),
            InlineKeyboardButton("🔄 تحديث بيانات الحساب", callback_data="refresh_account")
        )
    else:
        text = "🎮 **حساب iChancy**\n\n❌ لا يوجد لديك حساب بعد.\n\n"
        text += "يمكنك إنشاء حساب جديد مجاناً:"
        
        keyboard.add(
            InlineKeyboardButton("➕ إنشاء حساب جديد", callback_data="ichancy_create"),
            InlineKeyboardButton("❓ كيف يعمل؟", callback_data="ichancy_help")
        )

    keyboard.add(InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))

    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

    bot.answer_callback_query(call.id)

# =========================
# إنشاء حساب IChancy
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "ichancy_create")
def handle_ichancy_create(call):
    # عرض رسالة الانتظار
    processing_msg = bot.send_message(
        call.message.chat.id,
        "⏳ **جاري إعداد نظام إنشاء الحساب...**\n\n"
        "قد يستغرق هذا بضع ثوانٍ."
    )
    
    try:
        # استيراد وتشغيل وظيفة إنشاء الحساب
        from ichancy_create_account import start_create_account
        start_create_account(bot, call)
        
    except Exception as e:
        logger.error(f"❌ خطأ في إنشاء الحساب: {e}")
        bot.edit_message_text(
            f"❌ **حدث خطأ:**\n\n{str(e)}\n\n"
            "يرجى المحاولة مرة أخرى لاحقاً.",
            chat_id=call.message.chat.id,
            message_id=processing_msg.message_id
        )

# =========================
# تحديث بيانات الحساب
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "refresh_account")
def handle_refresh_account(call):
    user = db.get_user(call.from_user.id)
    
    if not user or not user.get("player_username"):
        bot.answer_callback_query(call.id, "❌ لا يوجد حساب لتحديثه!")
        return
    
    bot.answer_callback_query(call.id, "⏳ جاري تحديث البيانات...")
    
    # هنا يمكنك إضافة منطق تحديث بيانات الحساب من iChancy
    bot.send_message(
        call.message.chat.id,
        f"🔄 **تحديث البيانات**\n\n"
        f"سيتم إضافة هذه الميزة قريباً.\n\n"
        f"حسابك الحالي:\n"
        f"👤 المستخدم: `{user.get('player_username')}`"
    )

# =========================
# رجوع للقائمة الرئيسية
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "back_main")
def handle_back_main(call):
    show_main_menu(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)

# =========================
# باقي الأزرار
# =========================
@bot.callback_query_handler(func=lambda c: c.data in ["deposit", "withdraw", "referrals", "gift_code", "gift_balance", "contact", "admin_msg", "tutorials", "transactions", "download_app", "terms"])
def handle_other_buttons(call):
    button_texts = {
        "deposit": "💰 **شحن الرصيد**\n\nهذه الميزة قيد التطوير.",
        "withdraw": "💸 **سحب الرصيد**\n\nهذه الميزة قيد التطوير.",
        "referrals": "👥 **نظام الإحالات**\n\nهذه الميزة قيد التطوير.",
        "gift_code": "🎁 **كود الهدية**\n\nهذه الميزة قيد التطوير.",
        "gift_balance": "💝 **إهداء الرصيد**\n\nهذه الميزة قيد التطوير.",
        "contact": "📞 **تواصل معنا**\n\nللتواصل: @YourSupportUsername",
        "admin_msg": "✉️ **رسالة للإدارة**\n\nأرسل رسالتك هنا.",
        "tutorials": "📚 **الشروحات**\n\nسيتم إضافة الشروحات قريباً.",
        "transactions": "📜 **سجل المعاملات**\n\nهذه الميزة قيد التطوير.",
        "download_app": "📱 **تحميل التطبيق**\n\nرابط التطبيق: https://www.ichancy.com/app",
        "terms": "📄 **الشروط والأحكام**\n\nأنت قد وافقت على الشروط مسبقاً."
    }
    
    text = button_texts.get(call.data, "هذه الميزة قيد التطوير.")
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 رجوع", callback_data="ichancy"))
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb
    )
    
    bot.answer_callback_query(call.id)

# =========================
# معالج الأخطاء
# =========================
@bot.callback_query_handler(func=lambda call: True)
def handle_unknown_callback(call):
    bot.answer_callback_query(call.id, "❌ هذا الزر غير معروف!")

# =========================
# تشغيل البوت
# =========================
def run_bot():
    """تشغيل البوت في thread منفصل"""
    try:
        logger.info("🚀 بدء تشغيل البوت...")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        logger.error(f"❌ خطأ في تشغيل البوت: {e}")

def run_flask():
    """تشغيل Flask في thread منفصل"""
    port = int(os.environ.get("PORT", 3000))
    logger.info(f"🌐 بدء تشغيل خادم الويب على المنفذ {port}")
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    # تهيئة API في الخلفية
    threading.Thread(target=init_ichancy_api, daemon=True).start()
    
    # بدء تشغيل Flask
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # بدء تشغيل البوت
    run_bot()
