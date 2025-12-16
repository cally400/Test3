from ichancy_api import IChancyAPI
import time

def keep_session_alive():
    """
    إبقاء جلسة iChancy نشطة.
    - تتحقق من تسجيل الدخول كل 5 دقائق
    - تعيد تسجيل الدخول إذا انتهت الجلسة
    """
    api = IChancyAPI()
    while True:
        try:
            api.ensure_login()
            print("✅ Session is active")
        except Exception as e:
            print(f"❌ Error in keep_session_alive: {e}")
        time.sleep(300)  # كل 5 دقائق
