from ichancy_api import IChancyAPI
import telebot
from telebot import types
import os
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# تهيئة API
api = IChancyAPI()

# تهيئة بوت التليجرام
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

# قاموس لحفظ البيانات المؤقتة
user_data = {}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("إنشاء حساب", callback_data="create_account"),
        InlineKeyboardButton("حسابي", callback_data="my_account"),
        InlineKeyboardButton("سحب رصيد", callback_data="withdraw"),
        InlineKeyboardButton("إضافة رصيد", callback_data="deposit"),
        InlineKeyboardButton("رصيد اللاعب", callback_data="check_balance")  # جديد
    )
    
    bot.send_message(
        message.chat.id,
        "مرحباً بك في بوت iChancy\nاختر أحد الخيارات:",
        reply_markup=markup
    )

# ... [الكود الحالي لإنشاء الحساب يبقى كما هو] ...

@bot.callback_query_handler(func=lambda call: call.data == "deposit")
def handle_deposit(call):
    """بدء عملية الإيداع"""
    msg = bot.send_message(
        call.message.chat.id,
        "💵 **عملية إيداع رصيد**\n\n"
        "أرسل اسم المستخدم للاعب:"
    )
    bot.register_next_step_handler(msg, process_deposit_username)

def process_deposit_username(message):
    """معالجة اسم المستخدم للإيداع"""
    try:
        username = message.text.strip()
        
        # التحقق من وجود اللاعب
        if not api.check_player_exists(username):
            bot.send_message(
                message.chat.id,
                f"❌ اللاعب '{username}' غير موجود!\n"
                "تأكد من اسم المستخدم وحاول مرة أخرى."
            )
            return send_welcome(message)
        
        # الحصول على معرف اللاعب
        player_id = api.get_player_id(username)
        if not player_id:
            bot.send_message(
                message.chat.id,
                f"❌ تعذر العثور على معرف اللاعب '{username}'"
            )
            return send_welcome(message)
        
        # حفظ البيانات مؤقتاً
        user_data[message.from_user.id] = {
            'action': 'deposit',
            'username': username,
            'player_id': player_id
        }
        
        # طلب المبلغ
        msg = bot.send_message(
            message.chat.id,
            f"👤 اللاعب: {username}\n"
            f"🆔 المعرف: {player_id}\n\n"
            "💰 أرسل المبلغ المطلوب إيداعه:"
        )
        bot.register_next_step_handler(msg, process_deposit_amount)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ: {str(e)}")
        send_welcome(message)

def process_deposit_amount(message):
    """معالجة مبلغ الإيداع"""
    try:
        user_id = message.from_user.id
        
        if user_id not in user_data or user_data[user_id]['action'] != 'deposit':
            raise ValueError("انتهت الجلسة، الرجاء البدء من جديد")
        
        # التحقق من صحة المبلغ
        try:
            amount = float(message.text.strip())
            if amount <= 0:
                raise ValueError("المبلغ يجب أن يكون أكبر من الصفر")
            if amount > 10000:  # حد أقصى (يمكن تغييره)
                raise ValueError("المبلغ كبير جداً، الحد الأقصى 10,000")
        except ValueError:
            raise ValueError("يرجى إدخال مبلغ صحيح (مثال: 100 أو 50.5)")
        
        # تنفيذ الإيداع
        bot.send_message(message.chat.id, "⏳ جاري تنفيذ الإيداع...")
        
        username = user_data[user_id]['username']
        player_id = user_data[user_id]['player_id']
        
        status, data = api.deposit_to_player(player_id, amount)
        
        if status == 200:
            # الحصول على الرصيد الجديد
            _, _, new_balance = api.get_player_balance(player_id)
            
            success_msg = (
                "✅ **تم الإيداع بنجاح**\n"
                "━━━━━━━━━━━━━━\n"
                f"👤 اللاعب: {username}\n"
                f"🆔 المعرف: {player_id}\n"
                f"💰 المبلغ: {amount:.2f} NSP\n"
                f"💳 الرصيد الجديد: {new_balance:.2f} NSP\n"
                f"📅 الوقت: {message.date}\n"
                "━━━━━━━━━━━━━━"
            )
            
            bot.send_message(message.chat.id, success_msg)
            
            # مسح البيانات المؤقتة
            del user_data[user_id]
        else:
            error_msg = data.get("notification", [{}])[0].get("content", "فشل عملية الإيداع")
            raise ValueError(f"فشل الإيداع: {error_msg}")
            
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ {str(e)}")
        send_welcome(message)

@bot.callback_query_handler(func=lambda call: call.data == "withdraw")
def handle_withdraw(call):
    """بدء عملية السحب"""
    msg = bot.send_message(
        call.message.chat.id,
        "💸 **عملية سحب رصيد**\n\n"
        "أرسل اسم المستخدم للاعب:"
    )
    bot.register_next_step_handler(msg, process_withdraw_username)

def process_withdraw_username(message):
    """معالجة اسم المستخدم للسحب"""
    try:
        username = message.text.strip()
        
        # التحقق من وجود اللاعب
        if not api.check_player_exists(username):
            bot.send_message(
                message.chat.id,
                f"❌ اللاعب '{username}' غير موجود!"
            )
            return send_welcome(message)
        
        # الحصول على معرف اللاعب والرصيد الحالي
        player_id = api.get_player_id(username)
        if not player_id:
            bot.send_message(
                message.chat.id,
                f"❌ تعذر العثور على معرف اللاعب"
            )
            return send_welcome(message)
        
        # الحصول على الرصيد الحالي
        _, _, current_balance = api.get_player_balance(player_id)
        
        # حفظ البيانات مؤقتاً
        user_data[message.from_user.id] = {
            'action': 'withdraw',
            'username': username,
            'player_id': player_id,
            'current_balance': current_balance
        }
        
        # طلب المبلغ مع عرض الرصيد الحالي
        msg = bot.send_message(
            message.chat.id,
            f"👤 اللاعب: {username}\n"
            f"🆔 المعرف: {player_id}\n"
            f"💳 الرصيد الحالي: {current_balance:.2f} NSP\n\n"
            "💰 أرسل المبلغ المطلوب سحبه:"
        )
        bot.register_next_step_handler(msg, process_withdraw_amount)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ: {str(e)}")
        send_welcome(message)

def process_withdraw_amount(message):
    """معالجة مبلغ السحب"""
    try:
        user_id = message.from_user.id
        
        if user_id not in user_data or user_data[user_id]['action'] != 'withdraw':
            raise ValueError("انتهت الجلسة، الرجاء البدء من جديد")
        
        # التحقق من صحة المبلغ
        try:
            amount = float(message.text.strip())
            if amount <= 0:
                raise ValueError("المبلغ يجب أن يكون أكبر من الصفر")
            
            # التحقق من أن المبلغ لا يتجاوز الرصيد
            current_balance = user_data[user_id]['current_balance']
            if amount > current_balance:
                raise ValueError(f"المبلغ يتجاوز الرصيد المتاح ({current_balance:.2f} NSP)")
                
        except ValueError as e:
            raise ValueError(str(e))
        
        # تأكيد السحب
        username = user_data[user_id]['username']
        player_id = user_data[user_id]['player_id']
        
        markup = InlineKeyboardMarkup()
        markup.row_width = 2
        markup.add(
            InlineKeyboardButton("✅ نعم، تأكيد السحب", callback_data=f"confirm_withdraw:{amount}"),
            InlineKeyboardButton("❌ إلغاء", callback_data="cancel_withdraw")
        )
        
        bot.send_message(
            message.chat.id,
            f"⚠️ **تأكيد عملية السحب**\n\n"
            f"👤 اللاعب: {username}\n"
            f"💰 المبلغ: {amount:.2f} NSP\n"
            f"💳 الرصيد قبل: {current_balance:.2f} NSP\n"
            f"💳 الرصيد بعد: {(current_balance - amount):.2f} NSP\n\n"
            "هل تريد متابعة عملية السحب؟",
            reply_markup=markup
        )
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ {str(e)}")
        send_welcome(message)

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_withdraw:"))
def confirm_withdraw(call):
    """تأكيد وتنفيذ السحب"""
    try:
        # استخراج المبلغ من callback_data
        amount = float(call.data.split(":")[1])
        user_id = call.from_user.id
        
        if user_id not in user_data or user_data[user_id]['action'] != 'withdraw':
            bot.answer_callback_query(call.id, "انتهت الجلسة")
            return
        
        username = user_data[user_id]['username']
        player_id = user_data[user_id]['player_id']
        current_balance = user_data[user_id]['current_balance']
        
        bot.edit_message_text(
            "⏳ جاري تنفيذ السحب...",
            call.message.chat.id,
            call.message.message_id
        )
        
        # تنفيذ السحب
        status, data = api.withdraw_from_player(player_id, amount)
        
        if status == 200:
            # الحصول على الرصيد الجديد
            _, _, new_balance = api.get_player_balance(player_id)
            
            success_msg = (
                "✅ **تم السحب بنجاح**\n"
                "━━━━━━━━━━━━━━\n"
                f"👤 اللاعب: {username}\n"
                f"🆔 المعرف: {player_id}\n"
                f"💰 المبلغ المسحوب: {amount:.2f} NSP\n"
                f"💳 الرصيد السابق: {current_balance:.2f} NSP\n"
                f"💳 الرصيد الحالي: {new_balance:.2f} NSP\n"
                f"📅 الوقت: {call.message.date}\n"
                "━━━━━━━━━━━━━━"
            )
            
            bot.edit_message_text(
                success_msg,
                call.message.chat.id,
                call.message.message_id
            )
            
            # مسح البيانات المؤقتة
            del user_data[user_id]
        else:
            error_msg = data.get("notification", [{}])[0].get("content", "فشل عملية السحب")
            bot.edit_message_text(
                f"❌ فشل السحب: {error_msg}",
                call.message.chat.id,
                call.message.message_id
            )
            
    except Exception as e:
        bot.edit_message_text(
            f"❌ خطأ: {str(e)}",
            call.message.chat.id,
            call.message.message_id
        )
        send_welcome(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_withdraw")
def cancel_withdraw(call):
    """إلغاء عملية السحب"""
    user_id = call.from_user.id
    if user_id in user_data:
        del user_data[user_id]
    
    bot.edit_message_text(
        "❌ **تم إلغاء عملية السحب**\n\n"
        "العملية ملغاة، يمكنك البدء من جديد.",
        call.message.chat.id,
        call.message.message_id
    )
    send_welcome(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "check_balance")
def handle_check_balance(call):
    """التحقق من رصيد اللاعب"""
    msg = bot.send_message(
        call.message.chat.id,
        "💳 **التحقق من الرصيد**\n\n"
        "أرسل اسم المستخدم للاعب:"
    )
    bot.register_next_step_handler(msg, process_check_balance)

def process_check_balance(message):
    """معالجة طلب التحقق من الرصيد"""
    try:
        username = message.text.strip()
        
        # التحقق من وجود اللاعب
        if not api.check_player_exists(username):
            bot.send_message(
                message.chat.id,
                f"❌ اللاعب '{username}' غير موجود!"
            )
            return send_welcome(message)
        
        # الحصول على معرف اللاعب والرصيد
        player_id = api.get_player_id(username)
        if not player_id:
            bot.send_message(
                message.chat.id,
                f"❌ تعذر العثور على معرف اللاعب"
            )
            return send_welcome(message)
        
        # الحصول على الرصيد
        status, data, balance = api.get_player_balance(player_id)
        
        if status == 200:
            balance_msg = (
                "💳 **رصيد اللاعب**\n"
                "━━━━━━━━━━━━━━\n"
                f"👤 اللاعب: {username}\n"
                f"🆔 المعرف: {player_id}\n"
                f"💰 الرصيد الحالي: {balance:.2f} NSP\n"
                f"📅 وقت الاستعلام: {message.date}\n"
                "━━━━━━━━━━━━━━"
            )
            
            bot.send_message(message.chat.id, balance_msg)
        else:
            error_msg = data.get("notification", [{}])[0].get("content", "فشل جلب الرصيد")
            bot.send_message(message.chat.id, f"❌ {error_msg}")
            
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ: {str(e)}")
    
    send_welcome(message)
