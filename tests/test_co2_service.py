import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from co2_service import (
    calculate_transport_emission,
    project_annual,
    calculate_spend_emission,
    summarize_spend,
)

# ── Transport emission tests ───────────────────────────────────────────────────

PETROL_MEDIUM = 0.170  # kg CO₂e/km — car_petrol_medium factor


def test_single_trip_basic():
    kg = calculate_transport_emission(PETROL_MEDIUM, 10.0, per_vehicle=True)
    assert kg == pytest.approx(1.700, abs=0.001)


def test_per_vehicle_split_four_passengers():
    full = calculate_transport_emission(PETROL_MEDIUM, 10.0, per_vehicle=True)
    shared = calculate_transport_emission(PETROL_MEDIUM, 10.0, passengers=4, per_vehicle=True)
    assert shared == pytest.approx(full / 4, abs=0.001)


def test_round_trip_doubles_result():
    one_way = calculate_transport_emission(PETROL_MEDIUM, 10.0, per_vehicle=True)
    both_ways = calculate_transport_emission(PETROL_MEDIUM, 10.0, round_trip=True, per_vehicle=True)
    assert both_ways == pytest.approx(one_way * 2, abs=0.001)


def test_public_transport_ignores_passengers():
    bus_factor = 0.103
    single = calculate_transport_emission(bus_factor, 20.0, passengers=1, per_vehicle=False)
    group = calculate_transport_emission(bus_factor, 20.0, passengers=4, per_vehicle=False)
    assert single == group


# ── Annual projection tests ────────────────────────────────────────────────────

def test_annual_projection_daily():
    per_trip = 1.0
    assert project_annual(per_trip, "daily") == pytest.approx(365.0, abs=0.001)


def test_annual_projection_weekly():
    per_trip = 1.0
    assert project_annual(per_trip, "weekly") == pytest.approx(52.0, abs=0.001)


def test_annual_projection_monthly():
    per_trip = 1.0
    assert project_annual(per_trip, "monthly") == pytest.approx(12.0, abs=0.001)


def test_frequency_once_multiplier_is_one():
    per_trip = 5.5
    assert project_annual(per_trip, "once") == pytest.approx(5.5, abs=0.001)


def test_unknown_frequency_raises():
    with pytest.raises(ValueError, match="Unknown frequency"):
        project_annual(1.0, "fortnightly")


# ── Input validation tests ─────────────────────────────────────────────────────

def test_negative_distance_raises():
    with pytest.raises(ValueError, match="distance_km"):
        calculate_transport_emission(PETROL_MEDIUM, -5.0)


def test_zero_distance_returns_zero():
    kg = calculate_transport_emission(PETROL_MEDIUM, 0.0)
    assert kg == 0.0


def test_passengers_zero_raises():
    with pytest.raises(ValueError, match="passengers"):
        calculate_transport_emission(PETROL_MEDIUM, 10.0, passengers=0, per_vehicle=True)


# ── Spend emission tests ───────────────────────────────────────────────────────

GROCERIES_FACTOR = 0.076  # kg CO₂e/EUR


def test_spend_single_item():
    kg = calculate_spend_emission(200.0, GROCERIES_FACTOR)
    assert kg == pytest.approx(15.2, abs=0.001)


def test_spend_zero_amount():
    assert calculate_spend_emission(0.0, GROCERIES_FACTOR) == 0.0


# ── summarize_spend tests ──────────────────────────────────────────────────────

def test_summarize_single_item_share_is_100():
    lines = [{"label": "Groceries", "amount_eur": 100.0, "kg_co2e": 7.6, "uncertainty_pct": 20}]
    result = summarize_spend(lines)
    assert result["total_kg_co2e"] == pytest.approx(7.6, abs=0.001)
    assert result["breakdown"][0]["share_pct"] == pytest.approx(100.0, abs=0.1)


def test_summarize_multi_item_total_and_order():
    lines = [
        {"label": "Electronics", "amount_eur": 80.0,  "kg_co2e": 4.0, "uncertainty_pct": 30},
        {"label": "Groceries",   "amount_eur": 200.0, "kg_co2e": 15.2, "uncertainty_pct": 20},
    ]
    result = summarize_spend(lines)
    assert result["total_kg_co2e"] == pytest.approx(19.2, abs=0.001)
    # Breakdown is sorted descending — groceries first
    assert result["breakdown"][0]["label"] == "Groceries"
    assert result["breakdown"][1]["label"] == "Electronics"


def test_summarize_share_pct_sums_to_100():
    lines = [
        {"label": "A", "amount_eur": 100.0, "kg_co2e": 5.0, "uncertainty_pct": 10},
        {"label": "B", "amount_eur": 50.0,  "kg_co2e": 3.0, "uncertainty_pct": 15},
        {"label": "C", "amount_eur": 30.0,  "kg_co2e": 2.0, "uncertainty_pct": 20},
    ]
    result = summarize_spend(lines)
    total_share = sum(item["share_pct"] for item in result["breakdown"])
    assert total_share == pytest.approx(100.0, abs=0.2)
