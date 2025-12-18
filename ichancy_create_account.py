# ichancy_create_account.py

import os
import random
import string
from pymongo import MongoClient
from ichancy_api import IChancyAPI

# API
api = IChancyAPI()

# MongoDB
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["ichancy"]
users_col = db["users"]


def _random_suffix(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def generate_username(raw_username: str) -> str:
    """
    توليد اسم مستخدم متاح على iChancy بصيغة:
    ZEUS_name أو ZEUS_name_x7a
    """
    base = f"ZEUS_{raw_username}"

    for i in range(6):
        username = base if i == 0 else f"{base}_{_random_suffix()}"

        status, data, _, _ = api.create_player_with_credentials(
            username,
            "TempPassword123!"
        )

        # إذا نجح الإنشاء → الاسم متاح
        if status == 200:
            return username

        # لو الخطأ ليس متعلقًا بالاسم نوقف المحاولة
        if "username" not in str(data).lower():
            break

    raise ValueError("❌ اسم المستخدم غير متاح، جرّب اسمًا آخر")


def create_ichancy_account(telegram_id: int, raw_username: str, password: str):
    """
    إنشاء حساب iChancy + حفظه في MongoDB
    """
    username = generate_username(raw_username)

    status, data, player_id, email = api.create_player_with_credentials(
        username,
        password
    )

    if status != 200:
        error_msg = data.get("notification", [{}])[0].get("content", "فشل إنشاء الحساب")
        raise ValueError(error_msg)

    users_col.insert_one({
        "telegram_id": telegram_id,
        "username": username,
        "password": password,
        "email": email,
        "player_id": player_id
    })

    return {
        "username": username,
        "password": password,
        "email": email,
        "player_id": player_id
    }

