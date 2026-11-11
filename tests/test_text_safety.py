"""
utils/text_safety.py — the server-side profanity check.

Leet-speak (digits and symbols read as letters) applies only inside words
that have letters in them ("sh1t", "b4d", "$hit"). Standalone numbers and
number+unit tokens ("30", "5km", "10k", "2L") are left alone. Same rule as
the iOS ContentSafetyFilter.swift.

Run:  python3 -m pytest tests/test_text_safety.py -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from utils.text_safety import ProfanityFilter

REALISTIC_TITLES = [
    "Walk 5 km",
    "Drink 2L water",
    "Meditate 10 min",
    "Read 30 pages",
    "Run 5k",
    "Run 10k on Sunday",
    "Bike 15 km to work",
    "Walk 10,000 steps",
    "Walk 10000 steps",
    "Plant 3 trees",
    "Shower in 5 min",
    "Do 20 squats",
    "Drink 8 glasses of water",
    "Sleep 8h",
    "Unplug 4 chargers",
    "Save 1.5kg CO2",
    "Save 50 kWh this month",
    "Heating down to 19°C",
    "Wash at 30°",
    "Lights off at 23:00",
    "Meat-free 3 days a week",
    "Cut screen time by 50%",
    "Recycle 6 bottles",
    "Take the 7:45 bus",
    "Bring 2 reusable bags",
    "Compost 1 kg of food waste",
    "Use 1 cup of coffee, not 2",
    "Top 10 eco tips",
    "Turn off 4 lights & 2 fans",
    "Fix the leak in 1 day",
    "Line 13 tram instead of car",
    "Week 52 challenge",
    "Bring a reusable cup",
    "",
]

REFUSED = [
    "fuck",
    "FUCK",
    "what the fuck",
    "sh1t",
    "5h1t",
    "b1tch",
    "a55hole",
    "4sshole",
    "$hit",
    "@sshole",
    "bullsh1t habit",
    "you are a b1tch",
    "siktir",
    "s1kt1r",
    "orospu",
    "pu55y",
    "p0rn",
    "4ss",
    "amk",          # was glued to the emoji below by a missing comma
    "🖕",
    "go 🖕 yourself",
]


@pytest.mark.parametrize("title", REALISTIC_TITLES)
def test_realistic_titles_with_numbers_are_allowed(title):
    assert ProfanityFilter.is_safe(title), title


@pytest.mark.parametrize("text", REFUSED)
def test_offensive_words_are_still_refused(text):
    assert not ProfanityFilter.is_safe(text), text


@pytest.mark.parametrize("token", ["30", "5km", "10k", "2l", "1.5kg", "10,000", "19°c", "8h", "45min",
                                   "3x", "1st", "100%", "#1", "(5km),", "23:00"])
def test_numbers_and_units_are_left_alone(token):
    assert ProfanityFilter.substitute_leet(token) == token


@pytest.mark.parametrize("token, expected", [
    ("sh1t", "shit"), ("b4d", "bad"), ("5h1t", "shit"), ("$hit", "shit"), ("@sshole", "asshole"),
    ("4ss", "ass"), ("co2", "coz"),
])
def test_mixed_words_are_read_as_leetspeak(token, expected):
    assert ProfanityFilter.substitute_leet(token) == expected


def test_validate_content_raises_with_the_field_name():
    ProfanityFilter.validate_content("Walk 5 km", "Task Title")
    with pytest.raises(ValueError, match="Task Title contains inappropriate language"):
        ProfanityFilter.validate_content("sh1t", "Task Title")


def test_same_rule_as_the_ios_filter():
    """The map and the units must match ContentSafetyFilter.swift."""
    swift = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                         "GreenHabit", "ContentSafetyFilter.swift")
    if not os.path.exists(swift):
        pytest.skip("iOS sources not next to the backend")
    source = open(swift, encoding="utf-8").read()
    for unit in ProfanityFilter.NUMBER_UNITS:
        assert f'"{unit}"' in source, f"unit {unit!r} missing on iOS"
    for key, value in ProfanityFilter.LEET_MAP.items():
        assert f'"{key}": "{value}"' in source, f"leet {key!r} → {value!r} missing on iOS"
