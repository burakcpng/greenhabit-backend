"""
Habit System v1.5 — habit definitions + lazily materialized task instances.

Model:
  - A habit is a recurring definition stored in `habits`.
  - For dates <= today (user TZ) each due habit is materialized as a normal
    row in `tasks` (carrying `habitId`), so completions, streaks, stats and
    widgets keep working on `tasks` alone.
  - For future dates no row is written: callers get *virtual occurrences*
    (id "habit_{habitId}_{YYYY-MM-DD}", isVirtual: true, not completable).

Rules:
  - Weekdays are ISO-8601: 1 = Monday ... 7 = Sunday.
  - `time` is a floating wall-clock "HH:mm" (no timezone) or None = all-day.
  - "Today" is always the user's today (streak_system.user_today), never
    the server's date.today().
  - Materialization is idempotent: one row per (userId, habitId, date),
    enforced by a partial unique index (see ensure_habit_indexes).
"""

import calendar
import math
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pytz
from pymongo.errors import DuplicateKeyError

from streak_system import user_today


# ======================== CONSTANTS ========================

MAX_ACTIVE_HABITS = 30            # Hard cap per user
MAX_REMINDER_OFFSETS = 2          # Reminders per habit
MAX_REMINDER_OFFSET_MINUTES = 1440
MAX_INTERVAL_DAYS = 365
MAX_START_BACKDATE_DAYS = 1       # startDate may be at most 1 day in the past
RECURRENCE_TYPES = ("daily", "weekdays", "everyNDays")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_VIRTUAL_ID_RE = re.compile(r"^habit_(.+)_(\d{4}-\d{2}-\d{2})$")

# Filter for "uncompleted and never reversed" instances. Reversed instances
# (completed, then un-completed) are kept so a habit edit cannot be used to
# bypass the completion-finality guard in PATCH /tasks.
_REPLACEABLE_INSTANCE = {"isCompleted": {"$ne": True}, "wasReversed": {"$ne": True}}


# ======================== EXCEPTIONS ========================

class HabitError(Exception):
    """Carries the HTTP status the endpoint should return."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _invalid(detail: str) -> HabitError:
    return HabitError(422, detail)


# ======================== TIMEZONE / DATE HELPERS ========================

def resolve_tz(tz_id: Optional[str]) -> Optional[str]:
    """Return a valid IANA timezone id, or None when absent/invalid (invalid is logged)."""
    if not tz_id or not isinstance(tz_id, str):
        return None
    candidate = tz_id.strip()
    try:
        pytz.timezone(candidate)
        return candidate
    except Exception:
        print(f"⚠️ Habit system: ignoring invalid tz '{candidate[:64]}'")
        return None


def today_for(tz_id: Optional[str]) -> date:
    """User's today for a valid tz id; UTC today when tz is absent/invalid."""
    return user_today(resolve_tz(tz_id) or "UTC")


def parse_date(value, field: str = "date") -> date:
    """Strict YYYY-MM-DD parser."""
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise _invalid(f"Invalid {field}: expected YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _invalid(f"Invalid {field}: expected YYYY-MM-DD")


def validate_time(value, field: str = "time") -> Optional[str]:
    """Validate a floating wall-clock "HH:mm" string. None means all-day."""
    if value is None:
        return None
    if not isinstance(value, str) or not _TIME_RE.match(value):
        raise _invalid(f"Invalid {field}: expected HH:mm (24-hour)")
    return value


# ======================== VALIDATION ========================

def normalize_recurrence(raw) -> Dict:
    """Validate and normalize a recurrence rule to its canonical stored form."""
    if not isinstance(raw, dict):
        raise _invalid("recurrence is required")

    rec_type = raw.get("type")
    if rec_type not in RECURRENCE_TYPES:
        raise _invalid(f"Invalid recurrence type. Allowed: {list(RECURRENCE_TYPES)}")

    if rec_type == "daily":
        return {"type": "daily"}

    if rec_type == "weekdays":
        weekdays = raw.get("weekdays")
        if not isinstance(weekdays, list) or not weekdays:
            raise _invalid("recurrence.weekdays is required for type 'weekdays'")
        for d in weekdays:
            if isinstance(d, bool) or not isinstance(d, int) or d < 1 or d > 7:
                raise _invalid("recurrence.weekdays must be ISO weekdays 1 (Mon) to 7 (Sun)")
        return {"type": "weekdays", "weekdays": sorted(set(weekdays))}

    interval = raw.get("interval")
    if isinstance(interval, bool) or not isinstance(interval, int):
        raise _invalid("recurrence.interval is required for type 'everyNDays'")
    if interval < 1 or interval > MAX_INTERVAL_DAYS:
        raise _invalid(f"recurrence.interval must be between 1 and {MAX_INTERVAL_DAYS}")
    return {"type": "everyNDays", "interval": interval}


def normalize_reminder_offsets(offsets, time_value: Optional[str]) -> List[int]:
    """Minutes before `time`. Max 2, unique. Must be empty for all-day habits."""
    if offsets is None:
        offsets = []
    if not isinstance(offsets, list):
        raise _invalid("reminderOffsets must be a list of minutes")
    for o in offsets:
        if isinstance(o, bool) or not isinstance(o, int):
            raise _invalid("reminderOffsets must be whole minutes")
        if o < 0 or o > MAX_REMINDER_OFFSET_MINUTES:
            raise _invalid(f"reminderOffsets must be between 0 and {MAX_REMINDER_OFFSET_MINUTES} minutes")
    unique = sorted(set(offsets))
    if len(unique) > MAX_REMINDER_OFFSETS:
        raise _invalid(f"At most {MAX_REMINDER_OFFSETS} reminders per habit")
    if unique and time_value is None:
        raise _invalid("reminderOffsets must be empty when time is null (all-day habits have no reminders)")
    return unique


def compute_points(co2_kg: float) -> int:
    """Same formula as POST /tasks: min(100, ceil(co2Kg * 10))."""
    return min(100, int(math.ceil(co2_kg * 10)))


def format_impact(co2_kg: float) -> str:
    """Same text the iOS client builds (EcoImpactCalculator.formatImpactString)."""
    return f"Saves ~{co2_kg:.1f}kg CO₂"


# ======================== RECURRENCE ========================

def occurs_on(habit: Dict, day: date) -> bool:
    """Pure function: does this habit have an occurrence on `day`?"""
    if not habit.get("active", True):
        return False

    try:
        start = date.fromisoformat(habit["startDate"])
    except (KeyError, TypeError, ValueError):
        return False
    if day < start:
        return False

    end_str = habit.get("endDate")
    if end_str:
        try:
            if day > date.fromisoformat(end_str):
                return False
        except (TypeError, ValueError):
            return False

    if day.isoformat() in (habit.get("skippedDates") or []):
        return False

    recurrence = habit.get("recurrence") or {}
    rec_type = recurrence.get("type")
    if rec_type == "daily":
        return True
    if rec_type == "weekdays":
        return day.isoweekday() in (recurrence.get("weekdays") or [])
    if rec_type == "everyNDays":
        interval = int(recurrence.get("interval") or 1)
        return (day - start).days % interval == 0
    return False


# ======================== VIRTUAL IDS ========================

def virtual_id(habit_id: str, day_str: str) -> str:
    return f"habit_{habit_id}_{day_str}"


def parse_virtual_id(task_id: str) -> Optional[Tuple[str, str]]:
    """Return (habitId, 'YYYY-MM-DD') for a virtual occurrence id, else None."""
    if not isinstance(task_id, str):
        return None
    match = _VIRTUAL_ID_RE.match(task_id)
    if not match:
        return None
    return match.group(1), match.group(2)


# ======================== INDEXES ========================

def ensure_habit_indexes(db):
    """Create indexes for habits and habit-generated task instances. Call once at startup."""
    db.habits.create_index([("userId", 1), ("active", 1)], name="habit_user_active")
    db.habits.create_index([("id", 1)], unique=True, name="habit_id_unique")

    # One instance per (user, habit, date). PARTIAL on purpose: one-off tasks
    # have no habitId, and a plain unique index would treat them all as null
    # and reject the second one-off task a user creates on the same day.
    db.tasks.create_index(
        [("userId", 1), ("habitId", 1), ("date", 1)],
        unique=True,
        partialFilterExpression={"habitId": {"$type": "string"}},
        name="unique_user_habit_date",
    )
    # Day-view lookup (GET /tasks?date=...)
    db.tasks.create_index([("userId", 1), ("date", 1)], name="task_user_date")
    print("✅ Habit indexes ensured")


# ======================== MATERIALIZATION ========================

def _active_habits(db, user_id: str) -> List[Dict]:
    return list(db.habits.find({"userId": user_id, "active": True}))


def _task_fields_from_habit(habit: Dict) -> Dict:
    """Fields a task (instance, virtual or detached) copies from its habit."""
    return {
        "title": habit.get("title", ""),
        "details": habit.get("details", ""),
        "category": habit.get("category", ""),
        "points": habit.get("points", compute_points(habit.get("co2Kg", 0.0))),
        "estimatedImpact": habit.get("estimatedImpact") or format_impact(habit.get("co2Kg", 0.0)),
        "co2Kg": habit.get("co2Kg", 0.0),
        "time": habit.get("time"),
        "evidenceImagePath": None,
        "creatorType": "user",
        "sharedBy": None,
        "isCompleted": False,
        "completedAt": None,
    }


def _existing_instance_habit_ids(db, user_id: str, day_str: str, habit_ids: List[str]) -> set:
    return {
        t.get("habitId")
        for t in db.tasks.find(
            {"userId": user_id, "date": day_str, "habitId": {"$in": habit_ids}},
            {"habitId": 1},
        )
    }


def materialize_day(db, user_id: str, day: date) -> int:
    """
    Upsert one task instance per active habit that occurs on `day`.
    Idempotent: a second call (or a concurrent one) creates nothing.
    Callers must only pass days <= the user's today.
    Returns the number of rows created.
    """
    due = [h for h in _active_habits(db, user_id) if occurs_on(h, day)]
    if not due:
        return 0

    day_str = day.isoformat()
    existing = _existing_instance_habit_ids(db, user_id, day_str, [h["id"] for h in due])

    created = 0
    for habit in due:
        if habit["id"] in existing:
            continue
        now = datetime.utcnow()
        fields = _task_fields_from_habit(habit)
        fields.update({
            "id": str(uuid.uuid4()),
            "createdAt": now,
            # updatedAt = when the definition last changed, NOT "now". PATCH /tasks
            # applies a 5-second toggle cooldown based on updatedAt; stamping "now"
            # would reject a completion made right after the day is first opened.
            "updatedAt": habit.get("updatedAt") or now,
        })
        try:
            result = db.tasks.update_one(
                {"userId": user_id, "habitId": habit["id"], "date": day_str},
                {"$setOnInsert": fields},
                upsert=True,
            )
            if result.upserted_id is not None:
                created += 1
        except DuplicateKeyError:
            # A concurrent request materialized the same instance first.
            pass
    return created


def virtual_occurrences(db, user_id: str, day: date) -> List[Dict]:
    """
    Read-only occurrences for a future day. Nothing is written.
    Habits that already have a real row on that day (e.g. after a timezone
    change) are left out so the caller never shows a duplicate.
    """
    due = [h for h in _active_habits(db, user_id) if occurs_on(h, day)]
    if not due:
        return []

    day_str = day.isoformat()
    existing = _existing_instance_habit_ids(db, user_id, day_str, [h["id"] for h in due])

    occurrences = []
    for habit in due:
        if habit["id"] in existing:
            continue
        item = _task_fields_from_habit(habit)
        item.pop("sharedBy", None)
        item.update({
            "id": virtual_id(habit["id"], day_str),
            "userId": user_id,
            "habitId": habit["id"],
            "isVirtual": True,
            "date": day_str,
            "creatorId": None,
            "creatorName": None,
            "createdAt": habit.get("createdAt"),
            "updatedAt": habit.get("updatedAt"),
        })
        occurrences.append(item)
    return occurrences


def sync_day(db, user_id: str, date_str: str, tz_id: str) -> List[Dict]:
    """
    Entry point for GET /tasks?date=...&tz=...
      - date <= today (user TZ): materialize, return []
      - date  > today: return virtual occurrences (no DB write)
    `tz_id` must already be validated with resolve_tz().
    """
    if not isinstance(date_str, str) or not _DATE_RE.match(date_str):
        return []
    try:
        day = date.fromisoformat(date_str)
    except ValueError:
        return []

    if day <= user_today(tz_id):
        materialize_day(db, user_id, day)
        return []
    return virtual_occurrences(db, user_id, day)


# ======================== CALENDAR ========================

def calendar_virtual_counts(db, user_id: str, year: int, month: int) -> Dict[str, int]:
    """
    Per-day count of habit occurrences in a month that have NO real task row
    (future days, and past days the user never opened). Read-only.
    """
    habits = _active_habits(db, user_id)
    if not habits:
        return {}

    _, last_day = calendar.monthrange(year, month)
    start_str = f"{year:04d}-{month:02d}-01"
    end_str = f"{year:04d}-{month:02d}-{last_day:02d}"

    existing = {
        (t.get("habitId"), t.get("date"))
        for t in db.tasks.find(
            {
                "userId": user_id,
                "date": {"$gte": start_str, "$lte": end_str},
                "habitId": {"$type": "string"},
            },
            {"habitId": 1, "date": 1},
        )
    }

    counts: Dict[str, int] = {}
    for day_num in range(1, last_day + 1):
        day = date(year, month, day_num)
        day_str = day.isoformat()
        n = sum(
            1 for h in habits
            if occurs_on(h, day) and (h["id"], day_str) not in existing
        )
        if n:
            counts[day_str] = n
    return counts


def merge_calendar_counts(calendar_data: Dict, virtual_counts: Dict[str, int]) -> Dict:
    """Fold virtual habit counts into the response of social_system.get_calendar_data."""
    if not virtual_counts:
        return calendar_data

    days_by_date = {d["date"]: d for d in calendar_data.get("days", [])}
    for day_str, n in virtual_counts.items():
        entry = days_by_date.get(day_str)
        if entry is None:
            entry = {"date": day_str, "completedCount": 0, "totalCount": 0}
            days_by_date[day_str] = entry
        entry["totalCount"] = entry.get("totalCount", 0) + n
        entry["virtualCount"] = n

    days = [days_by_date[k] for k in sorted(days_by_date)]
    total_tasks = sum(d.get("totalCount", 0) for d in days)
    total_completed = sum(d.get("completedCount", 0) for d in days)

    calendar_data["days"] = days
    calendar_data["totalTasks"] = total_tasks
    calendar_data["totalCompleted"] = total_completed
    calendar_data["allTasksCompleted"] = total_tasks > 0 and total_completed == total_tasks
    return calendar_data


# ======================== HABIT CRUD ========================

def get_habit(db, user_id: str, habit_id: str) -> Dict:
    """Fetch an active habit owned by the user or raise 404."""
    habit = db.habits.find_one({"id": habit_id, "userId": user_id, "active": True})
    if not habit:
        raise HabitError(404, "Habit not found")
    return habit


def list_habits(db, user_id: str) -> List[Dict]:
    return list(db.habits.find({"userId": user_id, "active": True}).sort("createdAt", -1))


def create_habit(db, user_id: str, data: Dict, tz_id: Optional[str]) -> Dict:
    """
    Create a habit. `data` holds already length/profanity/category-checked
    title, details, category, co2Kg plus raw time/recurrence/reminderOffsets/
    startDate/endDate.
    """
    active_count = db.habits.count_documents({"userId": user_id, "active": True})
    if active_count >= MAX_ACTIVE_HABITS:
        raise HabitError(
            400,
            f"You've reached the limit of {MAX_ACTIVE_HABITS} active habits. "
            "Delete a habit to add a new one.",
        )

    today = today_for(tz_id)

    time_value = validate_time(data.get("time"))
    recurrence = normalize_recurrence(data.get("recurrence"))
    offsets = normalize_reminder_offsets(data.get("reminderOffsets"), time_value)

    start = parse_date(data["startDate"], "startDate") if data.get("startDate") else today
    if start < today - timedelta(days=MAX_START_BACKDATE_DAYS):
        raise _invalid("startDate cannot be in the past")

    end_str = None
    if data.get("endDate"):
        end = parse_date(data["endDate"], "endDate")
        if end < start:
            raise _invalid("endDate cannot be before startDate")
        end_str = end.isoformat()

    co2_kg = float(data["co2Kg"])
    now = datetime.utcnow()
    habit = {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "title": data["title"],
        "details": data.get("details") or "",
        "category": data["category"],
        "co2Kg": co2_kg,
        "points": compute_points(co2_kg),
        "estimatedImpact": format_impact(co2_kg),
        "time": time_value,
        "recurrence": recurrence,
        "reminderOffsets": offsets,
        "startDate": start.isoformat(),
        "endDate": end_str,
        "skippedDates": [],
        "active": True,
        "createdAt": now,
        "updatedAt": now,
    }
    db.habits.insert_one(habit)
    return habit


def cleanup_instances_from(db, user_id: str, habit_id: str, from_day: date) -> int:
    """
    Delete a habit's uncompleted, never-reversed instances dated >= from_day
    so they re-materialize from the current definition. Completed history stays.
    """
    query = {
        "userId": user_id,
        "habitId": habit_id,
        "date": {"$gte": from_day.isoformat()},
    }
    query.update(_REPLACEABLE_INSTANCE)
    return db.tasks.delete_many(query).deleted_count


def update_habit(db, user_id: str, habit_id: str, changes: Dict, tz_id: Optional[str]) -> Tuple[Dict, int]:
    """
    Apply a partial edit ("this and future").
    `changes` contains only the fields the client actually sent. `time` and
    `endDate` may be None (clear); None for any other field is ignored.
    If the recurrence changes, startDate resets to the user's today.
    Returns (updated habit, number of instances removed for re-materialization).
    """
    habit = get_habit(db, user_id, habit_id)
    today = today_for(tz_id)
    update: Dict = {}

    for field in ("title", "details", "category"):
        if changes.get(field) is not None:
            update[field] = changes[field]

    if changes.get("co2Kg") is not None:
        co2_kg = float(changes["co2Kg"])
        update["co2Kg"] = co2_kg
        update["points"] = compute_points(co2_kg)
        update["estimatedImpact"] = format_impact(co2_kg)

    time_value = habit.get("time")
    if "time" in changes:
        time_value = validate_time(changes["time"])
        update["time"] = time_value

    start_str = habit["startDate"]
    if changes.get("recurrence") is not None:
        recurrence = normalize_recurrence(changes["recurrence"])
        if recurrence != habit.get("recurrence"):
            update["recurrence"] = recurrence
            start_str = today.isoformat()
            update["startDate"] = start_str

    if changes.get("reminderOffsets") is not None:
        offsets_source = changes["reminderOffsets"]
    else:
        offsets_source = habit.get("reminderOffsets") or []
    offsets = normalize_reminder_offsets(offsets_source, time_value)
    if offsets != (habit.get("reminderOffsets") or []):
        update["reminderOffsets"] = offsets

    end_str = habit.get("endDate")
    if "endDate" in changes:
        end_str = parse_date(changes["endDate"], "endDate").isoformat() if changes["endDate"] else None
        update["endDate"] = end_str
    if end_str and end_str < start_str:
        raise _invalid("endDate cannot be before startDate")

    if not update:
        raise HabitError(400, "No fields to update")

    update["updatedAt"] = datetime.utcnow()
    db.habits.update_one({"id": habit_id, "userId": user_id}, {"$set": update})

    removed = cleanup_instances_from(db, user_id, habit_id, today)
    return get_habit(db, user_id, habit_id), removed


def soft_delete_habit(db, user_id: str, habit_id: str, tz_id: Optional[str]) -> int:
    """Deactivate a habit and drop its uncompleted instances from today on. History stays."""
    get_habit(db, user_id, habit_id)
    db.habits.update_one(
        {"id": habit_id, "userId": user_id},
        {"$set": {"active": False, "updatedAt": datetime.utcnow()}},
    )
    return cleanup_instances_from(db, user_id, habit_id, today_for(tz_id))


def add_skipped_dates(db, user_id: str, habit_id: str, dates: List[str]) -> None:
    """Record dates that must never be (re-)materialized for a habit."""
    unique = sorted({d for d in dates if d})
    if not unique:
        return
    db.habits.update_one(
        {"id": habit_id, "userId": user_id},
        {
            "$addToSet": {"skippedDates": {"$each": unique}},
            "$set": {"updatedAt": datetime.utcnow()},
        },
    )


def skip_occurrence(db, user_id: str, habit_id: str, date_str: str) -> Tuple[Dict, bool]:
    """
    Skip one occurrence: the date is never materialized again. An existing
    uncompleted instance is removed; a completed one cannot be skipped.
    Returns (updated habit, whether a real instance was removed).
    """
    get_habit(db, user_id, habit_id)
    day_str = parse_date(date_str).isoformat()

    instance = db.tasks.find_one({"userId": user_id, "habitId": habit_id, "date": day_str})
    if instance and instance.get("isCompleted"):
        raise HabitError(400, "A completed occurrence cannot be skipped")

    # Record the skip first: if the delete below fails the row simply stays.
    add_skipped_dates(db, user_id, habit_id, [day_str])

    removed = False
    if instance:
        result = db.tasks.delete_one({
            "userId": user_id,
            "habitId": habit_id,
            "date": day_str,
            "isCompleted": {"$ne": True},
        })
        removed = result.deleted_count > 0

    return get_habit(db, user_id, habit_id), removed


# ======================== INSTANCE DELETION / RESCHEDULE ========================

def register_deleted_instances(db, user_id: str, task_ids: List[str]) -> int:
    """
    Call BEFORE deleting tasks. For every task that is a habit instance, add
    its date to the habit's skippedDates so the deleted occurrence is not
    re-materialized on the next fetch. Returns how many instances were found.
    """
    if not task_ids:
        return 0
    instances = list(db.tasks.find(
        {"userId": user_id, "id": {"$in": list(task_ids)}, "habitId": {"$type": "string"}},
        {"habitId": 1, "date": 1},
    ))
    by_habit: Dict[str, List[str]] = {}
    for inst in instances:
        by_habit.setdefault(inst["habitId"], []).append(inst.get("date"))
    for habit_id, dates in by_habit.items():
        add_skipped_dates(db, user_id, habit_id, dates)
    return len(instances)


def reschedule_virtual_occurrence(
    db,
    user_id: str,
    habit_id: str,
    original_date_str: str,
    new_date_str: Optional[str],
    time_provided: bool,
    new_time: Optional[str],
) -> Dict:
    """
    Reschedule a future (virtual) occurrence: create a detached one-off task
    on the new date/time and skip the original date. Returns the new task.
    """
    habit = get_habit(db, user_id, habit_id)
    original_day = parse_date(original_date_str)
    if not occurs_on(habit, original_day):
        raise HabitError(404, "Occurrence not found")

    target_date = parse_date(new_date_str).isoformat() if new_date_str else original_date_str
    target_time = validate_time(new_time) if time_provided else habit.get("time")

    if target_date == original_date_str and target_time == habit.get("time"):
        raise HabitError(400, "No fields to update")

    # Skip first, then create: a failure in between can never leave a duplicate.
    add_skipped_dates(db, user_id, habit_id, [original_date_str])

    now = datetime.utcnow()
    task = _task_fields_from_habit(habit)
    task.update({
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "date": target_date,
        "time": target_time,
        "originHabitId": habit_id,
        "createdAt": now,
        "updatedAt": now,
    })
    db.tasks.insert_one(task)
    return task
