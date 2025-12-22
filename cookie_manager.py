import json
import requests
import os

print("📁 Current working directory:", os.getcwd())
print("📂 Files in directory:", os.listdir())

def load_cookies_into_session(session: requests.Session) -> bool:
    """
    تحميل الكوكيز من ملف ichancy_cookies.json
    وإضافتها إلى جلسة Requests.
    """
    try:
        cookie_file = "ichancy_cookies.json"

        if not os.path.exists(cookie_file):
            print("⚠️ ملف الكوكيز غير موجود — سيتم انتظار التجديد التلقائي")
            return False

        with open(cookie_file, "r") as f:
            cookies = json.load(f)

        for c in cookies:
            # إضافة كل كوكي إلى الجلسة
            session.cookies.set(
                name=c.get("name"),
                value=c.get("value"),
                domain=c.get("domain"),
                path=c.get("path", "/")
            )

        print("✅ تم تحميل الكوكيز بنجاح")
        return True

    except Exception as e:
        print(f"❌ خطأ أثناء تحميل الكوكيز: {e}")
        return False
