from fastapi import FastAPI, APIRouter, HTTPException, Query, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta
from typing import List, Optional
import os
import random
import uuid  
from pymongo import MongoClient, DESCENDING
from bson import ObjectId

# Import external data files
from task_templates import TASK_POOL
from learning_content import LEARNING_ARTICLES

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
    """Convert MongoDB _id to string id"""
    if doc and "_id" in doc:
        if "id" not in doc:
            doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc

def sanitize_docs(docs):
    return [sanitize_doc(doc) for doc in docs]

def get_user_id(x_user_id: Optional[str] = Header(None)) -> str:
    return x_user_id or "demo-user"

# ======================== MODELS ========================

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

# ======================== ROOT ENDPOINTS ========================

@app.get("/")
async def root():
    return {
        "service": "GreenHabit API",
        "version": "2.1.0",
        "status": "running"
    }

@app.get("/healthz")
async def health_check():
    return {"ok": True}

# ======================== TASK ROUTES ========================

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
        
        task_id = str(uuid.uuid4())
        
        task_dict = {
            "id": task_id,
            "userId": user_id,
            "title": payload.title,
            "details": payload.details,
            "category": payload.category,
            "date": task_date,
            "points": payload.points,
            "estimatedImpact": payload.estimatedImpact,
            "isCompleted": False,
            "completedAt": None,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        db = get_db()
        result = db.tasks.insert_one(task_dict)
        
        return {
            "success": True,
            "taskId": task_id,
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
        
        task = db.tasks.find_one({"id": task_id, "userId": user_id})
        
        if not task:
            try:
                object_id = ObjectId(task_id)
                task = db.tasks.find_one({"_id": object_id, "userId": user_id})
            except:
                pass
        
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        update_data = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        update_data["updatedAt"] = datetime.utcnow()
        
        # Check if task is being completed
        is_completing_task = "isCompleted" in update_data and update_data["isCompleted"] and not task.get("isCompleted", False)
        
        if is_completing_task:
            update_data["completedAt"] = datetime.utcnow()
        
        # Update task
        if "id" in task:
            result = db.tasks.update_one(
                {"id": task_id, "userId": user_id},
                {"$set": update_data}
            )
        else:
            result = db.tasks.update_one(
                {"_id": task["_id"], "userId": user_id},
                {"$set": update_data}
            )
        
        # ✅ NEW: If completing task, calculate rewards and check achievements
        response = {
            "success": True,
            "message": "Task updated successfully",
            "modified": result.modified_count > 0
        }
        
        if is_completing_task:
            from rewards_system import calculate_rewards, check_new_achievements, calculate_streak
            
            # Calculate rewards
            rewards = await calculate_rewards(db, user_id, task)
            
            # Check for new achievements
            new_achievements = await check_new_achievements(db, user_id)
            
            # Get updated streak info
            streak_info = await calculate_streak(db, user_id)
            
            response["rewards"] = rewards
            response["newAchievements"] = new_achievements
            response["streakInfo"] = streak_info
            response["celebration"] = True  # Frontend trigger
        
        return response
        
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
            try:
                object_id = ObjectId(task_id)
                result = db.tasks.delete_one({"_id": object_id, "userId": user_id})
            except:
                pass
        
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

# ======================== STATS ROUTES ========================

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

# ======================== PREFERENCES ROUTES ========================

@api.get("/preferences")
async def get_preferences(x_user_id: Optional[str] = Header(None)):
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        prefs = db.preferences.find_one({"userId": user_id})
        
        if not prefs:
            prefs = {
                "userId": user_id,
                "country": "EU",
                "interests": ["Energy", "Water", "Waste", "Transport"],
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

# ======================== LEARNING ROUTES ========================

@api.get("/learning")
async def get_learning(category: Optional[str] = Query(None)):
    try:
        db = get_db()
        
        count = db.learning.count_documents({})
        if count == 0:
            # Use imported learning articles
            db.learning.insert_many(LEARNING_ARTICLES)
        
        query = {}
        if category:
            query["category"] = category
        
        items = list(db.learning.find(query).limit(100))
        return sanitize_docs(items)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch learning content: {str(e)}")

# ======================== AI ROUTES ========================

@api.post("/ai/generate-tasks")
async def generate_ai_tasks():
    """Generate random eco-friendly tasks from different categories"""
    today = date.today().isoformat()
    
    # Generate 3-4 random tasks
    all_categories = ["Energy", "Water", "Waste", "Transport"]
    num_tasks = random.randint(3, 4)
    selected_categories = random.sample(all_categories, k=num_tasks)
    
    generated_tasks = []
    
    for category in selected_categories:
        # Pick random task from imported TASK_POOL
        task_template = random.choice(TASK_POOL[category])
        
        task = {
            "title": task_template["title"],
            "details": task_template["details"],
            "category": category,
            "date": today,
            "points": task_template["points"],
            "estimatedImpact": task_template["estimatedImpact"]
        }
        
        generated_tasks.append(task)
    
    return {
        "tasks": generated_tasks,
        "count": len(generated_tasks)
    }

app.include_router(api)

# ======================== NEW: USER PROFILE & ACHIEVEMENTS ========================

@api.get("/profile")
async def get_profile(x_user_id: Optional[str] = Header(None)):
    """Get user profile with achievements and stats"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        
        from rewards_system import get_user_profile, calculate_streak
        
        profile = await get_user_profile(db, user_id)
        streak_info = await calculate_streak(db, user_id)
        
        # Merge streak info into profile
        profile["currentStreak"] = streak_info["currentStreak"]
        profile["longestStreak"] = streak_info["longestStreak"]
        
        return profile
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch profile: {str(e)}")

@api.get("/achievements")
async def get_achievements(x_user_id: Optional[str] = Header(None)):
    """Get all achievements with unlock status"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        
        from rewards_system import ACHIEVEMENTS, get_user_profile
        
        profile = await get_user_profile(db, user_id)
        unlocked = set(profile.get("unlockedAchievements", []))
        
        achievements_list = []
        for achievement_id, achievement in ACHIEVEMENTS.items():
            achievements_list.append({
                **achievement,
                "unlocked": achievement_id in unlocked
            })
        
        return {
            "achievements": achievements_list,
            "totalUnlocked": len(unlocked),
            "totalAvailable": len(ACHIEVEMENTS)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch achievements: {str(e)}")

@api.get("/streak")
async def get_streak(x_user_id: Optional[str] = Header(None)):
    """Get streak information"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        
        from rewards_system import calculate_streak
        
        streak_info = await calculate_streak(db, user_id)
        
        return streak_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch streak: {str(e)}")

app.include_router(api)