# webhook_ap7p.py
import os
from flask import Flask, request
from main import bot

# =========================
# إعداد Flask
# =========================
app = Flask(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("🔴 TELEGRAM_BOT_TOKEN غير موجود في متغيرات البيئة!")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # رابط Webhook الخاص بك، مثال: https://yourapp.up.railway.app
if not WEBHOOK_URL:
    raise ValueError("🔴 WEBHOOK_URL غير موجود في متغيرات البيئة!")

# =========================
# ضبط Webhook
# =========================
@app.before_first_request
def set_webhook():
    url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    success = bot.set_webhook(url)
    if success:
        print(f"✅ Webhook set successfully: {url}")
    else:
        print("❌ Failed to set webhook")


# =========================
# نقطة استقبال الرسائل
# =========================
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_data = request.get_json(force=True)
    bot.process_new_updates([bot.types.Update.de_json(json_data)])
    return "OK", 200


# =========================
# مسار اختبار
# =========================
@app.route("/")
def index():
    return "Bot is running with Webhook!", 200


# =========================
# تشغيل السيرفر
# =========================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
