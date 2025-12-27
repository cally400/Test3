# config.py - إعدادات التطبيق
import os
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()

# إعدادات البوت
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
CHANNEL_INVITE_LINK = os.getenv("CHANNEL_INVITE_LINK", "")

# إعدادات iChancy
ICHANCY_USERNAME = os.getenv("AGENT_USERNAME")
ICHANCY_PASSWORD = os.getenv("AGENT_PASSWORD")
ICHANCY_PARENT_ID = os.getenv("PARENT_ID")
ICHANCY_ORIGIN = os.getenv("ICHANCY_ORIGIN", "https://agents.ichancy.com")

# إعدادات Redis
REDIS_URL = os.getenv("REDIS_URL")

# التحقق من الإعدادات المطلوبة
REQUIRED_VARS = ["TELEGRAM_BOT_TOKEN", "AGENT_USERNAME", "AGENT_PASSWORD", "PARENT_ID", "REDIS_URL"]
for var in REQUIRED_VARS:
    if not os.getenv(var):
        raise ValueError(f"❌ المتغير {var} غير موجود في .env")
