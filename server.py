from fastapi import FastAPI, APIRouter, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
import os
import uuid
from pymongo import MongoClient, DESCENDING
from functools import lru_cache

app = FastAPI(
    title="GreenHabit API",
    description="Sustainable habits tracking platform",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

api = APIRouter(prefix="/api/v1")

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
        doc["_id"] = str(doc["_id"])
    return doc

def sanitize_docs(docs):
    return [sanitize_doc(doc) for doc in docs]

class TaskCategory(str):
    ENERGY = "Energy"
    WATER = "Water"
    WASTE = "Waste"
    TRANSPORT = "Transport"
    FOOD = "Food"

class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    userId: str = "demo-user"
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
    
    @validator('date')
    def validate_date(cls, v):
        try:
            datetime.fromisoformat(v)
            return v
        except:
            raise ValueError('Invalid date format. Use ISO format (YYYY-MM-DD)')

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

class LearningContent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(..., min_length=1, max_length=200)
    details: str = Field(..., max_length=2000)
    category: str
    imageUrl: Optional[str] = None
    readTimeMinutes: int = Field(default=5, ge=1, le=60)
    createdAt: datetime = Field(default_factory=datetime.utcnow)

class UserPreferences(BaseModel):
    userId: str = "demo-user"
    country: str = Field(..., min_length=2, max_length=2)
    interests: List[str] = Field(..., min_items=1)
    language: str = Field(default="en", min_length=2, max_length=5)
    notificationsEnabled: bool = True
    dailyGoal: int = Field(default=3, ge=1, le=20)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

class DailyStats(BaseModel):
    date: str
    completed: int
    points: int
    co2Saved: float

class WeeklyStatsResponse(BaseModel):
    days: List[DailyStats]
    totalCompleted: int
    totalPoints: int
    co2Saved: float
    streak: int

@app.get("/")
async def root():
    return {
        "service": "GreenHabit API",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "health": "/healthz",
            "docs": "/docs",
            "api": "/api/v1"
        }
    }

@app.get("/healthz")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "GreenHabit API"
    }

@api.get("/tasks", response_model=List[Task])
async def get_tasks(
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    completed: Optional[bool] = Query(None, description="Filter by completion status"),
    limit: int = Query(100, ge=1, le=500)
):
    try:
        db = get_db()
        
        query = {"userId": "demo-user"}
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
        result = db.tasks.insert_one(task.dict())
        
        return {
            "success": True,
            "taskId": task.id,
            "message": "Task created successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create task: {str(e)}")

@api.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: str):
    try:
        db = get_db()
        task = db.tasks.find_one({"id": task_id, "userId": "demo-user"})
        
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        return sanitize_doc(task)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch task: {str(e)}")

@api.patch("/tasks/{task_id}")
async def update_task(task_id: str, payload: UpdateTaskPayload):
    try:
        db = get_db()
        
        update_data = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        update_data["updatedAt"] = datetime.utcnow()
        
        if "isCompleted" in update_data and update_data["isCompleted"]:
            update_data["completedAt"] = datetime.utcnow()
        
        result = db.tasks.update_one(
            {"id": task_id, "userId": "demo-user"},
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
async def delete_task(task_id: str):
    try:
        db = get_db()
        result = db.tasks.delete_one({"id": task_id, "userId": "demo-user"})
        
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

@api.get("/learning", response_model=List[LearningContent])
async def get_learning(
    category: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500)
):
    try:
        db = get_db()
        
        count = db.learning.count_documents({})
        if count == 0:
            seed_data = [
                LearningContent(
                    title="Save Water: Daily Habits",
                    details="Learn practical ways to reduce water consumption. Take shorter showers (5 min max), fix leaky faucets, and use water-efficient appliances.",
                    category="Water",
                    readTimeMinutes=5
                ),
                LearningContent(
                    title="Energy Efficiency at Home",
                    details="Reduce your carbon footprint with simple actions. Turn off lights when leaving rooms, unplug devices, use LED bulbs, and optimize heating/cooling.",
                    category="Energy",
                    readTimeMinutes=7
                ),
                LearningContent(
                    title="Zero Waste Kitchen",
                    details="Transform your kitchen into a sustainable space. Compost food scraps, use reusable containers, buy in bulk, and plan meals to reduce waste.",
                    category="Waste",
                    readTimeMinutes=10
                ),
                LearningContent(
                    title="Sustainable Transportation",
                    details="Reduce emissions through smart travel choices. Walk, bike, or use public transit when possible. Consider carpooling or electric vehicles.",
                    category="Transport",
                    readTimeMinutes=6
                ),
                LearningContent(
                    title="Plant-Based Eating Benefits",
                    details="Discover the environmental impact of food choices. Incorporating more plant-based meals reduces water usage and greenhouse gas emissions.",
                    category="Food",
                    readTimeMinutes=8
                ),
            ]
            db.learning.insert_many([item.dict() for item in seed_data])
        
        query = {}
        if category:
            query["category"] = category
        
        items = list(db.learning.find(query).sort("createdAt", DESCENDING).limit(limit))
        return sanitize_docs(items)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch learning content: {str(e)}")

@api.get("/preferences", response_model=UserPreferences)
async def get_preferences():
    try:
        db = get_db()
        prefs = db.preferences.find_one({"userId": "demo-user"})
        
        if not prefs:
            default_prefs = UserPreferences(
                country="TR",
                interests=["energy", "water", "waste"],
                language="en",
                notificationsEnabled=True,
                dailyGoal=3
            )
            db.preferences.insert_one(default_prefs.dict())
            prefs = db.preferences.find_one({"userId": "demo-user"})
        
        return sanitize_doc(prefs)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch preferences: {str(e)}")

@api.put("/preferences")
async def update_preferences(prefs: UserPreferences):
    try:
        db = get_db()
        prefs.updatedAt = datetime.utcnow()
        
        db.preferences.update_one(
            {"userId": prefs.userId},
            {"$set": prefs.dict()},
            upsert=True
        )
        
        return {
            "success": True,
            "message": "Preferences updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update preferences: {str(e)}")

@api.get("/stats/weekly", response_model=WeeklyStatsResponse)
async def weekly_stats():
    try:
        db = get_db()
        
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        
        daily_stats = []
        total_completed = 0
        total_points = 0
        
        for i in range(7):
            day = week_start + timedelta(days=i)
            day_str = day.isoformat()
            
            tasks = list(db.tasks.find({
                "userId": "demo-user",
                "date": day_str,
                "isCompleted": True
            }))
            
            completed = len(tasks)
            points = sum(t.get("points", 0) for t in tasks)
            
            daily_stats.append(DailyStats(
                date=day_str,
                completed=completed,
                points=points,
                co2Saved=round(completed * 0.3, 2)
            ))
            
            total_completed += completed
            total_points += points
        
        streak = 0
        for stat in reversed(daily_stats):
            if stat.completed > 0:
                streak += 1
            else:
                break
        
        return WeeklyStatsResponse(
            days=daily_stats,
            totalCompleted=total_completed,
            totalPoints=total_points,
            co2Saved=round(total_completed * 0.3, 2),
            streak=streak
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch weekly stats: {str(e)}")

@api.get("/stats/monthly")
async def monthly_stats():
    try:
        db = get_db()
        
        today = date.today()
        month_start = today.replace(day=1)
        
        weeks_data = []
        total_completed = 0
        total_points = 0
        
        current_date = month_start
        week_num = 1
        
        while current_date.month == today.month and week_num <= 4:
            week_end = current_date + timedelta(days=6)
            
            tasks = list(db.tasks.find({
                "userId": "demo-user",
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
            "co2Saved": round(total_completed * 0.3, 2),
            "month": today.strftime("%B %Y")
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch monthly stats: {str(e)}")

@api.get("/stats/summary")
async def stats_summary():
    try:
        db = get_db()
        
        all_tasks = list(db.tasks.find({"userId": "demo-user", "isCompleted": True}))
        
        total_completed = len(all_tasks)
        total_points = sum(t.get("points", 0) for t in all_tasks)
        
        categories = {}
        for task in all_tasks:
            cat = task.get("category", "Other")
            if cat not in categories:
                categories[cat] = {"count": 0, "points": 0}
            categories[cat]["count"] += 1
            categories[cat]["points"] += task.get("points", 0)
        
        return {
            "totalCompleted": total_completed,
            "totalPoints": total_points,
            "co2Saved": round(total_completed * 0.3, 2),
            "categoriesBreakdown": categories,
            "averagePointsPerTask": round(total_points / total_completed, 2) if total_completed > 0 else 0
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch summary: {str(e)}")

@api.post("/ai/generate-tasks")
async def generate_ai_tasks(
    category: Optional[str] = Query(None),
    count: int = Query(3, ge=1, le=10)
):
    try:
        db = get_db()
        prefs = db.preferences.find_one({"userId": "demo-user"})
        
        today = date.today().isoformat()
        
        task_templates = {
            "Energy": [
                {"title": "Turn off unused lights", "details": "Walk through your home and turn off lights in empty rooms.", "points": 10, "impact": "Saves ~0.3kg CO₂"},
                {"title": "Unplug idle electronics", "details": "Unplug chargers and devices not in use to reduce phantom power.", "points": 15, "impact": "Saves ~0.5kg CO₂"},
                {"title": "Use natural lighting", "details": "Open curtains during day instead of using artificial lights.", "points": 12, "impact": "Saves ~0.4kg CO₂"},
            ],
            "Water": [
                {"title": "Take a 5-minute shower", "details": "Reduce shower time to conserve water and energy.", "points": 20, "impact": "Saves ~40L water"},
                {"title": "Fix leaky faucets", "details": "Check and repair any dripping taps in your home.", "points": 25, "impact": "Saves ~20L water/day"},
                {"title": "Use full dishwasher loads", "details": "Only run dishwasher when completely full.", "points": 15, "impact": "Saves ~15L water"},
            ],
            "Waste": [
                {"title": "Use reusable bottle", "details": "Bring your own water bottle instead of buying plastic.", "points": 15, "impact": "Prevents 1 plastic bottle"},
                {"title": "Bring reusable bags", "details": "Use cloth bags for shopping trips.", "points": 10, "impact": "Prevents 3-5 plastic bags"},
                {"title": "Compost food scraps", "details": "Start or maintain composting kitchen waste.", "points": 20, "impact": "Diverts ~0.5kg from landfill"},
            ],
            "Transport": [
                {"title": "Walk or bike today", "details": "Choose active transportation for short trips.", "points": 25, "impact": "Saves ~2kg CO₂"},
                {"title": "Use public transit", "details": "Take bus or train instead of driving alone.", "points": 20, "impact": "Saves ~1.5kg CO₂"},
                {"title": "Carpool to work", "details": "Share ride with colleague or neighbor.", "points": 18, "impact": "Saves ~1kg CO₂"},
            ],
            "Food": [
                {"title": "Eat plant-based meal", "details": "Choose vegetarian or vegan option for one meal.", "points": 18, "impact": "Saves ~1.2kg CO₂"},
                {"title": "Buy local produce", "details": "Shop at farmer's market or choose local items.", "points": 15, "impact": "Reduces transport emissions"},
                {"title": "Meal prep to reduce waste", "details": "Plan and prepare meals to avoid food waste.", "points": 12, "impact": "Prevents ~0.8kg food waste"},
            ],
        }
        
        if category and category in task_templates:
            templates = task_templates[category]
        else:
            import random
            all_templates = []
            for cat_templates in task_templates.values():
                all_templates.extend([(cat, t) for cat in task_templates.keys() for t in task_templates[cat] if t in cat_templates])
            random.shuffle(all_templates)
            templates = [{"category": cat, **tmpl} for cat, tmpl in all_templates[:count]]
            
            generated_tasks = []
            for i, tmpl in enumerate(templates[:count]):
                cat = tmpl.get("category", list(task_templates.keys())[i % len(task_templates)])
                generated_tasks.append({
                    "title": tmpl["title"],
                    "details": tmpl["details"],
                    "category": cat,
                    "date": today,
                    "points": tmpl["points"],
                    "estimatedImpact": tmpl["impact"]
                })
            
            return {"tasks": generated_tasks, "count": len(generated_tasks)}
        
        import random
        selected = random.sample(templates, min(count, len(templates)))
        
        generated_tasks = []
        for tmpl in selected:
            generated_tasks.append({
                "title": tmpl["title"],
                "details": tmpl["details"],
                "category": category or "General",
                "date": today,
                "points": tmpl["points"],
                "estimatedImpact": tmpl["impact"]
            })
        
        return {"tasks": generated_tasks, "count": len(generated_tasks)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate tasks: {str(e)}")

@api.get("/categories")
async def get_categories():
    return {
        "categories": [
            {"id": "energy", "name": "Energy", "icon": "⚡", "color": "#FFB800"},
            {"id": "water", "name": "Water", "icon": "💧", "color": "#00A3FF"},
            {"id": "waste", "name": "Waste", "icon": "♻️", "color": "#00C853"},
            {"id": "transport", "name": "Transport", "icon": "🚲", "color": "#FF6B00"},
            {"id": "food", "name": "Food", "icon": "🌱", "color": "#7CB342"},
        ]
    }

app.include_router(api)
