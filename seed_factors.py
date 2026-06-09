"""
Idempotent seeder for emission factor reference data.

Usage:
    python seed_factors.py

Can also be called at app startup via seed() — but only when both
collections are empty, to avoid slowing down every cold start.

⚠️  The emission_factors.json values are ADEME order-of-magnitude
approximations. Replace with official Base Empreinte V23.6 values
from data.ademe.fr before any public release.
"""
import json
import os
import sys
from pathlib import Path

from pymongo import MongoClient, ASCENDING

FACTORS_FILE = Path(__file__).parent / "emission_factors.json"


def _get_client():
    mongo_url = os.getenv("MONGO_URL")
    if not mongo_url:
        raise RuntimeError("MONGO_URL environment variable is not set")
    return MongoClient(
        mongo_url,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )


def seed(client=None):
    """
    Upsert emission factors into ef_transport and ef_spend collections.

    Safe to call multiple times — uses upsert on the unique key fields.
    Pass an existing MongoClient to reuse a connection; otherwise one is
    created (and closed) for the duration of this call.
    """
    own_client = client is None
    if own_client:
        client = _get_client()

    try:
        db_name = os.getenv("DB_NAME", "GreenHabit_db")
        db = client[db_name]

        with open(FACTORS_FILE, encoding="utf-8") as f:
            data = json.load(f)

        version = data["version"]

        # ── Transport ─────────────────────────────────────────────────
        transport_col = db["ef_transport"]
        transport_col.create_index([("mode_key", ASCENDING)], unique=True)

        transport_ops = []
        for record in data["transport"]:
            doc = {**record, "source": version}
            transport_ops.append({
                "filter": {"mode_key": record["mode_key"]},
                "update": {"$set": doc},
                "upsert": True,
            })

        if transport_ops:
            from pymongo import UpdateOne
            transport_col.bulk_write(
                [UpdateOne(op["filter"], op["update"], upsert=op["upsert"]) for op in transport_ops],
                ordered=False,
            )
            print(f"✅ Seeded {len(transport_ops)} transport factors (source: {version})")

        # ── Spend ──────────────────────────────────────────────────────
        spend_col = db["ef_spend"]
        spend_col.create_index([("sector_key", ASCENDING)], unique=True)

        spend_ops = []
        for record in data["spend"]:
            doc = {**record, "source": version}
            spend_ops.append({
                "filter": {"sector_key": record["sector_key"]},
                "update": {"$set": doc},
                "upsert": True,
            })

        if spend_ops:
            from pymongo import UpdateOne
            spend_col.bulk_write(
                [UpdateOne(op["filter"], op["update"], upsert=op["upsert"]) for op in spend_ops],
                ordered=False,
            )
            print(f"✅ Seeded {len(spend_ops)} spend factors (source: {version})")

    finally:
        if own_client:
            client.close()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    seed()
    print("✅ Seed complete")
