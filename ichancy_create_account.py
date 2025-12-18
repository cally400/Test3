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
# توليد اسم مستخدم متاح
# =========================
def make_username_available(base_username):
    username = f"ZEUS_{base_username}"
    attempt = 0

    while attempt < 10:
        try:
            if not api.check_player_exists(username):
                return username
        except Exception:
            pass

        suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=3))
        username = f"ZEUS_{base_username}_{suffix}"
        attempt += 1

    return username

# =========================
# بدء إنشاء الحساب
# =========================
def start_create_account(bot, call):
    user_id = call.from_user.id

    # منع التكرار
    user = db.get_user(user_id)
    if user and user.get("player_id"):
        bot.answer_callback_query(call.id, "⚠️ لديك حساب مسبقًا")
        return

    create_sessions[user_id] = {}

    bot.edit_message_text(
        "📝 **أرسل اسم المستخدم المطلوب**\n"
        "- إنجليزي فقط\n"
        "- 4 أحرف على الأقل",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown"
    )

    bot.register_next_step_handler(call.message, process_username, bot)

# =========================
# استقبال اسم المستخدم
# =========================
def process_username(message, bot):
    user_id = message.from_user.id
    base_username = message.text.strip()

    if not base_username.isascii() or len(base_username) < 4:
        msg = bot.send_message(
            message.chat.id,
            "❌ اسم المستخدم غير صالح\nأرسل اسمًا إنجليزيًا (4 أحرف على الأقل)"
        )
        bot.register_next_step_handler(msg, process_username, bot)
        return

    final_username = make_username_available(base_username)

    if user_id not in create_sessions:
        create_sessions[user_id] = {}

    create_sessions[user_id]["username"] = final_username

    bot.send_message(
        message.chat.id,
        f"✅ الاسم النهائي: `{final_username}`",
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
        msg = bot.send_message(
            message.chat.id,
            "❌ كلمة المرور ضعيفة\nأرسل كلمة مرور من 8 أحرف على الأقل"
        )
        bot.register_next_step_handler(msg, process_password, bot)
        return

    session = create_sessions.get(user_id)
    if not session or "username" not in session:
        bot.send_message(message.chat.id, "❌ انتهت الجلسة، أعد المحاولة")
        create_sessions.pop(user_id, None)
        return

    session["password"] = password

    bot.send_message(message.chat.id, "⏳ جاري إنشاء الحساب...")

    try:
        status, data, player_id, email = api.create_player_with_credentials(
            session["username"],
            session["password"]
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ فشل الاتصال بـ iChancy")
        create_sessions.pop(user_id, None)
        return

    if status == 200 and player_id:
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
        error = "فشل إنشاء الحساب"
        if isinstance(data, dict):
            error = data.get("notification", [{}])[0].get("content", error)
        bot.send_message(message.chat.id, f"❌ {error}")

    create_sessions.pop(user_id, None)

