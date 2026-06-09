from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_system import get_current_user
from db import get_db
import co2_service

calc_router = APIRouter(prefix="/api/calc")

_SPEND_NOTE = (
    "Spend-based emission estimates are rough approximations. "
    "Actual emissions vary significantly by supplier, region, and product. "
    "Use for indicative purposes only."
)


# ── Response models ────────────────────────────────────────────────────────────

class TransportModeOut(BaseModel):
    mode_key: str
    label: str
    category: str
    uncertainty_pct: float
    per_vehicle: bool


class SpendSectorOut(BaseModel):
    sector_key: str
    label: str
    uncertainty_pct: float


class TransportRequest(BaseModel):
    mode_key: str
    distance_km: float = Field(..., gt=0, description="Distance in km (must be > 0)")
    round_trip: bool = False
    passengers: int = Field(1, ge=1)
    frequency: str = "once"


class TransportResponse(BaseModel):
    kg_co2e: float
    annual_projection_kg: Optional[float] = None
    uncertainty_pct: float
    label: str
    source: str


class SpendItem(BaseModel):
    sector_key: str
    amount_eur: float = Field(..., gt=0, description="Amount in EUR (must be > 0)")


class SpendRequest(BaseModel):
    items: list[SpendItem] = Field(..., min_length=1)


class SpendBreakdownItem(BaseModel):
    label: str
    amount_eur: float
    kg_co2e: float
    share_pct: float
    uncertainty_pct: float


class SpendResponse(BaseModel):
    total_kg_co2e: float
    breakdown: list[SpendBreakdownItem]
    source: str
    note: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@calc_router.get("/transport/modes", response_model=list[TransportModeOut])
def list_transport_modes(user_id: str = Depends(get_current_user)):
    """Return available transport modes for the UI picker (factors excluded)."""
    db = get_db()
    docs = list(db.ef_transport.find({}, {"_id": 0, "factor_per_km": 0, "source": 0}))
    return docs


@calc_router.get("/spend/sectors", response_model=list[SpendSectorOut])
def list_spend_sectors(user_id: str = Depends(get_current_user)):
    """Return available spend categories for the UI picker (factors excluded)."""
    db = get_db()
    docs = list(db.ef_spend.find({}, {"_id": 0, "factor_per_eur": 0, "source": 0}))
    return docs


@calc_router.post("/transport", response_model=TransportResponse)
def calculate_transport(
    payload: TransportRequest,
    user_id: str = Depends(get_current_user),
):
    db = get_db()
    mode = db.ef_transport.find_one({"mode_key": payload.mode_key})
    if not mode:
        raise HTTPException(status_code=404, detail=f"Unknown mode_key '{payload.mode_key}'")

    if payload.frequency not in co2_service.FREQUENCY_MULTIPLIERS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown frequency '{payload.frequency}'. "
                f"Valid values: {list(co2_service.FREQUENCY_MULTIPLIERS)}"
            ),
        )

    try:
        kg = co2_service.calculate_transport_emission(
            factor_per_km=mode["factor_per_km"],
            distance_km=payload.distance_km,
            round_trip=payload.round_trip,
            passengers=payload.passengers,
            per_vehicle=mode["per_vehicle"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    annual: Optional[float] = None
    if payload.frequency != "once":
        annual = co2_service.project_annual(kg, payload.frequency)

    return TransportResponse(
        kg_co2e=kg,
        annual_projection_kg=annual,
        uncertainty_pct=mode["uncertainty_pct"],
        label=mode["label"],
        source=mode["source"],
    )


@calc_router.post("/spend", response_model=SpendResponse)
def calculate_spend(
    payload: SpendRequest,
    user_id: str = Depends(get_current_user),
):
    db = get_db()

    lines = []
    for item in payload.items:
        sector = db.ef_spend.find_one({"sector_key": item.sector_key})
        if not sector:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown sector_key '{item.sector_key}'",
            )
        kg = co2_service.calculate_spend_emission(item.amount_eur, sector["factor_per_eur"])
        lines.append({
            "label": sector["label"],
            "amount_eur": item.amount_eur,
            "kg_co2e": kg,
            "uncertainty_pct": sector["uncertainty_pct"],
        })

    summary = co2_service.summarize_spend(lines)

    # Attach source from any sector (all share the same version string)
    source = db.ef_spend.find_one({}, {"source": 1, "_id": 0}) or {}

    return SpendResponse(
        total_kg_co2e=summary["total_kg_co2e"],
        breakdown=[SpendBreakdownItem(**b) for b in summary["breakdown"]],
        source=source.get("source", "ADEME-BaseEmpreinte-V23.6"),
        note=_SPEND_NOTE,
    )
