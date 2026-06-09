"""
Pure CO₂ calculation logic — no database calls, no FastAPI imports.
All functions are synchronous and fully unit-testable.
"""

FREQUENCY_MULTIPLIERS: dict[str, int] = {
    "once": 1,
    "daily": 365,
    "weekly": 52,
    "monthly": 12,
}


def calculate_transport_emission(
    factor_per_km: float,
    distance_km: float,
    round_trip: bool = False,
    passengers: int = 1,
    per_vehicle: bool = False,
) -> float:
    """
    Return kg CO₂e for a single trip leg (or both legs if round_trip).

    For per_vehicle modes (car, motorcycle) the total is divided by
    the number of passengers to give per-person emissions.
    Public-transport and flight factors are already per-passenger, so
    per_vehicle=False skips the division.
    """
    if distance_km < 0:
        raise ValueError("distance_km must be >= 0")
    if passengers < 1:
        raise ValueError("passengers must be >= 1")

    legs = 2 if round_trip else 1
    total = factor_per_km * distance_km * legs
    if per_vehicle:
        total /= passengers
    return round(total, 3)


def project_annual(per_trip_kg: float, frequency: str) -> float:
    """
    Scale a single-trip emission to an annualised figure.

    Supported frequencies: once, daily, weekly, monthly.
    Raises ValueError for unknown frequency strings.
    """
    if frequency not in FREQUENCY_MULTIPLIERS:
        raise ValueError(
            f"Unknown frequency '{frequency}'. "
            f"Valid values: {list(FREQUENCY_MULTIPLIERS)}"
        )
    return round(per_trip_kg * FREQUENCY_MULTIPLIERS[frequency], 3)


def calculate_spend_emission(amount_eur: float, factor_per_eur: float) -> float:
    """Return kg CO₂e for a spend amount in EUR."""
    return round(amount_eur * factor_per_eur, 3)


def summarize_spend(lines: list[dict]) -> dict:
    """
    Aggregate a list of spend line items into a summary.

    Each input dict must have: label, amount_eur, kg_co2e, uncertainty_pct.
    Returns a dict with total_kg_co2e and a breakdown list sorted
    descending by kg_co2e, with share_pct added to each entry.
    """
    total = sum(line["kg_co2e"] for line in lines)
    total = round(total, 3)

    enriched = []
    for line in lines:
        share = round((line["kg_co2e"] / total * 100) if total > 0 else 0.0, 1)
        enriched.append({**line, "share_pct": share})

    enriched.sort(key=lambda x: x["kg_co2e"], reverse=True)

    return {"total_kg_co2e": total, "breakdown": enriched}
