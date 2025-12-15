from flask import Flask, request, jsonify
import telebot
import os
from main import bot, user_data  # استيراد الكائنات من main.py
from threading import Thread

app = Flask(__name__)

# الحصول التوكن من متغيرات البيئة
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot.token = TOKEN

# تعيين ويب هوك
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
if WEBHOOK_URL:
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}")

@app.route(f'/{TOKEN}', methods=['POST'])
def telegram_webhook():
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
    return "✅ Telegram Bot is Running!"

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy", "service": "telegram-bot"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
