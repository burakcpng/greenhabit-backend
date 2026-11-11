"""
utils/text_safety.py — the server-side profanity check.

Leet-speak (digits and symbols read as letters) applies only inside words
that have letters in them ("sh1t", "b4d", "$hit"). Standalone numbers and
number+unit tokens ("30", "5km", "10k", "2L") are left alone. Same rule as
the iOS ContentSafetyFilter.swift.

Run:  python3 -m pytest tests/test_text_safety.py -v
"""

import json
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


# ── The corpus shared with the iOS filter ──────────────────────────────────
#   Canonical copy : <ios repo>/shared/content_filter_corpus.json
#   This repo      : tests/fixtures/content_filter_corpus.json   (never edit by hand)
#   Sync           : <ios repo>/scripts/sync_recurrence_fixture.sh  [--check]

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS_PATH = os.path.join(BACKEND_ROOT, "tests", "fixtures", "content_filter_corpus.json")
CANONICAL_CORPUS_PATH = os.path.join(os.path.dirname(BACKEND_ROOT), "shared", "content_filter_corpus.json")

with open(CORPUS_PATH, encoding="utf-8") as corpus_file:
    CORPUS = json.load(corpus_file)

# Ordinary titles the backend refuses on purpose, because the word itself is
# on its list (decided 2026-11-11: keep "kaşar"). The iOS filter accepts them.
PENDING_DECISION = {
    "Kaşar peyniri yerine sebze ye": "kaşar",     # a cheese; also a slur
}


def test_corpus_is_large_enough():
    assert CORPUS["schema"] == 1
    assert len(CORPUS["allowed"]) >= 150
    assert set(PENDING_DECISION) <= set(CORPUS["allowed"])


@pytest.mark.parametrize("title", [t for t in CORPUS["allowed"] if t not in PENDING_DECISION])
def test_corpus_ordinary_titles_are_accepted(title):
    assert ProfanityFilter.is_safe(title), title


@pytest.mark.parametrize("title, word", sorted(PENDING_DECISION.items()))
def test_corpus_titles_pending_a_decision_are_still_refused(title, word):
    assert not ProfanityFilter.is_safe(title)
    assert word in ProfanityFilter.BANNED_WORDS


@pytest.mark.parametrize("text", CORPUS["refused"])
def test_corpus_obscene_texts_are_refused(text):
    assert not ProfanityFilter.is_safe(text), text


def test_corpus_copy_matches_the_canonical_file():
    if not os.path.exists(CANONICAL_CORPUS_PATH):
        pytest.skip("iOS repo not next to the backend")
    with open(CANONICAL_CORPUS_PATH, "rb") as canonical, open(CORPUS_PATH, "rb") as copy:
        assert canonical.read() == copy.read(), "run scripts/sync_recurrence_fixture.sh in the iOS repo"


@pytest.mark.parametrize("text", ["Sık sık su iç", "Proti nudě číst knihu", "Got my bike fixed", "Go to bed by 11",
                                  "Vitamin D a day", "Read Dickens for an hour"])
def test_folding_and_joining_do_not_create_false_positives(text):
    assert ProfanityFilter.is_safe(text)


@pytest.mark.parametrize("word", ["anne", "babanne"])
def test_mother_and_grandmother_are_ordinary_words(word):
    """Removed from the list on purpose (2026-11-11); the insults stay."""
    assert word not in ProfanityFilter.BANNED_WORDS
    assert ProfanityFilter.is_safe(f"{word.capitalize()} ile yürüyüşe çık")
    assert not ProfanityFilter.is_safe("ananı")


@pytest.mark.parametrize("text", ["fück", "fu\u0441k", "f u c k", "f.u.c.k", "f_u_c_k", "fu ck", "s h i t", "nude"])
def test_spaced_out_lookalike_and_accented_forms_are_refused(text):
    assert not ProfanityFilter.is_safe(text)
