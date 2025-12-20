from fastapi import FastAPI, APIRouter, HTTPException, Query, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta
from typing import List, Optional
import os
import uuid
from pymongo import MongoClient, DESCENDING

app = FastAPI(
    title="GreenHabit API",
    description="Sustainable habits tracking platform",
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
        raise HTTPException(status_code=503, detail=f"Database unavailable: {str(e)}")

def sanitize_doc(doc):
    if doc and "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc

def sanitize_docs(docs):
    return [sanitize_doc(doc) for doc in docs]

def get_user_id(x_user_id: Optional[str] = Header(None)) -> str:
    return x_user_id or "demo-user"

class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    userId: str
    title: str = Field(..., min_length=1, max_length=200)
    details: str = Field(..., max_length=1000)
    category: str = Field(..., description="Task category")
    date: str = Field(..., description="ISO date string")
    points: int = Field(..., ge=0, le=1000)
    estimatedImpact: str = Field(..., max_length=200)
    isCompleted: bool = False
    completedAt: Optional[datetime] = None
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

class CreateTaskPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    details: str = Field(..., max_length=1000)
    category: str
    points: int = Field(..., ge=0, le=1000)
    estimatedImpact: str = Field(..., max_length=200)
    date: Optional[str] = None

class UpdateTaskPayload(BaseModel):
    isCompleted: Optional[bool] = None
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    details: Optional[str] = Field(None, max_length=1000)
    category: Optional[str] = None
    points: Optional[int] = Field(None, ge=0, le=1000)

@app.get("/")
async def root():
    return {
        "service": "GreenHabit API",
        "version": "2.1.0",
        "status": "running"
    }

@app.get("/healthz")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

@api.get("/tasks")
async def get_tasks(
    date: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    completed: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    x_user_id: Optional[str] = Header(None)
):
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        
        query = {"userId": user_id}
        if date:
            query["date"] = date
        if category:
            query["category"] = category
        if completed is not None:
            query["isCompleted"] = completed
        
        tasks = list(db.tasks.find(query).sort("createdAt", DESCENDING).limit(limit))
        return sanitize_docs(tasks)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch tasks: {str(e)}")

@api.post("/tasks", status_code=201)
async def create_task(
    payload: CreateTaskPayload,
    x_user_id: Optional[str] = Header(None)
):
    try:
        task_date = payload.date or date.today().isoformat()
        user_id = get_user_id(x_user_id)
        
        task = Task(
            userId=user_id,
            title=payload.title,
            details=payload.details,
            category=payload.category,
            date=task_date,
            points=payload.points,
            estimatedImpact=payload.estimatedImpact,
        )
        
        db = get_db()
        db.tasks.insert_one(task.dict())
        
        return {
            "success": True,
            "taskId": task.id,
            "message": "Task created successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create task: {str(e)}")

@api.patch("/tasks/{task_id}")
async def update_task(
    task_id: str,
    payload: UpdateTaskPayload,
    x_user_id: Optional[str] = Header(None)
):
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        
        update_data = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        update_data["updatedAt"] = datetime.utcnow()
        
        if "isCompleted" in update_data and update_data["isCompleted"]:
            update_data["completedAt"] = datetime.utcnow()
        
        result = db.tasks.update_one(
            {"id": task_id, "userId": user_id},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        
        return {
            "success": True,
            "message": "Task updated successfully",
            "modified": result.modified_count > 0
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update task: {str(e)}")

@api.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    x_user_id: Optional[str] = Header(None)
):
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        result = db.tasks.delete_one({"id": task_id, "userId": user_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        
        return {
            "success": True,
            "message": "Task deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete task: {str(e)}")

@api.get("/stats/weekly")
async def weekly_stats(x_user_id: Optional[str] = Header(None)):
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        
        daily_stats = []
        total_completed = 0
        total_points = 0
        
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        
        for i in range(7):
            day = week_start + timedelta(days=i)
            day_str = day.isoformat()
            
            tasks = list(db.tasks.find({
                "userId": user_id,
                "date": day_str,
                "isCompleted": True
            }))
            
            completed = len(tasks)
            points = sum(t.get("points", 0) for t in tasks)
            
            daily_stats.append({
                "day": days[i],
                "date": day_str,
                "completed": completed,
                "points": points
            })
            
            total_completed += completed
            total_points += points
        
        return {
            "days": daily_stats,
            "totalCompleted": total_completed,
            "totalPoints": total_points,
            "co2Saved": round(total_completed * 0.3, 2)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {str(e)}")

@api.get("/stats/monthly")
async def monthly_stats(x_user_id: Optional[str] = Header(None)):
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        
        today = date.today()
        month_start = today.replace(day=1)
        
        weeks_data = []
        total_completed = 0
        total_points = 0
        
        current_date = month_start
        week_num = 1
        
        while current_date.month == today.month and week_num <= 5:
            week_end = min(current_date + timedelta(days=6), today)
            
            tasks = list(db.tasks.find({
                "userId": user_id,
                "date": {"$gte": current_date.isoformat(), "$lte": week_end.isoformat()},
                "isCompleted": True
            }))
            
            completed = len(tasks)
            points = sum(t.get("points", 0) for t in tasks)
            
            weeks_data.append({
                "week": week_num,
                "completed": completed,
                "points": points
            })
            
            total_completed += completed
            total_points += points
            
            current_date = week_end + timedelta(days=1)
            week_num += 1
        
        return {
            "weeks": weeks_data,
            "totalCompleted": total_completed,
            "totalPoints": total_points,
            "co2Saved": round(total_completed * 0.3, 2)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {str(e)}")

@api.get("/preferences")
async def get_preferences(x_user_id: Optional[str] = Header(None)):
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        prefs = db.preferences.find_one({"userId": user_id})
        
        if not prefs:
            prefs = {
                "userId": user_id,
                "country": "TR",
                "interests": ["energy", "water", "waste"],
                "language": "en"
            }
            db.preferences.insert_one(prefs)
            prefs = db.preferences.find_one({"userId": user_id})
        
        return sanitize_doc(prefs)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch preferences: {str(e)}")

@api.put("/preferences")
async def update_preferences(
    country: Optional[str] = Body(None),
    interests: Optional[List[str]] = Body(None),
    language: Optional[str] = Body(None),
    x_user_id: Optional[str] = Header(None)
):
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        
        update_data = {}
        if country:
            update_data["country"] = country
        if interests:
            update_data["interests"] = interests
        if language:
            update_data["language"] = language
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        db.preferences.update_one(
            {"userId": user_id},
            {"$set": update_data},
            upsert=True
        )
        
        prefs = db.preferences.find_one({"userId": user_id})
        return sanitize_doc(prefs)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update preferences: {str(e)}")

@api.get("/learning")
async def get_learning(category: Optional[str] = Query(None)):
    try:
        db = get_db()
        
        count = db.learning.count_documents({})
        if count == 0:
            seed_data = [
                {
                    "id": str(uuid.uuid4()),
                    "title": "Save Water: Daily Habits",
                    "details": "Learn practical ways to reduce water consumption.",
                    "category": "Water"
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "Energy Efficiency at Home",
                    "details": "Reduce your carbon footprint with simple actions.",
                    "category": "Energy"
                }
            ]
            db.learning.insert_many(seed_data)
        
        query = {}
        if category:
            query["category"] = category
        
        items = list(db.learning.find(query).limit(100))
        return sanitize_docs(items)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch learning content: {str(e)}")

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
                "estimatedImpact": "Saves ~0.3kg CO₂"
            },
            {
                "title": "Use a reusable bottle",
                "details": "Avoid single-use plastic bottles.",
                "category": "Waste",
                "date": today,
                "points": 15,
                "estimatedImpact": "Reduces plastic waste"
            },
            {
                "title": "Take shorter showers",
                "details": "Save water by limiting shower time to 5 minutes.",
                "category": "Water",
                "date": today,
                "points": 20,
                "estimatedImpact": "Saves ~40L water"
            }
        ],
        "count": 3
    }

app.include_router(api)
