from fastapi import FastAPI, APIRouter, HTTPException, Query, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
import os
import uuid
from pymongo import MongoClient, DESCENDING

app = FastAPI(
    title="GreenHabit API",
    description="Sustainable habit tracking platform",
    version="2.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

api = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Database Connection ---
def get_db():
    mongo_url = os.getenv("MONGO_URL")
    db_name = os.getenv("DB_NAME", "GreenHabit_db")
    
    if not mongo_url:
        raise HTTPException(status_code=500, detail="Database configuration missing")
    
    try:
        client = MongoClient(
            mongo_url,
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=3000,
            maxPoolSize=10,
            retryWrites=True
        )
        client.admin.command('ping')
        return client[db_name]
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {str(e)}")

# --- Helper Functions ---
def sanitize_doc(doc):
    if doc and "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc

def sanitize_docs(docs):
    return [sanitize_doc(doc) for doc in docs]

def get_current_user(x_user_id: Optional[str] = Header(None)):
    """Validates User ID from header or assigns default."""
    if not x_user_id:
        return "demo-user"
    return x_user_id

# --- Models ---
class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    userId: str
    title: str = Field(..., min_length=1, max_length=200)
    details: str = Field(..., max_length=1000)
    category: str
    date: str
    points: int
    estimatedImpact: str
    isCompleted: bool = False
    completedAt: Optional[datetime] = None
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

class CreateTaskPayload(BaseModel):
    title: str
    details: str
    category: str
    points: int
    estimatedImpact: str
    date: Optional[str] = None

class UpdateTaskPayload(BaseModel):
    isCompleted: Optional[bool] = None
    title: Optional[str] = None
    details: Optional[str] = None
    category: Optional[str] = None
    points: Optional[int] = None

# --- Main Endpoints ---
@app.get("/")
async def root():
    return {"service": "GreenHabit API", "status": "running"}

# --- Tasks API ---
@api.get("/tasks")
async def get_tasks(
    date: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(None)
):
    user_id = get_current_user(x_user_id)
    db = get_db()
    
    query = {"userId": user_id}
    if date:
        query["date"] = date
        
    tasks = list(db.tasks.find(query).sort("createdAt", DESCENDING))
    return sanitize_docs(tasks)

@api.post("/tasks", status_code=201)
async def create_task(payload: CreateTaskPayload, x_user_id: Optional[str] = Header(None)):
    user_id = get_current_user(x_user_id)
    task_date = payload.date or date.today().isoformat()
    
    task = Task(
        userId=user_id,
        title=payload.title,
        details=payload.details,
        category=payload.category,
        date=task_date,
        points=payload.points,
        estimatedImpact=payload.estimatedImpact
    )
    
    db = get_db()
    db.tasks.insert_one(task.dict())
    
    return {"success": True, "taskId": task.id, "message": "Task created successfully"}

@api.patch("/tasks/{task_id}")
async def update_task(
    task_id: str,
    payload: UpdateTaskPayload,
    x_user_id: Optional[str] = Header(None)
):
    user_id = get_current_user(x_user_id)
    db = get_db()
    
    update_data = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    update_data["updatedAt"] = datetime.utcnow()
    if update_data.get("isCompleted"):
        update_data["completedAt"] = datetime.utcnow()
    
    result = db.tasks.update_one(
        {"id": task_id, "userId": user_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found or unauthorized")
    
    return {"success": True, "modified": result.modified_count > 0}

@api.delete("/tasks/{task_id}")
async def delete_task(task_id: str, x_user_id: Optional[str] = Header(None)):
    user_id = get_current_user(x_user_id)
    db = get_db()
    result = db.tasks.delete_one({"id": task_id, "userId": user_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"success": True}

# --- Stats API ---
@api.get("/stats/weekly")
async def weekly_stats(x_user_id: Optional[str] = Header(None)):
    user_id = get_current_user(x_user_id)
    db = get_db()
    
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    
    daily_stats = []
    total_completed = 0
    
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for i in range(7):
        current_day = week_start + timedelta(days=i)
        day_str = current_day.isoformat()
        
        count = db.tasks.count_documents({
            "userId": user_id,
            "date": day_str,
            "isCompleted": True
        })
        
        daily_stats.append({
            "day": days[i],
            "date": day_str,
            "completed": count,
            "points": count * 10
        })
        total_completed += count
        
    return {
        "days": daily_stats,
        "totalCompleted": total_completed,
        "totalPoints": total_completed * 10,
        "co2Saved": round(total_completed * 0.3, 2)
    }

# --- Preferences API ---
@api.get("/preferences")
async def get_preferences(x_user_id: Optional[str] = Header(None)):
    user_id = get_current_user(x_user_id)
    db = get_db()
    prefs = db.preferences.find_one({"userId": user_id})
    
    if not prefs:
        prefs = {
            "userId": user_id,
            "country": "US",
            "interests": ["energy", "water"],
            "language": "en"
        }
        db.preferences.insert_one(prefs)
        prefs = db.preferences.find_one({"userId": user_id})
        
    return sanitize_doc(prefs)

@api.put("/preferences")
async def update_preferences(
    payload: Dict[str, Any],
    x_user_id: Optional[str] = Header(None)
):
    user_id = get_current_user(x_user_id)
    db = get_db()
    
    db.preferences.update_one(
        {"userId": user_id},
        {"$set": payload},
        upsert=True
    )
    return {"success": True}

app.include_router(api)
