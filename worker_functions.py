from ichancy_api import IChancyAPI
import time
import datetime

def keep_session_alive():
    api = IChancyAPI()
    while True:
        try:
            api.ensure_login()
            print(f"{datetime.datetime.now()} ✅ Session is active")
        except Exception as e:
            print(f"{datetime.datetime.now()} ❌ Error in keep_session_alive: {e}")
        time.sleep(300)  # كل 5 دقائق
