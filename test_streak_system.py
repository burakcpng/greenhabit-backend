"""
Tests for streak_system.py v3 — Production-Grade Streak Engine

Run: cd /Users/burak/Documents/GreenHabit/GREENHABİTBACK && python3 -m pytest test_streak_system.py -v

IMPORTANT: All dates in integration tests must be relative to today
to avoid triggering the anti-cheat backdate guard (MAX_BACKDATE_DAYS = 7).
"""

import pytest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch
from pymongo.errors import DuplicateKeyError

from streak_system import (
    record_completion,
    calculate_streak_from_completions,
    validate_offline_completions,
    get_streak_with_decay,
    safe_streak_fallback,
    compute_streak_transition,
    _validate_completion,
    InvalidCompletionError,
    StreakState,
    MAX_BACKDATE_DAYS,
)

# ======================== HELPERS ========================

def _d(offset: int) -> str:
    """Return YYYY-MM-DD for today + offset days."""
    return (date.today() + timedelta(days=offset)).isoformat()


# ======================== FIXTURES ========================

class MockCollection:
    """In-memory mock for a MongoDB collection."""

    def __init__(self):
        self.documents = []
        self._unique_indexes = []

    def create_index(self, fields, **kwargs):
        if kwargs.get("unique"):
            self._unique_indexes.append(tuple(f[0] for f in fields))

    def insert_one(self, doc):
        for idx_fields in self._unique_indexes:
            for existing in self.documents:
                if all(existing.get(f) == doc.get(f) for f in idx_fields):
                    raise DuplicateKeyError("Duplicate key")
        self.documents.append(doc)
        return MagicMock(inserted_id="mock_id")

    def find_one(self, query):
        for doc in self.documents:
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None

    def update_one(self, query, update, upsert=False):
        for doc in self.documents:
            if all(doc.get(k) == v for k, v in query.items()):
                if "$set" in update:
                    doc.update(update["$set"])
                if "$setOnInsert" in update:
                    for k, v in update["$setOnInsert"].items():
                        if k not in doc:
                            doc[k] = v
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        doc[k] = doc.get(k, 0) + v
                return MagicMock(matched_count=1, modified_count=1)

        if upsert:
            new_doc = {}
            for k, v in query.items():
                if not k.startswith("$"):
                    new_doc[k] = v
            if "$set" in update:
                new_doc.update(update["$set"])
            if "$setOnInsert" in update:
                new_doc.update(update["$setOnInsert"])
            if "$inc" in update:
                for k, v in update["$inc"].items():
                    new_doc[k] = new_doc.get(k, 0) + v
            self.documents.append(new_doc)
            return MagicMock(matched_count=0, modified_count=0, upserted_id="mock")

        return MagicMock(matched_count=0, modified_count=0)

    def find(self, query, projection=None):
        results = []
        for doc in self.documents:
            if all(doc.get(k) == v for k, v in query.items()):
                if projection:
                    filtered = {k: doc.get(k) for k in projection if k != "_id" and projection.get(k, 0)}
                    results.append(filtered)
                else:
                    results.append(doc)
        return MockCursor(results)

    def count_documents(self, query):
        return len([d for d in self.documents if all(d.get(k) == v for k, v in query.items())])


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, field, direction):
        self.docs.sort(key=lambda d: d.get(field, ""), reverse=(direction == -1))
        return self

    def __iter__(self):
        return iter(self.docs)

    def __list__(self):
        return self.docs


class MockDB:
    def __init__(self):
        self.habit_completions = MockCollection()
        self.user_profiles = MockCollection()
        self.tasks = MockCollection()

        self.habit_completions.create_index(
            [("userId", 1), ("completion_local_date", 1)],
            unique=True,
        )


@pytest.fixture
def db():
    return MockDB()


# ======================== TESTS: PURE FUNCTION ========================

class TestComputeStreakTransition:
    """Unit tests for the pure streak math — no DB, no validation."""

    def test_first_ever_completion(self):
        result = compute_streak_transition(0, 0, None, "2026-03-04")
        assert result == StreakState(current=1, longest=1, last_date="2026-03-04")

    def test_consecutive_day(self):
        result = compute_streak_transition(1, 1, "2026-03-04", "2026-03-05")
        assert result == StreakState(current=2, longest=2, last_date="2026-03-05")

    def test_same_day_idempotent(self):
        result = compute_streak_transition(5, 10, "2026-03-04", "2026-03-04")
        assert result == StreakState(current=5, longest=10, last_date="2026-03-04")

    def test_gap_resets_to_1(self):
        result = compute_streak_transition(5, 10, "2026-03-02", "2026-03-05")
        assert result == StreakState(current=1, longest=10, last_date="2026-03-05")

    def test_backfill_raises(self):
        with pytest.raises(ValueError, match="BACKFILL_REQUIRED"):
            compute_streak_transition(5, 10, "2026-03-05", "2026-03-03")

    def test_longest_never_decreases(self):
        result = compute_streak_transition(10, 10, "2026-03-01", "2026-03-10")
        assert result.longest == 10
        assert result.current == 1

    def test_longest_increases_on_new_high(self):
        result = compute_streak_transition(9, 9, "2026-03-04", "2026-03-05")
        assert result.current == 10
        assert result.longest == 10


# ======================== TESTS: FIRST COMPLETION ========================

class TestFirstCompletion:
    def test_creates_streak_of_1(self, db):
        result = record_completion(db, "user1", _d(0), "Europe/Istanbul")
        assert result["currentStreak"] == 1
        assert result["longestStreak"] == 1
        assert result["isDuplicate"] == False
        assert result["streakAlive"] == True

    def test_creates_profile_with_version(self, db):
        record_completion(db, "user1", _d(0), "Europe/Istanbul")
        profile = db.user_profiles.find_one({"userId": "user1"})
        assert profile is not None
        assert profile["currentStreak"] == 1
        assert profile["streakVersion"] == 1
        assert profile["lastTimezoneIdentifier"] == "Europe/Istanbul"


# ======================== TESTS: CONSECUTIVE DAYS ========================

class TestConsecutiveDays:
    def test_consecutive_day_increments(self, db):
        record_completion(db, "user1", _d(-1), "Europe/Istanbul")
        result = record_completion(db, "user1", _d(0), "Europe/Istanbul")
        assert result["currentStreak"] == 2
        assert result["longestStreak"] == 2

    def test_three_consecutive_days(self, db):
        record_completion(db, "user1", _d(-2), "Europe/Istanbul")
        record_completion(db, "user1", _d(-1), "Europe/Istanbul")
        result = record_completion(db, "user1", _d(0), "Europe/Istanbul")
        assert result["currentStreak"] == 3
        assert result["longestStreak"] == 3


# ======================== TESTS: STREAK RESET ========================

class TestStreakReset:
    def test_gap_resets_streak_to_1(self, db):
        record_completion(db, "user1", _d(-3), "Europe/Istanbul")
        record_completion(db, "user1", _d(-2), "Europe/Istanbul")
        # Skip _d(-1)
        result = record_completion(db, "user1", _d(0), "Europe/Istanbul")
        assert result["currentStreak"] == 1
        assert result["longestStreak"] == 2

    def test_longest_never_decreases(self, db):
        record_completion(db, "user1", _d(-6), "UTC")
        record_completion(db, "user1", _d(-5), "UTC")
        record_completion(db, "user1", _d(-4), "UTC")
        # Gap of 3 days → reset
        result = record_completion(db, "user1", _d(0), "UTC")
        assert result["currentStreak"] == 1
        assert result["longestStreak"] == 3


# ======================== TESTS: DUPLICATE SAME-DAY ========================

class TestDuplicateCompletion:
    def test_returns_isDuplicate_true(self, db):
        record_completion(db, "user1", _d(0), "Europe/Istanbul")
        result = record_completion(db, "user1", _d(0), "Europe/Istanbul")
        assert result["isDuplicate"] == True

    def test_does_not_change_streak(self, db):
        record_completion(db, "user1", _d(-1), "UTC")
        record_completion(db, "user1", _d(0), "UTC")
        result = record_completion(db, "user1", _d(0), "UTC")
        assert result["isDuplicate"] == True
        assert result["currentStreak"] == 2


# ======================== TESTS: ANTI-CHEAT ========================

class TestAntiCheat:
    def test_future_date_rejected(self, db):
        future = _d(5)
        with pytest.raises(InvalidCompletionError, match="Future date"):
            _validate_completion(future, "UTC", datetime.utcnow())

    def test_backdate_beyond_limit_rejected(self, db):
        old_date = _d(-(MAX_BACKDATE_DAYS + 5))
        with pytest.raises(InvalidCompletionError, match="Backdate rejected"):
            _validate_completion(old_date, "UTC", datetime.utcnow())

    def test_invalid_timezone_rejected(self, db):
        with pytest.raises(InvalidCompletionError, match="Unknown timezone"):
            _validate_completion(_d(0), "Fake/Zone", datetime.utcnow())

    def test_invalid_date_format_rejected(self, db):
        with pytest.raises(InvalidCompletionError, match="Invalid date format"):
            _validate_completion("not-a-date", "UTC", datetime.utcnow())

    def test_valid_date_passes(self, db):
        _validate_completion(_d(0), "UTC", datetime.utcnow())


# ======================== TESTS: OFFLINE BATCH SYNC ========================

class TestOfflineBatchSync:
    def test_batch_processes_chronologically(self, db):
        completions = [
            {"taskId": "t3", "completionLocalDate": _d(0), "timezoneIdentifier": "UTC"},
            {"taskId": "t1", "completionLocalDate": _d(-2), "timezoneIdentifier": "UTC"},
            {"taskId": "t2", "completionLocalDate": _d(-1), "timezoneIdentifier": "UTC"},
        ]
        result = validate_offline_completions(db, "user1", completions)
        assert result["totalNew"] == 3
        assert result["totalDuplicate"] == 0
        assert result["finalStreak"]["currentStreak"] == 3

    def test_batch_handles_duplicates(self, db):
        record_completion(db, "user1", _d(-1), "UTC")
        completions = [
            {"taskId": "t1", "completionLocalDate": _d(-1), "timezoneIdentifier": "UTC"},
            {"taskId": "t2", "completionLocalDate": _d(0), "timezoneIdentifier": "UTC"},
        ]
        result = validate_offline_completions(db, "user1", completions)
        assert result["totalDuplicate"] == 1
        assert result["totalNew"] == 1

    def test_batch_rejects_invalid(self, db):
        completions = [{"taskId": "t1"}]
        result = validate_offline_completions(db, "user1", completions)
        assert result["totalRejected"] == 1


# ======================== TESTS: FULL RECALCULATION ========================

class TestFullRecalculation:
    def test_recalculate_from_completions(self, db):
        for offset in [-2, -1, 0]:
            db.habit_completions.insert_one({
                "userId": "user1",
                "completion_local_date": _d(offset),
                "completion_timestamp_utc": datetime.utcnow(),
                "timezone_identifier": "UTC",
                "source": "test",
                "created_at": datetime.utcnow(),
            })
        result = calculate_streak_from_completions(db, "user1", "UTC")
        assert result["longestStreak"] == 3
        assert result["currentStreak"] == 3
        assert result["lastCompletedDate"] == _d(0)

    def test_recalculate_empty(self, db):
        result = calculate_streak_from_completions(db, "user1", "UTC")
        assert result["currentStreak"] == 0
        assert result["longestStreak"] == 0
        assert result["lastCompletedDate"] is None


# ======================== TESTS: READ-TIME DECAY ========================

class TestReadTimeDecay:
    def test_completed_today(self, db):
        db.user_profiles.documents.append({
            "userId": "user1",
            "currentStreak": 15,
            "longestStreak": 42,
            "lastCompletedLocalDate": _d(0),
            "lastTimezoneIdentifier": "UTC",
            "streakVersion": 5,
        })
        result = get_streak_with_decay(db, "user1")
        assert result["currentStreak"] == 15
        assert result["streakAlive"] == True
        assert result["streakAtRisk"] == False

    def test_completed_yesterday_at_risk(self, db):
        db.user_profiles.documents.append({
            "userId": "user1",
            "currentStreak": 15,
            "longestStreak": 42,
            "lastCompletedLocalDate": _d(-1),
            "lastTimezoneIdentifier": "UTC",
            "streakVersion": 5,
        })
        result = get_streak_with_decay(db, "user1")
        assert result["currentStreak"] == 15
        assert result["streakAlive"] == True
        assert result["streakAtRisk"] == True

    def test_expired_streak(self, db):
        db.user_profiles.documents.append({
            "userId": "user1",
            "currentStreak": 15,
            "longestStreak": 42,
            "lastCompletedLocalDate": _d(-3),
            "lastTimezoneIdentifier": "UTC",
            "streakVersion": 5,
        })
        result = get_streak_with_decay(db, "user1")
        assert result["currentStreak"] == 0
        assert result["streakAlive"] == False
        assert result["longestStreak"] == 42

    def test_no_profile_returns_zero(self, db):
        result = get_streak_with_decay(db, "nonexistent")
        assert result["currentStreak"] == 0
        assert result["streakAlive"] == False


# ======================== TESTS: SAFE FALLBACK ========================

class TestSafeFallback:
    def test_returns_stored_streak(self, db):
        db.user_profiles.documents.append({
            "userId": "user1",
            "currentStreak": 10,
            "longestStreak": 20,
            "lastCompletedLocalDate": _d(0),
        })
        result = safe_streak_fallback(db, "user1")
        assert result["currentStreak"] == 10
        assert result["longestStreak"] == 20

    def test_returns_zero_for_missing_profile(self, db):
        result = safe_streak_fallback(db, "nonexistent")
        assert result["currentStreak"] == 0
        assert result["longestStreak"] == 0


# ======================== TESTS: OCC / STREAK VERSION ========================

class TestStreakVersion:
    def test_version_increments_on_completion(self, db):
        record_completion(db, "user1", _d(-1), "UTC")
        profile = db.user_profiles.find_one({"userId": "user1"})
        assert profile["streakVersion"] == 1

        record_completion(db, "user1", _d(0), "UTC")
        profile = db.user_profiles.find_one({"userId": "user1"})
        assert profile["streakVersion"] == 2

    def test_last_timezone_stored(self, db):
        record_completion(db, "user1", _d(-1), "Europe/Istanbul")
        profile = db.user_profiles.find_one({"userId": "user1"})
        assert profile["lastTimezoneIdentifier"] == "Europe/Istanbul"

        record_completion(db, "user1", _d(0), "America/New_York")
        profile = db.user_profiles.find_one({"userId": "user1"})
        assert profile["lastTimezoneIdentifier"] == "America/New_York"
