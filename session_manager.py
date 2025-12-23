import json
import os
from datetime import datetime
from ichancy_api import IChancyAPI

COOKIE_FILE = "ichancy_session.json"

api = None


def get_api():
    global api
    if api is None:
        api = IChancyAPI()
    return api


def load_session_into_api():
    """تحميل الجلسة داخل API فقط عند الحاجة"""
    if not os.path.exists(COOKIE_FILE):
        return False

    try:
        with open(COOKIE_FILE, "r") as f:
            data = json.load(f)

        expiry = datetime.fromisoformat(data["expiry"])
        if expiry < datetime.now():
            return False

        _api = get_api()
        _api.session_cookies = data["cookies"]
        _api.session_expiry = expiry
        _api.last_login_time = datetime.fromisoformat(data["last_login"])
        _api.is_logged_in = True

        print("✅ تم تحميل الجلسة من الملف")
        return True

    except Exception as e:
        print("❌ فشل تحميل الجلسة:", e)
        return False


def save_session_from_api():
    """حفظ الجلسة بعد تسجيل الدخول فقط"""
    try:
        _api = get_api()
        data = {
            "cookies": _api.session_cookies,
            "expiry": _api.session_expiry.isoformat(),
            "last_login": _api.last_login_time.isoformat(),
        }
        with open(COOKIE_FILE, "w") as f:
            json.dump(data, f)

        print("💾 تم حفظ الجلسة في الملف")
    except Exception as e:
        print("❌ فشل حفظ الجلسة:", e)


def ensure_session():
    """إرجاع API فقط — بدون تحميل جلسة وبدون تسجيل دخول"""
    return get_api()
