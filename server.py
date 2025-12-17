from fastapi import FastAPI, APIRouter, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import List, Optional
import os
import uuid
from pymongo import MongoClient

app = FastAPI(title="GreenHabit Backend")
api = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    mongo_url = os.getenv("MONGO_URL")
    db_name = os.getenv("DB_NAME", "GreenHabit_db")

    if not mongo_url:
        raise HTTPException(status_code=500, detail="MONGO_URL environment variable is missing")

    client = MongoClient(
        mongo_url,
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=3000
    )

    return client[db_name]

def sanitize_doc(doc):
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc

def sanitize_docs(docs):
    return [sanitize_doc(doc) for doc in docs]

class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    userId: str = "demo-user"
    title: str
    details: str
    category: str
    date: str
    points: int
    estimatedImpact: str
    isCompleted: bool = False
    createdAt: datetime = Field(default_factory=datetime.utcnow)

class CreateTaskPayload(BaseModel):
    title: str
    details: str
    category: str
    points: int
    estimatedImpact: str
    date: Optional[str] = None

class LearningContent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    details: str
    category: str

class UserPreferences(BaseModel):
    userId: str = "demo-user"
    country: str
    interests: List[str]
    language: str

@app.get("/")
async def root():
    return {"status": "GreenHabit backend running"}

@app.get("/healthz")
async def health_check():
    return {"ok": True}

@api.get("/tasks")
async def get_tasks(date: str = Query(...)):
    try:
        db = get_db()
        tasks = list(db.tasks.find({"date": date}).limit(100))
        return sanitize_docs(tasks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@api.post("/tasks")
async def create_task(payload: CreateTaskPayload):
    try:
        task_date = payload.date or date.today().isoformat()
        
        task = Task(
            title=payload.title,
            details=payload.details,
            category=payload.category,
            date=task_date,
            points=payload.points,
            estimatedImpact=payload.estimatedImpact,
        )
        
        db = get_db()
        db.tasks.insert_one(task.dict())
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@api.patch("/tasks/{task_id}")
async def update_task(task_id: str, isCompleted: bool):
    try:
        db = get_db()
        result = db.tasks.update_one(
            {"id": task_id},
            {"$set": {"isCompleted": isCompleted}},
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@api.get("/learning")
async def get_learning():
    try:
        db = get_db()
        count = db.learning.count_documents({})
        if count == 0:
            seed = [
                LearningContent(
                    title="Save Water",
                    details="Take shorter showers and fix leaks.",
                    category="Water",
                ),
                LearningContent(
                    title="Reduce Energy Use",
                    details="Turn off lights when leaving rooms.",
                    category="Energy",
                ),
            ]
            db.learning.insert_many([item.dict() for item in seed])
        
        items = list(db.learning.find().limit(100))
        return sanitize_docs(items)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@api.get("/preferences")
async def get_preferences():
    try:
        db = get_db()
        prefs = db.preferences.find_one({"userId": "demo-user"})
        if not prefs:
            prefs = UserPreferences(
                country="TR",
                interests=["energy", "water"],
                language="en",
            ).dict()
            db.preferences.insert_one(prefs)
            prefs = db.preferences.find_one({"userId": "demo-user"})
        
        return sanitize_doc(prefs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@api.put("/preferences")
async def update_preferences(prefs: UserPreferences):
    try:
        db = get_db()
        db.preferences.update_one(
            {"userId": prefs.userId},
            {"$set": prefs.dict()},
            upsert=True,
        )
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@api.get("/stats/weekly")
async def weekly_stats():
    return {
        "days": [
            {"day": "Mon", "completed": 1, "points": 10},
            {"day": "Tue", "completed": 2, "points": 20},
            {"day": "Wed", "completed": 1, "points": 10},
        ],
        "totalCompleted": 4,
        "totalPoints": 40,
        "co2Saved": 1.2,
    }

@api.get("/stats/monthly")
async def monthly_stats():
    return {
        "weeks": [
            {"week": 1, "completed": 5, "points": 50},
            {"week": 2, "completed": 7, "points": 70},
        ],
        "totalCompleted": 12,
        "totalPoints": 120,
        "co2Saved": 3.5,
    }

@api.post("/ai/generate-tasks")
async def generate_ai_tasks():
    today = date.today().isoformat()
    return {
        "tasks": [
            {
                "title": "Turn off unused lights",
                "details": "Reduce electricity usage at home.",
                "category": "Energy",
                "date": today,
                "points": 10,
                "estimatedImpact": "Saves ~0.3kg CO₂",
            },
            {
                "title": "Use a reusable bottle",
                "details": "Avoid single-use plastic bottles.",
                "category": "Waste",
                "date": today,
                "points": 15,
                "estimatedImpact": "Reduces plastic waste",
            },
        ]
    }

app.include_router(api)
