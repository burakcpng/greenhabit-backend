import os
from datetime import datetime
from fastapi import HTTPException
from pymongo import MongoClient

_mongo_client = None
_db = None


def get_db():
    global _mongo_client, _db
    if _mongo_client is None:
        mongo_url = os.getenv("MONGO_URL")
        db_name = os.getenv("DB_NAME", "GreenHabit_db")
        if not mongo_url:
            raise HTTPException(status_code=500, detail="Database configuration missing")
        try:
            _mongo_client = MongoClient(
                mongo_url,
                serverSelectionTimeoutMS=3000,
                connectTimeoutMS=3000,
                maxPoolSize=10,
                retryWrites=True,
            )
            _mongo_client.admin.command("ping")
            _db = _mongo_client[db_name]
            print("✅ MongoDB connection established")
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Database unavailable: {str(e)}")
    return _db


def sanitize_doc(doc):
    if doc and "_id" in doc:
        if "id" not in doc:
            doc["id"] = str(doc["_id"])
        del doc["_id"]
    date_fields = ["createdAt", "updatedAt", "completedAt"]
    for field in date_fields:
        if field in doc and doc[field] is not None:
            if isinstance(doc[field], datetime):
                doc[field] = doc[field].replace(microsecond=0).isoformat() + "Z"
    return doc


def sanitize_docs(docs):
    return [sanitize_doc(doc) for doc in docs]
