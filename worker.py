import os
import time
from ichancy_api import IChancyAPI

def keep_session_alive():
    """إبقاء الجلسة نشطة"""
    api = IChancyAPI()
    while True:
        try:
            api.ensure_login()
            print("✅ Session is active")
        except Exception as e:
            print(f"❌ Error: {e}")
        time.sleep(300)  # كل 5 دقائق

if __name__ == '__main__':
    keep_session_alive()
