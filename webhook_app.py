"""
Telegram Bot Webhook Server for Railway
"""
from flask import Flask, request, jsonify
import telebot
import os
import logging
from threading import Thread
import time

# استيراد البوت من main.py
from main import bot

# =========================
# إعدادات التسجيل
# =========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =========================
# تهيئة Flask
# =========================
app = Flask(__name__)

# =========================
# تحميل الإعدادات
# =========================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN")
SECRET_TOKEN = os.getenv("WEBHOOK_SECRET", TOKEN)  # توكن سري للتحقق
PORT = int(os.getenv("PORT", 8080))

if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN غير موجود في متغيرات البيئة!")

if not WEBHOOK_URL:
    logger.warning("⚠️ RAILWAY_PUBLIC_DOMAIN غير موجود، البوت لن يعمل بشكل صحيح")
    logger.info("ℹ️ يرجى إضافة RAILWAY_PUBLIC_DOMAIN في متغيرات بيئة Railway")

# =========================
# تهيئة البوت
# =========================
bot.token = TOKEN
bot.parse_mode = "Markdown"

# =========================
# إعداد Webhook
# =========================
def setup_webhook():
    """إعداد وتكوين Webhook"""
    if WEBHOOK_URL:
        try:
            webhook_url = f"https://{WEBHOOK_URL}/webhook/{SECRET_TOKEN}"
            logger.info(f"🔗 جاري إعداد Webhook: {webhook_url}")
            
            # إزالة أي Webhook سابق
            bot.remove_webhook()
            time.sleep(1)
            
            # تعيين Webhook جديد
            bot.set_webhook(
                url=webhook_url,
                secret_token=SECRET_TOKEN,
                max_connections=40,
                allowed_updates=["message", "callback_query", "inline_query"]
            )
            
            logger.info("✅ تم تكوين Webhook بنجاح")
            
            # التحقق من Webhook
            webhook_info = bot.get_webhook_info()
            if webhook_info.url:
                logger.info(f"📊 حالة Webhook: {webhook_info.url}")
                logger.info(f"📊 عدد التحديثات المعلقة: {webhook_info.pending_update_count}")
            
        except Exception as e:
            logger.error(f"❌ فشل إعداد Webhook: {e}")
            # يمكنك اختيار تشغيل polling كبديل
            start_polling_backup()
    else:
        logger.warning("⚠️ لا يوجد Webhook URL، تشغيل وضع Polling")
        start_polling_backup()

def start_polling_backup():
    """بديل Polling إذا فشل Webhook"""
    def polling_thread():
        logger.info("🔄 بدء البوت في وضع Polling (وضع النسخ الاحتياطي)")
        try:
            bot.infinity_polling(
                skip_pending=True,
                timeout=30,
                long_polling_timeout=30
            )
        except Exception as e:
            logger.error(f"❌ فشل Polling: {e}")
    
    Thread(target=polling_thread, daemon=True).start()

# =========================
# مسارات Flask
# =========================
@app.route(f'/webhook/<token>', methods=['POST'])
def telegram_webhook(token):
    """معالجة تحديثات Telegram"""
    if token != SECRET_TOKEN:
        logger.warning(f"⛔ محاولة وصول غير مصرح بها: {token}")
        return 'Unauthorized', 401
    
    if request.headers.get('content-type') != 'application/json':
        logger.warning("⛔ نوع محتوى غير مدعوم")
        return 'Bad Request', 400
    
    try:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        
        # معالجة التحديث
        bot.process_new_updates([update])
        
        logger.debug(f"✅ تم معالجة تحديث بنجاح")
        return 'OK', 200
        
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة Webhook: {e}")
        return 'Internal Server Error', 500

@app.route('/')
def index():
    """الصفحة الرئيسية"""
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Telegram Bot - iChancy</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 50px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            .container {
                background: rgba(255, 255, 255, 0.1);
                padding: 30px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
                max-width: 600px;
                margin: 0 auto;
            }
            h1 {
                font-size: 2.5em;
                margin-bottom: 20px;
            }
            .status {
                background: rgba(0, 0, 0, 0.2);
                padding: 15px;
                border-radius: 10px;
                margin: 20px 0;
            }
            .mode {
                font-size: 1.2em;
                font-weight: bold;
                color: #4ade80;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✅ Telegram Bot</h1>
            <p>بوت iChancy يعمل بنجاح على Railway</p>
            
            <div class="status">
                <p>الحالة: <span class="mode">🟢 نشط</span></p>
                <p>الوضع: <strong>{"Webhook" if WEBHOOK_URL else "Polling"}</strong></p>
                <p>البوت: @{(bot.get_me() or {}).get('username', 'غير معروف')}</p>
            </div>
            
            <p>🚀 تم نشر البوت بنجاح وجاهز لاستقبال الرسائل.</p>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health_check():
    """فحص صحة الخدمة"""
    try:
        # محاولة الحصول على معلومات البوت
        bot_info = bot.get_me()
        return jsonify({
            "status": "healthy",
            "service": "telegram-bot",
            "bot": {
                "username": bot_info.username if bot_info else "unknown",
                "id": bot_info.id if bot_info else "unknown"
            },
            "mode": "webhook" if WEBHOOK_URL else "polling",
            "webhook_url": WEBHOOK_URL or "none"
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "mode": "webhook" if WEBHOOK_URL else "polling"
        }), 500

@app.route('/webhook-info')
def webhook_info():
    """معلومات Webhook"""
    try:
        info = bot.get_webhook_info()
        return jsonify({
            "url": info.url,
            "has_custom_certificate": info.has_custom_certificate,
            "pending_update_count": info.pending_update_count,
            "ip_address": info.ip_address,
            "last_error_date": info.last_error_date,
            "last_error_message": info.last_error_message,
            "max_connections": info.max_connections,
            "allowed_updates": info.allowed_updates
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================
# تهيئة التطبيق
# =========================
@app.before_first_request
def initialize():
    """تهيئة التطبيق عند البدء"""
    logger.info("🚀 بدء تهيئة تطبيق Telegram Bot")
    setup_webhook()

# =========================
# نقطة الدخول الرئيسية
# =========================
if __name__ == '__main__':
    logger.info(f"🌐 بدء تشغيل الخادم على المنفذ {PORT}")
    
    # تهيئة Webhook
    setup_webhook()
    
    # تشغيل Flask
    app.run(
        host='0.0.0.0',
        port=PORT,
        debug=False,
        threaded=True
            )
