"""
Streak Engine v3 — Production-Grade, Timezone-Safe, Race-Resistant
Handles: completion recording, duplicate guarding, streak calculation,
         offline batch sync, anti-cheat validation, and read-time decay.

Authoritative field: completion_local_date (client-derived YYYY-MM-DD)
Audit field: completion_timestamp_utc (server clock)

Architecture:
  - Pure streak math in compute_streak_transition() (no DB, no side effects)
  - OCC via streakVersion (monotonic CAS counter)
  - Read-time decay via get_streak_with_decay() (no DB writes on read)
  - user_today() always uses user's timezone — NEVER date.today()
"""

from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, NamedTuple
from pymongo.errors import DuplicateKeyError
import pytz


# ======================== CONSTANTS ========================

MAX_FUTURE_DAYS    = 1     # Cannot claim > 1 day ahead of server view
MAX_BACKDATE_DAYS  = 7     # Cannot claim > 7 days in the past (offline grace)
MAX_BATCH_SIZE     = 30    # Max completions per offline sync batch
MAX_OCC_RETRIES    = 3     # Max optimistic concurrency retries before recalc


# ======================== EXCEPTIONS ========================

class InvalidCompletionError(Exception):
    """Raised when a completion fails anti-cheat validation."""
    pass


# ======================== PURE FUNCTIONS ========================

class StreakState(NamedTuple):
    current: int
    longest: int
    last_date: str   # YYYY-MM-DD


def user_today(tz_id: str) -> date:
    """
    Compute 'today' in the user's timezone using server UTC + TZ offset.
    CRITICAL: This is the ONLY way to get "today" in streak logic.
    NEVER use date.today() — it uses the server's local timezone.
    """
    tz = pytz.timezone(tz_id)
    return datetime.now(pytz.utc).astimezone(tz).date()


def compute_streak_transition(
    current_streak: int,
    longest_streak: int,
    last_date_str: Optional[str],
    new_date_str: str,
) -> StreakState:
    """
    Pure function — no DB access, no side effects, fully unit-testable.
    Computes the new streak state from transition rules.

    Raises ValueError("BACKFILL_REQUIRED") when d_new < d_last,
    signaling the caller to perform a full recalculation.
    """
    new_date = date.fromisoformat(new_date_str)

    if last_date_str is None:
        # First-ever completion
        return StreakState(
            current=1,
            longest=max(longest_streak, 1),
            last_date=new_date_str,
        )

    last_date = date.fromisoformat(last_date_str)
    gap = (new_date - last_date).days

    if gap == 0:
        # Same day — idempotent, no change
        return StreakState(
            current=current_streak,
            longest=longest_streak,
            last_date=last_date_str,
        )
    elif gap == 1:
        # Consecutive day — increment
        new_current = current_streak + 1
        return StreakState(
            current=new_current,
            longest=max(longest_streak, new_current),
            last_date=new_date_str,
        )
    elif gap > 1:
        # Gap > 1 day — streak broken, reset to 1
        return StreakState(
            current=1,
            longest=longest_streak,
            last_date=new_date_str,
        )
    else:
        # gap < 0 → backfill (completion for an earlier date)
        # Caller must trigger full recalculation
        raise ValueError("BACKFILL_REQUIRED")


# ======================== ANTI-CHEAT VALIDATION ========================

def _validate_completion(
    local_date_str: str,
    tz_id: str,
    server_utc: datetime,
) -> None:
    """
    6-layer anti-cheat pipeline:
      Layer 1: Date format validation
      Layer 2: IANA timezone validation
      Layer 3: Clock skew check (server view of user's local date)
      Layer 4: Future date guard
      Layer 5: Backdate guard
      Layer 6: Velocity guard (handled by unique index, not here)
    """
    # Layer 1: Parse local date
    try:
        local_date = date.fromisoformat(local_date_str)
    except (ValueError, TypeError):
        raise InvalidCompletionError(f"Invalid date format: {local_date_str}")

    # Layer 2: Validate timezone identifier
    try:
        tz = pytz.timezone(tz_id)
    except pytz.exceptions.UnknownTimeZoneError:
        raise InvalidCompletionError(f"Unknown timezone: {tz_id}")

    # Layer 3–5: Clock skew + future + backdate
    server_in_user_tz = server_utc.replace(tzinfo=pytz.utc).astimezone(tz)
    server_local_date = server_in_user_tz.date()
    days_diff = (local_date - server_local_date).days

    # Layer 4: Future date guard
    if days_diff > MAX_FUTURE_DAYS:
        raise InvalidCompletionError(
            f"Future date rejected: claimed {local_date_str}, "
            f"server sees {server_local_date.isoformat()} in {tz_id}"
        )

    # Layer 5: Backdate guard
    if days_diff < -MAX_BACKDATE_DAYS:
        raise InvalidCompletionError(
            f"Backdate rejected: claimed {local_date_str}, "
            f"server sees {server_local_date.isoformat()} in {tz_id} "
            f"(max {MAX_BACKDATE_DAYS} days back)"
        )


# ======================== INDEXES ========================

def ensure_streak_indexes(db):
    """Create required indexes for the streak system. Call once at startup."""
    # Core uniqueness constraint — prevents duplicate same-day completions
    db.habit_completions.create_index(
        [("userId", 1), ("completion_local_date", 1)],
        unique=True,
        name="unique_user_date",
    )
    # Fast lookup for streak recalculation (descending date)
    db.habit_completions.create_index(
        [("userId", 1), ("completion_local_date", -1)],
        name="user_date_desc",
    )
    #if DEBUG
    print("✅ Streak indexes ensured")


# ======================== CORE: RECORD COMPLETION ========================

def record_completion(
    db,
    user_id: str,
    local_date_str: str,
    tz_id: str,
    source: str = "online",
) -> Dict:
    """
    Record a habit completion for a specific calendar day.

    This is the SINGLE entry point for all completion recording.
    Handles: validation → dedup (unique index) → OCC streak update.

    Args:
        db: MongoDB database instance
        user_id: User's unique ID
        local_date_str: "YYYY-MM-DD" in user's local timezone (AUTHORITATIVE)
        tz_id: IANA timezone identifier (e.g. "Europe/Istanbul")
        source: "online" | "offline_sync" | "migration"

    Returns:
        {currentStreak, longestStreak, lastCompletedDate, isDuplicate,
         streakAlive, streakAtRisk}
    """
    server_utc = datetime.utcnow()

    # 1. Anti-cheat validation
    _validate_completion(local_date_str, tz_id, server_utc)

    # 2. Insert into immutable audit log (unique index guards duplicates)
    try:
        db.habit_completions.insert_one({
            "userId": user_id,
            "completion_local_date": local_date_str,
            "completion_timestamp_utc": server_utc,
            "timezone_identifier": tz_id,
            "source": source,
            "created_at": server_utc,
        })
    except DuplicateKeyError:
        # Same day already recorded — return current state unchanged
        profile = db.user_profiles.find_one({"userId": user_id}) or {}
        return {
            "currentStreak": profile.get("currentStreak", 0),
            "longestStreak": profile.get("longestStreak", 0),
            "lastCompletedDate": local_date_str,
            "isDuplicate": True,
            "streakAlive": True,
            "streakAtRisk": False,
        }

    # 3. Atomic streak update with OCC
    return _update_streak_occ(db, user_id, local_date_str, tz_id)


# ======================== OCC STREAK UPDATE ========================

def _update_streak_occ(
    db, user_id: str, local_date_str: str, tz_id: str
) -> Dict:
    """
    Update streak using Optimistic Concurrency Control (OCC).
    Uses streakVersion as a monotonic CAS guard.
    Falls back to full recalculation after MAX_OCC_RETRIES failures.
    """
    for attempt in range(MAX_OCC_RETRIES):
        profile = db.user_profiles.find_one({"userId": user_id})

        if not profile:
            # First-time user — upsert with version 1
            db.user_profiles.update_one(
                {"userId": user_id},
                {
                    "$set": {
                        "currentStreak": 1,
                        "longestStreak": 1,
                        "lastCompletedLocalDate": local_date_str,
                        "lastTimezoneIdentifier": tz_id,
                        "streakUpdatedAt": datetime.utcnow(),
                        "streakVersion": 1,
                    },
                    "$setOnInsert": {
                        "userId": user_id,
                        "unlockedAchievements": [],
                        "totalPoints": 0,
                        "level": 1,
                        "createdAt": datetime.utcnow(),
                    },
                },
                upsert=True,
            )
            return {
                "currentStreak": 1,
                "longestStreak": 1,
                "lastCompletedDate": local_date_str,
                "isDuplicate": False,
                "streakAlive": True,
                "streakAtRisk": False,
            }

        version = profile.get("streakVersion", 0)
        last_date_str = profile.get("lastCompletedLocalDate")
        current_streak = profile.get("currentStreak", 0)
        longest_streak = profile.get("longestStreak", 0)

        # Pure streak computation — no DB, no side effects
        try:
            new_state = compute_streak_transition(
                current_streak, longest_streak, last_date_str, local_date_str
            )
        except ValueError:
            # BACKFILL_REQUIRED — full recalc needed
            return _recalculate_and_store(db, user_id, tz_id)

        # Atomic CAS write — only succeeds if streakVersion hasn't changed
        result = db.user_profiles.update_one(
            {"userId": user_id, "streakVersion": version},
            {
                "$set": {
                    "currentStreak": new_state.current,
                    "longestStreak": new_state.longest,
                    "lastCompletedLocalDate": new_state.last_date,
                    "lastTimezoneIdentifier": tz_id,
                    "streakUpdatedAt": datetime.utcnow(),
                },
                "$inc": {"streakVersion": 1},
            },
        )

        if result.matched_count == 1:
            # CAS succeeded
            return {
                "currentStreak": new_state.current,
                "longestStreak": new_state.longest,
                "lastCompletedDate": new_state.last_date,
                "isDuplicate": False,
                "streakAlive": True,
                "streakAtRisk": False,
            }

        # CAS failed — another concurrent write won. Retry.

    # All retries exhausted — fall back to full recalculation
    return _recalculate_and_store(db, user_id, tz_id)


# ======================== FULL RECALCULATION ========================

def calculate_streak_from_completions(
    db, user_id: str, tz_id: str = None
) -> Dict:
    """
    Full streak recalculation from the immutable habit_completions audit log.

    Used for:
    - Recovery after OCC exhaustion (race conditions)
    - Backfill completions (out-of-order submissions)
    - Admin recalculation endpoint
    - Account migration

    CRITICAL: Uses user's timezone for "today", NEVER date.today().
    """
    completions = list(db.habit_completions.find(
        {"userId": user_id},
        {"completion_local_date": 1, "timezone_identifier": 1, "_id": 0},
    ).sort("completion_local_date", 1))

    if not completions:
        return {
            "currentStreak": 0,
            "longestStreak": 0,
            "lastCompletedDate": None,
        }

    dates = []
    last_tz = "UTC"
    for c in completions:
        try:
            dates.append(date.fromisoformat(c["completion_local_date"]))
            last_tz = c.get("timezone_identifier", last_tz)
        except (ValueError, TypeError):
            continue

    if not dates:
        return {
            "currentStreak": 0,
            "longestStreak": 0,
            "lastCompletedDate": None,
        }

    # Deduplicate and sort (should be unique from index, but defensive)
    dates = sorted(set(dates))

    # ── Longest streak (full forward walk) ──
    longest = 1
    temp = 1
    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days == 1:
            temp += 1
        else:
            longest = max(longest, temp)
            temp = 1
    longest = max(longest, temp)

    # ── Current streak (backward walk from most recent) ──
    # Use provided tz or last-known tz — NEVER date.today()
    effective_tz = tz_id or last_tz
    try:
        today = user_today(effective_tz)
    except Exception:
        today = user_today("UTC")

    most_recent = dates[-1]
    gap = (today - most_recent).days

    if gap > 1:
        # Streak already broken
        current = 0
    else:
        # Walk backward from most recent
        current = 1
        for i in range(len(dates) - 2, -1, -1):
            if (dates[i + 1] - dates[i]).days == 1:
                current += 1
            else:
                break

    return {
        "currentStreak": current,
        "longestStreak": longest,
        "lastCompletedDate": dates[-1].isoformat(),
    }


def _recalculate_and_store(db, user_id: str, tz_id: str = None) -> Dict:
    """Recalculate streak from completions and atomically store the result."""
    streak_info = calculate_streak_from_completions(db, user_id, tz_id)

    db.user_profiles.update_one(
        {"userId": user_id},
        {
            "$set": {
                "currentStreak": streak_info["currentStreak"],
                "longestStreak": streak_info["longestStreak"],
                "lastCompletedLocalDate": streak_info["lastCompletedDate"],
                "streakUpdatedAt": datetime.utcnow(),
            },
            "$inc": {"streakVersion": 1},
        },
    )

    streak_info["isDuplicate"] = False
    streak_info["streakAlive"] = streak_info["currentStreak"] > 0
    streak_info["streakAtRisk"] = False
    return streak_info


# ======================== READ-TIME DECAY ========================

def get_streak_with_decay(db, user_id: str) -> Dict:
    """
    GET /streak — reads stored value with virtual (read-time) decay.
    
    Returns streakAlive + streakAtRisk for UX clarity.
    Does NOT write to DB — zero write amplification on reads.
    The stored currentStreak is lazily corrected on the next write.
    """
    profile = db.user_profiles.find_one({"userId": user_id}) or {}
    stored = profile.get("currentStreak", 0)
    last_str = profile.get("lastCompletedLocalDate")
    tz_id = profile.get("lastTimezoneIdentifier", "UTC")
    longest = profile.get("longestStreak", 0)

    base = {
        "longestStreak": longest,
        "lastCompletedDate": last_str,
    }

    if stored == 0 or not last_str:
        return {**base, "currentStreak": 0,
                "streakAlive": False, "streakAtRisk": False}

    try:
        last_date = date.fromisoformat(last_str)
        today = user_today(tz_id)
        gap = (today - last_date).days
    except Exception:
        # If TZ or date parsing fails, return stored value as-is
        return {**base, "currentStreak": stored,
                "streakAlive": True, "streakAtRisk": False}

    if gap > 1:
        # Streak expired — return 0 virtually (no DB write)
        return {**base, "currentStreak": 0,
                "streakAlive": False, "streakAtRisk": False}
    elif gap == 1:
        # Streak alive but user hasn't completed today — at risk
        return {**base, "currentStreak": stored,
                "streakAlive": True, "streakAtRisk": True}
    else:
        # gap == 0 → completed today
        return {**base, "currentStreak": stored,
                "streakAlive": True, "streakAtRisk": False}


# ======================== SAFE FALLBACK ========================

def safe_streak_fallback(db, user_id: str) -> Dict:
    """
    When anti-cheat validation fails, return STORED streak — never hardcode 0.
    This preserves the user's rewards/achievement eligibility even when
    the completion date can't be validated.
    """
    profile = db.user_profiles.find_one({"userId": user_id}) or {}
    return {
        "currentStreak": profile.get("currentStreak", 0),
        "longestStreak": profile.get("longestStreak", 0),
        "lastCompletedDate": profile.get("lastCompletedLocalDate"),
        "isDuplicate": False,
        "streakAlive": profile.get("currentStreak", 0) > 0,
        "streakAtRisk": False,
    }


# ======================== OFFLINE BATCH SYNC ========================

def validate_offline_completions(
    db,
    user_id: str,
    completions: List[Dict],
) -> Dict:
    """
    Batch-validate and record offline completions.
    Processes in CHRONOLOGICAL ORDER for correct streak calculation.

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
        {finalStreak, results, totalProcessed, totalNew, totalDuplicate, totalRejected}
    """
    if len(completions) > MAX_BATCH_SIZE:
        return {
            "error": f"Batch too large: {len(completions)} > {MAX_BATCH_SIZE}",
            "results": [],
            "totalProcessed": 0,
            "totalNew": 0,
            "totalDuplicate": 0,
            "totalRejected": 0,
        }

    # Sort by date ascending for correct chronological processing
    sorted_completions = sorted(
        completions,
        key=lambda c: c.get("completionLocalDate", ""),
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
                "error": "Missing completionLocalDate",
            })
            total_rejected += 1
            continue

        try:
            streak_result = record_completion(
                db=db,
                user_id=user_id,
                local_date_str=local_date,
                tz_id=tz_id,
                source="offline_sync",
            )

            if streak_result.get("isDuplicate"):
                results.append({"taskId": task_id, "status": "duplicate"})
                total_duplicate += 1
            else:
                results.append({"taskId": task_id, "status": "recorded"})
                total_new += 1

            final_streak = streak_result

        except InvalidCompletionError as e:
            results.append({
                "taskId": task_id,
                "status": "rejected",
                "error": str(e),
            })
            total_rejected += 1
        except Exception as e:
            results.append({
                "taskId": task_id,
                "status": "error",
                "error": str(e),
            })
            total_rejected += 1

    # If no completions were processed successfully, read current streak
    if final_streak is None:
        final_streak = safe_streak_fallback(db, user_id)

    return {
        "finalStreak": final_streak,
        "results": results,
        "totalProcessed": len(sorted_completions),
        "totalNew": total_new,
        "totalDuplicate": total_duplicate,
        "totalRejected": total_rejected,
    }


# ======================== MIGRATION HELPER ========================

def migrate_existing_completions(db, user_id: str) -> int:
    """
    One-time migration: Convert existing completed tasks into
    habit_completions entries.

    Uses task.date as completion_local_date (best effort).
    Returns number of completions migrated.
    """
    completed_tasks = list(db.tasks.find(
        {"userId": user_id, "isCompleted": True},
        {"date": 1, "completedAt": 1, "_id": 0},
    ))

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
                "created_at": datetime.utcnow(),
            })
            migrated += 1
        except DuplicateKeyError:
            pass  # Already migrated

    # Recalculate and store streak from migrated data
    if migrated > 0:
        _recalculate_and_store(db, user_id)
        #if DEBUG
        print(f"🔄 Migrated {migrated} completions for user {user_id}")

    return migrated
