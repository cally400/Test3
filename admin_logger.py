import requests
import os
from datetime import datetime

ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_CHANNEL_ID = os.getenv("ADMIN_CHANNEL_ID")

def send_admin_log(title: str, message: str):
    if not ADMIN_BOT_TOKEN or not ADMIN_CHANNEL_ID:
        return

    text = f"**{title}**\n\n{message}\n\n🕒 {datetime.now()}"
    url = f"https://api.telegram.org/bot{ADMIN_BOT_TOKEN}/sendMessage"

    try:
        requests.post(url, json={
            "chat_id": ADMIN_CHANNEL_ID,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=5)
    except:
        pass
