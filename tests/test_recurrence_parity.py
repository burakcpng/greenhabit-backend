"""
Recurrence parity: habit_system.occurs_on vs the fixture shared with iOS.

The same file drives GreenHabitTests/RecurrenceParityTests.swift, so the Python
and Swift recurrence engines cannot drift apart without a test failing.

  Canonical copy : <ios repo>/shared/recurrence_cases.json
  This repo      : tests/fixtures/recurrence_cases.json   (never edit by hand)
  Sync           : <ios repo>/scripts/sync_recurrence_fixture.sh  [--check]
"""

import json
import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from habit_system import occurs_on

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_PATH = os.path.join(BACKEND_ROOT, "tests", "fixtures", "recurrence_cases.json")
# When the backend is checked out inside the iOS repo (the local layout).
CANONICAL_PATH = os.path.join(os.path.dirname(BACKEND_ROOT), "shared", "recurrence_cases.json")

with open(FIXTURE_PATH, encoding="utf-8") as fixture_file:
    FIXTURE = json.load(fixture_file)

CASES = FIXTURE["cases"]


def days_between(first: str, last: str):
    day, end = date.fromisoformat(first), date.fromisoformat(last)
    while day <= end:
        yield day
        day += timedelta(days=1)


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_occurs_on_matches_fixture(case):
    expected = set(case["expected"])
    actual = [
        day.isoformat()
        for day in days_between(case["from"], case["to"])
        if occurs_on(case["habit"], day)
    ]
    assert actual == sorted(expected), case.get("note", "")


def test_fixture_is_well_formed():
    assert FIXTURE["schema"] == 1
    assert len(CASES) >= 30
    names = [c["name"] for c in CASES]
    assert len(names) == len(set(names)), "case names must be unique"
    for case in CASES:
        assert case["from"] <= case["to"], case["name"]
        assert case["expected"] == sorted(set(case["expected"])), case["name"]
        for day in case["expected"]:
            assert case["from"] <= day <= case["to"], case["name"]
        assert case["habit"]["recurrence"]["type"] in ("daily", "weekdays", "everyNDays"), case["name"]


def test_fixture_covers_every_recurrence_type_and_edge():
    types = {c["habit"]["recurrence"]["type"] for c in CASES}
    assert types == {"daily", "weekdays", "everyNDays"}
    assert any(c["habit"]["skippedDates"] for c in CASES)
    assert any(c["habit"]["endDate"] for c in CASES)
    assert any(not c["habit"]["active"] for c in CASES)
    assert any("2028-02-29" in c["expected"] for c in CASES), "leap day"
    assert {"Europe/Prague", "Europe/Istanbul"} <= {c["timezone"] for c in CASES}


def test_backend_copy_matches_canonical_copy():
    """Catches a fixture edited in one repo only. Skipped when the iOS repo is not around (CI, Render)."""
    if not os.path.isfile(CANONICAL_PATH):
        pytest.skip("canonical fixture not reachable from this checkout")
    with open(CANONICAL_PATH, "rb") as canonical, open(FIXTURE_PATH, "rb") as local:
        assert canonical.read() == local.read(), (
            "tests/fixtures/recurrence_cases.json differs from shared/recurrence_cases.json; "
            "run scripts/sync_recurrence_fixture.sh in the iOS repo and commit both"
        )
