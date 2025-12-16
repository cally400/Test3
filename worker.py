import time
from worker_functions import keep_session_alive  # استيراد الدالة من worker_functions.py

if __name__ == '__main__':
    print("🚀 Worker started - Keeping iChancy session alive")
    keep_session_alive()

