"""
Tests for the v1.5 habit system (habit_system.py + the habit/task endpoints).

Run:  python3 -m pytest tests/test_habit_system.py -v
Needs the dev-only package `mongomock` (in-memory MongoDB, supports the
partial unique index these tests rely on):  pip install mongomock

All integration dates are relative to "today in UTC" and every request uses
tz=UTC, so the suite does not depend on the machine's local timezone.
"""

import os
import sys
import uuid
from datetime import date, datetime, timedelta

os.environ.setdefault("JWT_SECRET", "test-secret-for-habit-tests-0123456789abcdef")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import mongomock
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

import habit_system
import server
from auth_system import get_current_user
from habit_system import (
    HabitError,
    MAX_ACTIVE_HABITS,
    compute_points,
    materialize_day,
    normalize_recurrence,
    normalize_reminder_offsets,
    occurs_on,
    parse_date,
    parse_virtual_id,
    validate_time,
    virtual_id,
)


# ======================== HELPERS ========================

def today() -> date:
    return habit_system.today_for("UTC")


def d(offset: int) -> str:
    """YYYY-MM-DD for UTC today + offset days."""
    return (today() + timedelta(days=offset)).isoformat()


def habit_body(**overrides) -> dict:
    body = {
        "title": "Bike to work",
        "details": "Leave the car at home",
        "category": "Transport",
        "co2Kg": 2.4,
        "time": "08:00",
        "recurrence": {"type": "daily"},
        "reminderOffsets": [0, 15],
    }
    body.update(overrides)
    return body


def habit_doc(**overrides) -> dict:
    """A stored habit document for pure-function tests."""
    doc = {
        "id": "h1",
        "userId": "u1",
        "active": True,
        "startDate": "2026-03-02",   # a Monday
        "endDate": None,
        "skippedDates": [],
        "recurrence": {"type": "daily"},
    }
    doc.update(overrides)
    return doc


# ======================== FIXTURES ========================

@pytest.fixture
def db():
    database = mongomock.MongoClient().greenhabit_test
    habit_system.ensure_habit_indexes(database)
    return database


@pytest.fixture
def user_id():
    # Unique per test: the rate limiter keeps in-memory state per user.
    return f"user-{uuid.uuid4()}"


@pytest.fixture
def client(db, user_id, monkeypatch):
    monkeypatch.setattr(server, "get_db", lambda: db)
    # The 5-second toggle cooldown is unrelated to habits and would make
    # "create then complete" tests wait.
    monkeypatch.setattr(server, "check_toggle_cooldown", lambda *a, **k: True)
    server.app.dependency_overrides[get_current_user] = lambda: user_id
    yield TestClient(server.app)
    server.app.dependency_overrides.clear()


def create_habit(client, **overrides) -> dict:
    response = client.post("/api/habits?tz=UTC", json=habit_body(**overrides))
    assert response.status_code == 201, response.text
    return response.json()["habit"]


def get_tasks(client, day: str, tz: str = "UTC", **params) -> list:
    query = {"date": day, **params}
    if tz is not None:
        query["tz"] = tz
    response = client.get("/api/tasks", params=query)
    assert response.status_code == 200, response.text
    return response.json()


# ======================== VALIDATION (pure) ========================

class TestValidation:
    def test_recurrence_daily_is_normalized(self):
        assert normalize_recurrence({"type": "daily", "weekdays": [1], "interval": 3}) == {"type": "daily"}

    def test_recurrence_weekdays_sorted_and_deduped(self):
        assert normalize_recurrence({"type": "weekdays", "weekdays": [5, 1, 5, 3]}) == {
            "type": "weekdays", "weekdays": [1, 3, 5]
        }

    @pytest.mark.parametrize("weekdays", [None, [], [0], [8], ["1"], [True], [1.5]])
    def test_recurrence_weekdays_rejects_bad_values(self, weekdays):
        with pytest.raises(HabitError) as exc:
            normalize_recurrence({"type": "weekdays", "weekdays": weekdays})
        assert exc.value.status_code == 422

    def test_recurrence_every_n_days(self):
        assert normalize_recurrence({"type": "everyNDays", "interval": 3}) == {"type": "everyNDays", "interval": 3}

    @pytest.mark.parametrize("interval", [None, 0, -1, 366, "2", True])
    def test_recurrence_every_n_days_rejects_bad_interval(self, interval):
        with pytest.raises(HabitError):
            normalize_recurrence({"type": "everyNDays", "interval": interval})

    @pytest.mark.parametrize("raw", [None, {}, {"type": "monthly"}, "daily"])
    def test_recurrence_rejects_unknown_type(self, raw):
        with pytest.raises(HabitError):
            normalize_recurrence(raw)

    def test_reminder_offsets_sorted_and_deduped(self):
        assert normalize_reminder_offsets([15, 0, 15], "08:00") == [0, 15]

    def test_reminder_offsets_max_two(self):
        with pytest.raises(HabitError):
            normalize_reminder_offsets([0, 15, 60], "08:00")

    def test_reminder_offsets_must_be_empty_for_all_day(self):
        with pytest.raises(HabitError) as exc:
            normalize_reminder_offsets([0], None)
        assert exc.value.status_code == 422
        assert normalize_reminder_offsets([], None) == []
        assert normalize_reminder_offsets(None, None) == []

    @pytest.mark.parametrize("offsets", [[-1], [1441], ["15"], [1.5], [True], "15"])
    def test_reminder_offsets_reject_bad_values(self, offsets):
        with pytest.raises(HabitError):
            normalize_reminder_offsets(offsets, "08:00")

    @pytest.mark.parametrize("value", ["00:00", "07:30", "23:59"])
    def test_time_valid(self, value):
        assert validate_time(value) == value

    @pytest.mark.parametrize("value", ["24:00", "7:30", "07:60", "0730", "07:30:00", "", 730])
    def test_time_invalid(self, value):
        with pytest.raises(HabitError):
            validate_time(value)

    def test_time_none_means_all_day(self):
        assert validate_time(None) is None

    @pytest.mark.parametrize("value", ["2026-02-30", "20260301", "2026-3-1", "01-03-2026", "", None, 20260301])
    def test_parse_date_is_strict(self, value):
        with pytest.raises(HabitError):
            parse_date(value)

    def test_points_match_task_formula(self):
        assert compute_points(2.4) == 24
        assert compute_points(0.05) == 1     # ceil
        assert compute_points(0.0) == 0
        assert compute_points(10.0) == 100
        assert compute_points(50.0) == 100   # capped

    def test_virtual_id_roundtrip(self):
        habit_id = str(uuid.uuid4())
        assert parse_virtual_id(virtual_id(habit_id, "2026-03-09")) == (habit_id, "2026-03-09")

    @pytest.mark.parametrize("task_id", [str(uuid.uuid4()), "habit_abc", "habit__2026-03-09x", "", None])
    def test_virtual_id_rejects_normal_ids(self, task_id):
        assert parse_virtual_id(task_id) is None


# ======================== RECURRENCE MATCHING (pure) ========================

class TestOccursOn:
    def test_reference_dates_are_what_the_tests_assume(self):
        assert date(2026, 3, 2).isoweekday() == 1   # Monday
        assert date(2026, 3, 8).isoweekday() == 7   # Sunday

    def test_daily(self):
        habit = habit_doc()
        assert occurs_on(habit, date(2026, 3, 2))
        assert occurs_on(habit, date(2026, 3, 3))
        assert occurs_on(habit, date(2027, 1, 1))

    def test_weekdays_are_iso_monday_is_one(self):
        habit = habit_doc(recurrence={"type": "weekdays", "weekdays": [1, 3, 7]})
        assert occurs_on(habit, date(2026, 3, 2))        # Mon = 1
        assert not occurs_on(habit, date(2026, 3, 3))    # Tue = 2
        assert occurs_on(habit, date(2026, 3, 4))        # Wed = 3
        assert not occurs_on(habit, date(2026, 3, 7))    # Sat = 6
        assert occurs_on(habit, date(2026, 3, 8))        # Sun = 7

    def test_every_n_days_anchored_on_start_date(self):
        habit = habit_doc(recurrence={"type": "everyNDays", "interval": 3})
        assert occurs_on(habit, date(2026, 3, 2))        # day 0
        assert not occurs_on(habit, date(2026, 3, 3))
        assert not occurs_on(habit, date(2026, 3, 4))
        assert occurs_on(habit, date(2026, 3, 5))        # day 3
        assert occurs_on(habit, date(2026, 3, 8))        # day 6
        # Moving the anchor moves the whole series
        shifted = habit_doc(startDate="2026-03-03", recurrence={"type": "everyNDays", "interval": 3})
        assert occurs_on(shifted, date(2026, 3, 3))
        assert not occurs_on(shifted, date(2026, 3, 5))
        assert occurs_on(shifted, date(2026, 3, 6))

    def test_every_one_day_is_daily(self):
        habit = habit_doc(recurrence={"type": "everyNDays", "interval": 1})
        assert all(occurs_on(habit, date(2026, 3, n)) for n in range(2, 12))

    def test_not_before_start_date(self):
        habit = habit_doc()
        assert not occurs_on(habit, date(2026, 3, 1))
        assert occurs_on(habit, date(2026, 3, 2))

    def test_end_date_is_inclusive(self):
        habit = habit_doc(endDate="2026-03-05")
        assert occurs_on(habit, date(2026, 3, 5))
        assert not occurs_on(habit, date(2026, 3, 6))

    def test_skipped_dates(self):
        habit = habit_doc(skippedDates=["2026-03-04"])
        assert occurs_on(habit, date(2026, 3, 3))
        assert not occurs_on(habit, date(2026, 3, 4))
        assert occurs_on(habit, date(2026, 3, 5))

    def test_skipped_date_does_not_shift_every_n_days(self):
        habit = habit_doc(recurrence={"type": "everyNDays", "interval": 2}, skippedDates=["2026-03-04"])
        assert occurs_on(habit, date(2026, 3, 2))
        assert not occurs_on(habit, date(2026, 3, 4))    # skipped
        assert occurs_on(habit, date(2026, 3, 6))        # series unchanged

    def test_inactive_habit_never_occurs(self):
        assert not occurs_on(habit_doc(active=False), date(2026, 3, 2))

    def test_malformed_habit_never_occurs(self):
        assert not occurs_on(habit_doc(startDate=None), date(2026, 3, 2))
        assert not occurs_on(habit_doc(recurrence={"type": "monthly"}), date(2026, 3, 2))


# ======================== MATERIALIZATION ========================

class TestMaterialization:
    def test_materialize_twice_creates_one_row(self, db, client, user_id):
        habit = create_habit(client)
        assert materialize_day(db, user_id, today()) == 1
        assert materialize_day(db, user_id, today()) == 0
        assert db.tasks.count_documents({"userId": user_id, "habitId": habit["id"]}) == 1

    def test_upsert_itself_is_idempotent_without_the_precheck(self, db, client, user_id, monkeypatch):
        """Simulates two concurrent requests that both miss the existence pre-check."""
        create_habit(client)
        monkeypatch.setattr(habit_system, "_existing_instance_habit_ids", lambda *a, **k: set())
        assert materialize_day(db, user_id, today()) == 1
        assert materialize_day(db, user_id, today()) == 0
        assert db.tasks.count_documents({"userId": user_id}) == 1

    def test_get_tasks_twice_returns_one_instance(self, db, client, user_id):
        habit = create_habit(client)
        first = get_tasks(client, d(0))
        second = get_tasks(client, d(0))
        assert len(first) == len(second) == 1
        assert first[0]["id"] == second[0]["id"]
        assert db.tasks.count_documents({"userId": user_id}) == 1
        assert first[0]["habitId"] == habit["id"]

    def test_instance_copies_habit_fields(self, client):
        habit = create_habit(client, co2Kg=1.5, time="07:30")
        task = get_tasks(client, d(0))[0]
        assert task["title"] == "Bike to work"
        assert task["details"] == "Leave the car at home"
        assert task["category"] == "Transport"
        assert task["time"] == "07:30"
        assert task["date"] == d(0)
        assert task["co2Kg"] == 1.5
        assert task["points"] == 15
        assert task["estimatedImpact"] == "Saves ~1.5kg CO₂"
        assert task["isCompleted"] is False
        assert task["creatorType"] == "user"
        assert task["habitId"] == habit["id"]
        assert "isVirtual" not in task
        assert not task["id"].startswith("habit_")

    def test_instance_points_equal_one_off_task_points(self, db, client, user_id):
        create_habit(client, co2Kg=3.3)
        instance = get_tasks(client, d(0))[0]
        response = client.post("/api/tasks", json={
            "title": "One-off", "details": "", "category": "Transport",
            "estimatedImpact": "Saves ~3.3kg CO₂", "co2Kg": 3.3, "date": d(0),
        })
        one_off = db.tasks.find_one({"id": response.json()["taskId"]})
        assert instance["points"] == one_off["points"]

    def test_only_due_habits_materialize(self, db, client, user_id):
        weekday_today = today().isoweekday()
        other_weekday = weekday_today % 7 + 1
        due = create_habit(client, title="Due today", recurrence={"type": "weekdays", "weekdays": [weekday_today]})
        create_habit(client, title="Not today", recurrence={"type": "weekdays", "weekdays": [other_weekday]})
        tasks = get_tasks(client, d(0))
        assert [t["habitId"] for t in tasks] == [due["id"]]

    def test_past_day_since_start_materializes_on_first_open(self, db, client, user_id):
        create_habit(client, startDate=d(-1))
        assert db.tasks.count_documents({"userId": user_id}) == 0   # nothing until fetched
        tasks = get_tasks(client, d(-1))
        assert len(tasks) == 1 and tasks[0]["date"] == d(-1)

    def test_day_before_start_date_gets_nothing(self, db, client, user_id):
        create_habit(client)
        assert get_tasks(client, d(-1)) == []
        assert db.tasks.count_documents({"userId": user_id}) == 0

    def test_other_users_habits_are_not_materialized(self, db, client, user_id):
        habit_system.create_habit(db, "someone-else", habit_body(), "UTC")
        assert get_tasks(client, d(0)) == []
        assert db.tasks.count_documents({}) == 0

    def test_fresh_instance_is_not_blocked_by_toggle_cooldown(self, db, client, user_id):
        """updatedAt comes from the habit, so a day opened later can be completed at once."""
        create_habit(client)
        db.habits.update_many({"userId": user_id}, {"$set": {"updatedAt": datetime(2026, 1, 1)}})
        task = get_tasks(client, d(0))[0]
        stored = db.tasks.find_one({"id": task["id"]})
        assert stored["updatedAt"] == datetime(2026, 1, 1)


# ======================== PARTIAL UNIQUE INDEX ========================

class TestPartialUniqueIndex:
    def test_index_is_partial_on_string_habit_id(self, db):
        index = db.tasks.index_information()["unique_user_habit_date"]
        assert index["unique"] is True
        assert index["partialFilterExpression"] == {"habitId": {"$type": "string"}}

    def test_multiple_one_off_tasks_on_the_same_day(self, db, client, user_id):
        for n in range(3):
            response = client.post("/api/tasks", json={
                "title": f"One-off {n}", "details": "", "category": "Energy",
                "estimatedImpact": "Saves ~0.5kg CO₂", "date": d(0),
            })
            assert response.status_code == 201, response.text
        assert db.tasks.count_documents({"userId": user_id, "date": d(0)}) == 3

    def test_one_off_tasks_with_explicit_null_habit_id_do_not_collide(self, db, user_id):
        db.tasks.insert_one({"id": "a", "userId": user_id, "date": d(0), "habitId": None})
        db.tasks.insert_one({"id": "b", "userId": user_id, "date": d(0), "habitId": None})
        assert db.tasks.count_documents({"userId": user_id}) == 2

    def test_duplicate_instance_is_rejected(self, db, user_id):
        db.tasks.insert_one({"id": "a", "userId": user_id, "date": d(0), "habitId": "h1"})
        with pytest.raises(DuplicateKeyError):
            db.tasks.insert_one({"id": "b", "userId": user_id, "date": d(0), "habitId": "h1"})

    def test_same_habit_on_other_day_or_other_user_is_allowed(self, db, user_id):
        db.tasks.insert_one({"id": "a", "userId": user_id, "date": d(0), "habitId": "h1"})
        db.tasks.insert_one({"id": "b", "userId": user_id, "date": d(1), "habitId": "h1"})
        db.tasks.insert_one({"id": "c", "userId": "other", "date": d(0), "habitId": "h1"})
        assert db.tasks.count_documents({}) == 3


# ======================== VIRTUAL FUTURE OCCURRENCES ========================

class TestVirtualOccurrences:
    def test_future_date_returns_virtual_and_writes_nothing(self, db, client, user_id):
        habit = create_habit(client)
        tasks = get_tasks(client, d(3))
        assert len(tasks) == 1
        task = tasks[0]
        assert task["id"] == f"habit_{habit['id']}_{d(3)}"
        assert task["isVirtual"] is True
        assert task["habitId"] == habit["id"]
        assert task["date"] == d(3)
        assert task["isCompleted"] is False
        assert task["time"] == "08:00"
        assert task["points"] == 24
        assert task["estimatedImpact"] == "Saves ~2.4kg CO₂"
        assert task["createdAt"].endswith("Z")
        assert db.tasks.count_documents({"userId": user_id}) == 0

    def test_tomorrow_is_virtual_today_is_real(self, db, client, user_id):
        create_habit(client)
        assert "isVirtual" not in get_tasks(client, d(0))[0]
        assert get_tasks(client, d(1))[0]["isVirtual"] is True
        assert db.tasks.count_documents({"userId": user_id}) == 1

    def test_virtual_respects_end_date_and_recurrence(self, client):
        create_habit(client, recurrence={"type": "everyNDays", "interval": 2}, endDate=d(4))
        assert len(get_tasks(client, d(1))) == 0
        assert len(get_tasks(client, d(2))) == 1
        assert len(get_tasks(client, d(4))) == 1
        assert len(get_tasks(client, d(6))) == 0      # after endDate

    def test_virtual_mixed_with_real_one_off_tasks(self, client):
        create_habit(client)
        client.post("/api/tasks", json={
            "title": "Future one-off", "details": "", "category": "Energy",
            "estimatedImpact": "Saves ~0.5kg CO₂", "date": d(2),
        })
        tasks = get_tasks(client, d(2))
        assert len(tasks) == 2
        assert sorted(bool(t.get("isVirtual")) for t in tasks) == [False, True]

    def test_completed_filter_excludes_virtual(self, client):
        create_habit(client)
        assert get_tasks(client, d(2), completed="true") == []
        assert len(get_tasks(client, d(2), completed="false")) == 1

    def test_category_filter_applies_to_virtual(self, client):
        create_habit(client)
        assert len(get_tasks(client, d(2), category="Transport")) == 1
        assert get_tasks(client, d(2), category="Water") == []

    def test_virtual_cannot_be_completed(self, db, client, user_id):
        habit = create_habit(client)
        response = client.patch(f"/api/tasks/habit_{habit['id']}_{d(2)}", json={
            "isCompleted": True, "completionLocalDate": d(0), "timezoneIdentifier": "UTC",
        })
        assert response.status_code == 400
        assert "can't be completed" in response.json()["detail"]
        assert db.tasks.count_documents({"userId": user_id}) == 0

    def test_virtual_cannot_be_edited_only_rescheduled(self, client):
        habit = create_habit(client)
        response = client.patch(f"/api/tasks/habit_{habit['id']}_{d(2)}", json={"title": "New title"})
        assert response.status_code == 400

    def test_reschedule_virtual_creates_detached_one_off_and_skips_original(self, db, client, user_id):
        habit = create_habit(client)
        response = client.patch(f"/api/tasks/habit_{habit['id']}_{d(2)}", json={"date": d(5), "time": "18:15"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["detached"] is True and body["originHabitId"] == habit["id"]

        moved = db.tasks.find_one({"id": body["taskId"]})
        assert moved["date"] == d(5) and moved["time"] == "18:15"
        assert moved["originHabitId"] == habit["id"]
        assert "habitId" not in moved
        assert moved["title"] == "Bike to work" and moved["points"] == 24
        assert moved["category"] == "Transport" and moved["isCompleted"] is False

        assert d(2) in db.habits.find_one({"id": habit["id"]})["skippedDates"]
        assert get_tasks(client, d(2)) == []                      # original occurrence gone
        on_target = get_tasks(client, d(5))                        # one-off + the habit's own occurrence
        assert len(on_target) == 2
        assert sorted(bool(t.get("isVirtual")) for t in on_target) == [False, True]

    def test_reschedule_virtual_date_only_keeps_habit_time(self, db, client):
        habit = create_habit(client, time="06:45")
        response = client.patch(f"/api/tasks/habit_{habit['id']}_{d(2)}", json={"date": d(3)})
        assert db.tasks.find_one({"id": response.json()["taskId"]})["time"] == "06:45"

    def test_reschedule_virtual_time_only(self, db, client):
        habit = create_habit(client)
        response = client.patch(f"/api/tasks/habit_{habit['id']}_{d(2)}", json={"time": "20:00"})
        assert response.status_code == 200
        moved = db.tasks.find_one({"id": response.json()["taskId"]})
        assert moved["date"] == d(2) and moved["time"] == "20:00"
        tasks = get_tasks(client, d(2))
        assert len(tasks) == 1 and tasks[0]["id"] == moved["id"]   # no virtual twin

    def test_reschedule_virtual_without_change_is_rejected(self, db, client, user_id):
        habit = create_habit(client)
        response = client.patch(f"/api/tasks/habit_{habit['id']}_{d(2)}", json={"date": d(2), "time": "08:00"})
        assert response.status_code == 400
        assert db.habits.find_one({"id": habit["id"]})["skippedDates"] == []

    def test_reschedule_virtual_validates_input(self, db, client):
        habit = create_habit(client)
        base = f"/api/tasks/habit_{habit['id']}_{d(2)}"
        assert client.patch(base, json={"date": "next tuesday"}).status_code == 422
        assert client.patch(base, json={"time": "25:00"}).status_code == 422
        assert db.habits.find_one({"id": habit["id"]})["skippedDates"] == []

    def test_virtual_id_of_unknown_or_non_occurring_habit_is_404(self, client):
        assert client.patch(f"/api/tasks/habit_{uuid.uuid4()}_{d(2)}", json={"date": d(3)}).status_code == 404
        habit = create_habit(client, endDate=d(1))
        assert client.patch(f"/api/tasks/habit_{habit['id']}_{d(2)}", json={"date": d(3)}).status_code == 404

    def test_virtual_id_of_another_users_habit_is_404(self, db, client):
        other = habit_system.create_habit(db, "someone-else", habit_body(), "UTC")
        response = client.patch(f"/api/tasks/habit_{other['id']}_{d(2)}", json={"date": d(3)})
        assert response.status_code == 404
        assert db.tasks.count_documents({}) == 0

    def test_virtual_id_resolves_to_real_row_once_materialized(self, db, client, user_id):
        """A client holding yesterday's virtual id can still act on today's real instance."""
        habit = create_habit(client)
        real = get_tasks(client, d(0))[0]
        response = client.patch(f"/api/tasks/habit_{habit['id']}_{d(0)}", json={
            "isCompleted": True, "completionLocalDate": d(0), "timezoneIdentifier": "UTC",
        })
        assert response.status_code == 200, response.text
        assert db.tasks.find_one({"id": real["id"]})["isCompleted"] is True

    def test_existing_row_on_future_date_suppresses_virtual(self, db, client, user_id):
        """E.g. a row materialized before the user travelled west."""
        habit = create_habit(client)
        db.tasks.insert_one({
            "id": "real-future", "userId": user_id, "habitId": habit["id"], "date": d(1),
            "title": "Bike to work", "isCompleted": False, "createdAt": datetime.utcnow(),
        })
        tasks = get_tasks(client, d(1))
        assert [t["id"] for t in tasks] == ["real-future"]


# ======================== TIMEZONE HANDLING ========================

class TestTimezone:
    def test_tz_decides_what_today_is(self, db, client, user_id, monkeypatch):
        real_today = today()
        ahead = {"Pacific/Kiritimati": real_today + timedelta(days=1)}
        monkeypatch.setattr(habit_system, "user_today", lambda tz: ahead.get(tz, real_today))
        create_habit(client)
        tomorrow = (real_today + timedelta(days=1)).isoformat()

        assert get_tasks(client, tomorrow, tz="UTC")[0]["isVirtual"] is True
        assert db.tasks.count_documents({"userId": user_id}) == 0

        in_kiritimati = get_tasks(client, tomorrow, tz="Pacific/Kiritimati")
        assert "isVirtual" not in in_kiritimati[0]
        assert db.tasks.count_documents({"userId": user_id}) == 1

    def test_resolve_tz(self):
        assert habit_system.resolve_tz("Europe/Istanbul") == "Europe/Istanbul"
        assert habit_system.resolve_tz(" UTC ") == "UTC"
        for bad in [None, "", "Mars/Olympus", "GMT+25", 3]:
            assert habit_system.resolve_tz(bad) is None

    def test_create_task_without_date_uses_user_today_when_tz_sent(self, db, client, monkeypatch):
        import streak_system
        monkeypatch.setattr(streak_system, "user_today", lambda tz: date(2031, 5, 6))
        response = client.post("/api/tasks?tz=Europe/Istanbul", json={
            "title": "No date", "details": "", "category": "Energy", "estimatedImpact": "Saves ~0.5kg CO₂",
        })
        assert db.tasks.find_one({"id": response.json()["taskId"]})["date"] == "2031-05-06"

    def test_create_task_without_date_and_tz_keeps_legacy_server_date(self, db, client, monkeypatch):
        import streak_system
        monkeypatch.setattr(streak_system, "user_today", lambda tz: date(2031, 5, 6))
        for url in ["/api/tasks", "/api/tasks?tz=Not/AZone"]:
            response = client.post(url, json={
                "title": "No date", "details": "", "category": "Energy", "estimatedImpact": "Saves ~0.5kg CO₂",
            })
            assert db.tasks.find_one({"id": response.json()["taskId"]})["date"] == date.today().isoformat()

    def test_create_task_explicit_date_always_wins(self, db, client):
        response = client.post("/api/tasks?tz=UTC", json={
            "title": "Dated", "details": "", "category": "Energy",
            "estimatedImpact": "Saves ~0.5kg CO₂", "date": "2030-01-02",
        })
        assert db.tasks.find_one({"id": response.json()["taskId"]})["date"] == "2030-01-02"


# ======================== LEGACY BEHAVIOUR (tz absent) ========================

class TestLegacyClients:
    def test_get_tasks_without_tz_never_materializes(self, db, client, user_id):
        create_habit(client)
        assert get_tasks(client, d(0), tz=None) == []
        assert get_tasks(client, d(3), tz=None) == []
        assert db.tasks.count_documents({"userId": user_id}) == 0

    def test_get_tasks_with_invalid_tz_behaves_like_no_tz(self, db, client, user_id):
        create_habit(client)
        assert get_tasks(client, d(0), tz="Mars/Olympus") == []
        assert get_tasks(client, d(3), tz="Mars/Olympus") == []
        assert db.tasks.count_documents({"userId": user_id}) == 0

    def test_get_tasks_without_date_is_untouched(self, db, client, user_id):
        create_habit(client)
        response = client.get("/api/tasks", params={"tz": "UTC"})
        assert response.status_code == 200 and response.json() == []
        assert db.tasks.count_documents({"userId": user_id}) == 0

    def test_legacy_client_still_sees_already_materialized_instances(self, client):
        create_habit(client)
        materialized = get_tasks(client, d(0))
        legacy_view = get_tasks(client, d(0), tz=None)
        assert [t["id"] for t in legacy_view] == [t["id"] for t in materialized]

    def test_old_ios_create_payload_is_accepted(self, db, client):
        """Exactly what GHDataModels.CreateTaskPayload encodes today (incl. the ignored `points`)."""
        response = client.post("/api/tasks", json={
            "title": "Old client task", "details": "From v1.3", "category": "Energy",
            "date": d(0), "points": 10, "estimatedImpact": "Saves ~1.0kg CO₂",
        })
        assert response.status_code == 201
        assert set(response.json()) == {"success", "taskId", "message"}
        stored = db.tasks.find_one({"id": response.json()["taskId"]})
        assert stored["points"] == 10 and stored["date"] == d(0)
        assert "time" not in stored and "habitId" not in stored    # document shape unchanged

    def test_old_ios_completion_payload_on_one_off_task(self, db, client):
        task_id = client.post("/api/tasks", json={
            "title": "Complete me", "details": "", "category": "Energy",
            "date": d(0), "points": 10, "estimatedImpact": "Saves ~1.0kg CO₂",
        }).json()["taskId"]
        response = client.patch(f"/api/tasks/{task_id}", json={
            "isCompleted": True, "completionLocalDate": d(0), "timezoneIdentifier": "UTC",
        })
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True and body["celebration"] is True
        assert "rewards" in body and "streakInfo" in body
        assert "detached" not in body
        assert db.tasks.find_one({"id": task_id})["isCompleted"] is True

    def test_old_ios_completion_payload_on_habit_instance(self, db, client):
        habit = create_habit(client)
        task = get_tasks(client, d(0))[0]
        response = client.patch(f"/api/tasks/{task['id']}", json={
            "isCompleted": True, "completionLocalDate": d(0), "timezoneIdentifier": "UTC",
        })
        assert response.status_code == 200, response.text
        stored = db.tasks.find_one({"id": task["id"]})
        assert stored["isCompleted"] is True
        assert stored["habitId"] == habit["id"]                      # completing never detaches
        assert stored["earnedPoints"] >= stored["points"]
        assert db.habits.find_one({"id": habit["id"]})["skippedDates"] == []

    def test_patch_echoing_the_current_date_is_a_no_op(self, db, client):
        """A client that sends the whole task back must not trigger a reschedule/detach."""
        habit = create_habit(client)
        task = get_tasks(client, d(0))[0]
        response = client.patch(f"/api/tasks/{task['id']}", json={
            "title": "Renamed", "date": d(0), "time": "08:00",
        })
        assert response.status_code == 200
        stored = db.tasks.find_one({"id": task["id"]})
        assert stored["title"] == "Renamed" and stored["habitId"] == habit["id"]
        assert "originHabitId" not in stored
        assert db.habits.find_one({"id": habit["id"]})["skippedDates"] == []

    def test_patch_with_only_unchanged_date_keeps_old_400(self, client):
        task_id = client.post("/api/tasks", json={
            "title": "T", "details": "", "category": "Energy",
            "date": d(0), "estimatedImpact": "Saves ~1.0kg CO₂",
        }).json()["taskId"]
        response = client.patch(f"/api/tasks/{task_id}", json={"date": d(0)})
        assert response.status_code == 400 and response.json()["detail"] == "No fields to update"

    def test_completed_task_echoing_its_date_is_not_rejected(self, db, client):
        task_id = client.post("/api/tasks", json={
            "title": "T", "details": "", "category": "Energy",
            "date": d(0), "estimatedImpact": "Saves ~1.0kg CO₂",
        }).json()["taskId"]
        db.tasks.update_one({"id": task_id}, {"$set": {"isCompleted": True, "completedAt": datetime.utcnow()}})
        response = client.patch(f"/api/tasks/{task_id}", json={"title": "Edited", "date": d(0)})
        assert response.status_code == 200

    def test_unknown_task_id_is_still_404(self, client):
        assert client.patch(f"/api/tasks/{uuid.uuid4()}", json={"title": "x"}).status_code == 404
        assert client.delete(f"/api/tasks/{uuid.uuid4()}").status_code == 404

    def test_calendar_without_tz_ignores_habits(self, client):
        create_habit(client)
        response = client.get(f"/api/calendar/{today().year}/{today().month}")
        assert response.status_code == 200
        body = response.json()
        assert body["days"] == [] and body["totalTasks"] == 0 and body["allTasksCompleted"] is False
        invalid = client.get(f"/api/calendar/{today().year}/{today().month}", params={"tz": "Mars/Olympus"})
        assert invalid.json() == body


# ======================== RESCHEDULE / DETACH ========================

class TestReschedule:
    def one_off(self, client, **extra) -> str:
        body = {"title": "One-off", "details": "", "category": "Energy",
                "estimatedImpact": "Saves ~1.0kg CO₂", "date": d(0)}
        body.update(extra)
        response = client.post("/api/tasks", json=body)
        assert response.status_code == 201, response.text
        return response.json()["taskId"]

    def test_one_off_task_can_change_date_and_time(self, db, client):
        task_id = self.one_off(client)
        response = client.patch(f"/api/tasks/{task_id}", json={"date": d(4), "time": "09:30"})
        assert response.status_code == 200 and "detached" not in response.json()
        stored = db.tasks.find_one({"id": task_id})
        assert stored["date"] == d(4) and stored["time"] == "09:30"
        assert "originHabitId" not in stored

    def test_one_off_task_can_be_created_with_time(self, db, client):
        task_id = self.one_off(client, time="21:05")
        assert db.tasks.find_one({"id": task_id})["time"] == "21:05"
        assert get_tasks(client, d(0), tz=None)[0]["time"] == "21:05"

    def test_create_task_rejects_bad_time(self, client):
        response = client.post("/api/tasks", json={
            "title": "T", "details": "", "category": "Energy",
            "estimatedImpact": "Saves ~1.0kg CO₂", "time": "9am",
        })
        assert response.status_code == 422

    def test_explicit_null_time_clears_it(self, db, client):
        task_id = self.one_off(client, time="21:05")
        response = client.patch(f"/api/tasks/{task_id}", json={"time": None})
        assert response.status_code == 200
        assert db.tasks.find_one({"id": task_id})["time"] is None

    def test_reschedule_validates_date_and_time(self, db, client):
        task_id = self.one_off(client)
        assert client.patch(f"/api/tasks/{task_id}", json={"date": "2026-13-45"}).status_code == 422
        assert client.patch(f"/api/tasks/{task_id}", json={"time": "24:00"}).status_code == 422
        assert db.tasks.find_one({"id": task_id})["date"] == d(0)

    def test_completed_task_cannot_be_rescheduled(self, db, client):
        task_id = self.one_off(client)
        db.tasks.update_one({"id": task_id}, {"$set": {"isCompleted": True, "completedAt": datetime.utcnow()}})
        for change in ({"date": d(2)}, {"time": "10:00"}):
            response = client.patch(f"/api/tasks/{task_id}", json=change)
            assert response.status_code == 400
            assert "cannot be rescheduled" in response.json()["detail"]
        assert db.tasks.find_one({"id": task_id})["date"] == d(0)

    def test_moving_a_habit_instance_detaches_it(self, db, client, user_id):
        habit = create_habit(client)
        task = get_tasks(client, d(0))[0]
        response = client.patch(f"/api/tasks/{task['id']}", json={"date": d(2)})
        assert response.status_code == 200, response.text
        assert response.json()["detached"] is True
        assert response.json()["originHabitId"] == habit["id"]

        stored = db.tasks.find_one({"id": task["id"]})
        assert "habitId" not in stored
        assert stored["originHabitId"] == habit["id"]
        assert stored["date"] == d(2)
        assert stored["title"] == "Bike to work" and stored["category"] == "Transport"
        assert stored["points"] == 24 and stored["time"] == "08:00"
        assert db.habits.find_one({"id": habit["id"]})["skippedDates"] == [d(0)]

    def test_no_ghost_after_moving_a_habit_instance(self, db, client, user_id):
        create_habit(client)
        task = get_tasks(client, d(0))[0]
        client.patch(f"/api/tasks/{task['id']}", json={"date": d(2)})
        assert get_tasks(client, d(0)) == []                      # original day stays empty
        assert get_tasks(client, d(0)) == []
        assert db.tasks.count_documents({"userId": user_id}) == 1

    def test_moving_onto_a_day_where_the_habit_also_occurs(self, db, client, user_id):
        """The detached task has no habitId, so it cannot collide with that day's own instance."""
        habit = create_habit(client, startDate=d(-1))
        yesterday_task = get_tasks(client, d(-1))[0]
        today_task = get_tasks(client, d(0))[0]
        response = client.patch(f"/api/tasks/{yesterday_task['id']}", json={"date": d(0)})
        assert response.status_code == 200, response.text
        tasks = get_tasks(client, d(0))
        assert {t["id"] for t in tasks} == {yesterday_task["id"], today_task["id"]}
        assert sum(1 for t in tasks if t.get("habitId") == habit["id"]) == 1

    def test_time_only_change_also_detaches(self, db, client):
        habit = create_habit(client)
        task = get_tasks(client, d(0))[0]
        response = client.patch(f"/api/tasks/{task['id']}", json={"time": "19:00"})
        assert response.json()["detached"] is True
        stored = db.tasks.find_one({"id": task["id"]})
        assert stored["time"] == "19:00" and stored["date"] == d(0) and "habitId" not in stored
        tasks = get_tasks(client, d(0))
        assert [t["id"] for t in tasks] == [task["id"]]            # not re-materialized next to it

    def test_detached_task_survives_habit_edit_and_delete(self, db, client):
        habit = create_habit(client)
        task = get_tasks(client, d(0))[0]
        client.patch(f"/api/tasks/{task['id']}", json={"date": d(1)})
        client.patch(f"/api/habits/{habit['id']}?tz=UTC", json={"title": "Renamed habit"})
        assert db.tasks.find_one({"id": task["id"]})["title"] == "Bike to work"
        client.delete(f"/api/habits/{habit['id']}?tz=UTC")
        assert db.tasks.find_one({"id": task["id"]}) is not None

    def test_reschedule_and_complete_in_one_request(self, db, client):
        habit = create_habit(client, startDate=d(-1))
        task = get_tasks(client, d(-1))[0]
        response = client.patch(f"/api/tasks/{task['id']}", json={
            "date": d(0), "isCompleted": True, "completionLocalDate": d(0), "timezoneIdentifier": "UTC",
        })
        assert response.status_code == 200, response.text
        stored = db.tasks.find_one({"id": task["id"]})
        assert stored["isCompleted"] is True and stored["date"] == d(0)
        assert "habitId" not in stored and stored["originHabitId"] == habit["id"]


# ======================== TASK REMINDERS ========================

class TestTaskReminders:
    """reminderOffsets on tasks: same rules as habits (max 2, only with a time)."""

    def one_off(self, client, expect=201, **extra):
        body = {"title": "One-off", "details": "", "category": "Energy",
                "estimatedImpact": "Saves ~1.0kg CO₂", "date": d(0)}
        body.update(extra)
        response = client.post("/api/tasks", json=body)
        assert response.status_code == expect, response.text
        return response.json().get("taskId")

    # ---- create

    def test_create_with_time_and_reminders(self, db, client):
        task_id = self.one_off(client, time="09:00", reminderOffsets=[60, 0, 60])
        assert db.tasks.find_one({"id": task_id})["reminderOffsets"] == [0, 60]
        assert get_tasks(client, d(0))[0]["reminderOffsets"] == [0, 60]

    def test_create_without_reminders_keeps_the_legacy_document_shape(self, db, client):
        for extra in ({}, {"time": "09:00"}, {"reminderOffsets": []}, {"reminderOffsets": None}):
            task_id = self.one_off(client, **extra)
            assert "reminderOffsets" not in db.tasks.find_one({"id": task_id})

    @pytest.mark.parametrize("extra", [
        {"reminderOffsets": [15]},                                   # no time
        {"time": "09:00", "reminderOffsets": [0, 15, 60]},           # more than two
        {"time": "09:00", "reminderOffsets": [-5]},
        {"time": "09:00", "reminderOffsets": [1441]},
        {"time": "09:00", "reminderOffsets": "15"},
        {"time": "9am", "reminderOffsets": [15]},
    ])
    def test_create_rejects_invalid_reminders(self, db, client, user_id, extra):
        self.one_off(client, expect=422, **extra)
        assert db.tasks.count_documents({"userId": user_id}) == 0

    # ---- update

    def test_patch_sets_and_clears_reminders(self, db, client):
        task_id = self.one_off(client, time="09:00")
        response = client.patch(f"/api/tasks/{task_id}", json={"reminderOffsets": [15, 0]})
        assert response.status_code == 200, response.text
        assert "detached" not in response.json()
        assert db.tasks.find_one({"id": task_id})["reminderOffsets"] == [0, 15]

        assert client.patch(f"/api/tasks/{task_id}", json={"reminderOffsets": []}).status_code == 200
        assert db.tasks.find_one({"id": task_id})["reminderOffsets"] == []

    def test_patch_null_or_absent_leaves_reminders_alone(self, db, client):
        task_id = self.one_off(client, time="09:00", reminderOffsets=[15])
        response = client.patch(f"/api/tasks/{task_id}", json={"title": "Renamed", "reminderOffsets": None})
        assert response.status_code == 200
        stored = db.tasks.find_one({"id": task_id})
        assert stored["title"] == "Renamed" and stored["reminderOffsets"] == [15]

    def test_patch_echoing_the_stored_reminders_is_a_no_op(self, db, client):
        task_id = self.one_off(client, time="09:00", reminderOffsets=[15])
        assert client.patch(f"/api/tasks/{task_id}", json={"reminderOffsets": [15]}).status_code == 400
        response = client.patch(f"/api/tasks/{task_id}", json={"title": "Renamed", "reminderOffsets": [15]})
        assert response.status_code == 200
        assert db.tasks.find_one({"id": task_id})["reminderOffsets"] == [15]

    @pytest.mark.parametrize("change", [
        {"reminderOffsets": [0, 15, 60]},
        {"reminderOffsets": [2000]},
        {"reminderOffsets": [-1]},
    ])
    def test_patch_rejects_invalid_reminders(self, db, client, change):
        task_id = self.one_off(client, time="09:00", reminderOffsets=[15])
        assert client.patch(f"/api/tasks/{task_id}", json=change).status_code == 422
        assert db.tasks.find_one({"id": task_id})["reminderOffsets"] == [15]

    def test_patch_rejects_reminders_on_a_task_without_time(self, db, client):
        task_id = self.one_off(client)
        assert client.patch(f"/api/tasks/{task_id}", json={"reminderOffsets": [15]}).status_code == 422
        assert "reminderOffsets" not in db.tasks.find_one({"id": task_id})

    def test_patch_can_add_time_and_reminders_together(self, db, client):
        task_id = self.one_off(client)
        response = client.patch(f"/api/tasks/{task_id}", json={"time": "18:00", "reminderOffsets": [60]})
        assert response.status_code == 200, response.text
        stored = db.tasks.find_one({"id": task_id})
        assert stored["time"] == "18:00" and stored["reminderOffsets"] == [60]

    def test_clearing_the_time_clears_the_reminders(self, db, client):
        task_id = self.one_off(client, time="09:00", reminderOffsets=[0, 15])
        assert client.patch(f"/api/tasks/{task_id}", json={"time": None}).status_code == 200
        stored = db.tasks.find_one({"id": task_id})
        assert stored["time"] is None and stored["reminderOffsets"] == []

    def test_clearing_the_time_while_sending_reminders_is_rejected(self, db, client):
        task_id = self.one_off(client, time="09:00", reminderOffsets=[15])
        response = client.patch(f"/api/tasks/{task_id}", json={"time": None, "reminderOffsets": [15]})
        assert response.status_code == 422
        stored = db.tasks.find_one({"id": task_id})
        assert stored["time"] == "09:00" and stored["reminderOffsets"] == [15]

    def test_changing_date_or_time_keeps_the_reminders(self, db, client):
        task_id = self.one_off(client, time="09:00", reminderOffsets=[15])
        assert client.patch(f"/api/tasks/{task_id}", json={"date": d(3), "time": "10:30"}).status_code == 200
        stored = db.tasks.find_one({"id": task_id})
        assert (stored["date"], stored["time"], stored["reminderOffsets"]) == (d(3), "10:30", [15])

    def test_completed_task_can_still_drop_its_reminders(self, db, client):
        task_id = self.one_off(client, time="09:00", reminderOffsets=[15])
        db.tasks.update_one({"id": task_id}, {"$set": {"isCompleted": True, "completedAt": datetime.utcnow()}})
        assert client.patch(f"/api/tasks/{task_id}", json={"reminderOffsets": []}).status_code == 200
        assert db.tasks.find_one({"id": task_id})["reminderOffsets"] == []

    # ---- habit occurrences

    def test_instance_and_virtual_occurrence_expose_the_habits_reminders(self, client):
        create_habit(client, time="08:00", reminderOffsets=[15, 0])
        assert get_tasks(client, d(0))[0]["reminderOffsets"] == [0, 15]
        virtual = get_tasks(client, d(2))[0]
        assert virtual["isVirtual"] is True and virtual["reminderOffsets"] == [0, 15]

    def test_all_day_habit_occurrences_have_no_reminders(self, client):
        create_habit(client, time=None, reminderOffsets=[])
        assert get_tasks(client, d(0))[0]["reminderOffsets"] == []
        assert get_tasks(client, d(2))[0]["reminderOffsets"] == []

    def test_habit_reminder_edit_reaches_todays_instance_and_future_days(self, client):
        habit = create_habit(client, reminderOffsets=[0])
        assert get_tasks(client, d(0))[0]["reminderOffsets"] == [0]
        response = client.patch(f"/api/habits/{habit['id']}?tz=UTC", json={"reminderOffsets": [60]})
        assert response.status_code == 200, response.text
        assert get_tasks(client, d(0))[0]["reminderOffsets"] == [60]
        assert get_tasks(client, d(1))[0]["reminderOffsets"] == [60]

    def test_reminders_of_a_habit_instance_are_set_on_the_habit(self, db, client):
        create_habit(client, reminderOffsets=[0, 15])
        task = get_tasks(client, d(0))[0]
        response = client.patch(f"/api/tasks/{task['id']}", json={"reminderOffsets": [60]})
        assert response.status_code == 400
        assert "habit" in response.json()["detail"]
        stored = db.tasks.find_one({"id": task["id"]})
        assert stored["reminderOffsets"] == [0, 15] and "habitId" in stored
        # Echoing the current value next to another change is harmless
        response = client.patch(f"/api/tasks/{task['id']}", json={"title": "Renamed", "reminderOffsets": [0, 15]})
        assert response.status_code == 200 and "detached" not in response.json()

    # ---- detach (real instance)

    def test_moving_a_habit_instance_copies_the_habits_reminders(self, db, client):
        create_habit(client, reminderOffsets=[0, 15])
        task = get_tasks(client, d(0))[0]
        response = client.patch(f"/api/tasks/{task['id']}", json={"date": d(2)})
        assert response.json()["detached"] is True
        assert db.tasks.find_one({"id": task["id"]})["reminderOffsets"] == [0, 15]

    def test_detach_copies_from_the_habit_even_when_the_row_has_no_reminder_field(self, db, client):
        """Rows materialized before tasks had reminderOffsets."""
        create_habit(client, reminderOffsets=[60])
        task = get_tasks(client, d(0))[0]
        db.tasks.update_one({"id": task["id"]}, {"$unset": {"reminderOffsets": ""}})
        client.patch(f"/api/tasks/{task['id']}", json={"time": "19:00"})
        stored = db.tasks.find_one({"id": task["id"]})
        assert stored["time"] == "19:00" and stored["reminderOffsets"] == [60] and "habitId" not in stored

    def test_detach_to_all_day_drops_the_reminders(self, db, client):
        create_habit(client, reminderOffsets=[0, 15])
        task = get_tasks(client, d(0))[0]
        response = client.patch(f"/api/tasks/{task['id']}", json={"date": d(1), "time": None})
        assert response.status_code == 200, response.text
        stored = db.tasks.find_one({"id": task["id"]})
        assert stored["time"] is None and stored["reminderOffsets"] == []

    def test_detach_with_explicit_reminders_uses_them(self, db, client):
        create_habit(client, reminderOffsets=[0, 15])
        task = get_tasks(client, d(0))[0]
        response = client.patch(f"/api/tasks/{task['id']}", json={"date": d(1), "reminderOffsets": [60]})
        assert response.status_code == 200 and response.json()["detached"] is True
        assert db.tasks.find_one({"id": task["id"]})["reminderOffsets"] == [60]

    def test_detach_with_invalid_reminders_changes_nothing(self, db, client):
        habit = create_habit(client, reminderOffsets=[0, 15])
        task = get_tasks(client, d(0))[0]
        response = client.patch(f"/api/tasks/{task['id']}", json={"time": None, "reminderOffsets": [60]})
        assert response.status_code == 422
        assert db.tasks.find_one({"id": task["id"]})["habitId"] == habit["id"]
        assert db.habits.find_one({"id": habit["id"]})["skippedDates"] == []

    def test_detached_task_keeps_its_reminders_when_the_habit_changes(self, db, client):
        habit = create_habit(client, reminderOffsets=[0, 15])
        task = get_tasks(client, d(0))[0]
        client.patch(f"/api/tasks/{task['id']}", json={"date": d(1)})
        client.patch(f"/api/habits/{habit['id']}?tz=UTC", json={"reminderOffsets": []})
        assert db.tasks.find_one({"id": task["id"]})["reminderOffsets"] == [0, 15]
        client.delete(f"/api/habits/{habit['id']}?tz=UTC")
        assert db.tasks.find_one({"id": task["id"]})["reminderOffsets"] == [0, 15]

    def test_instance_of_a_deleted_habit_still_detaches_with_reminders(self, db, client):
        habit = create_habit(client, startDate=d(-1), reminderOffsets=[15])
        past = get_tasks(client, d(-1))[0]
        client.delete(f"/api/habits/{habit['id']}?tz=UTC")
        response = client.patch(f"/api/tasks/{past['id']}", json={"date": d(0)})
        assert response.status_code == 200, response.text
        assert db.tasks.find_one({"id": past["id"]})["reminderOffsets"] == [15]

    # ---- detach (virtual occurrence)

    def test_rescheduling_a_virtual_occurrence_copies_the_habits_reminders(self, db, client):
        habit = create_habit(client, reminderOffsets=[0, 15])
        response = client.patch(f"/api/tasks/habit_{habit['id']}_{d(2)}", json={"date": d(4)})
        assert response.status_code == 200, response.text
        moved = db.tasks.find_one({"id": response.json()["taskId"]})
        assert moved["reminderOffsets"] == [0, 15] and "habitId" not in moved
        listed = [t for t in get_tasks(client, d(4)) if not t.get("isVirtual")]
        assert listed[0]["reminderOffsets"] == [0, 15]

    def test_rescheduling_a_virtual_occurrence_to_all_day_drops_reminders(self, db, client):
        habit = create_habit(client, reminderOffsets=[0, 15])
        response = client.patch(f"/api/tasks/habit_{habit['id']}_{d(2)}", json={"time": None})
        assert response.status_code == 200, response.text
        moved = db.tasks.find_one({"id": response.json()["taskId"]})
        assert moved["time"] is None and moved["reminderOffsets"] == []

    def test_rescheduling_a_virtual_occurrence_with_explicit_reminders(self, db, client):
        habit = create_habit(client, reminderOffsets=[0, 15])
        response = client.patch(
            f"/api/tasks/habit_{habit['id']}_{d(2)}", json={"time": "20:00", "reminderOffsets": [60]}
        )
        assert response.status_code == 200, response.text
        assert db.tasks.find_one({"id": response.json()["taskId"]})["reminderOffsets"] == [60]

    def test_rescheduling_a_virtual_occurrence_with_invalid_reminders_changes_nothing(self, db, client, user_id):
        habit = create_habit(client, reminderOffsets=[0, 15])
        for change in ({"time": None, "reminderOffsets": [15]}, {"date": d(4), "reminderOffsets": [0, 15, 60]}):
            response = client.patch(f"/api/tasks/habit_{habit['id']}_{d(2)}", json=change)
            assert response.status_code == 422
        assert db.habits.find_one({"id": habit["id"]})["skippedDates"] == []
        assert db.tasks.count_documents({"userId": user_id}) == 0

    def test_reminders_alone_cannot_address_a_virtual_occurrence(self, db, client, user_id):
        habit = create_habit(client, reminderOffsets=[0])
        response = client.patch(f"/api/tasks/habit_{habit['id']}_{d(2)}", json={"reminderOffsets": [60]})
        assert response.status_code == 400
        assert db.tasks.count_documents({"userId": user_id}) == 0


# ======================== HABIT CRUD ========================

class TestCreateHabit:
    def test_response_shape_and_derived_fields(self, db, client, user_id):
        response = client.post("/api/habits?tz=UTC", json=habit_body(reminderOffsets=[15, 0]))
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True and body["habitId"] == body["habit"]["id"]
        habit = body["habit"]
        assert habit["userId"] == user_id
        assert habit["points"] == 24 and habit["estimatedImpact"] == "Saves ~2.4kg CO₂"
        assert habit["startDate"] == d(0) and habit["endDate"] is None
        assert habit["reminderOffsets"] == [0, 15]
        assert habit["recurrence"] == {"type": "daily"}
        assert habit["skippedDates"] == [] and habit["active"] is True
        assert "_id" not in habit and habit["createdAt"].endswith("Z")
        assert db.habits.count_documents({"userId": user_id}) == 1

    def test_all_day_habit(self, client):
        habit = create_habit(client, time=None, reminderOffsets=[])
        assert habit["time"] is None and habit["reminderOffsets"] == []

    def test_minimal_payload(self, client):
        response = client.post("/api/habits?tz=UTC", json={
            "title": "Short shower", "category": "Water", "co2Kg": 0.5, "recurrence": {"type": "daily"},
        })
        assert response.status_code == 201
        habit = response.json()["habit"]
        assert habit["details"] == "" and habit["time"] is None and habit["reminderOffsets"] == []

    def test_list_returns_active_habits_newest_first(self, db, client, user_id):
        first = create_habit(client, title="First")
        db.habits.update_one({"id": first["id"]}, {"$set": {"createdAt": datetime(2026, 1, 1)}})
        second = create_habit(client, title="Second")
        habit_system.create_habit(db, "someone-else", habit_body(title="Not mine"), "UTC")
        listed = client.get("/api/habits").json()
        assert [h["id"] for h in listed] == [second["id"], first["id"]]

    @pytest.mark.parametrize("overrides", [
        {"time": None, "reminderOffsets": [0]},                       # reminders need a time
        {"reminderOffsets": [0, 15, 60]},                             # max 2
        {"time": "8:00"},
        {"recurrence": {"type": "weekdays"}},
        {"recurrence": {"type": "weekdays", "weekdays": [0, 3]}},
        {"recurrence": {"type": "everyNDays"}},
        {"recurrence": {"type": "everyNDays", "interval": 0}},
        {"recurrence": {"type": "yearly"}},
        {"category": "Gardening"},
        {"co2Kg": 10.5},
        {"co2Kg": -1},
        {"title": ""},
        {"title": "x" * 201},
        {"startDate": "tomorrow"},
    ])
    def test_invalid_payloads_are_422(self, db, client, user_id, overrides):
        response = client.post("/api/habits?tz=UTC", json=habit_body(**overrides))
        assert response.status_code == 422, response.text
        assert db.habits.count_documents({"userId": user_id}) == 0

    def test_profanity_is_rejected_like_tasks(self, db, client, user_id, monkeypatch):
        def reject(text, context="Content"):
            if "badword" in text:
                raise ValueError(f"{context} contains inappropriate language and cannot be saved.")
        monkeypatch.setattr(server.ProfanityFilter, "validate_content", staticmethod(reject))
        assert client.post("/api/habits?tz=UTC", json=habit_body(title="badword habit")).status_code == 422
        assert client.post("/api/habits?tz=UTC", json=habit_body(details="some badword")).status_code == 422
        assert db.habits.count_documents({"userId": user_id}) == 0

    def test_start_date_cannot_be_backdated(self, client):
        assert client.post("/api/habits?tz=UTC", json=habit_body(startDate=d(-2))).status_code == 422
        assert client.post("/api/habits?tz=UTC", json=habit_body(startDate=d(-1))).status_code == 201
        assert client.post("/api/habits?tz=UTC", json=habit_body(startDate=d(30))).status_code == 201

    def test_end_date_cannot_precede_start_date(self, client):
        assert client.post("/api/habits?tz=UTC", json=habit_body(startDate=d(2), endDate=d(1))).status_code == 422
        assert client.post("/api/habits?tz=UTC", json=habit_body(startDate=d(2), endDate=d(2))).status_code == 201

    def test_future_start_date_produces_nothing_before_it(self, client):
        create_habit(client, startDate=d(3))
        assert get_tasks(client, d(0)) == []
        assert get_tasks(client, d(2)) == []
        assert len(get_tasks(client, d(3))) == 1


class TestHabitCap:
    def test_thirty_first_active_habit_is_rejected_with_400(self, db, client, user_id):
        for n in range(MAX_ACTIVE_HABITS):
            habit_system.create_habit(db, user_id, habit_body(title=f"Habit {n}"), "UTC")
        response = client.post("/api/habits?tz=UTC", json=habit_body(title="One too many"))
        assert response.status_code == 400
        assert "30 active habits" in response.json()["detail"]
        assert db.habits.count_documents({"userId": user_id}) == MAX_ACTIVE_HABITS

    def test_deleting_a_habit_frees_a_slot(self, db, client, user_id):
        ids = [habit_system.create_habit(db, user_id, habit_body(title=f"Habit {n}"), "UTC")["id"]
               for n in range(MAX_ACTIVE_HABITS)]
        assert client.delete(f"/api/habits/{ids[0]}?tz=UTC").status_code == 200
        assert client.post("/api/habits?tz=UTC", json=habit_body(title="Replacement")).status_code == 201

    def test_cap_is_per_user(self, db, client):
        for n in range(MAX_ACTIVE_HABITS):
            habit_system.create_habit(db, "someone-else", habit_body(title=f"Habit {n}"), "UTC")
        assert client.post("/api/habits?tz=UTC", json=habit_body()).status_code == 201


class TestEditHabit:
    def test_todays_uncompleted_instance_is_rebuilt_from_new_definition(self, db, client, user_id):
        habit = create_habit(client)
        old = get_tasks(client, d(0))[0]
        response = client.patch(f"/api/habits/{habit['id']}?tz=UTC", json={"title": "Cycle to work", "time": "09:15"})
        assert response.status_code == 200, response.text
        assert response.json()["removedInstances"] == 1
        assert response.json()["habit"]["title"] == "Cycle to work"
        assert db.tasks.count_documents({"userId": user_id}) == 0   # removed, not yet re-fetched

        new = get_tasks(client, d(0))
        assert len(new) == 1
        assert new[0]["title"] == "Cycle to work" and new[0]["time"] == "09:15"
        assert new[0]["id"] != old["id"]

    def test_completed_and_past_instances_are_history(self, db, client, user_id):
        habit = create_habit(client, startDate=d(-1))
        yesterday = get_tasks(client, d(-1))[0]                    # past, uncompleted
        today_task = get_tasks(client, d(0))[0]
        db.tasks.update_one({"id": today_task["id"]}, {"$set": {"isCompleted": True, "completedAt": datetime.utcnow()}})

        response = client.patch(f"/api/habits/{habit['id']}?tz=UTC", json={"title": "Renamed"})
        assert response.json()["removedInstances"] == 0
        assert db.tasks.find_one({"id": yesterday["id"]})["title"] == "Bike to work"
        assert db.tasks.find_one({"id": today_task["id"]})["title"] == "Bike to work"
        assert len(get_tasks(client, d(0))) == 1                   # completed one is not duplicated

    def test_reversed_instance_is_kept(self, db, client, user_id):
        """Completion finality (wasReversed) must not be resettable by editing the habit."""
        habit = create_habit(client)
        task = get_tasks(client, d(0))[0]
        db.tasks.update_one({"id": task["id"]}, {"$set": {"wasReversed": True}})
        response = client.patch(f"/api/habits/{habit['id']}?tz=UTC", json={"title": "Renamed"})
        assert response.json()["removedInstances"] == 0
        tasks = get_tasks(client, d(0))
        assert [t["id"] for t in tasks] == [task["id"]]
        assert db.tasks.find_one({"id": task["id"]})["wasReversed"] is True

    def test_future_occurrences_follow_the_new_definition(self, client):
        habit = create_habit(client)
        client.patch(f"/api/habits/{habit['id']}?tz=UTC", json={"co2Kg": 5.0, "category": "Energy"})
        future = get_tasks(client, d(3))[0]
        assert future["points"] == 50 and future["category"] == "Energy"
        assert future["estimatedImpact"] == "Saves ~5.0kg CO₂"

    def test_recurrence_change_resets_start_date_to_today(self, db, client):
        habit = create_habit(client, startDate=d(-1))
        assert habit["startDate"] == d(-1)
        response = client.patch(f"/api/habits/{habit['id']}?tz=UTC",
                                json={"recurrence": {"type": "everyNDays", "interval": 3}})
        updated = response.json()["habit"]
        assert updated["startDate"] == d(0)
        assert updated["recurrence"] == {"type": "everyNDays", "interval": 3}
        # anchored on today: today, +3, +6
        assert len(get_tasks(client, d(0))) == 1
        assert get_tasks(client, d(1)) == [] and get_tasks(client, d(2)) == []
        assert len(get_tasks(client, d(3))) == 1
        assert get_tasks(client, d(-1)) == []                      # before the new start

    def test_same_recurrence_or_other_fields_keep_start_date(self, client):
        habit = create_habit(client, startDate=d(-1))
        same = client.patch(f"/api/habits/{habit['id']}?tz=UTC",
                            json={"recurrence": {"type": "daily"}, "title": "Renamed"})
        assert same.json()["habit"]["startDate"] == d(-1)
        other = client.patch(f"/api/habits/{habit['id']}?tz=UTC", json={"time": "10:00"})
        assert other.json()["habit"]["startDate"] == d(-1)

    def test_recurrence_change_removes_todays_instance_when_today_no_longer_matches(self, db, client, user_id):
        habit = create_habit(client)
        get_tasks(client, d(0))
        not_today = today().isoweekday() % 7 + 1
        client.patch(f"/api/habits/{habit['id']}?tz=UTC",
                     json={"recurrence": {"type": "weekdays", "weekdays": [not_today]}})
        assert get_tasks(client, d(0)) == []
        assert db.tasks.count_documents({"userId": user_id}) == 0

    def test_making_all_day_requires_clearing_reminders(self, client):
        habit = create_habit(client)                                # time 08:00, offsets [0, 15]
        rejected = client.patch(f"/api/habits/{habit['id']}?tz=UTC", json={"time": None})
        assert rejected.status_code == 422
        accepted = client.patch(f"/api/habits/{habit['id']}?tz=UTC", json={"time": None, "reminderOffsets": []})
        assert accepted.status_code == 200
        assert accepted.json()["habit"]["time"] is None
        assert accepted.json()["habit"]["reminderOffsets"] == []

    def test_reminders_cannot_be_added_to_all_day_habit(self, client):
        habit = create_habit(client, time=None, reminderOffsets=[])
        assert client.patch(f"/api/habits/{habit['id']}?tz=UTC", json={"reminderOffsets": [15]}).status_code == 422
        ok = client.patch(f"/api/habits/{habit['id']}?tz=UTC", json={"time": "07:00", "reminderOffsets": [15]})
        assert ok.status_code == 200 and ok.json()["habit"]["reminderOffsets"] == [15]

    def test_end_date_can_be_set_and_cleared(self, client):
        habit = create_habit(client)
        set_end = client.patch(f"/api/habits/{habit['id']}?tz=UTC", json={"endDate": d(2)})
        assert set_end.json()["habit"]["endDate"] == d(2)
        assert get_tasks(client, d(3)) == []
        cleared = client.patch(f"/api/habits/{habit['id']}?tz=UTC", json={"endDate": None})
        assert cleared.json()["habit"]["endDate"] is None
        assert len(get_tasks(client, d(3))) == 1

    def test_end_date_before_start_is_rejected(self, client):
        habit = create_habit(client)
        assert client.patch(f"/api/habits/{habit['id']}?tz=UTC", json={"endDate": d(-1)}).status_code == 422

    def test_invalid_edits(self, client):
        habit = create_habit(client)
        base = f"/api/habits/{habit['id']}?tz=UTC"
        assert client.patch(base, json={}).status_code == 400
        assert client.patch(base, json={"category": "Gardening"}).status_code == 422
        assert client.patch(base, json={"time": "noon"}).status_code == 422
        assert client.patch(base, json={"co2Kg": 11}).status_code == 422
        assert client.patch(base, json={"recurrence": {"type": "weekdays", "weekdays": []}}).status_code == 422
        assert client.patch(base, json={"reminderOffsets": [0, 5, 10]}).status_code == 422

    def test_cannot_edit_someone_elses_or_unknown_habit(self, db, client):
        other = habit_system.create_habit(db, "someone-else", habit_body(), "UTC")
        assert client.patch(f"/api/habits/{other['id']}?tz=UTC", json={"title": "Hijack"}).status_code == 404
        assert client.patch(f"/api/habits/{uuid.uuid4()}?tz=UTC", json={"title": "Ghost"}).status_code == 404
        assert db.habits.find_one({"id": other["id"]})["title"] == "Bike to work"


class TestSoftDelete:
    def test_soft_delete_keeps_history_and_stops_future(self, db, client, user_id):
        habit = create_habit(client, startDate=d(-1))
        done = get_tasks(client, d(-1))[0]
        db.tasks.update_one({"id": done["id"]}, {"$set": {"isCompleted": True, "completedAt": datetime.utcnow()}})
        get_tasks(client, d(0))                                     # today's uncompleted instance

        response = client.delete(f"/api/habits/{habit['id']}?tz=UTC")
        assert response.status_code == 200
        assert response.json() == {"success": True, "message": "Habit deleted successfully", "removedInstances": 1}

        stored = db.habits.find_one({"id": habit["id"]})
        assert stored is not None and stored["active"] is False     # soft delete
        assert client.get("/api/habits").json() == []
        assert db.tasks.find_one({"id": done["id"]})["isCompleted"] is True
        assert get_tasks(client, d(0)) == []                        # not re-materialized
        assert get_tasks(client, d(3)) == []                        # no virtual occurrences
        assert [t["id"] for t in get_tasks(client, d(-1))] == [done["id"]]

    def test_past_uncompleted_instances_stay(self, db, client, user_id):
        habit = create_habit(client, startDate=d(-1))
        missed = get_tasks(client, d(-1))[0]
        client.delete(f"/api/habits/{habit['id']}?tz=UTC")
        assert db.tasks.find_one({"id": missed["id"]}) is not None

    def test_deleted_habit_is_gone_for_every_endpoint(self, client):
        habit = create_habit(client)
        base = f"/api/habits/{habit['id']}"
        assert client.delete(f"{base}?tz=UTC").status_code == 200
        assert client.delete(f"{base}?tz=UTC").status_code == 404
        assert client.patch(f"{base}?tz=UTC", json={"title": "Zombie"}).status_code == 404
        assert client.post(f"{base}/skip", json={"date": d(1)}).status_code == 404

    def test_cannot_delete_someone_elses_habit(self, db, client):
        other = habit_system.create_habit(db, "someone-else", habit_body(), "UTC")
        assert client.delete(f"/api/habits/{other['id']}?tz=UTC").status_code == 404
        assert db.habits.find_one({"id": other["id"]})["active"] is True


class TestSkip:
    def test_skip_future_occurrence(self, db, client, user_id):
        habit = create_habit(client)
        response = client.post(f"/api/habits/{habit['id']}/skip", json={"date": d(2)})
        assert response.status_code == 200
        body = response.json()
        assert body["skippedDates"] == [d(2)] and body["removedInstance"] is False
        assert get_tasks(client, d(2)) == []
        assert len(get_tasks(client, d(1))) == 1 and len(get_tasks(client, d(3))) == 1
        assert db.tasks.count_documents({"userId": user_id}) == 0

    def test_skip_today_removes_instance_and_blocks_rematerialization(self, db, client, user_id):
        habit = create_habit(client)
        get_tasks(client, d(0))
        response = client.post(f"/api/habits/{habit['id']}/skip", json={"date": d(0)})
        assert response.json()["removedInstance"] is True
        assert get_tasks(client, d(0)) == []
        assert db.tasks.count_documents({"userId": user_id}) == 0

    def test_skip_is_idempotent(self, db, client):
        habit = create_habit(client)
        for _ in range(3):
            assert client.post(f"/api/habits/{habit['id']}/skip", json={"date": d(2)}).status_code == 200
        assert db.habits.find_one({"id": habit["id"]})["skippedDates"] == [d(2)]

    def test_completed_occurrence_cannot_be_skipped(self, db, client):
        habit = create_habit(client)
        task = get_tasks(client, d(0))[0]
        db.tasks.update_one({"id": task["id"]}, {"$set": {"isCompleted": True}})
        response = client.post(f"/api/habits/{habit['id']}/skip", json={"date": d(0)})
        assert response.status_code == 400
        assert db.tasks.find_one({"id": task["id"]}) is not None
        assert db.habits.find_one({"id": habit["id"]})["skippedDates"] == []

    def test_skip_validates_date(self, client):
        habit = create_habit(client)
        assert client.post(f"/api/habits/{habit['id']}/skip", json={"date": "soon"}).status_code == 422
        assert client.post(f"/api/habits/{habit['id']}/skip", json={}).status_code == 422


# ======================== DELETING INSTANCES ========================

class TestDeleteInstance:
    def test_deleted_instance_is_not_resurrected(self, db, client, user_id):
        habit = create_habit(client)
        task = get_tasks(client, d(0))[0]
        assert client.delete(f"/api/tasks/{task['id']}").status_code == 200
        assert db.habits.find_one({"id": habit["id"]})["skippedDates"] == [d(0)]
        assert get_tasks(client, d(0)) == []
        assert db.tasks.count_documents({"userId": user_id}) == 0

    def test_bulk_delete_of_completed_instances_is_not_resurrected(self, db, client, user_id):
        """Export-then-delete must not hand back fresh, completable copies."""
        habit = create_habit(client, startDate=d(-1))
        ids = [get_tasks(client, d(-1))[0]["id"], get_tasks(client, d(0))[0]["id"]]
        db.tasks.update_many({"id": {"$in": ids}}, {"$set": {"isCompleted": True, "completedAt": datetime.utcnow()}})

        response = client.request("DELETE", "/api/tasks/bulk-delete", json={"taskIds": ids})
        assert response.status_code == 200 and response.json()["deletedCount"] == 2
        assert sorted(db.habits.find_one({"id": habit["id"]})["skippedDates"]) == [d(-1), d(0)]
        assert get_tasks(client, d(-1)) == [] and get_tasks(client, d(0)) == []
        assert db.tasks.count_documents({"userId": user_id}) == 0

    def test_deleting_one_off_tasks_does_not_touch_habits(self, db, client):
        habit = create_habit(client)
        task_id = client.post("/api/tasks", json={
            "title": "One-off", "details": "", "category": "Energy",
            "estimatedImpact": "Saves ~1.0kg CO₂", "date": d(0),
        }).json()["taskId"]
        assert client.delete(f"/api/tasks/{task_id}").status_code == 200
        assert db.habits.find_one({"id": habit["id"]})["skippedDates"] == []
        assert len(get_tasks(client, d(0))) == 1                   # the habit instance still appears


# ======================== CALENDAR ========================

class TestCalendar:
    def month_of(self, offset: int):
        day = today() + timedelta(days=offset)
        return day.year, day.month

    def test_virtual_counts_cover_future_and_unopened_past_days(self, client):
        create_habit(client, startDate=d(-1))
        get_tasks(client, d(0))                                     # only today is materialized
        expected = {}
        for offset in (-1, 0, 1, 2):
            year, month = self.month_of(offset)
            expected.setdefault((year, month), []).append(offset)

        for (year, month), offsets in expected.items():
            body = client.get(f"/api/calendar/{year}/{month}", params={"tz": "UTC"}).json()
            days = {day["date"]: day for day in body["days"]}
            for offset in offsets:
                entry = days[d(offset)]
                assert entry["totalCount"] == 1 and entry["completedCount"] == 0
                if offset == 0:
                    assert "virtualCount" not in entry              # real row, counted once
                else:
                    assert entry["virtualCount"] == 1
            assert body["allTasksCompleted"] is False
            assert body["totalTasks"] == sum(day["totalCount"] for day in body["days"])
            assert [day["date"] for day in body["days"]] == sorted(days)

    def test_calendar_never_writes(self, db, client, user_id):
        create_habit(client)
        year, month = self.month_of(0)
        client.get(f"/api/calendar/{year}/{month}", params={"tz": "UTC"})
        assert db.tasks.count_documents({"userId": user_id}) == 0

    def test_missed_habit_days_prevent_month_complete(self, db, client, user_id):
        """Without virtual counts a month with unopened habit days would look 'all completed'."""
        create_habit(client)
        task = get_tasks(client, d(0))[0]
        db.tasks.update_one({"id": task["id"]}, {"$set": {"isCompleted": True}})
        # Pick a month that holds today plus at least one other habit day.
        neighbour = 1 if self.month_of(1) == self.month_of(0) else -1
        if neighbour == -1:
            db.habits.update_many({"userId": user_id}, {"$set": {"startDate": d(-1)}})
        year, month = self.month_of(0)
        legacy = client.get(f"/api/calendar/{year}/{month}").json()
        with_tz = client.get(f"/api/calendar/{year}/{month}", params={"tz": "UTC"}).json()
        assert legacy["allTasksCompleted"] is True
        assert with_tz["allTasksCompleted"] is False
        assert with_tz["totalCompleted"] == 1 and with_tz["totalTasks"] > 1

    def test_skipped_days_are_not_counted(self, client):
        habit = create_habit(client)
        client.post(f"/api/habits/{habit['id']}/skip", json={"date": d(1)})
        year, month = self.month_of(1)
        body = client.get(f"/api/calendar/{year}/{month}", params={"tz": "UTC"}).json()
        assert d(1) not in {day["date"] for day in body["days"]}


# ======================== SOCIAL LISTINGS / ACCOUNT DELETION ========================

class TestSideEffects:
    def test_habit_instances_are_hidden_from_profile_task_lists(self, db, client, user_id):
        from social_system import get_created_tasks, get_user_manual_tasks
        create_habit(client)
        instance = get_tasks(client, d(0))[0]
        one_off_id = client.post("/api/tasks", json={
            "title": "One-off", "details": "", "category": "Energy",
            "estimatedImpact": "Saves ~1.0kg CO₂", "date": d(0),
        }).json()["taskId"]

        created = [t["id"] for t in get_created_tasks(db, user_id)["tasks"]]
        manual = [t["id"] for t in get_user_manual_tasks(db, user_id)]
        assert created == [one_off_id] and manual == [one_off_id]
        assert instance["id"] not in created

    def test_detached_task_is_listed_like_a_one_off(self, db, client, user_id):
        from social_system import get_created_tasks
        create_habit(client)
        instance = get_tasks(client, d(0))[0]
        client.patch(f"/api/tasks/{instance['id']}", json={"date": d(1)})
        assert [t["id"] for t in get_created_tasks(db, user_id)["tasks"]] == [instance["id"]]

    def test_account_deletion_removes_habits(self, db, client, user_id):
        create_habit(client)
        get_tasks(client, d(0))
        habit_system.create_habit(db, "someone-else", habit_body(), "UTC")
        result = server._perform_full_deletion(user_id)
        assert result["success"] is True
        assert db.habits.count_documents({"userId": user_id}) == 0
        assert db.tasks.count_documents({"userId": user_id}) == 0
        assert db.habits.count_documents({"userId": "someone-else"}) == 1

    def test_ai_suggestions_use_user_today_only_when_tz_sent(self, client, monkeypatch):
        import streak_system
        monkeypatch.setattr(streak_system, "user_today", lambda tz: date(2031, 5, 6))
        with_tz = client.post("/api/ai/generate-tasks", params={"tz": "Asia/Tokyo"}).json()
        assert {t["date"] for t in with_tz["tasks"]} == {"2031-05-06"}
        legacy = client.post("/api/ai/generate-tasks").json()
        assert {t["date"] for t in legacy["tasks"]} == {date.today().isoformat()}

    def test_habit_create_is_rate_limited(self, client):
        from rate_limiter import RATE_LIMITS
        limit = RATE_LIMITS["habit_create"]["requests"]
        for n in range(limit):
            assert client.post("/api/habits?tz=UTC", json=habit_body(title=f"Habit {n}")).status_code == 201
        assert client.post("/api/habits?tz=UTC", json=habit_body(title="Too fast")).status_code == 429
