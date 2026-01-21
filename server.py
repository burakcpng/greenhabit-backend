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

# ======================== GLOBAL DATABASE CLIENT ========================

# ✅ FIX 3: Connection Pooling - Global MongoDB Client
_mongo_client = None
_db = None

def get_db():
    """
    Get database connection with connection pooling
    Creates client only once and reuses it
    """
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
                retryWrites=True
            )
            _mongo_client.admin.command('ping')
            _db = _mongo_client[db_name]
            print("✅ MongoDB connection established")
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Database unavailable: {str(e)}")
    
    return _db

def sanitize_doc(doc):
    """
    Convert MongoDB _id to string id
    ✅ FIX 1: Standardize date formats to ISO8601 without microseconds
    """
    if doc and "_id" in doc:
        if "id" not in doc:
            doc["id"] = str(doc["_id"])
        del doc["_id"]
    
    # ✅ FIX 1: Convert datetime fields to ISO8601 string (YYYY-MM-DDTHH:MM:SS)
    date_fields = ["createdAt", "updatedAt", "completedAt"]
    for field in date_fields:
        if field in doc and doc[field] is not None:
            if isinstance(doc[field], datetime):
                # Remove microseconds and convert to ISO format
                doc[field] = doc[field].replace(microsecond=0).isoformat() + "Z"
    
    return doc

def sanitize_docs(docs):
    return [sanitize_doc(doc) for doc in docs]

def get_user_id(x_user_id: Optional[str] = Header(None)) -> str:
    """
    Get user ID from header
    ✅ FIX 4: Never generate ID on backend, always require from client
    """
    if not x_user_id or x_user_id.strip() == "":
        raise HTTPException(
            status_code=401,
            detail="User ID required. Please provide X-User-Id header."
        )
    return x_user_id.strip()

# ======================== MODELS ========================

class CreateTaskPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    details: str = Field(..., max_length=1000)
    category: str
    points: int = Field(..., ge=0, le=1000)
    estimatedImpact: str = Field(..., max_length=200)
    date: Optional[str] = None
    evidenceImagePath: Optional[str] = None  # ✅ FIX: Photo proof persistence

class UpdateTaskPayload(BaseModel):
    isCompleted: Optional[bool] = None
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    details: Optional[str] = Field(None, max_length=1000)
    category: Optional[str] = None
    points: Optional[int] = Field(None, ge=0, le=1000)
    estimatedImpact: Optional[str] = None
    evidenceImagePath: Optional[str] = None  # ✅ FIX: Photo proof persistence

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
def get_tasks(
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
def create_task(
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
            "evidenceImagePath": payload.evidenceImagePath,  # ✅ FIX: Save photo proof path
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
def update_task(
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
        
        # ✅ FIX 2: Race Condition Prevention - Atomic Update
        # Only set completedAt if not already completed
        if is_completing_task:
            if task.get("isCompleted", False):
                 # Task was already completed by another request
                 is_completing_task = False
            else:
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
            rewards = calculate_rewards(db, user_id, task)
            
            # Check for new achievements
            new_achievements = check_new_achievements(db, user_id)
            
            # Get updated streak info
            streak_info = calculate_streak(db, user_id)
            
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
def delete_task(
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
def weekly_stats(x_user_id: Optional[str] = Header(None)):
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
def monthly_stats(x_user_id: Optional[str] = Header(None)):
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

# ======================== LIFECYCLE HANDLERS ========================

@app.on_event("startup")
def startup_event():
    """Initialize resources on startup"""
    print("🚀 GreenHabit API starting up...")
    # Trigger DB connection
    try:
        db = get_db()
        print("✅ Database connected successfully")
        
        # Create social indexes
        from social_system import ensure_social_indexes
        ensure_social_indexes(db)
        
        # Create team indexes
        from team_system import ensure_team_indexes
        ensure_team_indexes(db)
    except Exception as e:
        print(f"❌ Database connection failed: {e}")

@app.on_event("shutdown")
def shutdown_event():
    """Cleanup resources on shutdown"""
    global _mongo_client
    if _mongo_client:
        _mongo_client.close()
        print("👋 MongoDB connection closed")
    print("👋 GreenHabit API shutting down...")

# ======================== NEW: USER PROFILE & ACHIEVEMENTS ========================

@api.get("/profile")
def get_profile(x_user_id: Optional[str] = Header(None)):
    """Get user profile with achievements and stats"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        
        from rewards_system import get_user_profile, calculate_streak
        
        profile = get_user_profile(db, user_id)
        streak_info = calculate_streak(db, user_id)
        
        # Merge streak info into profile
        profile["currentStreak"] = streak_info["currentStreak"]
        profile["longestStreak"] = streak_info["longestStreak"]
        
        return profile
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch profile: {str(e)}")

@api.get("/achievements")
def get_achievements(x_user_id: Optional[str] = Header(None)):
    """Get all achievements with unlock status"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        
        from rewards_system import ACHIEVEMENTS, get_user_profile
        
        profile = get_user_profile(db, user_id)
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
def get_streak(x_user_id: Optional[str] = Header(None)):
    """Get streak information"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        
        from rewards_system import calculate_streak
        
        streak_info = calculate_streak(db, user_id)
        
        return streak_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch streak: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch streak: {str(e)}")

# ======================== NEW: SHARING ROUTES ========================

class ShareTaskPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    details: str = Field(..., max_length=1000)
    category: str
    points: int = Field(..., ge=0, le=1000)
    estimatedImpact: str = Field(..., max_length=200)

def generate_share_id():
    """Generate a short 6-character ID"""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # Removed ambiguous chars (I, 1, O, 0)
    return "".join(random.choice(chars) for _ in range(6))

@api.post("/share")
def share_task(payload: ShareTaskPayload, x_user_id: Optional[str] = Header(None)):
    """Create a short share link for a task"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        
        # Generate unique ID
        share_id = generate_share_id()
        while db.shared_tasks.find_one({"shareId": share_id}):
            share_id = generate_share_id()
        
        share_doc = {
            "shareId": share_id,
            "creatorId": user_id,
            "title": payload.title,
            "details": payload.details,
            "category": payload.category,
            "points": payload.points,
            "estimatedImpact": payload.estimatedImpact,
            "createdAt": datetime.utcnow()
        }
        
        db.shared_tasks.insert_one(share_doc)
        
        return {
            "success": True,
            "shareId": share_id,
            "shareUrl": f"https://greenhabit-backend.onrender.com/share/{share_id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to share task: {str(e)}")

@api.get("/share/{share_id}")
def get_shared_task(share_id: str):
    """Get shared task details"""
    try:
        db = get_db()
        
        task = db.shared_tasks.find_one({"shareId": share_id})
        if not task:
            raise HTTPException(status_code=404, detail="Shared task not found")
        
        return sanitize_doc(task)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch shared task: {str(e)}")

# ======================== SOCIAL SYSTEM ROUTES ========================

# Pydantic models for social endpoints
class ProfileUpdatePayload(BaseModel):
    displayName: Optional[str] = Field(None, max_length=50)
    bio: Optional[str] = Field(None, max_length=200)

class PrivacySettingsPayload(BaseModel):
    profilePublic: Optional[bool] = None
    showAchievements: Optional[bool] = None
    showStats: Optional[bool] = None
    showFollowers: Optional[bool] = None
    appearInLeaderboard: Optional[bool] = None

# --- Ranking Endpoints ---

@api.get("/ranking")
def get_ranking(
    limit: int = Query(50, ge=1, le=100),
    x_user_id: Optional[str] = Header(None)
):
    """Get global leaderboard"""
    try:
        db = get_db()
        from social_system import get_global_ranking
        
        ranking = get_global_ranking(db, limit)
        return ranking
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch ranking: {str(e)}")

@api.get("/ranking/me")
def get_my_rank(x_user_id: Optional[str] = Header(None)):
    """Get current user's rank and nearby users"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from social_system import get_user_rank
        
        rank_info = get_user_rank(db, user_id)
        return rank_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch rank: {str(e)}")

# --- Social Profile Endpoints ---

@api.get("/social/profile")
def get_social_profile_endpoint(x_user_id: Optional[str] = Header(None)):
    """Get current user's extended social profile"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from social_system import get_social_profile, get_user_rank
        
        profile = get_social_profile(db, user_id)
        
        # Add rank
        rank_info = get_user_rank(db, user_id)
        profile["rank"] = rank_info["rank"]
        
        return profile
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch profile: {str(e)}")

@api.patch("/social/profile")
def update_social_profile(
    payload: ProfileUpdatePayload,
    x_user_id: Optional[str] = Header(None)
):
    """Update current user's profile (displayName, bio)"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from social_system import update_user_profile
        
        profile = update_user_profile(db, user_id, payload.displayName, payload.bio)
        return profile
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {str(e)}")

@api.get("/users/{target_id}/profile")
def get_public_profile(
    target_id: str,
    x_user_id: Optional[str] = Header(None)
):
    """Get another user's public profile"""
    try:
        db = get_db()
        viewer_id = None
        try:
            viewer_id = get_user_id(x_user_id)
        except:
            pass
        
        from social_system import get_social_profile, get_user_rank
        
        # Check if profile is public
        privacy = db.user_privacy.find_one({"userId": target_id}) or {"profilePublic": True}
        
        if not privacy.get("profilePublic", True) and viewer_id != target_id:
            # Check if viewer is following
            is_following = db.follows.count_documents({
                "followerId": viewer_id,
                "followedId": target_id
            }) > 0 if viewer_id else False
            
            if not is_following:
                return {
                    "userId": target_id,
                    "isPrivate": True,
                    "message": "This profile is private"
                }
        
        profile = get_social_profile(db, target_id, viewer_id)
        
        # Add rank
        rank_info = get_user_rank(db, target_id)
        profile["rank"] = rank_info["rank"]
        
        return profile
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch profile: {str(e)}")

# --- Follow System Endpoints ---

@api.post("/users/{target_id}/follow")
def follow_user_endpoint(
    target_id: str,
    x_user_id: Optional[str] = Header(None)
):
    """Follow a user"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from social_system import follow_user
        
        result = follow_user(db, user_id, target_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to follow user: {str(e)}")

@api.delete("/users/{target_id}/follow")
def unfollow_user_endpoint(
    target_id: str,
    x_user_id: Optional[str] = Header(None)
):
    """Unfollow a user"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from social_system import unfollow_user
        
        result = unfollow_user(db, user_id, target_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unfollow user: {str(e)}")

@api.get("/users/{target_id}/followers")
def get_followers_endpoint(
    target_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    x_user_id: Optional[str] = Header(None)
):
    """Get followers list for a user"""
    try:
        db = get_db()
        from social_system import get_followers
        
        result = get_followers(db, target_id, page, limit)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch followers: {str(e)}")

@api.get("/users/{target_id}/following")
def get_following_endpoint(
    target_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    x_user_id: Optional[str] = Header(None)
):
    """Get following list for a user"""
    try:
        db = get_db()
        from social_system import get_following
        
        result = get_following(db, target_id, page, limit)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch following: {str(e)}")

# --- Privacy Settings Endpoints ---

@api.get("/social/privacy")
def get_privacy_endpoint(x_user_id: Optional[str] = Header(None)):
    """Get current user's privacy settings"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from social_system import get_privacy_settings
        
        return get_privacy_settings(db, user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch privacy settings: {str(e)}")

@api.patch("/social/privacy")
def update_privacy_endpoint(
    payload: PrivacySettingsPayload,
    x_user_id: Optional[str] = Header(None)
):
    """Update user's privacy settings"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from social_system import update_privacy_settings
        
        settings = payload.dict(exclude_unset=True)
        result = update_privacy_settings(db, user_id, settings)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update privacy settings: {str(e)}")

# ======================== TASK SHARING ROUTES ========================

class TaskSharePayload(BaseModel):
    recipientId: str
    title: str
    details: str = ""
    category: str = "Other"
    points: int = 10
    estimatedImpact: Optional[str] = None

@api.post("/shares")
def create_share(
    payload: TaskSharePayload,
    x_user_id: Optional[str] = Header(None)
):
    """Send a task to a friend"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from task_sharing import create_task_share
        
        task_data = {
            "title": payload.title,
            "details": payload.details,
            "category": payload.category,
            "points": payload.points,
            "estimatedImpact": payload.estimatedImpact
        }
        
        result = create_task_share(db, user_id, payload.recipientId, task_data)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to share task: {str(e)}")

@api.get("/shares/incoming")
def get_incoming(
    status: Optional[str] = Query("pending"),
    x_user_id: Optional[str] = Header(None)
):
    """Get incoming task shares"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from task_sharing import get_incoming_shares
        
        shares = get_incoming_shares(db, user_id, status)
        return {"shares": shares, "count": len(shares)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch shares: {str(e)}")

@api.get("/shares/sent")
def get_sent(x_user_id: Optional[str] = Header(None)):
    """Get sent task shares"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from task_sharing import get_sent_shares
        
        shares = get_sent_shares(db, user_id)
        return {"shares": shares, "count": len(shares)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch shares: {str(e)}")

@api.get("/shares/pending-count")
def get_pending(x_user_id: Optional[str] = Header(None)):
    """Get count of pending incoming shares"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from task_sharing import get_pending_count
        
        count = get_pending_count(db, user_id)
        return {"count": count}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch count: {str(e)}")

@api.patch("/shares/{share_id}/accept")
def accept_share_endpoint(
    share_id: str,
    x_user_id: Optional[str] = Header(None)
):
    """Accept a shared task"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from task_sharing import accept_share
        
        result = accept_share(db, share_id, user_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to accept share: {str(e)}")

@api.patch("/shares/{share_id}/reject")
def reject_share_endpoint(
    share_id: str,
    x_user_id: Optional[str] = Header(None)
):
    """Reject a shared task"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from task_sharing import reject_share
        
        result = reject_share(db, share_id, user_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reject share: {str(e)}")


# ======================== TEAM ROUTES ========================

class CreateTeamPayload(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    invitedUserIds: Optional[List[str]] = None

class InviteToTeamPayload(BaseModel):
    userId: str

class ShareTaskToTeamPayload(BaseModel):
    title: str
    details: str = ""
    category: str = "Other"
    points: int = 10
    estimatedImpact: Optional[str] = None

# --- Team CRUD ---

@api.post("/teams")
def create_team_endpoint(
    payload: CreateTeamPayload,
    x_user_id: Optional[str] = Header(None)
):
    """Create a new team"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from team_system import create_team, get_my_team, get_team_members
        
        result = create_team(db, user_id, payload.name, payload.invitedUserIds)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        # Return full team response for iOS decoding (TeamResponse expects {team, members})
        team = get_my_team(db, user_id)
        members = get_team_members(db, result["teamId"]) if result.get("teamId") else []
        return {"team": team, "members": members}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create team: {str(e)}")

@api.get("/teams/my")
def get_my_team_endpoint(x_user_id: Optional[str] = Header(None)):
    """Get current user's team"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from team_system import get_my_team, get_team_members
        
        team = get_my_team(db, user_id)
        if not team:
            return {"team": None}
        
        # Include members - return at top level to match Swift TeamResponse
        members = get_team_members(db, team["id"])
        
        return {"team": team, "members": members}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get team: {str(e)}")

@api.get("/teams/{team_id}")
def get_team_endpoint(
    team_id: str,
    x_user_id: Optional[str] = Header(None)
):
    """Get team by ID"""
    try:
        db = get_db()
        get_user_id(x_user_id)  # Validate user
        from team_system import get_team, get_team_members
        
        team = get_team(db, team_id)
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        
        # Include members
        members = get_team_members(db, team_id)
        team["members"] = members
        
        return team
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get team: {str(e)}")

@api.delete("/teams/{team_id}")
def delete_team_endpoint(
    team_id: str,
    x_user_id: Optional[str] = Header(None)
):
    """Delete team (creator only)"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from team_system import delete_team
        
        result = delete_team(db, team_id, user_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete team: {str(e)}")

@api.post("/teams/{team_id}/leave")
def leave_team_endpoint(
    team_id: str,
    x_user_id: Optional[str] = Header(None)
):
    """Leave team (members only)"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from team_system import leave_team
        
        result = leave_team(db, team_id, user_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to leave team: {str(e)}")

# --- Team Member Management ---

@api.delete("/teams/{team_id}/members/{target_user_id}")
def remove_member_endpoint(
    team_id: str,
    target_user_id: str,
    x_user_id: Optional[str] = Header(None)
):
    """Remove member from team (creator only)"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from team_system import remove_member
        
        result = remove_member(db, team_id, user_id, target_user_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove member: {str(e)}")


class UpdateMemberPermissionsPayload(BaseModel):
    canShareTasks: bool = False


@api.patch("/teams/{team_id}/members/{target_user_id}/permissions")
def update_member_permissions_endpoint(
    team_id: str,
    target_user_id: str,
    payload: UpdateMemberPermissionsPayload,
    x_user_id: Optional[str] = Header(None)
):
    """Update member permissions (creator only)"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from team_system import update_member_permissions
        
        result = update_member_permissions(
            db, 
            team_id, 
            user_id, 
            target_user_id, 
            payload.canShareTasks
        )
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update permissions: {str(e)}")

# --- Team Invitations ---

@api.post("/teams/{team_id}/invite")
def invite_to_team_endpoint(
    team_id: str,
    payload: InviteToTeamPayload,
    x_user_id: Optional[str] = Header(None)
):
    """Invite user to team (creator only)"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from team_system import invite_to_team
        
        result = invite_to_team(db, team_id, user_id, payload.userId)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to invite user: {str(e)}")

@api.get("/teams/invitations/incoming")
def get_pending_invitations_endpoint(x_user_id: Optional[str] = Header(None)):
    """Get pending team invitations for current user"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from team_system import get_pending_invitations
        
        invitations = get_pending_invitations(db, user_id)
        return {"invitations": invitations, "count": len(invitations)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get invitations: {str(e)}")

@api.get("/teams/invitations/sent")
def get_sent_invitations_endpoint(x_user_id: Optional[str] = Header(None)):
    """Get team invitations sent by current user (outgoing)"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from team_system import get_sent_invitations
        
        invitations = get_sent_invitations(db, user_id)
        return {"invitations": invitations, "count": len(invitations)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get sent invitations: {str(e)}")

@api.patch("/teams/invitations/{invitation_id}/accept")
def accept_invitation_endpoint(
    invitation_id: str,
    x_user_id: Optional[str] = Header(None)
):
    """Accept team invitation"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from team_system import accept_invitation
        
        result = accept_invitation(db, invitation_id, user_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to accept invitation: {str(e)}")

@api.patch("/teams/invitations/{invitation_id}/reject")
def reject_invitation_endpoint(
    invitation_id: str,
    x_user_id: Optional[str] = Header(None)
):
    """Reject team invitation"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from team_system import reject_invitation
        
        result = reject_invitation(db, invitation_id, user_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reject invitation: {str(e)}")

# --- Team Task Sharing ---

@api.post("/teams/{team_id}/share-task")
def share_task_to_team_endpoint(
    team_id: str,
    payload: ShareTaskToTeamPayload,
    x_user_id: Optional[str] = Header(None)
):
    """Share task to all team members (creator only)"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from team_system import share_task_to_team
        
        task_data = {
            "title": payload.title,
            "details": payload.details,
            "category": payload.category,
            "points": payload.points,
            "estimatedImpact": payload.estimatedImpact
        }
        
        result = share_task_to_team(db, team_id, user_id, task_data)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to share task: {str(e)}")

@api.get("/teams/tasks/incoming")
def get_pending_team_tasks_endpoint(x_user_id: Optional[str] = Header(None)):
    """Get pending team task shares for current user"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from team_system import get_pending_team_tasks
        
        tasks = get_pending_team_tasks(db, user_id)
        return {"tasks": tasks, "count": len(tasks)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get team tasks: {str(e)}")

@api.patch("/teams/tasks/{share_id}/accept")
def accept_team_task_endpoint(
    share_id: str,
    x_user_id: Optional[str] = Header(None)
):
    """Accept team task share"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from team_system import accept_team_task
        
        result = accept_team_task(db, share_id, user_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to accept task: {str(e)}")

@api.patch("/teams/tasks/{share_id}/reject")
def reject_team_task_endpoint(
    share_id: str,
    x_user_id: Optional[str] = Header(None)
):
    """Reject team task share"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        from team_system import reject_team_task
        
        result = reject_team_task(db, share_id, user_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reject task: {str(e)}")

# --- Team Stats & Leaderboard ---

@api.get("/teams/{team_id}/stats")
def get_team_stats_endpoint(
    team_id: str,
    x_user_id: Optional[str] = Header(None)
):
    """Get team statistics"""
    try:
        db = get_db()
        get_user_id(x_user_id)  # Validate user
        from team_system import get_team_stats
        
        stats = get_team_stats(db, team_id)
        if not stats:
            raise HTTPException(status_code=404, detail="Team not found")
        
        return stats
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

@api.get("/teams/{team_id}/leaderboard")
def get_team_leaderboard_endpoint(
    team_id: str,
    x_user_id: Optional[str] = Header(None)
):
    """Get team leaderboard"""
    try:
        db = get_db()
        get_user_id(x_user_id)  # Validate user
        from team_system import get_team_leaderboard
        
        leaderboard = get_team_leaderboard(db, team_id)
        return {"leaderboard": leaderboard, "count": len(leaderboard)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get leaderboard: {str(e)}")


# ======================== USER SEARCH ROUTES ========================

@api.get("/users/search")
def search_users_endpoint(
    query: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    x_user_id: Optional[str] = Header(None)
):
    """Search for users by display name"""
    try:
        db = get_db()
        user_id = None
        try:
            user_id = get_user_id(x_user_id)
        except:
            pass
        
        from social_system import search_users
        
        users = search_users(db, query, limit, user_id)
        return {"users": users, "count": len(users)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search users: {str(e)}")


# ======================== CALENDAR DATA ROUTES ========================

@api.get("/calendar/{year}/{month}")
def get_calendar_endpoint(
    year: int,
    month: int,
    x_user_id: Optional[str] = Header(None)
):
    """Get daily task completion data for a specific month"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        
        if month < 1 or month > 12:
            raise HTTPException(status_code=400, detail="Invalid month")
        if year < 2020 or year > 2100:
            raise HTTPException(status_code=400, detail="Invalid year")
        
        from social_system import get_calendar_data
        
        calendar_data = get_calendar_data(db, user_id, year, month)
        return calendar_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get calendar data: {str(e)}")


# ======================== EXPORT DATA ROUTES ========================

class BulkDeletePayload(BaseModel):
    taskIds: List[str]

@api.get("/tasks/export")
def export_tasks_endpoint(
    year: int = Query(...),
    month: int = Query(...),
    x_user_id: Optional[str] = Header(None)
):
    """Get all completed tasks for export (PDF generation)"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        
        if month < 1 or month > 12:
            raise HTTPException(status_code=400, detail="Invalid month")
        if year < 2020 or year > 2100:
            raise HTTPException(status_code=400, detail="Invalid year")
        
        from social_system import get_tasks_for_export
        
        tasks = get_tasks_for_export(db, user_id, year, month)
        
        # Calculate summary
        total_points = sum(t.get("points", 0) for t in tasks)
        co2_saved = round(len(tasks) * 0.3, 2)
        
        return {
            "tasks": tasks,
            "count": len(tasks),
            "year": year,
            "month": month,
            "totalPoints": total_points,
            "co2Saved": co2_saved
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export tasks: {str(e)}")


@api.delete("/tasks/bulk-delete")
def bulk_delete_tasks_endpoint(
    payload: BulkDeletePayload,
    x_user_id: Optional[str] = Header(None)
):
    """Delete multiple tasks after export confirmation"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        
        if not payload.taskIds:
            raise HTTPException(status_code=400, detail="No task IDs provided")
        
        from social_system import bulk_delete_tasks
        
        result = bulk_delete_tasks(db, user_id, payload.taskIds)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete tasks: {str(e)}")


app.include_router(api)



# ======================== WEB/DEEP LINK ROUTES ========================
from fastapi.responses import JSONResponse, HTMLResponse

@app.get("/.well-known/apple-app-site-association")
async def apple_app_site_association():
    """Serve AASA file for iOS Universal Links"""
    content = {
        "applinks": {
            "apps": [],
            "details": [
                {
                    "appID": "9264X3737M.com.burakcpng.GreenHabit", 
                    "paths": ["/share/*"]
                }
            ]
        }
    }
    return JSONResponse(content=content)

@app.get("/share/{share_id}", response_class=HTMLResponse)
def share_landing_page(share_id: str):
    """HTML Landing Page for when link is opened in browser"""
    try:
        db = get_db()
        task = db.shared_tasks.find_one({"shareId": share_id})
        
        title = task.get('title', 'Eco Task') if task else "Eco Task"
        points = task.get('points', 0) if task else 0
        details = task.get('details', 'Join me on GreenHabit!') if task else ""
        ios_url = f"greenhabit://share?id={share_id}" # Fallback custom scheme
        universal_url = f"https://greenhabit-backend.onrender.com/share/{share_id}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
            
            <title>{title} • GreenHabit</title>
            <meta property="og:title" content="{title}">
            <meta property="og:description" content="Earn {points} points and save carbon with GreenHabit!">
            <meta name="apple-itunes-app" content="app-id=YOUR_APP_ID, app-argument={universal_url}">
            
            <style>
                :root {{
                    --bg-color: #0b1c2d;
                    --card-bg: rgba(255, 255, 255, 0.08);
                    --text-primary: #FFFFFF;
                    --text-secondary: rgba(255, 255, 255, 0.6);
                    --accent: #00E676;
                    --accent-dim: rgba(0, 230, 118, 0.15);
                }}
                
                body {{
                    margin: 0;
                    padding: 0;
                    background-color: var(--bg-color);
                    color: var(--text-primary);
                    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    -webkit-font-smoothing: antialiased;
                }}
                
                .container {{
                    width: 90%;
                    max-width: 400px;
                    text-align: center;
                    padding: 40px 24px;
                }}
                
                .logo {{
                    width: 80px;
                    height: 80px;
                    background: linear-gradient(135deg, #00E676 0%, #00B359 100%);
                    border-radius: 22px;
                    margin: 0 auto 32px;
                    box-shadow: 0 12px 24px rgba(0, 230, 118, 0.2);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 40px;
                }}
                
                h1 {{
                    font-size: 28px;
                    font-weight: 700;
                    margin: 0 0 12px;
                    letter-spacing: -0.5px;
                    line-height: 1.2;
                }}
                
                .badge {{
                    display: inline-block;
                    background: var(--accent-dim);
                    color: var(--accent);
                    padding: 6px 14px;
                    border-radius: 100px;
                    font-size: 14px;
                    font-weight: 600;
                    margin-bottom: 24px;
                }}
                
                p {{
                    font-size: 16px;
                    line-height: 1.5;
                    color: var(--text-secondary);
                    margin: 0 0 40px;
                }}
                
                .btn {{
                    display: block;
                    width: 100%;
                    padding: 16px;
                    border-radius: 16px;
                    font-size: 17px;
                    font-weight: 600;
                    text-decoration: none;
                    transition: transform 0.1s ease, opacity 0.2s;
                    box-sizing: border-box;
                    cursor: pointer;
                    margin-bottom: 16px;
                }}
                
                .btn:active {{
                    transform: scale(0.98);
                }}
                
                .btn-primary {{
                    background: var(--accent);
                    color: #003b1c;
                    box-shadow: 0 4px 12px rgba(0, 230, 118, 0.3);
                }}
                
                .btn-secondary {{
                    background: var(--card-bg);
                    color: var(--text-primary);
                    backdrop-filter: blur(10px);
                    -webkit-backdrop-filter: blur(10px);
                }}

                .footer {{
                    margin-top: 40px;
                    font-size: 13px;
                    color: var(--text-secondary);
                    opacity: 0.5;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="logo">🌿</div>
                
                <h1>{title}</h1>
                <div class="badge">+{points} Points</div>
                
                <p>{details}</p>
                
                <a href="{ios_url}" class="btn btn-primary">Open in GreenHabit</a>
                <a href="#" class="btn btn-secondary">Download on App Store</a>
                
                <div class="footer">GreenHabit • Sustainable Living</div>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    except Exception:
        return HTMLResponse(content="<h1>Task not found</h1>", status_code=404)
