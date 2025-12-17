from fastapi import FastAPI, APIRouter, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from datetime import datetime, date
from typing import List, Optional
from pathlib import Path
import os
import uuid

# ==================================================
# ENV
# ==================================================

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / "env")

MONGO_URL = os.getenv("MONGO_URL")
if not MONGO_URL:
    raise RuntimeError("MONGO_URL environment variable is missing")

DB_NAME = os.getenv("DB_NAME", "GreenHabit_db")

# ==================================================
# APP
# ==================================================

app = FastAPI(title="GreenHabit Backend")
api = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# ==================================================
# MODELS
# ==================================================

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


# ==================================================
# HEALTH
# ==================================================

@app.get("/healthz")
async def health_check():
    return {"ok": True}


# ==================================================
# TASKS
# ==================================================

@api.get("/tasks")
async def get_tasks(date: str = Query(...)):
    tasks = await db.tasks.find({"date": date}).to_list(100)
    return tasks


@api.post("/tasks")
async def create_task(payload: CreateTaskPayload):
    task_date = payload.date or date.today().isoformat()

    task = Task(
        title=payload.title,
        details=payload.details,
        category=payload.category,
        date=task_date,
        points=payload.points,
        estimatedImpact=payload.estimatedImpact,
    )

    await db.tasks.insert_one(task.dict())
    return {"success": True}


@api.patch("/tasks/{task_id}")
async def update_task(task_id: str, isCompleted: bool):
    result = await db.tasks.update_one(
        {"id": task_id},
        {"$set": {"isCompleted": isCompleted}},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")

    return {"success": True}


# ==================================================
# LEARNING
# ==================================================

@api.get("/learning")
async def get_learning():
    count = await db.learning.count_documents({})
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
        await db.learning.insert_many([item.dict() for item in seed])

    items = await db.learning.find().to_list(100)
    return items


# ==================================================
# PREFERENCES
# ==================================================

@api.get("/preferences")
async def get_preferences():
    prefs = await db.preferences.find_one({"userId": "demo-user"})
    if not prefs:
        prefs = UserPreferences(
            country="TR",
            interests=["energy", "water"],
            language="en",
        ).dict()
        await db.preferences.insert_one(prefs)

    return prefs


@api.put("/preferences")
async def update_preferences(prefs: UserPreferences):
    await db.preferences.update_one(
        {"userId": prefs.userId},
        {"$set": prefs.dict()},
        upsert=True,
    )
    return {"success": True}


# ==================================================
# STATS
# ==================================================

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


# ==================================================
# AI (MOCK – STABLE)
# ==================================================

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


# ==================================================
# REGISTER ROUTER
# ==================================================

app.include_router(api)

