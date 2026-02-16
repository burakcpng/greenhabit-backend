"""
Streak System v2 — Production-Grade, Timezone-Safe Streak Engine
Handles: completion recording, duplicate guarding, streak calculation,
         offline batch sync, and anti-cheat validation.

Authoritative field: completion_local_date (client-derived YYYY-MM-DD)
Audit field: completion_timestamp_utc (server clock)
"""

from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from pymongo.errors import DuplicateKeyError
import pytz


# ======================== CONSTANTS ========================

MAX_CLOCK_SKEW_HOURS = 26      # UTC-12 to UTC+14 = 26h range
MAX_FUTURE_DAYS = 1            # Cannot claim > 1 day ahead of server
MAX_BACKDATE_DAYS = 7          # Cannot claim > 7 days in the past (offline grace)
MAX_BATCH_SIZE = 30            # Max completions per offline sync batch


# ======================== INDEXES ========================

def ensure_streak_indexes(db):
    """
    Create required indexes for the streak system.
    Call once at startup.
    """
    # Core uniqueness constraint — prevents duplicate same-day completions
    db.habit_completions.create_index(
        [("userId", 1), ("completion_local_date", 1)],
        unique=True,
        name="unique_user_date"
    )

    # Fast lookup for streak recalculation
    db.habit_completions.create_index(
        [("userId", 1), ("completion_local_date", -1)],
        name="user_date_desc"
    )

    print("✅ Streak indexes ensured")


# ======================== ANTI-CHEAT VALIDATION ========================

class InvalidCompletionError(Exception):
    """Raised when a completion fails anti-cheat validation."""
    pass


def _validate_completion(
    local_date_str: str,
    tz_id: str,
    server_utc: datetime
) -> None:
    """
    Validate a completion against anti-cheat rules.
    
    Checks:
    1. Date format is valid YYYY-MM-DD
    2. Timezone identifier is valid IANA
    3. Clock skew between claimed date and server UTC is within tolerance
    4. Date is not too far in the future
    5. Date is not too far in the past
    """
    # 1. Parse local date
    try:
        local_date = date.fromisoformat(local_date_str)
    except (ValueError, TypeError):
        raise InvalidCompletionError(f"Invalid date format: {local_date_str}")

    # 2. Validate timezone identifier
    try:
        tz = pytz.timezone(tz_id)
    except pytz.exceptions.UnknownTimeZoneError:
        raise InvalidCompletionError(f"Unknown timezone: {tz_id}")

    # 3. Clock skew check
    # Convert server UTC to user's claimed timezone
    server_in_user_tz = server_utc.replace(tzinfo=pytz.utc).astimezone(tz)
    server_local_date = server_in_user_tz.date()

    # The claimed date should be within reasonable range of server's view of user's local date
    days_diff = (local_date - server_local_date).days

    # 4. Future date guard
    if days_diff > MAX_FUTURE_DAYS:
        raise InvalidCompletionError(
            f"Future date rejected: claimed {local_date_str}, "
            f"server sees {server_local_date.isoformat()} in {tz_id}"
        )

    # 5. Backdate guard
    if days_diff < -MAX_BACKDATE_DAYS:
        raise InvalidCompletionError(
            f"Backdate rejected: claimed {local_date_str}, "
            f"server sees {server_local_date.isoformat()} in {tz_id} "
            f"(max {MAX_BACKDATE_DAYS} days back)"
        )


# ======================== CORE: RECORD COMPLETION ========================

def record_completion(
    db,
    user_id: str,
    local_date_str: str,
    tz_id: str,
    source: str = "online"
) -> Dict:
    """
    Record a habit completion for a specific calendar day.
    
    This is the SINGLE entry point for all completion recording.
    Handles: validation, deduplication, streak update.
    
    Args:
        db: MongoDB database instance
        user_id: User's unique ID
        local_date_str: "YYYY-MM-DD" in user's local timezone (AUTHORITATIVE)
        tz_id: IANA timezone identifier (e.g. "Europe/Istanbul")
        source: "online" or "offline_sync"
    
    Returns:
        {currentStreak, longestStreak, lastCompletedDate, isDuplicate}
    """
    server_utc = datetime.utcnow()

    # 1. Anti-cheat validation
    _validate_completion(local_date_str, tz_id, server_utc)

    # 2. Attempt insert (unique index guards duplicates)
    try:
        db.habit_completions.insert_one({
            "userId": user_id,
            "completion_local_date": local_date_str,
            "completion_timestamp_utc": server_utc,
            "timezone_identifier": tz_id,
            "source": source,
            "created_at": server_utc
        })
    except DuplicateKeyError:
        # Same day already recorded — return current streak unchanged
        profile = db.user_profiles.find_one({"userId": user_id}) or {}
        return {
            "currentStreak": profile.get("currentStreak", 0),
            "longestStreak": profile.get("longestStreak", 0),
            "lastCompletedDate": local_date_str,
            "isDuplicate": True
        }

    # 3. Atomic streak update
    return _update_streak(db, user_id, local_date_str)


def _update_streak(db, user_id: str, local_date_str: str) -> Dict:
    """
    Atomically update the streak after a NEW completion is recorded.
    
    Uses conditional update to prevent race conditions:
    Only updates if lastCompletedLocalDate hasn't changed since we read it.
    """
    # Read current streak state
    profile = db.user_profiles.find_one({"userId": user_id})

    if not profile:
        # First-time user — create profile with streak = 1
        db.user_profiles.update_one(
            {"userId": user_id},
            {
                "$set": {
                    "currentStreak": 1,
                    "longestStreak": 1,
                    "lastCompletedLocalDate": local_date_str
                },
                "$setOnInsert": {
                    "userId": user_id,
                    "unlockedAchievements": [],
                    "totalPoints": 0,
                    "level": 1,
                    "createdAt": datetime.utcnow()
                }
            },
            upsert=True
        )
        return {
            "currentStreak": 1,
            "longestStreak": 1,
            "lastCompletedDate": local_date_str,
            "isDuplicate": False
        }

    last_date_str = profile.get("lastCompletedLocalDate")
    current_streak = profile.get("currentStreak", 0)
    longest_streak = profile.get("longestStreak", 0)

    # Calculate new streak
    completion_date = date.fromisoformat(local_date_str)

    if last_date_str is None:
        new_streak = 1
    else:
        try:
            last_date = date.fromisoformat(last_date_str)
        except (ValueError, TypeError):
            # Corrupted data — reset
            new_streak = 1
            last_date = None
        else:
            days_diff = (completion_date - last_date).days

            if days_diff == 1:
                # Consecutive day — increment
                new_streak = current_streak + 1
            elif days_diff == 0:
                # Same day — shouldn't reach here (unique index), but safe
                new_streak = current_streak
            elif days_diff < 0:
                # Backfill: completion is for an earlier date
                # Requires full recalculation to handle correctly
                return _recalculate_and_store(db, user_id)
            else:
                # Gap > 1 day — streak reset
                new_streak = 1

    new_longest = max(longest_streak, new_streak)

    # Atomic conditional update — only succeeds if state hasn't changed
    result = db.user_profiles.update_one(
        {
            "userId": user_id,
            "lastCompletedLocalDate": last_date_str  # Optimistic lock
        },
        {
            "$set": {
                "currentStreak": new_streak,
                "longestStreak": new_longest,
                "lastCompletedLocalDate": local_date_str,
                "updatedAt": datetime.utcnow()
            }
        }
    )

    if result.matched_count == 0:
        # Race condition: another request updated between read and write
        # Fall back to full recalculation
        return _recalculate_and_store(db, user_id)

    return {
        "currentStreak": new_streak,
        "longestStreak": new_longest,
        "lastCompletedDate": local_date_str,
        "isDuplicate": False
    }


# ======================== FULL RECALCULATION ========================

def calculate_streak_from_completions(db, user_id: str) -> Dict:
    """
    Full streak recalculation from habit_completions collection.
    
    Used for:
    - Recovery after race conditions
    - Admin recalculation
    - Account migration
    - Verifying stored streak integrity
    
    Returns: {currentStreak, longestStreak, lastCompletedDate}
    """
    # Fetch all completion dates, sorted ascending
    completions = list(db.habit_completions.find(
        {"userId": user_id},
        {"completion_local_date": 1, "_id": 0}
    ).sort("completion_local_date", 1))

    if not completions:
        return {
            "currentStreak": 0,
            "longestStreak": 0,
            "lastCompletedDate": None
        }

    dates = []
    for c in completions:
        try:
            dates.append(date.fromisoformat(c["completion_local_date"]))
        except (ValueError, TypeError):
            continue

    if not dates:
        return {
            "currentStreak": 0,
            "longestStreak": 0,
            "lastCompletedDate": None
        }

    # Deduplicate and sort (should already be unique from index, but defensive)
    dates = sorted(set(dates))

    # Calculate longest streak
    longest_streak = 1
    temp_streak = 1

    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days == 1:
            temp_streak += 1
        else:
            longest_streak = max(longest_streak, temp_streak)
            temp_streak = 1

    longest_streak = max(longest_streak, temp_streak)

    # Calculate current streak (walk backward from most recent)
    current_streak = 1
    today = date.today()

    # Check if most recent completion is today or yesterday
    most_recent = dates[-1]
    gap_from_today = (today - most_recent).days

    if gap_from_today > 1:
        # Streak is already broken
        current_streak = 0
    else:
        # Walk backward from most recent
        current_streak = 1
        for i in range(len(dates) - 2, -1, -1):
            if (dates[i + 1] - dates[i]).days == 1:
                current_streak += 1
            else:
                break

    last_completed = dates[-1].isoformat()

    return {
        "currentStreak": current_streak,
        "longestStreak": longest_streak,
        "lastCompletedDate": last_completed
    }


def _recalculate_and_store(db, user_id: str) -> Dict:
    """Recalculate streak from completions and store the result."""
    streak_info = calculate_streak_from_completions(db, user_id)

    db.user_profiles.update_one(
        {"userId": user_id},
        {
            "$set": {
                "currentStreak": streak_info["currentStreak"],
                "longestStreak": streak_info["longestStreak"],
                "lastCompletedLocalDate": streak_info["lastCompletedDate"],
                "updatedAt": datetime.utcnow()
            }
        }
    )

    streak_info["isDuplicate"] = False
    return streak_info


# ======================== OFFLINE BATCH SYNC ========================

def validate_offline_completions(
    db,
    user_id: str,
    completions: List[Dict]
) -> Dict:
    """
    Batch-validate and record offline completions.
    
    Completions are processed in CHRONOLOGICAL ORDER to ensure
    correct streak calculation.
    
    Args:
        db: MongoDB database instance
        user_id: User's unique ID
        completions: List of {
            "taskId": str,
            "completionLocalDate": "YYYY-MM-DD",
            "timezoneIdentifier": "Europe/Istanbul",
            "completedAt": "ISO8601" (original client timestamp, for audit)
        }
    
    Returns:
        {
            "finalStreak": {currentStreak, longestStreak, lastCompletedDate},
            "results": [{taskId, status, error?}, ...],
            "totalProcessed": int,
            "totalNew": int,
            "totalDuplicate": int,
            "totalRejected": int
        }
    """
    if len(completions) > MAX_BATCH_SIZE:
        return {
            "error": f"Batch too large: {len(completions)} > {MAX_BATCH_SIZE}",
            "results": [],
            "totalProcessed": 0,
            "totalNew": 0,
            "totalDuplicate": 0,
            "totalRejected": 0
        }

    # Sort by date ascending for correct chronological processing
    sorted_completions = sorted(
        completions,
        key=lambda c: c.get("completionLocalDate", "")
    )

    results = []
    total_new = 0
    total_duplicate = 0
    total_rejected = 0
    final_streak = None

    for completion in sorted_completions:
        task_id = completion.get("taskId", "unknown")
        local_date = completion.get("completionLocalDate")
        tz_id = completion.get("timezoneIdentifier", "UTC")

        if not local_date:
            results.append({
                "taskId": task_id,
                "status": "rejected",
                "error": "Missing completionLocalDate"
            })
            total_rejected += 1
            continue

        try:
            streak_result = record_completion(
                db=db,
                user_id=user_id,
                local_date_str=local_date,
                tz_id=tz_id,
                source="offline_sync"
            )

            if streak_result.get("isDuplicate"):
                results.append({
                    "taskId": task_id,
                    "status": "duplicate"
                })
                total_duplicate += 1
            else:
                results.append({
                    "taskId": task_id,
                    "status": "recorded"
                })
                total_new += 1

            final_streak = streak_result

        except InvalidCompletionError as e:
            results.append({
                "taskId": task_id,
                "status": "rejected",
                "error": str(e)
            })
            total_rejected += 1
        except Exception as e:
            results.append({
                "taskId": task_id,
                "status": "error",
                "error": str(e)
            })
            total_rejected += 1

    # If no completions were processed successfully, read current streak
    if final_streak is None:
        profile = db.user_profiles.find_one({"userId": user_id}) or {}
        final_streak = {
            "currentStreak": profile.get("currentStreak", 0),
            "longestStreak": profile.get("longestStreak", 0),
            "lastCompletedDate": profile.get("lastCompletedLocalDate"),
            "isDuplicate": True
        }

    return {
        "finalStreak": final_streak,
        "results": results,
        "totalProcessed": len(sorted_completions),
        "totalNew": total_new,
        "totalDuplicate": total_duplicate,
        "totalRejected": total_rejected
    }


# ======================== MIGRATION HELPER ========================

def migrate_existing_completions(db, user_id: str) -> int:
    """
    One-time migration: Convert existing completed tasks into
    habit_completions entries.
    
    Uses task.date as completion_local_date (best effort).
    Returns number of completions migrated.
    """
    # Get all completed tasks for user
    completed_tasks = list(db.tasks.find({
        "userId": user_id,
        "isCompleted": True
    }, {
        "date": 1,
        "completedAt": 1,
        "_id": 0
    }))

    # Deduplicate by date
    seen_dates = set()
    migrated = 0

    for task in completed_tasks:
        task_date = task.get("date")
        if not task_date or task_date in seen_dates:
            continue

        seen_dates.add(task_date)

        try:
            db.habit_completions.insert_one({
                "userId": user_id,
                "completion_local_date": task_date,
                "completion_timestamp_utc": task.get("completedAt", datetime.utcnow()),
                "timezone_identifier": "UTC",  # Unknown — best effort
                "source": "migration",
                "created_at": datetime.utcnow()
            })
            migrated += 1
        except DuplicateKeyError:
            # Already migrated
            pass

    # Recalculate and store streak from migrated data
    if migrated > 0:
        _recalculate_and_store(db, user_id)
        print(f"🔄 Migrated {migrated} completions for user {user_id}")

    return migrated
