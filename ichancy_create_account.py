# ichancy_create_account.py
import random
import string
import logging
from ichancy_api import IChancyAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

api = IChancyAPI()

def generate_random_username(base="user", length=5):
    """توليد اسم مستخدم عشوائي"""
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
    return f"{base}_{suffix}"

def create_account(base_username="user"):
    """
    محاولة إنشاء حساب جديد
    تتحقق أولًا من صلاحية الجلسة
    """
    try:
        # التأكد من تسجيل الدخول
        if not api.ensure_login():
            logger.error("❌ فشل تسجيل الدخول للوكيل، لا يمكن إنشاء حساب.")
            return None

        for attempt in range(5):
            username = generate_random_username(base_username)
            status, resp = api.create_player(username, "Pass1234!")

            if status == 200 and resp.get("result"):
                logger.info(f"✅ تم إنشاء الحساب بنجاح: {username}")
                return {
                    "username": username,
                    "password": "Pass1234!",
                    "response": resp
                }
            else:
                logger.warning(f"⚠️ محاولة {attempt+1}: فشل إنشاء الحساب {username}, response: {resp}")

        logger.error("❌ جميع محاولات إنشاء الحساب فشلت.")
        return None

    except Exception as e:
        logger.error(f"❌ خطأ أثناء إنشاء الحساب: {str(e)}")
        return None

# مثال للاستخدام
if __name__ == "__main__":
    result = create_account("Her")
    if result:
        print("تم إنشاء الحساب:", result)
    else:
        print("فشل إنشاء الحساب.")

