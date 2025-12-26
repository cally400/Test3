import os
from flask import Flask, request
from main import bot

app = Flask(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN غير موجود")

if not WEBHOOK_URL:
    raise RuntimeError("❌ WEBHOOK_URL غير موجود")

# =========================
# إعداد Webhook مرة واحدة
# =========================
def setup_webhook():
    url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    bot.remove_webhook()
    bot.set_webhook(url)
    print(f"✅ Webhook set to: {url}")

setup_webhook()

# =========================
# استقبال التحديثات
# =========================
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    bot.process_new_updates([bot.types.Update.de_json(data)])
    return "OK", 200

# =========================
# فحص السيرفر
# =========================
@app.route("/")
def index():
    return "Bot is running ✅", 200

