import os
from flask import Flask, request
from telebot import types
from main import bot

app = Flask(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing")

if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL is missing")

# =========================
# إعداد Webhook مرة واحدة
# =========================
def setup_webhook():
    url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    bot.remove_webhook()
    success = bot.set_webhook(url)
    print("Webhook set:", success)

setup_webhook()

# =========================
# استقبال التحديثات
# =========================
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_data = request.get_json(force=True)
    update = types.Update.de_json(json_data)
    bot.process_new_updates([update])
    return "OK", 200

# =========================
# اختبار
# =========================
@app.route("/")
def index():
    return "Bot is running", 200

