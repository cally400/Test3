import os
import redis
import json
from datetime import datetime, timedelta

_api_instance = None

# إعداد Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(REDIS_URL)
SESSION_KEY = "ichancy_api_session"


def create_api_if_needed():
    """
    إنشاء API عند أول استخدام (Lazy Import)
    """
    global _api_instance
    if _api_instance is None:
        from ichancy_api import IChancyAPI
        _api_instance = IChancyAPI()
    return _api_instance


def load_session_from_redis():
    """
    تحميل الجلسة من Redis إذا كانت صالحة
    """
    try:
        data_raw = r.get(SESSION_KEY)
        if not data_raw:
            return False

        data = json.loads(data_raw)

        expiry = datetime.fromisoformat(data.get("expiry"))
        last_login = datetime.fromisoformat(data.get("last_login"))

        if expiry < datetime.now():
            return False

        api = create_api_if_needed()
        api.session_cookies = data.get("cookies", {})
        api.session_expiry = expiry
        api.last_login_time = last_login
        api.is_logged_in = True

        print("✅ تم تحميل الجلسة من Redis")
        return True
    except Exception as e:
        print("❌ فشل تحميل الجلسة من Redis:", e)
        return False


def save_session_to_redis(api):
    """
    حفظ الجلسة الحالية في Redis
    """
    try:
        if not api.session_cookies:
            return

        data = {
            "cookies": api.session_cookies,
            "expiry": api.session_expiry.isoformat() if api.session_expiry else None,
            "last_login": api.last_login_time.isoformat() if api.last_login_time else None
        }

        r.set(SESSION_KEY, json.dumps(data), ex=3600*2)  # صلاحية 2 ساعة
        print("💾 تم حفظ الجلسة في Redis")
    except Exception as e:
        print("❌ فشل حفظ الجلسة في Redis:", e)


def ensure_session():
    """
    الحصول على API مع جلسة واحدة مشتركة لكل المستخدمين
    """
    api = create_api_if_needed()

    if api.is_logged_in and api._is_session_valid():
        return api

    # محاولة تحميل الجلسة من Redis
    load_session_from_redis()

    # إذا ما زالت الجلسة غير صالحة → تسجيل دخول جديد
    if not api.is_logged_in or not api._is_session_valid():
        api.ensure_login()
        save_session_to_redis(api)

    return api

