import json
import os
from datetime import datetime
from ichancy_api import IChancyAPI

COOKIE_FILE = "ichancy_session.json"

api = IChancyAPI()


def load_session():
    """تحميل الجلسة من ملف JSON إذا كانت صالحة"""
    if not os.path.exists(COOKIE_FILE):
        return False

    try:
        with open(COOKIE_FILE, "r") as f:
            data = json.load(f)

        expiry = datetime.fromisoformat(data["expiry"])
        if expiry < datetime.now():
            return False

        api.session_cookies = data["cookies"]
        api.session_expiry = expiry
        api.last_login_time = datetime.fromisoformat(data["last_login"])
        api.is_logged_in = True

        print("✅ تم تحميل الجلسة من الملف")
        return True
    except Exception as e:
        print("❌ فشل تحميل الجلسة:", e)
        return False


def save_session():
    """حفظ الجلسة في ملف JSON"""
    try:
        data = {
            "cookies": api.session_cookies,
            "expiry": api.session_expiry.isoformat(),
            "last_login": api.last_login_time.isoformat(),
        }
        with open(COOKIE_FILE, "w") as f:
            json.dump(data, f)

        print("💾 تم حفظ الجلسة في الملف")
    except Exception as e:
        print("❌ فشل حفظ الجلسة:", e)


def ensure_session():
    """تحميل الجلسة أو تسجيل الدخول ثم حفظها"""
    if load_session():
        return api

    print("🔄 لا توجد جلسة صالحة — تسجيل دخول جديد...")
    api.ensure_login()
    save_session()
    return api
