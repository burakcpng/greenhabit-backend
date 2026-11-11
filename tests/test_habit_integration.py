"""
Integration tests against a REAL MongoDB (v1.5 habit indexes).

Skipped unless MONGO_TEST_URI is set. Run locally with Docker:

    docker run -d --rm --name gh-mongo-test -p 27018:27017 mongo:7
    MONGO_TEST_URI="mongodb://localhost:27018" python3 -m pytest tests/test_habit_integration.py -v
    docker stop gh-mongo-test

Safety: every test uses its own freshly created database named
"gh_it_<random>" and drops it afterwards. No existing database is read or
written, so pointing MONGO_TEST_URI at a shared server cannot touch real data
(still: use a disposable instance).
"""

import os
import sys
import uuid
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

MONGO_TEST_URI = os.environ.get("MONGO_TEST_URI")

pytestmark = pytest.mark.skipif(
    not MONGO_TEST_URI,
    reason="MONGO_TEST_URI not set (see module docstring for the Docker command)",
)

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

import habit_system


USER = "it-user-1"


def day(offset: int = 0) -> str:
    return (habit_system.today_for("UTC") + timedelta(days=offset)).isoformat()


@pytest.fixture
def db():
    client = MongoClient(MONGO_TEST_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    name = f"gh_it_{uuid.uuid4().hex[:12]}"
    try:
        yield client[name]
    finally:
        client.drop_database(name)
        client.close()


def legacy_task_documents():
    """Shapes that exist in production today (pre-v1.5), none with habitId."""
    now = datetime.utcnow()
    return [
        # Normal manual tasks: several for the same user on the same day
        {"id": str(uuid.uuid4()), "userId": USER, "title": "Legacy A", "details": "", "category": "Energy",
         "date": "2026-06-01", "points": 10, "estimatedImpact": "Saves ~1.0kg CO₂", "co2Kg": 1.0,
         "evidenceImagePath": None, "creatorType": "user", "sharedBy": None,
         "isCompleted": False, "completedAt": None, "createdAt": now, "updatedAt": now},
        {"id": str(uuid.uuid4()), "userId": USER, "title": "Legacy B", "details": "", "category": "Water",
         "date": "2026-06-01", "points": 5, "estimatedImpact": "Saves ~0.5kg CO₂", "co2Kg": 0.5,
         "creatorType": "system", "isCompleted": True, "completedAt": now,
         "earnedPoints": 12, "bonuses": {"streak": 2, "category": 5, "time": 0},
         "createdAt": now, "updatedAt": now},
        {"id": str(uuid.uuid4()), "userId": USER, "title": "Legacy C (reversed)", "details": "", "category": "Food",
         "date": "2026-06-01", "points": 8, "estimatedImpact": "", "isCompleted": False,
         "wasReversed": True, "likeCount": 3, "addCount": 1, "createdAt": now, "updatedAt": now},
        # Very old task: no custom `id` (addressed by _id), no creatorType
        {"userId": USER, "title": "Legacy D (no id)", "details": "", "category": "Waste",
         "date": "2026-06-01", "points": 10, "isCompleted": False, "createdAt": now},
        # Accepted team share: extra keys, no co2Kg
        {"id": str(uuid.uuid4()), "userId": USER, "title": "Legacy E (team share)", "details": "",
         "category": "Social", "date": "2026-06-02", "points": 10, "estimatedImpact": None,
         "isCompleted": False, "sharedBy": "someone", "sharedByTeam": "team-1",
         "createdAt": now, "updatedAt": now},
        # Malformed: no date at all
        {"id": str(uuid.uuid4()), "userId": USER, "title": "Legacy F (no date)", "isCompleted": False,
         "createdAt": now},
        # Another user, same day
        {"id": str(uuid.uuid4()), "userId": "it-user-2", "title": "Other user", "category": "Energy",
         "date": "2026-06-01", "points": 10, "isCompleted": False, "createdAt": now, "updatedAt": now},
    ]


def run_all_startup_index_creation(database):
    """Same calls, same order, as server.startup_event()."""
    from social_system import ensure_social_indexes
    from team_system import ensure_team_indexes
    from streak_system import ensure_streak_indexes
    from block_system import ensure_block_indexes

    ensure_social_indexes(database)
    ensure_team_indexes(database)
    ensure_streak_indexes(database)
    ensure_block_indexes(database)
    habit_system.ensure_habit_indexes(database)


# ======================== STARTUP INDEXES ON LEGACY DATA ========================

class TestStartupIndexesOnLegacyData:
    def test_all_startup_indexes_build_on_existing_legacy_tasks(self, db):
        db.tasks.insert_many(legacy_task_documents())
        legacy_count = db.tasks.count_documents({})

        run_all_startup_index_creation(db)

        indexes = db.tasks.index_information()
        assert "unique_user_habit_date" in indexes
        assert "task_user_date" in indexes
        assert db.tasks.count_documents({}) == legacy_count      # nothing dropped or rewritten

    def test_startup_index_creation_is_repeatable(self, db):
        """Every deploy/restart runs the hook again; it must be a no-op, not an error."""
        db.tasks.insert_many(legacy_task_documents())
        run_all_startup_index_creation(db)
        before = db.tasks.index_information()
        run_all_startup_index_creation(db)
        assert db.tasks.index_information() == before

    def test_partial_index_definition_on_the_server(self, db):
        habit_system.ensure_habit_indexes(db)
        index = db.tasks.index_information()["unique_user_habit_date"]
        assert index["unique"] is True
        assert index["key"] == [("userId", 1), ("habitId", 1), ("date", 1)]
        assert dict(index["partialFilterExpression"]) == {"habitId": {"$type": "string"}}

        habit_indexes = db.habits.index_information()
        assert habit_indexes["habit_id_unique"]["unique"] is True
        assert habit_indexes["habit_user_active"]["key"] == [("userId", 1), ("active", 1)]

    def test_legacy_tasks_stay_writable_after_indexing(self, db):
        db.tasks.insert_many(legacy_task_documents())
        run_all_startup_index_creation(db)
        # Completing / editing legacy rows must not hit the new unique index
        result = db.tasks.update_many({"userId": USER, "date": "2026-06-01"}, {"$set": {"isCompleted": True}})
        assert result.modified_count >= 3


# ======================== PARTIAL UNIQUE INDEX SEMANTICS ========================

class TestPartialUniqueIndex:
    def test_multiple_one_off_tasks_per_user_per_day(self, db):
        habit_system.ensure_habit_indexes(db)
        for n in range(5):
            db.tasks.insert_one({"id": str(uuid.uuid4()), "userId": USER, "date": day(), "title": f"One-off {n}"})
        assert db.tasks.count_documents({"userId": USER, "date": day()}) == 5

    def test_one_off_tasks_with_explicit_null_habit_id(self, db):
        """Explicit nulls must not collide either ($type: "string" excludes null)."""
        habit_system.ensure_habit_indexes(db)
        for n in range(3):
            db.tasks.insert_one({"id": str(uuid.uuid4()), "userId": USER, "date": day(), "habitId": None})
        assert db.tasks.count_documents({"userId": USER}) == 3

    def test_duplicate_user_habit_date_is_rejected(self, db):
        habit_system.ensure_habit_indexes(db)
        db.tasks.insert_one({"id": "a", "userId": USER, "date": day(), "habitId": "habit-1"})
        with pytest.raises(DuplicateKeyError):
            db.tasks.insert_one({"id": "b", "userId": USER, "date": day(), "habitId": "habit-1"})
        assert db.tasks.count_documents({"habitId": "habit-1"}) == 1

    def test_same_habit_other_day_or_other_user_is_allowed(self, db):
        habit_system.ensure_habit_indexes(db)
        db.tasks.insert_one({"id": "a", "userId": USER, "date": day(), "habitId": "habit-1"})
        db.tasks.insert_one({"id": "b", "userId": USER, "date": day(1), "habitId": "habit-1"})
        db.tasks.insert_one({"id": "c", "userId": "it-user-2", "date": day(), "habitId": "habit-1"})
        db.tasks.insert_one({"id": "d", "userId": USER, "date": day(), "habitId": "habit-2"})
        assert db.tasks.count_documents({}) == 4

    def test_detaching_frees_the_slot(self, db):
        """Reschedule = $unset habitId. The row must leave the index so the day can re-fill."""
        habit_system.ensure_habit_indexes(db)
        db.tasks.insert_one({"id": "a", "userId": USER, "date": day(), "habitId": "habit-1"})
        db.tasks.update_one({"id": "a"}, {"$unset": {"habitId": ""}, "$set": {"originHabitId": "habit-1"}})
        db.tasks.insert_one({"id": "b", "userId": USER, "date": day(), "habitId": "habit-1"})
        assert db.tasks.count_documents({"userId": USER, "date": day()}) == 2


# ======================== MATERIALIZATION ON A REAL SERVER ========================

def make_habit(database, **overrides):
    body = {
        "title": "Bike to work", "details": "", "category": "Transport", "co2Kg": 2.4,
        "time": "08:00", "recurrence": {"type": "daily"}, "reminderOffsets": [0, 15],
    }
    body.update(overrides)
    return habit_system.create_habit(database, USER, body, "UTC")


class TestMaterializationOnRealServer:
    def test_materialize_twice_creates_one_row(self, db):
        habit_system.ensure_habit_indexes(db)
        habit = make_habit(db)
        today = habit_system.today_for("UTC")
        assert habit_system.materialize_day(db, USER, today) == 1
        assert habit_system.materialize_day(db, USER, today) == 0
        assert db.tasks.count_documents({"userId": USER, "habitId": habit["id"]}) == 1

    def test_upsert_is_idempotent_when_the_precheck_is_bypassed(self, db, monkeypatch):
        """Two racing requests that both miss the pre-check: the index + upsert still give one row."""
        habit_system.ensure_habit_indexes(db)
        make_habit(db)
        monkeypatch.setattr(habit_system, "_existing_instance_habit_ids", lambda *a, **k: set())
        today = habit_system.today_for("UTC")
        assert habit_system.materialize_day(db, USER, today) == 1
        assert habit_system.materialize_day(db, USER, today) == 0
        assert db.tasks.count_documents({"userId": USER}) == 1

    def test_materialization_next_to_legacy_tasks_on_the_same_day(self, db):
        legacy = legacy_task_documents()
        for doc in legacy:
            if "date" in doc:
                doc["date"] = day()
        db.tasks.insert_many(legacy)
        run_all_startup_index_creation(db)
        make_habit(db)
        make_habit(db, title="Short shower", category="Water", co2Kg=0.5)

        before = db.tasks.count_documents({"userId": USER, "date": day()})
        assert habit_system.materialize_day(db, USER, habit_system.today_for("UTC")) == 2
        assert db.tasks.count_documents({"userId": USER, "date": day()}) == before + 2

    def test_skip_and_virtual_queries(self, db):
        """The $type / $in:[None] / $addToSet queries behave on a real server as in the unit tests."""
        habit_system.ensure_habit_indexes(db)
        habit = make_habit(db)
        today = habit_system.today_for("UTC")
        habit_system.materialize_day(db, USER, today)
        db.tasks.insert_one({"id": "one-off", "userId": USER, "date": day(), "creatorType": "user", "title": "x",
                             "createdAt": datetime.utcnow()})

        assert db.tasks.count_documents({"userId": USER, "habitId": {"$type": "string"}}) == 1
        assert db.tasks.count_documents({"userId": USER, "habitId": {"$in": [None]}}) == 1

        instance = db.tasks.find_one({"userId": USER, "habitId": habit["id"]})
        assert habit_system.register_deleted_instances(db, USER, [instance["id"], "one-off"]) == 1
        habit_system.add_skipped_dates(db, USER, habit["id"], [day(), day(), day(2)])
        assert db.habits.find_one({"id": habit["id"]})["skippedDates"] == [day(), day(2)]

        db.tasks.delete_one({"id": instance["id"]})
        assert habit_system.materialize_day(db, USER, today) == 0          # skipped → not resurrected
        tomorrow = today + timedelta(days=1)
        assert len(habit_system.virtual_occurrences(db, USER, tomorrow)) == 1
        assert habit_system.virtual_occurrences(db, USER, today + timedelta(days=2)) == []

        counts = habit_system.calendar_virtual_counts(db, USER, tomorrow.year, tomorrow.month)
        assert counts.get(tomorrow.isoformat()) == 1
