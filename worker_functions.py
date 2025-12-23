import time
import datetime

def keep_session_alive():
    """Worker في وضع الخمول — لا يلمس الجلسة إطلاقًا"""
    while True:
        print(f"{datetime.datetime.now()} ⏳ Worker is running (idle mode)")
        time.sleep(300)  # كل 5 دقائق
