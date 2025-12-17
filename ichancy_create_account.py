import random
import string
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from ichancy_api import IChancyAPI
import db

# =========================
# تهيئة API
# =========================
api = IChancyAPI()

# =========================
# تخزين مؤقت لخطوات الإنشاء
# =========================
create_sessions = {}

# =========================
# توليد اسم مستخدم عشوائي إذا كان الاسم غير متاح
# =========================
def make_username_available(base_username):
    """تحقق من الاسم وإضافة أرقام عشوائية إذا لم يكن متاح"""
    username = f"ZEUS_{base_username}"
    attempt = 0
    while not api.check_username_available(username) and attempt < 10:
        suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=3))
        username = f"ZEUS_{base_username}_{suffix}"
        attempt += 1
    return username

# =========================
# بدء إنشاء الحساب
# =========================
def start_create_account(bot, call):
    user_id = call.from_user.id

    # منع إعادة الإنشاء إذا الحساب موجود مسبقاً
    user = db.get_user(user_id)
    if user and user.get("player_id"):
        bot.answer_callback_query(call.id, "⚠️ لديك حساب مسبقًا")
        return

    create_sessions[user_id] = {}

    msg = bot.edit_message_text(
        "📝 **أرسل اسم المستخدم المطلوب**\n"
        "- إنجليزي فقط\n"
        "- 4 أحرف على الأقل",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown"
    )

    bot.register_next_step_handler_by_chat_id(
        call.message.chat.id,
        process_username,
        bot
    )

# =========================
# استقبال اسم المستخدم
# =========================
def process_username(message, bot):
    user_id = message.from_user.id
    base_username = message.text.strip()

    if not base_username.isascii() or len(base_username) < 4:
        bot.send_message(
            message.chat.id,
            "❌ اسم المستخدم غير صالح\nأرسل اسمًا إنجليزيًا (4 أحرف على الأقل)"
        )
        return bot.register_next_step_handler(message, process_username, bot)

    # توليد اسم المستخدم النهائي مع ZEUS_ والتحقق من التوافر
    final_username = make_username_available(base_username)
    create_sessions[user_id]["username"] = final_username

    bot.send_message(
        message.chat.id,
        f"✅ الاسم النهائي للحساب: `{final_username}`",
        parse_mode="Markdown"
    )

    msg = bot.send_message(
        message.chat.id,
        "🔐 **أرسل كلمة المرور**\n(8 أحرف على الأقل)",
        parse_mode="Markdown"
    )

    bot.register_next_step_handler(msg, process_password, bot)

# =========================
# استقبال كلمة المرور
# =========================
def process_password(message, bot):
    user_id = message.from_user.id
    password = message.text.strip()

    if len(password) < 8:
        bot.send_message(
            message.chat.id,
            "❌ كلمة المرور ضعيفة\nأرسل كلمة مرور من 8 أحرف على الأقل"
        )
        return bot.register_next_step_handler(message, process_password, bot)

    session = create_sessions.get(user_id)
    if not session:
        bot.send_message(message.chat.id, "❌ انتهت الجلسة، أعد المحاولة")
        return

    session["password"] = password

    bot.send_message(message.chat.id, "⏳ جاري إنشاء الحساب...")

    # إنشاء الحساب في موقع iChancy
    status, data, player_id, email = api.create_player_with_credentials(
        session["username"],
        session["password"]
    )

    if status == 200 and player_id:
        # حفظ البيانات في قاعدة البيانات
        db.update_player_info(
            telegram_id=user_id,
            player_id=player_id,
            player_username=session["username"],
            player_email=email,
            player_password=session["password"]
        )

        bot.send_message(
            message.chat.id,
            f"""
✅ **تم إنشاء حساب iChancy بنجاح**
━━━━━━━━━━━━━━
👤 المستخدم: `{session['username']}`
🔐 كلمة المرور: `{session['password']}`
📧 الإيميل: `{email}`
🆔 ID: `{player_id}`
━━━━━━━━━━━━━━
""",
            parse_mode="Markdown"
        )

    else:
        error = data.get("notification", [{}])[0].get("content", "فشل إنشاء الحساب")
        bot.send_message(message.chat.id, f"❌ {error}")

    # مسح الجلسة المؤقتة
    create_sessions.pop(user_id, None)
