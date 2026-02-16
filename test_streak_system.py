"""
Tests for streak_system.py — Production-Grade Streak Engine

Run: cd /Users/burak/Desktop/GreenHabit/GREENHABİTBACK && python -m pytest test_streak_system.py -v
"""

import pytest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch
from pymongo.errors import DuplicateKeyError

from streak_system import (
    record_completion,
    calculate_streak_from_completions,
    validate_offline_completions,
    _validate_completion,
    InvalidCompletionError,
    MAX_CLOCK_SKEW_HOURS,
    MAX_BACKDATE_DAYS,
)


# ======================== FIXTURES ========================

class MockCollection:
    """In-memory mock for a MongoDB collection."""
    
    def __init__(self):
        self.documents = []
        self._unique_indexes = []  # list of field tuples
    
    def create_index(self, fields, **kwargs):
        if kwargs.get("unique"):
            self._unique_indexes.append(tuple(f[0] for f in fields))
    
    def insert_one(self, doc):
        # Check unique indexes
        for idx_fields in self._unique_indexes:
            for existing in self.documents:
                match = all(existing.get(f) == doc.get(f) for f in idx_fields)
                if match:
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
                return MagicMock(matched_count=1, modified_count=1)
        
        if upsert:
            new_doc = dict(query)
            if "$set" in update:
                new_doc.update(update["$set"])
            if "$setOnInsert" in update:
                new_doc.update(update["$setOnInsert"])
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
        
        # Set up unique index like production
        self.habit_completions.create_index(
            [("userId", 1), ("completion_local_date", 1)],
            unique=True
        )


@pytest.fixture
def db():
    return MockDB()


# ======================== TESTS: FIRST COMPLETION ========================

class TestFirstCompletion:
    def test_first_completion_creates_streak_of_1(self, db):
        result = record_completion(db, "user1", "2026-02-16", "Europe/Istanbul")
        
        assert result["currentStreak"] == 1
        assert result["longestStreak"] == 1
        assert result["isDuplicate"] == False
        assert result["lastCompletedDate"] == "2026-02-16"
    
    def test_first_completion_creates_profile(self, db):
        record_completion(db, "user1", "2026-02-16", "Europe/Istanbul")
        
        profile = db.user_profiles.find_one({"userId": "user1"})
        assert profile is not None
        assert profile["currentStreak"] == 1
        assert profile["lastCompletedLocalDate"] == "2026-02-16"


# ======================== TESTS: CONSECUTIVE DAYS ========================

class TestConsecutiveDays:
    def test_consecutive_day_increments_streak(self, db):
        record_completion(db, "user1", "2026-02-15", "Europe/Istanbul")
        result = record_completion(db, "user1", "2026-02-16", "Europe/Istanbul")
        
        assert result["currentStreak"] == 2
        assert result["longestStreak"] == 2
    
    def test_three_consecutive_days(self, db):
        record_completion(db, "user1", "2026-02-14", "Europe/Istanbul")
        record_completion(db, "user1", "2026-02-15", "Europe/Istanbul")
        result = record_completion(db, "user1", "2026-02-16", "Europe/Istanbul")
        
        assert result["currentStreak"] == 3
        assert result["longestStreak"] == 3


# ======================== TESTS: STREAK RESET ========================

class TestStreakReset:
    def test_gap_resets_streak_to_1(self, db):
        record_completion(db, "user1", "2026-02-13", "Europe/Istanbul")
        record_completion(db, "user1", "2026-02-14", "Europe/Istanbul")
        # Skip 2026-02-15
        result = record_completion(db, "user1", "2026-02-16", "Europe/Istanbul")
        
        assert result["currentStreak"] == 1
        assert result["longestStreak"] == 2  # Previous streak preserved
    
    def test_longest_streak_never_decreases(self, db):
        # Build a 3-day streak
        record_completion(db, "user1", "2026-02-10", "UTC")
        record_completion(db, "user1", "2026-02-11", "UTC")
        record_completion(db, "user1", "2026-02-12", "UTC")
        
        # Gap → reset
        result = record_completion(db, "user1", "2026-02-16", "UTC")
        
        assert result["currentStreak"] == 1
        assert result["longestStreak"] == 3


# ======================== TESTS: DUPLICATE SAME-DAY ========================

class TestDuplicateCompletion:
    def test_duplicate_returns_isDuplicate_true(self, db):
        record_completion(db, "user1", "2026-02-16", "Europe/Istanbul")
        result = record_completion(db, "user1", "2026-02-16", "Europe/Istanbul")
        
        assert result["isDuplicate"] == True
    
    def test_duplicate_does_not_change_streak(self, db):
        record_completion(db, "user1", "2026-02-15", "UTC")
        record_completion(db, "user1", "2026-02-16", "UTC")
        
        # Duplicate
        result = record_completion(db, "user1", "2026-02-16", "UTC")
        
        assert result["isDuplicate"] == True
        assert result["currentStreak"] == 2  # Unchanged


# ======================== TESTS: ANTI-CHEAT ========================

class TestAntiCheat:
    def test_future_date_rejected(self, db):
        future = (date.today() + timedelta(days=5)).isoformat()
        
        with pytest.raises(InvalidCompletionError, match="Future date"):
            _validate_completion(future, "UTC", datetime.utcnow())
    
    def test_backdate_beyond_limit_rejected(self, db):
        old_date = (date.today() - timedelta(days=MAX_BACKDATE_DAYS + 5)).isoformat()
        
        with pytest.raises(InvalidCompletionError, match="Backdate rejected"):
            _validate_completion(old_date, "UTC", datetime.utcnow())
    
    def test_invalid_timezone_rejected(self, db):
        with pytest.raises(InvalidCompletionError, match="Unknown timezone"):
            _validate_completion("2026-02-16", "Fake/Zone", datetime.utcnow())
    
    def test_invalid_date_format_rejected(self, db):
        with pytest.raises(InvalidCompletionError, match="Invalid date format"):
            _validate_completion("not-a-date", "UTC", datetime.utcnow())
    
    def test_valid_date_passes(self, db):
        today = date.today().isoformat()
        # Should not raise
        _validate_completion(today, "UTC", datetime.utcnow())


# ======================== TESTS: OFFLINE BATCH SYNC ========================

class TestOfflineBatchSync:
    def test_batch_processes_chronologically(self, db):
        completions = [
            {"taskId": "t3", "completionLocalDate": "2026-02-16", "timezoneIdentifier": "UTC"},
            {"taskId": "t1", "completionLocalDate": "2026-02-14", "timezoneIdentifier": "UTC"},
            {"taskId": "t2", "completionLocalDate": "2026-02-15", "timezoneIdentifier": "UTC"},
        ]
        
        result = validate_offline_completions(db, "user1", completions)
        
        assert result["totalNew"] == 3
        assert result["totalDuplicate"] == 0
        assert result["finalStreak"]["currentStreak"] == 3
    
    def test_batch_handles_duplicates(self, db):
        record_completion(db, "user1", "2026-02-15", "UTC")
        
        completions = [
            {"taskId": "t1", "completionLocalDate": "2026-02-15", "timezoneIdentifier": "UTC"},
            {"taskId": "t2", "completionLocalDate": "2026-02-16", "timezoneIdentifier": "UTC"},
        ]
        
        result = validate_offline_completions(db, "user1", completions)
        
        assert result["totalDuplicate"] == 1
        assert result["totalNew"] == 1
    
    def test_batch_rejects_invalid(self, db):
        completions = [
            {"taskId": "t1"},  # Missing date
        ]
        
        result = validate_offline_completions(db, "user1", completions)
        
        assert result["totalRejected"] == 1


# ======================== TESTS: FULL RECALCULATION ========================

class TestFullRecalculation:
    def test_recalculate_from_completions(self, db):
        # Manually insert completions
        for d in ["2026-02-13", "2026-02-14", "2026-02-15"]:
            db.habit_completions.insert_one({
                "userId": "user1",
                "completion_local_date": d,
                "completion_timestamp_utc": datetime.utcnow(),
                "timezone_identifier": "UTC",
                "source": "test",
                "created_at": datetime.utcnow()
            })
        
        result = calculate_streak_from_completions(db, "user1")
        
        assert result["longestStreak"] == 3
        assert result["lastCompletedDate"] == "2026-02-15"
    
    def test_recalculate_empty(self, db):
        result = calculate_streak_from_completions(db, "user1")
        
        assert result["currentStreak"] == 0
        assert result["longestStreak"] == 0
        assert result["lastCompletedDate"] is None
