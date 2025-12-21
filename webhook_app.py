# webhook_app.py
from flask import Flask, request, jsonify
import telebot
import os
from main import bot  # استيراد البوت من main.py

app = Flask(__name__)

# =========================
# تهيئة التوكن
# =========================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN غير موجود!")

bot.token = TOKEN

# =========================
# إعداد Webhook
# =========================
WEBHOOK_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
if not WEBHOOK_URL:
    raise ValueError("❌ RAILWAY_PUBLIC_DOMAIN غير موجود!")

bot.remove_webhook()
bot.set_webhook(url=f"https://{WEBHOOK_URL}/webhook/{TOKEN}")
print(f"✅ Webhook مضبوط على: https://{WEBHOOK_URL}/webhook/{TOKEN}")

# =========================
# مسار Webhook
# =========================
@app.route(f'/webhook/<token>', methods=['POST'])
def telegram_webhook(token):
    if token != TOKEN:
        return 'Unauthorized', 401

    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        try:
            bot.process_new_updates([update])
        except Exception as e:
            print("❌ خطأ أثناء معالجة التحديث:", e)
        return 'OK', 200

    return 'Bad Request', 400

# =========================
# صفحة رئيسية
# =========================
@app.route('/')
def index():
    return "✅ Telegram Bot is Running on Railway!"

# =========================
# Health Check
# =========================
@app.route('/health')
def health_check():
    return jsonify({"status": "healthy", "service": "telegram-bot"})

