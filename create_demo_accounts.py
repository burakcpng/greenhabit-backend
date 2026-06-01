"""
create_demo_accounts.py
Creates two demo accounts for App Store review.

Idempotent — safe to run multiple times. Uses deterministic, stable user IDs
so repeated runs update existing data rather than creating orphaned records.

Usage:
    MONGO_URL="..." DB_NAME="GreenHabit_db" python create_demo_accounts.py
"""

import os
import bcrypt
import certifi
from datetime import datetime, timedelta
from pymongo import MongoClient

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.getenv("DB_NAME", "GreenHabit_db")

client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000, tlsCAFile=certifi.where())
db = client[DB_NAME]

PASSWORD_STR = os.getenv("DEMO_PASSWORD", "GreenHabit2026!")
PASSWORD_HASH = bcrypt.hashpw(PASSWORD_STR.encode(), bcrypt.gensalt(rounds=12)).decode("utf-8")
NOW = datetime.utcnow()

# ── Stable, deterministic IDs (never change between runs) ───────────────────
USER_A_ID    = "demo-reviewer-001"
USER_A_EMAIL = "reviewer@greenhabit.app"
USER_A_USERNAME = "eco_reviewer"
CREATED_A = NOW - timedelta(days=30)

USER_B_ID    = "demo-explorer-001"
USER_B_EMAIL = "demouser@greenhabit.app"
USER_B_USERNAME = "green_explorer"
CREATED_B = NOW - timedelta(days=20)

TASKS_A = [
    # (category, title, points, days_ago)
    ("Energy",    "Switch to LED bulbs",           10, 0),
    ("Energy",    "Unplug idle devices",             8, 1),
    ("Energy",    "Air-dry laundry",                 9, 2),
    ("Water",     "Take a 5-min shower",             7, 3),
    ("Water",     "Fix dripping tap",               12, 4),
    ("Water",     "Collect rainwater for plants",    8, 5),
    ("Waste",     "Compost food scraps",            10, 6),
    ("Waste",     "Refuse single-use plastic bag",   9, 7),
    ("Waste",     "Recycle electronics",            15, 8),
    ("Transport", "Walk instead of drive",          10, 9),
    ("Transport", "Cycle to work",                  12, 10),
    ("Transport", "Carpool with colleague",          8, 11),
    ("Food",      "Meat-free Monday meal",           9, 12),
    ("Food",      "Buy local produce",               8, 13),
    ("Food",      "Zero-waste grocery run",         10, 14),
    ("Digital",   "Unsubscribe from junk email",     6, 15),
    ("Digital",   "Lower screen brightness",         5, 16),
    ("Social",    "Share eco tip with friend",        7, 17),
    ("Energy",    "Use cold wash cycle",              8, 18),
    ("Waste",     "Repair broken item",              10, 19),
    ("Water",     "Water plants at dusk",             6, 20),
    ("Transport", "Use public transport",            10, 21),
    ("Food",      "Cook from scratch",               9, 22),
    ("Digital",   "Stream at lower quality",          6, 23),
    ("Social",    "Join beach clean-up",             12, 24),
    ("Energy",    "Turn off lights when leaving",    7, 25),
    ("Waste",     "Buy second-hand item",            11, 26),
    ("Water",     "Turn off tap while brushing",      5, 27),
    ("Food",      "Pack a zero-waste lunch",          8, 28),
    ("Transport", "Work from home",                  9, 29),
]
TOTAL_POINTS_A = 450  # Bonus-adjusted

TASKS_B = [
    ("Energy",    "Turn off standby electronics",  10, 0),
    ("Energy",    "Open windows instead of AC",     8, 1),
    ("Water",     "Shorter shower today",            7, 2),
    ("Waste",     "Bring reusable bag",              8, 3),
    ("Waste",     "Sort recycling correctly",        9, 4),
    ("Transport", "Walk to the shops",              10, 5),
    ("Food",      "Plant-based dinner",              9, 6),
    ("Food",      "Avoid food waste today",          8, 7),
    ("Digital",   "Delete unused apps",              6, 8),
    ("Social",    "Recommend eco product",           7, 9),
    ("Energy",    "Line-dry clothes",                8, 10),
    ("Water",     "Re-use pasta cooking water",      5, 11),
    ("Waste",     "Upcycle a jar",                   7, 12),
    ("Transport", "Cycle to grocery store",         10, 13),
    ("Food",      "Buy seasonal vegetables",         8, 14),
]
TOTAL_POINTS_B = sum(t[2] for t in TASKS_B)


def create_user(user_id, email, username, password_hash, created_at, total_points, tasks_data,
                is_moderator=False):
    """Idempotent upsert — safe to call multiple times."""

    # Upsert by userId (stable) so repeated runs don't create duplicate users
    user_doc = {
        "userId": user_id,
        "appleUserId": None,
        "email": email,
        "username": username,
        "displayName": username,
        "passwordHash": password_hash,
        "auth_type": "email",
        "createdAt": created_at,
        "lastLogin": NOW,
        "isVerified": True,
        "isModerator": is_moderator,  # set True for reviewer so moderator bypass works
    }
    db.users.update_one(
        {"userId": user_id},
        {"$set": user_doc},
        upsert=True,
    )

    # Upsert user_profiles (leaderboard source of truth)
    db.user_profiles.update_one(
        {"userId": user_id},
        {"$set": {
            "userId": user_id,
            "displayName": username,
            "bio": "Demo account for App Store review",
            "totalPoints": total_points,
            "tasksCompleted": len(tasks_data),
            "level": max(1, total_points // 100),
            "createdAt": created_at,
        }},
        upsert=True,
    )

    # Upsert preferences
    db.preferences.update_one(
        {"userId": user_id},
        {"$set": {
            "userId": user_id,
            "country": "🇺🇸 United States",
            "interests": ["Energy", "Water", "Waste", "Transport", "Food", "Digital", "Social"],
            "language": "en",
        }},
        upsert=True,
    )

    # Upsert privacy: public profile so the reviewer can navigate directly to this
    # account from the leaderboard without needing to follow first.
    db.user_privacy.update_one(
        {"userId": user_id},
        {"$set": {
            "userId": user_id,
            "profilePublic": True,
            "showAchievements": True,
            "showStats": True,
            "showInterests": True,
            "showFollowers": True,
            "appearInLeaderboard": True,
        }},
        upsert=True,
    )

    # Upsert tasks (idempotent on userId+title+date)
    for (category, title, points, days_ago) in tasks_data:
        task_date = (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        completed_at = NOW - timedelta(days=days_ago)
        db.tasks.update_one(
            {"userId": user_id, "title": title, "date": task_date},
            {"$setOnInsert": {
                "id": f"{user_id}-task-{title[:20].replace(' ', '-').lower()}",
                "userId": user_id,
                "title": title,
                "details": f"Demo task: {title}",
                "category": category,
                "date": task_date,
                "points": points,
                "earnedPoints": points,
                "estimatedImpact": f"Saves ~{points * 0.05:.1f}kg CO₂",
                "co2Kg": round(points * 0.05, 2),
                "isCompleted": True,
                "completedAt": completed_at,
                "creatorType": "user",
                "sharedBy": None,
                "createdAt": completed_at,
                "updatedAt": completed_at,
            }},
            upsert=True,
        )

    print(f"✅ Upserted account: {username} ({email})  |  points={total_points}  |  tasks={len(tasks_data)}")


create_user(USER_A_ID, USER_A_EMAIL, USER_A_USERNAME, PASSWORD_HASH, CREATED_A, TOTAL_POINTS_A, TASKS_A, is_moderator=True)
create_user(USER_B_ID, USER_B_EMAIL, USER_B_USERNAME, PASSWORD_HASH, CREATED_B, TOTAL_POINTS_B, TASKS_B)

# Verify the accounts can be looked up
a = db.users.find_one({"userId": USER_A_ID})
b = db.users.find_one({"userId": USER_B_ID})
print(f"\nVerification:")
print(f"  A found: {bool(a)}  email={a.get('email') if a else 'N/A'}")
print(f"  B found: {bool(b)}  email={b.get('email') if b else 'N/A'}")

print(f"\nDemo accounts ready.")
print(f"  A → {USER_A_EMAIL}  /  {PASSWORD_STR}  (username: {USER_A_USERNAME})")
print(f"  B → {USER_B_EMAIL}  /  {PASSWORD_STR}  (username: {USER_B_USERNAME})")
