from pymongo import MongoClient
from pymongo.errors import OperationFailure
from datetime import datetime
import os

# ============================
# الاتصال بقاعدة البيانات
# ============================

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    print("⚠️ WARNING: MONGODB_URI غير موجود - سيتم تعطيل قاعدة البيانات")
    client = None
    db = None
else:
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    db = client.get_database("ichancy_bot")

# ============================
# المجموعات
# ============================

users = db.users if db else None
transactions = db.transactions if db else None
referrals = db.referrals if db else None

# ============================
# إنشاء الفهارس (آمن)
# ============================

def ensure_indexes():
    if not db:
        return

    try:
        users.create_index("telegram_id", unique=True)
        users.create_index("player_id", unique=True)
        transactions.create_index("telegram_id")
        transactions.create_index("created_at")
        referrals.create_index("referrer_id")
        referrals.create_index("referred_id", unique=True)
        print("✅ MongoDB indexes ensured")
    except Exception as e:
        print(f"⚠️ Index creation skipped: {e}")

ensure_indexes()

# ============================
# أدوات مساعدة
# ============================

def _db_check():
    if not db:
        print("⚠️ Database not available")
        return False
    return True

# ============================
# المستخدمين
# ============================

def get_user(telegram_id):
    if not _db_check():
        return None
    return users.find_one({"telegram_id": telegram_id})


def create_user(telegram_id, username, first_name, last_name):
    if not _db_check():
        return False

    user_data = {
        "telegram_id": telegram_id,
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "balance": 0.0,
        "referral_balance": 0.0,
        "total_earned": 0.0,
        "total_withdrawn": 0.0,
        "referral_link": f"https://t.me/{os.getenv('BOT_USERNAME', 'BOT')}?start={telegram_id}",
        "referrals_count": 0,
        "active_referrals_count": 0,
        "player_id": None,
        "player_username": None,
        "player_email": None,
        "player_password": None,
        "accepted_terms": False,
        "joined_channel": False,
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    try:
        users.insert_one(user_data)
        return True
    except Exception as e:
        print(f"❌ create_user error: {e}")
        return False


def update_user(telegram_id, update_data):
    if not _db_check():
        return False
    update_data["updated_at"] = datetime.utcnow()
    return users.update_one({"telegram_id": telegram_id}, {"$set": update_data})


def accept_terms(telegram_id):
    return update_user(telegram_id, {"accepted_terms": True})


def mark_channel_joined(telegram_id):
    return update_user(telegram_id, {"joined_channel": True})


def update_player_info(telegram_id, player_id, player_username, player_email, player_password):
    return update_user(
        telegram_id,
        {
            "player_id": player_id,
            "player_username": player_username,
            "player_email": player_email,
            "player_password": player_password,
        },
    )

# ============================
# المعاملات
# ============================

def log_transaction(telegram_id, player_id, amount, ttype, status="pending"):
    if not _db_check():
        return False

    return transactions.insert_one(
        {
            "telegram_id": telegram_id,
            "player_id": player_id,
            "type": ttype,
            "amount": amount,
            "status": status,
            "created_at": datetime.utcnow(),
        }
    )

