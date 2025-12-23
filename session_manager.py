import json
import os
from datetime import datetime

COOKIE_FILE = "ichancy_session.json"

api = None


def create_api_if_needed():
    """
    إنشاء API فقط عند أول استخدام فعلي.
    (Lazy Import لمنع الاستيراد الدائري)
    """
    global api
    if api is None:
        from ichancy_api import IChancyAPI  # ← استيراد Lazy لمنع circular import
        api = IChancyAPI()
    return api


def load_session_into_api():
    """
    تحميل الجلسة من الملف إلى API إذا كانت صالحة.
    """
    if not os.path.exists(COOKIE_FILE):
        return False

    try:
        with open(COOKIE_FILE, "r") as f:
            data = json.load(f)

        expiry = datetime.fromisoformat(data.get("expiry"))
        last_login = datetime.fromisoformat(data.get("last_login"))

        # الجلسة منتهية
        if expiry < datetime.now():
            return False

        _api = create_api_if_needed()

        _api.session_cookies = data.get("cookies", {})
        _api.session_expiry = expiry
        _api.last_login_time = last_login
        _api.is_logged_in = True

        print("✅ تم تحميل الجلسة من الملف")
        return True

    except Exception as e:
        print("❌ فشل تحميل الجلسة:", e)
        return False


def ensure_session():
    """
    إرجاع API جاهز مع جلسة محملة (إن وجدت).
    """
    _api = create_api_if_needed()

    # تحميل الجلسة فقط إذا لم تكن محملة
    if not _api.is_logged_in:
        load_session_into_api()

    return _api
