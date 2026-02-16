"""
Block System for GreenHabit
Apple Guideline 1.2 Compliance — Full Bidirectional Block Engine

Collection: user_blocks
Schema:
    blockerUserId: str     — who initiated the block
    blockedUserId: str     — who got blocked
    createdAt: datetime    — when the block was created

Indexes:
    (blockerUserId, blockedUserId) — unique compound
    (blockerUserId)                — fast "who did I block" queries
    (blockedUserId)                — fast "who blocked me" queries
"""

from datetime import datetime
from typing import Dict, List
from pymongo.errors import DuplicateKeyError


# ======================== INDEX SETUP ========================

def ensure_block_indexes(db):
    """Create indexes for user_blocks collection."""
    db.user_blocks.create_index(
        [("blockerUserId", 1), ("blockedUserId", 1)],
        unique=True
    )
    db.user_blocks.create_index([("blockerUserId", 1)])
    db.user_blocks.create_index([("blockedUserId", 1)])
    print("✅ Block system indexes created")


# ======================== CORE GUARD ========================

def is_blocked(db, user_a: str, user_b: str) -> bool:
    """
    Bidirectional block check.
    Returns True if EITHER user has blocked the other.
    O(1) via compound index scan.
    """
    if not user_a or not user_b or user_a == user_b:
        return False

    return db.user_blocks.find_one({
        "$or": [
            {"blockerUserId": user_a, "blockedUserId": user_b},
            {"blockerUserId": user_b, "blockedUserId": user_a}
        ]
    }) is not None


def get_all_blocked_ids(db, user_id: str) -> List[str]:
    """
    Get ALL user IDs involved in a block relationship with user_id.
    Includes both:
      - users blocked BY user_id
      - users who blocked user_id
    This is the bidirectional exclusion set for feed/ranking/search.
    """
    if not user_id:
        return []

    # Users I blocked
    blocked_by_me = db.user_blocks.find(
        {"blockerUserId": user_id}
    ).distinct("blockedUserId")

    # Users who blocked me
    blocked_me = db.user_blocks.find(
        {"blockedUserId": user_id}
    ).distinct("blockerUserId")

    # Merge into unique set
    all_ids = list(set(blocked_by_me + blocked_me))
    return all_ids


# ======================== BLOCK / UNBLOCK ========================

def block_user(db, blocker_id: str, blocked_id: str) -> Dict:
    """
    Block a user. Idempotent via unique index.
    Side effects:
      - Inserts block doc
      - Removes follow relationships in BOTH directions
      - Removes from legacy blockedUsers array (backward compat)
    """
    if blocker_id == blocked_id:
        return {"success": False, "message": "Cannot block yourself"}

    # Insert block document
    try:
        db.user_blocks.insert_one({
            "blockerUserId": blocker_id,
            "blockedUserId": blocked_id,
            "createdAt": datetime.utcnow()
        })
    except DuplicateKeyError:
        return {"success": True, "message": "Already blocked", "alreadyBlocked": True}

    # Remove follow relationships in BOTH directions
    db.follows.delete_many({
        "$or": [
            {"followerId": blocker_id, "followedId": blocked_id},
            {"followerId": blocked_id, "followedId": blocker_id}
        ]
    })

    # Backward compat: also update legacy blockedUsers array on users collection
    db.users.update_one(
        {"userId": blocker_id},
        {"$addToSet": {"blockedUsers": blocked_id}},
        upsert=True
    )

    # Remove any pending task shares between the two users
    db.task_shares.update_many(
        {
            "status": "pending",
            "$or": [
                {"senderId": blocker_id, "recipientId": blocked_id},
                {"senderId": blocked_id, "recipientId": blocker_id}
            ]
        },
        {"$set": {"status": "cancelled", "updatedAt": datetime.utcnow()}}
    )

    return {"success": True, "message": "User blocked successfully"}


def unblock_user(db, blocker_id: str, blocked_id: str) -> Dict:
    """
    Unblock a user. Only removes the blocker→blocked direction.
    If the other user also blocked, that block remains.
    """
    result = db.user_blocks.delete_one({
        "blockerUserId": blocker_id,
        "blockedUserId": blocked_id
    })

    # Backward compat: also remove from legacy array
    db.users.update_one(
        {"userId": blocker_id},
        {"$pull": {"blockedUsers": blocked_id}}
    )

    if result.deleted_count == 0:
        return {"success": True, "message": "Was not blocked"}

    return {"success": True, "message": "User unblocked successfully"}


# ======================== LIST BLOCKED USERS ========================

def get_blocked_users_list(db, user_id: str) -> List[Dict]:
    """
    Get detailed list of users blocked BY this user.
    Used for the Settings → Blocked Users screen.
    Returns user profile info for display.
    """
    block_docs = list(db.user_blocks.find(
        {"blockerUserId": user_id}
    ).sort("createdAt", -1))

    users = []
    for doc in block_docs:
        blocked_id = doc["blockedUserId"]
        profile = db.user_profiles.find_one({"userId": blocked_id})

        users.append({
            "userId": blocked_id,
            "displayName": profile.get("displayName") if profile else None,
            "blockedAt": doc["createdAt"].isoformat() + "Z" if doc.get("createdAt") else None
        })

    return users


# ======================== MIGRATION HELPER ========================

def migrate_legacy_blocks(db):
    """
    One-time migration: copy blockedUsers arrays from users collection
    into the new user_blocks collection.
    Run once during deployment, then remove.
    """
    migrated = 0
    users_with_blocks = db.users.find(
        {"blockedUsers": {"$exists": True, "$ne": []}},
        {"userId": 1, "blockedUsers": 1}
    )

    for user in users_with_blocks:
        blocker_id = user.get("userId")
        if not blocker_id:
            continue

        for blocked_id in user.get("blockedUsers", []):
            try:
                db.user_blocks.insert_one({
                    "blockerUserId": blocker_id,
                    "blockedUserId": blocked_id,
                    "createdAt": datetime.utcnow()
                })
                migrated += 1
            except DuplicateKeyError:
                pass  # Already migrated

    print(f"✅ Migrated {migrated} legacy block relationships to user_blocks collection")
    return {"migrated": migrated}
