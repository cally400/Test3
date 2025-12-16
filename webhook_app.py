from flask import Flask, request, jsonify
import telebot  # هذا سيستورد pyTelegramBotAPI تلقائياً
import os
from main import bot, user_data
from threading import Thread

app = Flask(__name__)

# الحصول على التوكن من متغيرات البيئة
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN غير موجود في متغيرات البيئة!")

bot.token = TOKEN

# إعداد ويب هوك
WEBHOOK_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
if WEBHOOK_URL:
    bot.remove_webhook()
    # Railway يعطي دومين عام، يمكننا استخدامه للويب هوك
    bot.set_webhook(url=f"https://{WEBHOOK_URL}/webhook/{TOKEN}")

@app.route(f'/webhook/<token>', methods=['POST'])
def telegram_webhook(token):
    if token != TOKEN:
        return 'Unauthorized', 401
    
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        
        # معالجة التحديث في ثانٍ منفصل
        Thread(target=process_update, args=(update,)).start()
        
        return 'OK', 200
    return 'Bad Request', 400

def process_update(update):
    bot.process_new_updates([update])

@app.route('/')
def index():
    return "✅ Telegram Bot is Running on Railway!"

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy", "service": "telegram-bot"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
