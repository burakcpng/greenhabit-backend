"""
remove_demo_accounts.py
Removes both App Store review demo accounts and all their data.

Usage:
    MONGO_URL="..." DB_NAME="GreenHabit_db" python remove_demo_accounts.py
"""

import os
import certifi
from pymongo import MongoClient

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.getenv("DB_NAME", "GreenHabit_db")

client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000, tlsCAFile=certifi.where())
db = client[DB_NAME]

DEMO_EMAILS = ["reviewer@greenhabit.app", "demouser@greenhabit.app"]


def delete_account(email: str):
    user = db.users.find_one({"email": email})
    if not user:
        print(f"⚠️  {email} not found — skipping")
        return

    user_id = user["userId"]
    username = user.get("username", "unknown")

    tasks_deleted = db.tasks.delete_many({"userId": user_id}).deleted_count
    db.user_profiles.delete_many({"userId": user_id})
    db.preferences.delete_many({"userId": user_id})
    db.achievements.delete_many({"userId": user_id})
    db.streak_data.delete_many({"userId": user_id})
    db.user_privacy.delete_many({"userId": user_id})
    # Social: remove from any follower/following lists
    db.follows.delete_many({"$or": [{"followerId": user_id}, {"followingId": user_id}]})
    db.users.delete_one({"userId": user_id})

    print(f"🗑️  Deleted {username} ({email})  |  {tasks_deleted} tasks removed")


for email in DEMO_EMAILS:
    delete_account(email)

print("\nDemo accounts removed.")
