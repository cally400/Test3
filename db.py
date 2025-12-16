from pymongo import MongoClient
from datetime import datetime
import os

client = MongoClient(os.getenv("MONGODB_URI"))
db = client["ichancy_bot"]

users = db.users
transactions = db.transactions


def get_user(telegram_id):
    return users.find_one({"telegram_id": telegram_id})


def create_user(telegram_id, username, player_id):
    users.insert_one({
        "telegram_id": telegram_id,
        "username": username,
        "player_id": player_id,
        "balance": 0.0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    })


def change_balance(telegram_id, amount):
    return users.update_one(
        {"telegram_id": telegram_id},
        {
            "$inc": {"balance": amount},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )


def log_transaction(telegram_id, player_id, amount, ttype, status):
    transactions.insert_one({
        "telegram_id": telegram_id,
        "player_id": player_id,
        "type": ttype,
        "amount": amount,
        "status": status,
        "created_at": datetime.utcnow()
    })
