from ichancy_api import IChancyAPI
import telebot
from telebot import types
import os
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import db  # قاعدة البيانات

# =========================
# تهيئة API
# =========================
api = IChancyAPI()

# =========================
# تهيئة بوت تيليغرام
# =========================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("🔴 TELEGRAM_BOT_TOKEN غير موجود في متغيرات البيئة!")

bot = telebot.TeleBot(TOKEN)

# =========================
# إعدادات القناة (مهم)
# =========================
CHANNEL_ID = os.getenv("CHANNEL_ID")
CHANNEL_INVITE_LINK = os.getenv("CHANNEL_INVITE_LINK")

if not CHANNEL_ID or not CHANNEL_INVITE_LINK:
    raise ValueError("🔴 CHANNEL_ID و CHANNEL_INVITE_LINK يجب تحديدهما في ENV!")

CHANNEL_ID = int(CHANNEL_ID)

# =========================
# بيانات مؤقتة
# =========================
user_data = {}

# =========================
# التحقق من الاشتراك بالقناة
# =========================
def check_channel_membership(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"⚠️ خطأ في التحقق من العضوية: {e}")
        return False

# =========================
# أمر /start
# =========================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    user = db.get_user(user_id)

    referral_id = None
    if len(message.text.split()) > 1:
        try:
            referral_id = int(message.text.split()[1])
        except ValueError:
            referral_id = None

    # مستخدم جديد
    if not user:
        if not check_channel_membership(CHANNEL_ID, user_id):
            show_channel_requirement(message, referral_id)
            return

        show_terms(message, user_id, username, first_name, last_name, referral_id)
        return

    # لم يقبل الشروط
    if not user.get("accepted_terms", False):
        show_terms(message, user_id, username, first_name, last_name)
        return

    # لم يتم توثيق الاشتراك بعد
    if not user.get("joined_channel", False):
        if not check_channel_membership(CHANNEL_ID, user_id):
            show_channel_requirement(message)
            return
        else:
            db.mark_channel_joined(user_id)

    show_main_menu(message)

# =========================
# رسالة طلب الاشتراك
# =========================
def show_channel_requirement(message, referral_id=None):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("🔗 انضم للقناة", url=CHANNEL_INVITE_LINK),
        InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data=f"check_join:{referral_id}")
    )

    bot.send_message(
        message.chat.id,
        "📢 **مرحباً بك!**\n\n"
        "للاستفادة من خدمات البوت يجب الانضمام إلى القناة الرسمية.\n\n"
        "بعد الانضمام اضغط على زر **تحقق من الاشتراك**.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# =========================
# عرض شروط الخدمة
# =========================
def show_terms(message, user_id, username, first_name, last_name, referral_id=None):
    terms_text = """
📜 **شروط الخدمة**

- باستخدامك للبوت فأنت توافق على الشروط
- المستخدم مسؤول عن حسابه
- يمنع الاستخدام غير القانوني
- نحتفظ بحق إيقاف أي حساب مخالف
"""

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ أوافق", callback_data=f"accept_terms:{user_id}:{referral_id}"),
        InlineKeyboardButton("❌ أرفض", callback_data=f"reject_terms:{user_id}")
    )

    bot.send_message(
        message.chat.id,
        terms_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# =========================
# تحقق من الاشتراك
# =========================
@bot.callback_query_handler(func=lambda call: call.data.startswith("check_join:"))
def handle_check_join(call):
    referral_id = call.data.split(":")[1]
    referral_id = int(referral_id) if referral_id.isdigit() else None

    if check_channel_membership(CHANNEL_ID, call.from_user.id):
        db.mark_channel_joined(call.from_user.id)
        show_terms(
            call.message,
            call.from_user.id,
            call.from_user.username,
            call.from_user.first_name,
            call.from_user.last_name,
            referral_id
        )
        bot.answer_callback_query(call.id, "✅ تم التحقق من اشتراكك")
    else:
        bot.answer_callback_query(call.id, "❌ لم يتم العثور على اشتراكك")

# =========================
# قبول الشروط
# =========================
@bot.callback_query_handler(func=lambda call: call.data.startswith("accept_terms:"))
def handle_accept_terms(call):
    parts = call.data.split(":")
    user_id = int(parts[1])
    referral_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None

    if call.from_user.id != user_id:
        bot.answer_callback_query(call.id, "❌ هذه الرسالة ليست لك")
        return

    if not db.get_user(user_id):
        db.create_user(
            telegram_id=user_id,
            username=call.from_user.username,
            first_name=call.from_user.first_name,
            last_name=call.from_user.last_name
        )

    db.accept_terms(user_id)

    if referral_id and referral_id != user_id:
        db.add_referral(referral_id, user_id)

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="✅ تم قبول الشروط بنجاح\n\nاكتب /start للمتابعة",
        parse_mode="Markdown"
    )

    show_main_menu(call.message)

# =========================
# رفض الشروط
# =========================
@bot.callback_query_handler(func=lambda call: call.data.startswith("reject_terms:"))
def handle_reject_terms(call):
    user_id = int(call.data.split(":")[1])

    if call.from_user.id != user_id:
        return

    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(
        call.message.chat.id,
        "❌ لا يمكنك استخدام البوت بدون قبول الشروط",
        parse_mode="Markdown"
    )

# =========================
# القائمة الرئيسية
# =========================
def show_main_menu(message):
    user = db.get_user(message.from_user.id)
    if not user:
        send_welcome(message)
        return

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("👤 حسابي", callback_data="my_account"),
        InlineKeyboardButton("💰 إيداع", callback_data="deposit"),
        InlineKeyboardButton("💸 سحب", callback_data="withdraw"),
        InlineKeyboardButton("📊 إحالات", callback_data="referrals"),
        InlineKeyboardButton("📜 السجل", callback_data="transactions"),
        InlineKeyboardButton("🔗 رابط الإحالة", callback_data="referral_link"),
        InlineKeyboardButton("🎰 رصيد اللاعب", callback_data="check_balance"),
        InlineKeyboardButton("🆘 الدعم", callback_data="support")
    )

    bot.send_message(
        message.chat.id,
        f"👋 **مرحباً {user['first_name']}**\n\n"
        f"💰 رصيدك: {user['balance']} NSP\n"
        "اختر من القائمة:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

