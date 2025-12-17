from ichancy_api import IChancyAPI
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import db

# =========================
# تهيئة API
# =========================
api = IChancyAPI()

# =========================
# تهيئة البوت
# =========================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN غير موجود")

bot = telebot.TeleBot(TOKEN)

# =========================
# إعدادات القناة
# =========================
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
CHANNEL_INVITE_LINK = os.getenv("CHANNEL_INVITE_LINK")

# =========================
# التحقق من الاشتراك
# =========================
def check_channel_membership(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# =========================
# /start
# =========================
@bot.message_handler(commands=["start"])
def send_welcome(message):
    user_id = message.from_user.id
    user = db.get_user(user_id)

    referral_id = None
    if len(message.text.split()) > 1:
        try:
            referral_id = int(message.text.split()[1])
        except:
            pass

    # مستخدم جديد
    if not user:
        if not check_channel_membership(CHANNEL_ID, user_id):
            show_channel_requirement(message, referral_id)
            return

        show_terms(message, user_id, referral_id)
        return

    # لم يقبل الشروط
    if not user.get("accepted_terms"):
        show_terms(message, user_id)
        return

    # لم يتم توثيق الاشتراك
    if not user.get("joined_channel"):
        if not check_channel_membership(CHANNEL_ID, user_id):
            show_channel_requirement(message)
            return
        db.mark_channel_joined(user_id)

    show_main_menu(message)

# =========================
# رسالة الاشتراك
# =========================
def show_channel_requirement(message, referral_id=None):
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("🔗 انضم للقناة", url=CHANNEL_INVITE_LINK),
        InlineKeyboardButton("✅ تحقق", callback_data=f"check_join:{referral_id}")
    )
    bot.send_message(
        message.chat.id,
        "📢 يجب الاشتراك بالقناة أولاً",
        reply_markup=kb
    )

# =========================
# الشروط
# =========================
def show_terms(message, user_id, referral_id=None):
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ أوافق", callback_data=f"accept_terms:{user_id}:{referral_id}"),
        InlineKeyboardButton("❌ أرفض", callback_data=f"reject_terms:{user_id}")
    )

    bot.send_message(
        message.chat.id,
        "📜 **شروط الخدمة**\n\n- باستخدامك للبوت فأنت توافق على الشروط",
        reply_markup=kb,
        parse_mode="Markdown"
    )

# =========================
# تحقق الاشتراك
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("check_join"))
def handle_check_join(call):
    referral_id = call.data.split(":")[1]
    referral_id = int(referral_id) if referral_id.isdigit() else None

    if check_channel_membership(CHANNEL_ID, call.from_user.id):
        db.mark_channel_joined(call.from_user.id)
        show_terms(call.message, call.from_user.id, referral_id)
        bot.answer_callback_query(call.id, "تم التحقق ✅")
    else:
        bot.answer_callback_query(call.id, "❌ غير مشترك")

# =========================
# قبول الشروط (مهم)
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("accept_terms"))
def handle_accept_terms(call):
    parts = call.data.split(":")
    user_id = int(parts[1])
    referral_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None

    if call.from_user.id != user_id:
        return

    user = db.get_user(user_id)
    is_new_user = False

    if not user:
        db.create_user(
            telegram_id=user_id,
            username=call.from_user.username,
            first_name=call.from_user.first_name,
            last_name=call.from_user.last_name
        )
        is_new_user = True

        if referral_id and referral_id != user_id:
            db.add_referral(referral_id, user_id)

    db.accept_terms(user_id)

    bot.edit_message_text(
        "✅ تم قبول الشروط",
        call.message.chat.id,
        call.message.message_id
    )

    # 🔥 إرسال القائمة فقط إذا كان جديد
    if is_new_user:
        show_main_menu(call.message)

# =========================
# رفض الشروط
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("reject_terms"))
def handle_reject_terms(call):
    bot.send_message(call.message.chat.id, "❌ لا يمكن استخدام البوت بدون قبول الشروط")

# =========================
# القائمة الرئيسية (حسب طلبك)
# =========================
def show_main_menu(message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🎮 I Chancy", callback_data="ichancy"),
        InlineKeyboardButton("💸 سحب رصيد", callback_data="withdraw"),
        InlineKeyboardButton("💰 شحن رصيد", callback_data="deposit"),
        InlineKeyboardButton("👥 نظام الإحالات", callback_data="referrals"),
        InlineKeyboardButton("🎁 كود هدية", callback_data="gift_code"),
        InlineKeyboardButton("💝 إهداء رصيد", callback_data="gift_balance"),
        InlineKeyboardButton("📞 تواصل معنا", callback_data="contact"),
        InlineKeyboardButton("✉️ رسالة للادمن", callback_data="admin_msg"),
        InlineKeyboardButton("📚 الشروحات", callback_data="tutorials"),
        InlineKeyboardButton("📜 السجل", callback_data="transactions"),
        InlineKeyboardButton("📱 IChancy APK", callback_data="apk"),
        InlineKeyboardButton("🛡 VPN", callback_data="vpn"),
        InlineKeyboardButton("📄 الشروط", callback_data="terms"),
        InlineKeyboardButton("🎰 الجاكبوت", callback_data="jackpot")
    )

    bot.send_message(
        message.chat.id,
        "🏠 **القائمة الرئيسية**",
        reply_markup=kb,
        parse_mode="Markdown"
    )

