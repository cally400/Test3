import json
import os
from datetime import datetime
from ichancy_api import IChancyAPI

COOKIE_FILE = "ichancy_session.json"

# لا ننشئ API هنا
api = None


def get_api():
    """إنشاء API عند الحاجة فقط (Lazy Initialization)"""
    global api
    if api is None:
        api = IChancyAPI()
    return api


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


def save_session():
    """حفظ الجلسة في ملف JSON"""
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
    """
    إرجاع API جاهز للاستخدام:
    - تحميل الجلسة من الملف إن وجدت
    - إذا لم توجد جلسة → تسجيل دخول عند الحاجة فقط
    """
    _api = get_api()

    # إذا تم تحميل الجلسة من الملف → نرجع API بدون تسجيل دخول
    if load_session():
        return _api

    # لا نسجل الدخول هنا إلا عند أول عملية API
    # فقط نرجع API فارغ، وسيقوم ensure_login داخل ichancy_api بالعمل عند الحاجة
    return _api
