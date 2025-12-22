from pymongo import MongoClient
from pymongo.errors import OperationFailure
from datetime import datetime
import os
from bson.objectid import ObjectId

# ============================
# الاتصال الكسول (Lazy Connection)
# ============================

MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise ValueError("🔴 MONGODB_URI غير موجود في متغيرات البيئة!")

client = None
db = None

def get_db():
    """الاتصال بقاعدة البيانات عند أول استخدام فقط"""
    global client, db
    if client is None:
        client = MongoClient(MONGODB_URI)
        db = client["ichancy_bot"]
        ensure_indexes()
    return db

# ============================
# إنشاء الفهارس
# ============================

def ensure_indexes():
    database = db

    users = database.users
    transactions = database.transactions
    referrals = database.referrals

    try:
        users.create_index("telegram_id", unique=True)
    except OperationFailure:
        pass

    try:
        users.create_index("player_id", unique=True, sparse=True)
    except OperationFailure:
        pass

    try:
        transactions.create_index("telegram_id")
        transactions.create_index("created_at")
    except OperationFailure:
        pass

    try:
        referrals.create_index("referrer_id")
    except OperationFailure:
        pass

    try:
        referrals.create_index("referred_id", unique=True)
    except OperationFailure:
        pass

# ============================
# دوال المجموعات
# ============================

def users_collection():
    return get_db().users

def transactions_collection():
    return get_db().transactions

def referrals_collection():
    return get_db().referrals

# ============================
# الدوال الأساسية للمستخدمين
# ============================

def get_user(telegram_id):
    return users_collection().find_one({"telegram_id": telegram_id})

def create_user(telegram_id, username, first_name, last_name):
    user_data = {
        "telegram_id": telegram_id,
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "balance": 0.0,
        "referral_balance": 0.0,
        "total_earned": 0.0,
        "total_withdrawn": 0.0,
        "referral_link": f"https://t.me/{os.getenv('BOT_USERNAME', '')}?start={telegram_id}",
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
        "updated_at": datetime.utcnow()
    }

    try:
        users_collection().insert_one(user_data)
        return True
    except Exception as e:
        if "duplicate key" in str(e).lower():
            return True
        print(f"❌ خطأ في إنشاء المستخدم: {e}")
        return False

def update_user(telegram_id, update_data):
    update_data["updated_at"] = datetime.utcnow()
    return users_collection().update_one(
        {"telegram_id": telegram_id},
        {"$set": update_data}
    )

def accept_terms(telegram_id):
    return update_user(telegram_id, {"accepted_terms": True})

def mark_channel_joined(telegram_id):
    return update_user(telegram_id, {"joined_channel": True})

def update_player_info(telegram_id, player_id, player_username, player_email, player_password):
    return update_user(telegram_id, {
        "player_id": player_id,
        "player_username": player_username,
        "player_email": player_email,
        "player_password": player_password
    })

# ============================
# تحديث الرصيد
# ============================

def update_balance(telegram_id, amount, is_withdrawal=False):
    transaction_type = "withdrawal" if is_withdrawal else "deposit"
    status = "completed" if amount > 0 else "pending"

    log_transaction(
        telegram_id=telegram_id,
        player_id=None,
        amount=abs(amount),
        ttype=transaction_type,
        status=status
    )

    inc_fields = {"balance": amount}

    if amount > 0:
        inc_fields["total_earned"] = amount
    elif is_withdrawal and amount < 0:
        inc_fields["total_withdrawn"] = abs(amount)

    result = users_collection().update_one(
        {"telegram_id": telegram_id},
        {"$inc": inc_fields, "$set": {"updated_at": datetime.utcnow()}}
    )

    return result.modified_count > 0

# ============================
# إدارة الإحالات
# ============================

def add_referral(referrer_id, referred_id):
    referral_data = {
        "referrer_id": referrer_id,
        "referred_id": referred_id,
        "is_active": False,
        "has_deposited": False,
        "referral_reward": 0.0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

    try:
        referrals_collection().insert_one(referral_data)
        users_collection().update_one(
            {"telegram_id": referrer_id},
            {"$inc": {"referrals_count": 1}}
        )
        return True
    except Exception as e:
        if "duplicate key" in str(e).lower():
            return True
        print(f"❌ خطأ في إضافة الإحالة: {e}")
        return False

def activate_referral(referred_id):
    referral = referrals_collection().find_one({"referred_id": referred_id})
    if not referral:
        return False

    referrals_collection().update_one(
        {"referred_id": referred_id},
        {"$set": {
            "is_active": True,
            "has_deposited": True,
            "updated_at": datetime.utcnow()
        }}
    )

    reward_amount = float(os.getenv("REFERRAL_REWARD", "5.0"))

    users_collection().update_one(
        {"telegram_id": referral["referrer_id"]},
        {"$inc": {
            "active_referrals_count": 1,
            "referral_balance": reward_amount
        }}
    )

    referrals_collection().update_one(
        {"referred_id": referred_id},
        {"$set": {"referral_reward": reward_amount}}
    )

    return True

# ============================
# إدارة المعاملات
# ============================

def log_transaction(telegram_id, player_id, amount, ttype, status="pending"):
    return transactions_collection().insert_one({
        "telegram_id": telegram_id,
        "player_id": player_id,
        "type": ttype,
        "amount": amount,
        "status": status,
        "created_at": datetime.utcnow()
    })

def get_user_transactions(telegram_id, limit=10, transaction_type=None):
    query = {"telegram_id": telegram_id}
    if transaction_type:
        query["type"] = transaction_type
    return list(
        transactions_collection()
        .find(query)
        .sort("created_at", -1)
        .limit(limit)
    )

def get_user_referrals(telegram_id):
    return list(referrals_collection().find({"referrer_id": telegram_id}))

def get_user_stats(telegram_id):
    user = get_user(telegram_id)
    if not user:
        return None

    referrals_list = get_user_referrals(telegram_id)
    transactions_list = get_user_transactions(telegram_id, limit=20)

    return {
        "user": user,
        "referrals": referrals_list,
        "transactions": transactions_list,
        "stats": {
            "total_referrals": len(referrals_list),
            "active_referrals": len([r for r in referrals_list if r.get("is_active")]),
            "total_referral_rewards": sum(r.get("referral_reward", 0) for r in referrals_list),
            "total_transactions": len(transactions_list)
        }
    }

def clear_player_info(telegram_id):
    result = users_collection().update_one(
        {"telegram_id": telegram_id},
        {
            "$set": {
                "player_id": None,
                "player_username": None,
                "player_email": None,
                "player_password": None,
                "updated_at": datetime.utcnow()
            }
        }
    )
    return result.matched_count > 0

def has_ichancy_account(telegram_id):
    user = users_collection().find_one(
        {
            "telegram_id": telegram_id,
            "player_id": {"$ne": None}
        }
    )
    return user is not None
