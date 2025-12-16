from ichancy_api import IChancyAPI
import telebot
from telebot import types
import os
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from db import create_user, get_user, change_balance, log_transaction

# تهيئة API
api = IChancyAPI()

# تهيئة بوت التليجرام
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

# قاموس لحفظ البيانات المؤقتة
user_data = {}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    # إنشاء إنلاين كيبورد
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("إنشاء حساب", callback_data="create_account"),
        InlineKeyboardButton("حسابي", callback_data="my_account"),
        InlineKeyboardButton("سحب رصيد", callback_data="withdraw"),
        InlineKeyboardButton("إضافة رصيد", callback_data="deposit")
    )

    bot.send_message(
        message.chat.id,
        "مرحباً بك في بوت iChancy\nاختر أحد الخيارات:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "create_account")
def handle_create_account(call):
    # مسح أي بيانات قديمة
    user_data[call.from_user.id] = {}

    # إرسال رسالة طلب اسم المستخدم
    msg = bot.send_message(
        call.message.chat.id,
        "📝 أرسل اسم المستخدم المطلوب (باللغة الإنجليزية فقط):"
    )

    # تسجيل الخطوة التالية
    bot.register_next_step_handler(msg, process_username_step)

def process_username_step(message):
    try:
        user_id = message.from_user.id
        username = message.text.strip()

        # التحقق من صحة اسم المستخدم
        if not username.isascii() or len(username) < 4:
            raise ValueError("يجب أن يكون اسم المستخدم بالإنجليزية وأن لا يقل عن 4 أحرف")

        # التحقق من عدم تكرار اسم المستخدم
        if api.check_player_exists(username):
            raise ValueError("اسم المستخدم محجوز، الرجاء اختيار اسم آخر")

        # حفظ اسم المستخدم مؤقتاً
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['username'] = username

        # طلب كلمة السر
        msg = bot.send_message(
            message.chat.id,
            "🔐 أرسل كلمة السر المطلوبة (8 أحرف على الأقل):"
        )
        bot.register_next_step_handler(msg, process_password_step)

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ: {str(e)}")
        send_welcome(message)

def process_password_step(message):
    try:
        user_id = message.from_user.id
        password = message.text.strip()

        # التحقق من صحة كلمة السر
        if len(password) < 8:
            raise ValueError("كلمة السر يجب أن تكون 8 أحرف على الأقل")

        # حفظ كلمة السر مؤقتاً
        if user_id not in user_data:
            raise ValueError("انتهت الجلسة، الرجاء البدء من جديد")

        user_data[user_id]['password'] = password

        # إنشاء الحساب
        bot.send_message(message.chat.id, "⏳ جاري إنشاء الحساب...")

        status, data, player_id, email = api.create_player_with_credentials(
            user_data[user_id]['username'],
            user_data[user_id]['password']
        )

        if status == 200:
            # إرسال تفاصيل الحساب
            account_info = f"""
✅ تم إنشاء الحساب بنجاح
━━━━━━━━━━━━━━
👤 اسم المستخدم: {user_data[user_id]['username']}
🔐 كلمة السر: {user_data[user_id]['password']}
📧 الإيميل: {email}
🆔 معرف اللاعب: {player_id}
━━━━━━━━━━━━━━
            """
            bot.send_message(message.chat.id, account_info)

            create_user(
                telegram_id=user_id,
                username=user_data[user_id]['username'],
                player_id=player_id
            )

            # مسح البيانات المؤقتة
            del user_data[user_id]
        else:
            error_msg = data.get("notification", [{}])[0].get("content", "فشل إنشاء الحساب")
            raise ValueError(error_msg)

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ فشل إنشاء الحساب: {str(e)}")
        send_welcome(message)

@bot.callback_query_handler(func=lambda call: call.data == "my_account")
def handle_my_account(call):
    bot.send_message(call.message.chat.id, "⏳ جاري جلب معلومات الحساب...")

@bot.callback_query_handler(func=lambda call: call.data == "withdraw")
def handle_withdraw(call):
    bot.send_message(call.message.chat.id, "⏳ جاري تحضير طلب السحب...")

@bot.callback_query_handler(func=lambda call: call.data == "deposit")
def handle_deposit(call):
    bot.answer_callback_query(call.id)

    user = get_user(call.from_user.id)
    if not user:
        bot.send_message(call.message.chat.id, "❌ لا يوجد حساب مرتبط.")
        return

    msg = bot.send_message(call.message.chat.id, "💰 أرسل مبلغ الإيداع:")
    bot.register_next_step_handler(msg, process_deposit_amount)

def process_deposit_amount(message):
    try:
        telegram_id = message.from_user.id
        amount = float(message.text)

        if amount <= 0:
            raise ValueError("المبلغ يجب أن يكون أكبر من صفر.")

        user = get_user(telegram_id)
        if not user:
            bot.send_message(message.chat.id, "❌ الحساب غير موجود.")
            return

        # تحقق من الرصيد المحلي
        if user["balance"] < amount:
            bot.send_message(message.chat.id, "❌ رصيدك غير كافٍ.")
            return

        # خصم محلي
        change_balance(telegram_id, -amount)

        # تعبئة فعلية في iChancy
        status, _ = api.deposit_to_player(user["player_id"], amount)

        if status == 200:
            log_transaction(telegram_id, user["player_id"], amount, "deposit", "success")
            bot.send_message(message.chat.id, f"✅ تم تعبئة {amount} NSP بنجاح.")
        else:
            # Rollback
            change_balance(telegram_id, amount)
            log_transaction(telegram_id, user["player_id"], amount, "deposit", "failed")
            bot.send_message(message.chat.id, "❌ فشل الإيداع وتمت إعادة الرصيد.")

    except Exception:
        bot.send_message(message.chat.id, "❌ مبلغ غير صالح.")

# if __name__ == "__main__":
#    print("جارِ تشغيل البوت...")
#    bot.polling()

