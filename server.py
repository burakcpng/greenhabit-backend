from fastapi import FastAPI, APIRouter, HTTPException, Query, Body, Header, Depends
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
from utils.text_safety import ProfanityFilter # ✅ Apple Guideline 1.2 Compliance
from auth_system import AuthSystem, get_current_user # ✅ NEW Secure Auth
from rate_limiter import check_rate_limit, check_toggle_cooldown  # ✅ Security: Rate Limiting

app = FastAPI(
    title="GreenHabit API",
    description="Sustainable habits tracking platform",
    version="2.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

api = APIRouter(prefix="/api")

# SECURITY: Restrict CORS to legitimate origins only
# For mobile-only API, we can be very restrictive
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",")
# Filter empty strings that result from empty env var
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Empty list = no browser access (mobile-only)
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-User-Id"],
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
    creatorType: Optional[str] = "user"  # ✅ Creator Attribution: "system" or "user"


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

# ======================== AUTH ROUTES (NEW) ========================

class LoginPayload(BaseModel):
    appleToken: str
    legacyUuid: Optional[str] = None # For syncing old data
    fullName: Optional[str] = None # From Apple (only on first login)

@api.post("/auth/login")
def login_with_apple(payload: LoginPayload):
    try:
        db = get_db()
        
        # 1. Verify Apple Token
        apple_user_id = AuthSystem.verify_apple_token(payload.appleToken)
        current_time = datetime.utcnow()
        
        # 2. Check if user exists
        user = db.users.find_one({"appleUserId": apple_user_id})
        
        if not user:
            # 3. New User or Migration
            
            # Check for legacy migration
            if payload.legacyUuid:
                # Try to find legacy user by UUID
                # Note: Legacy users don't have a 'users' collection entry typically, 
                # they just have tasks/stats with that userId.
                # But if we want to migrate, we need to associate that old ID with this new Apple ID.
                
                # Check if tasks exist for this legacy ID
                legacy_task_count = db.tasks.count_documents({"userId": payload.legacyUuid})
                
                if legacy_task_count > 0:
                    print(f"🔄 Migrating user {payload.legacyUuid} to Apple ID {apple_user_id}")
                    # MIGRATION STRATEGY:
                    # We will treat the 'apple_user_id' as the NEW canonical ID.
                    # We need to update all old documents to point to the new ID.
                    # This is heavy but safer than keeping the insecure UUID.
                    
                    # Update Tasks
                    db.tasks.update_many(
                        {"userId": payload.legacyUuid},
                        {"$set": {"userId": apple_user_id}}
                    )
                    
                    # Update Preferences
                    db.preferences.update_many(
                        {"userId": payload.legacyUuid},
                        {"$set": {"userId": apple_user_id}}
                    )
                    
                    # Update Achievements/Stats (if stored with ID)
                     # (Assuming simple aggregation, but if there are specific docs, update them too)
            
            # Create User Record
            new_user = {
                "userId": apple_user_id, # Our internal ID is now the Apple Sub 
                "appleUserId": apple_user_id,
                "email": None, # Apple might not provide it reliably every time
                "displayName": payload.fullName or "Eco Warrior",
                "createdAt": current_time,
                "lastLogin": current_time,
                "isVerified": True
            }
            db.users.insert_one(new_user)
            print(f"✅ Created new user: {apple_user_id}")
            
        else:
            # Update last login
            db.users.update_one(
                {"appleUserId": apple_user_id},
                {"$set": {"lastLogin": current_time}}
            )
            print(f"👋 Welcome back: {apple_user_id}")
            
        # 4. Issue Session Token
        session_token = AuthSystem.create_session_token(apple_user_id)
        
        return {
            "success": True,
            "token": session_token,
            "userId": apple_user_id,
            "isNewUser": user is None
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Login failed: {e}")
        raise HTTPException(status_code=500, detail=f"Login processing failed: {str(e)}")

# ======================== DEV LOGIN (SIMULATOR ONLY) ========================

class DevLoginPayload(BaseModel):
    userId: str = Field(..., min_length=1, max_length=100)
    displayName: Optional[str] = None

@api.post("/auth/dev-login")
def dev_login(payload: DevLoginPayload):
    """
    Simulator-only login bypass. Skips Apple token verification.
    SECURITY: Only available when DEV_MODE=1 environment variable is set.
    Never set DEV_MODE on production deployments.
    """
    if not os.getenv("DEV_MODE"):
        raise HTTPException(status_code=403, detail="Dev login is disabled")

    try:
        db = get_db()
        dev_user_id = payload.userId
        current_time = datetime.utcnow()

        # Upsert user record
        user = db.users.find_one({"userId": dev_user_id})

        if not user:
            db.users.insert_one({
                "userId": dev_user_id,
                "appleUserId": dev_user_id,
                "displayName": payload.displayName or f"Test {dev_user_id}",
                "createdAt": current_time,
                "lastLogin": current_time,
                "isVerified": True
            })
            print(f"🧪 Dev: Created test user '{dev_user_id}'")
        else:
            db.users.update_one(
                {"userId": dev_user_id},
                {"$set": {"lastLogin": current_time}}
            )
            print(f"🧪 Dev: Welcome back '{dev_user_id}'")

        # Issue session token (same as real login)
        session_token = AuthSystem.create_session_token(dev_user_id)

        return {
            "success": True,
            "token": session_token,
            "userId": dev_user_id,
            "isNewUser": user is None
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Dev login failed: {e}")
        raise HTTPException(status_code=500, detail=f"Dev login failed: {str(e)}")

# ======================== TASK ROUTES ========================

@api.get("/tasks")
def get_tasks(
    date: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    completed: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    user_id: str = Depends(get_current_user) # ✅ Secure Dependency
):
    try:
        db = get_db()
        # user_id is now provided by Depends

        
        query = {"userId": user_id}
        if date:
            query["date"] = date
        if category:
            query["category"] = category
        if completed is not None:
            query["isCompleted"] = completed
        
        tasks = list(db.tasks.find(query).sort("createdAt", DESCENDING).limit(limit))
        
        # ✅ Enrich shared tasks with creator info
        shared_by_ids = set(t.get("sharedBy") for t in tasks if t.get("sharedBy"))
        creator_names = {}
        
        if shared_by_ids:
            # Batch lookup creator profiles
            profiles = db.user_profiles.find({"userId": {"$in": list(shared_by_ids)}})
            for profile in profiles:
                creator_names[profile["userId"]] = profile.get("displayName", "GreenHabit User")
        
        # Add creatorId, creatorName, and creatorType to tasks
        for task in tasks:
            # Get stored creatorType, default to "user" for backward compatibility
            creator_type = task.get("creatorType", "user")
            shared_by = task.get("sharedBy")
            
            if creator_type == "system":
                # ✅ System-generated task (AI): Display as "Green Habit"
                task["creatorType"] = "system"
                task["creatorId"] = None
                task["creatorName"] = "Green Habit"
            elif shared_by:
                # ✅ Shared task: Display original creator
                task["creatorType"] = "user"
                task["creatorId"] = shared_by
                task["creatorName"] = creator_names.get(shared_by, "GreenHabit User")
            else:
                # ✅ User's own task: No external creator
                task["creatorType"] = "user"
                task["creatorId"] = None
                task["creatorName"] = None
        
        return sanitize_docs(tasks)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch tasks: {str(e)}")

@api.post("/tasks", status_code=201)
def create_task(
    payload: CreateTaskPayload,
    user_id: str = Depends(get_current_user)
):
    try:
        # ✅ SECURITY: Rate limit task creation (20/hour)
        check_rate_limit(user_id, "task_create")
        
        task_date = payload.date or date.today().isoformat()
        # user_id provided by Depends
        
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
            "creatorType": payload.creatorType or "user",  # ✅ Creator Attribution
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
    user_id: str = Depends(get_current_user) # ✅ Secure Dependency
):
    try:
        db = get_db()
        # user_id is now provided by Depends
        
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
        
        # ✅ SECURITY: Check if this is a completion toggle
        is_toggling_completion = "isCompleted" in update_data
        
        if is_toggling_completion:
            # Rate limit task completions (30/min)
            check_rate_limit(user_id, "task_complete")
            
            # Cooldown: Prevent rapid toggling of the same task (5 second minimum)
            last_updated = task.get("updatedAt")
            if last_updated:
                check_toggle_cooldown(user_id, task_id, last_updated)
        
        update_data["updatedAt"] = datetime.utcnow()
        
        # Check if task is being completed (not already completed)
        is_completing_task = is_toggling_completion and update_data["isCompleted"] and not task.get("isCompleted", False)
        
        # ✅ SECURITY: Atomic completion guard - prevents double completion race condition
        if is_completing_task:
            update_data["completedAt"] = datetime.utcnow()
            
            # Atomic update: only update if still not completed
            if "id" in task:
                result = db.tasks.update_one(
                    {"id": task_id, "userId": user_id, "isCompleted": False},
                    {"$set": update_data}
                )
            else:
                result = db.tasks.update_one(
                    {"_id": task["_id"], "userId": user_id, "isCompleted": False},
                    {"$set": update_data}
                )
            
            # If no document matched, task was already completed
            if result.matched_count == 0:
                return {
                    "success": True,
                    "message": "Task was already completed",
                    "alreadyCompleted": True,
                    "modified": False
                }
        else:
            # Non-completion update (or uncompleting)
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
        
        # Build response
        response = {
            "success": True,
            "message": "Task updated successfully",
            "modified": result.modified_count > 0
        }
        
        # If completing task, calculate rewards and check achievements
        if is_completing_task and result.modified_count > 0:
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


# ✅ ULTRATHINK FIX: Bulk-delete MUST be defined BEFORE /{task_id} to prevent route shadowing
# FastAPI matches routes in definition order - "bulk-delete" would be matched as task_id otherwise

# Payload class moved here (must be defined before use)
class BulkDeletePayload(BaseModel):
    taskIds: List[str]

@api.delete("/tasks/bulk-delete")

def bulk_delete_tasks_endpoint(
    payload: BulkDeletePayload,
    user_id: str = Depends(get_current_user)
):
    """Delete multiple tasks after export confirmation"""
    try:
        db = get_db()
        
        if not payload.taskIds:
            raise HTTPException(status_code=400, detail="No task IDs provided")
        
        from social_system import bulk_delete_tasks
        
        result = bulk_delete_tasks(db, user_id, payload.taskIds)
        
        # ✅ ULTRATHINK: Never return 404 for bulk operations
        # Always return 200 with success/failure info in response body
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete tasks: {str(e)}")

@api.delete("/tasks/{task_id}")
def delete_task(
    task_id: str,
    user_id: str = Depends(get_current_user) # ✅ Secure Dependency
):
    try:
        db = get_db()
        # user_id is now provided by Depends

        
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
def weekly_stats(user_id: str = Depends(get_current_user)):
    try:
        db = get_db()
        # user_id provided by Depends
        
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
def monthly_stats(user_id: str = Depends(get_current_user)):
    try:
        db = get_db()
        # user_id provided by Depends
        
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
async def get_preferences(user_id: str = Depends(get_current_user)):
    try:
        db = get_db()
        # user_id provided by Depends
        prefs = db.preferences.find_one({"userId": user_id})
        
        if not prefs:
            prefs = {
                "userId": user_id,
                "country": "EU",
                "interests": ["Energy", "Water", "Waste", "Transport", "Food", "Digital", "Social"],
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
    user_id: str = Depends(get_current_user) # ✅ Secure Dependency
):
    try:
        db = get_db()
        # user_id is now provided by Depends

        
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
    
    # Generate 3-4 random tasks from ALL categories
    all_categories = list(TASK_POOL.keys())  # Dynamic: ["Transport", "Energy", "Food", "Waste", "Water", "Digital", "Social"]
    num_tasks = random.randint(3, 4)
    selected_categories = random.sample(all_categories, k=min(num_tasks, len(all_categories)))
    
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
def get_profile(user_id: str = Depends(get_current_user)):
    """Get user profile with achievements and stats"""
    try:
        db = get_db()
        # user_id provided by Depends
        
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
def get_achievements(user_id: str = Depends(get_current_user)):
    """Get all achievements with unlock status"""
    try:
        db = get_db()
        # user_id provided by Depends
        
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
def get_streak(user_id: str = Depends(get_current_user)):
    """Get streak information"""
    try:
        db = get_db()
        # user_id provided by Depends
        
        from rewards_system import calculate_streak
        
        streak_info = calculate_streak(db, user_id)
        
        return streak_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch streak: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch streak: {str(e)}")

# ======================== USER ACCOUNT DELETION ========================

@api.delete("/user/delete")
def delete_user_account(user_id: str = Depends(get_current_user)):
    """
    Delete user account and ALL associated data.
    ✅ CRITICAL: Cascading deletion of ALL user-related documents.
    Apple Guideline 5.1.1(v) compliance: Full account deletion support.
    """
    try:
        db = get_db()
        
        print(f"🗑️ Starting account deletion for user: {user_id}")
        
        # 1. Delete all tasks
        tasks_result = db.tasks.delete_many({"userId": user_id})
        print(f"   - Deleted {tasks_result.deleted_count} tasks")
        
        # 2. Delete preferences
        prefs_result = db.preferences.delete_many({"userId": user_id})
        print(f"   - Deleted {prefs_result.deleted_count} preferences")
        
        # 3. Handle team memberships
        from team_system import handle_user_deletion_teams
        team_cleanup = handle_user_deletion_teams(db, user_id)
        print(f"   - Team cleanup: {team_cleanup}")
        
        # 4. Delete social connections
        from social_system import handle_user_deletion_social
        social_cleanup = handle_user_deletion_social(db, user_id)
        print(f"   - Social cleanup: {social_cleanup}")
        
        # 5. Delete device tokens (APNS)
        tokens_result = db.device_tokens.delete_many({"userId": user_id})
        print(f"   - Deleted {tokens_result.deleted_count} device tokens")
        
        # 6. Delete user record (Apple ID mapping)
        user_result = db.users.delete_one({"userId": user_id})
        print(f"   - Deleted {user_result.deleted_count} user records")
        
        print(f"✅ Account deletion complete for: {user_id}")
        
        return {
            "success": True,
            "message": "Account and all data deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Account deletion failed: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to delete account: {str(e)}"
        )


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
def share_task(payload: ShareTaskPayload, user_id: str = Depends(get_current_user)):
    """Create a short share link for a task"""
    try:
        db = get_db()
        # user_id provided by Depends
        
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
    user_id: str = Depends(get_current_user)
):
    """Get global leaderboard (filtered by viewer's blocked users)"""
    try:
        db = get_db()
        from social_system import get_global_ranking
        
        # Apple Guideline 1.2: Pass viewer_id for blocked user filtering
        ranking = get_global_ranking(db, limit, viewer_id=user_id)
        return ranking
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch ranking: {str(e)}")

@api.get("/ranking/me")
def get_my_rank(user_id: str = Depends(get_current_user)):
    """Get current user's rank and nearby users"""
    try:
        db = get_db()
        # user_id provided by Depends
        from social_system import get_user_rank
        
        rank_info = get_user_rank(db, user_id)
        return rank_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch rank: {str(e)}")

# --- Social Profile Endpoints ---

@api.get("/social/profile")
def get_social_profile_endpoint(user_id: str = Depends(get_current_user)):
    """Get current user's extended social profile"""
    try:
        db = get_db()
        # user_id provided by Depends
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
    user_id: str = Depends(get_current_user)
):
    """Update current user's profile (displayName, bio)"""
    try:
        db = get_db()
        # user_id provided by Depends
        from social_system import update_user_profile
        
        # ✅ Apple Guideline 1.2: Content Safety Check
        try:
            if payload.displayName:
                ProfanityFilter.validate_content(payload.displayName, "Display Name")
            if payload.bio:
                ProfanityFilter.validate_content(payload.bio, "Bio")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        profile = update_user_profile(db, user_id, payload.displayName, payload.bio)
        return profile
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {str(e)}")

@api.get("/users/{target_id}/profile")
def get_public_profile(
    target_id: str,
    user_id: str = Depends(get_current_user)
):
    """Get another user's public profile"""
    try:
        db = get_db()
        viewer_id = user_id  # The authenticated user is the viewer
        
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
    user_id: str = Depends(get_current_user)
):
    """Follow a user"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Unfollow a user"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Get followers list for a user (filtered by viewer's blocked users)"""
    try:
        db = get_db()
        from social_system import get_followers
        
        # Apple Guideline 1.2: Pass viewer_id for blocked user filtering
        result = get_followers(db, target_id, page, limit, viewer_id=user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch followers: {str(e)}")

@api.get("/users/{target_id}/following")
def get_following_endpoint(
    target_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    user_id: str = Depends(get_current_user)
):
    """Get following list for a user (filtered by viewer's blocked users)"""
    try:
        db = get_db()
        from social_system import get_following
        
        # Apple Guideline 1.2: Pass viewer_id for blocked user filtering
        result = get_following(db, target_id, page, limit, viewer_id=user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch following: {str(e)}")

# --- Privacy Settings Endpoints ---

@api.get("/social/privacy")
def get_privacy_endpoint(user_id: str = Depends(get_current_user)):
    """Get current user's privacy settings"""
    try:
        db = get_db()
        from social_system import get_privacy_settings
        
        return get_privacy_settings(db, user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch privacy settings: {str(e)}")

@api.patch("/social/privacy")
def update_privacy_endpoint(
    payload: PrivacySettingsPayload,
    user_id: str = Depends(get_current_user)
):
    """Update user's privacy settings"""
    try:
        db = get_db()
        from social_system import update_privacy_settings
        
        settings = payload.dict(exclude_unset=True)
        result = update_privacy_settings(db, user_id, settings)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update privacy settings: {str(e)}")

# ======================== UGC REPORT & BLOCK SYSTEM ========================
# Apple Guideline 1.2 Compliance: User-generated content moderation

class ReportUserPayload(BaseModel):
    reportedUserId: str
    contentType: str = Field(..., description="bio, name, post, profile")
    reason: str = Field(..., description="harassment, spam, inappropriate_content")

class BlockUserPayload(BaseModel):
    blockedUserId: str

@api.post("/social/report")
async def report_user_endpoint(
    payload: ReportUserPayload,
    user_id: str = Depends(get_current_user)
):
    """
    Report a user for inappropriate content.
    Triggers immediate Telegram notification for 24-hour response compliance.
    """
    try:
        db = get_db()
        
        # Prevent self-reporting
        if payload.reportedUserId == user_id:
            raise HTTPException(status_code=400, detail="Cannot report yourself")
        
        # Create report document
        report_doc = {
            "reporterId": user_id,
            "reportedUserId": payload.reportedUserId,
            "contentType": payload.contentType,
            "reason": payload.reason,
            "status": "pending",
            "createdAt": datetime.utcnow()
        }
        
        result = db.reports.insert_one(report_doc)
        report_id = str(result.inserted_id)
        
        # Send Telegram notification (async - don't block response)
        try:
            from telegram_notifications import send_ugc_report_notification
            await send_ugc_report_notification(
                reporter_id=user_id,
                reported_user_id=payload.reportedUserId,
                content_type=payload.contentType,
                reason=payload.reason,
                report_id=report_id
            )
        except Exception as telegram_error:
            print(f"⚠️ Telegram notification failed (non-blocking): {telegram_error}")
        
        return {
            "success": True,
            "message": "Report submitted successfully",
            "reportId": report_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit report: {str(e)}")

@api.post("/social/block")
def block_user_endpoint(
    payload: BlockUserPayload,
    user_id: str = Depends(get_current_user)
):
    """
    Block a user. Blocked users won't appear in social feeds, search, or rankings.
    """
    try:
        db = get_db()
        
        # Prevent self-blocking
        if payload.blockedUserId == user_id:
            raise HTTPException(status_code=400, detail="Cannot block yourself")
        
        # Add to blockedUsers array using $addToSet (prevents duplicates)
        db.users.update_one(
            {"userId": user_id},
            {"$addToSet": {"blockedUsers": payload.blockedUserId}},
            upsert=True
        )
        
        # Also unfollow the blocked user if following
        try:
            from social_system import unfollow_user
            unfollow_user(db, user_id, payload.blockedUserId)
        except:
            pass  # Ignore if not following
        
        return {
            "success": True,
            "message": "User blocked successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to block user: {str(e)}")

@api.delete("/social/block/{target_id}")
def unblock_user_endpoint(
    target_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Unblock a previously blocked user.
    """
    try:
        db = get_db()
        
        # Remove from blockedUsers array
        db.users.update_one(
            {"userId": user_id},
            {"$pull": {"blockedUsers": target_id}}
        )
        
        return {
            "success": True,
            "message": "User unblocked successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unblock user: {str(e)}")

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
    user_id: str = Depends(get_current_user)
):
    """Send a task to a friend"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Get incoming task shares"""
    try:
        db = get_db()
        from task_sharing import get_incoming_shares
        
        shares = get_incoming_shares(db, user_id, status)
        return {"shares": shares, "count": len(shares)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch shares: {str(e)}")

@api.get("/shares/sent")
def get_sent(user_id: str = Depends(get_current_user)):
    """Get sent task shares"""
    try:
        db = get_db()
        from task_sharing import get_sent_shares
        
        shares = get_sent_shares(db, user_id)
        return {"shares": shares, "count": len(shares)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch shares: {str(e)}")

@api.get("/shares/pending-count")
def get_pending(user_id: str = Depends(get_current_user)):
    """Get count of pending incoming shares"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Accept a shared task"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Reject a shared task"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Create a new team"""
    try:
        db = get_db()
        from team_system import create_team, get_my_team, get_team_members
        
        # ✅ Apple Guideline 1.2: Content Safety Check
        try:
            ProfanityFilter.validate_content(payload.name, "Team Name")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
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
def get_my_team_endpoint(user_id: str = Depends(get_current_user)):
    """Get current user's team"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Get team by ID"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Delete team (creator only)"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Leave team (members only)"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Remove member from team (creator only)"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Update member permissions (creator only)"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Invite user to team (creator only)"""
    try:
        db = get_db()
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
def get_pending_invitations_endpoint(user_id: str = Depends(get_current_user)):
    """Get pending team invitations for current user"""
    try:
        db = get_db()
        from team_system import get_pending_invitations
        
        invitations = get_pending_invitations(db, user_id)
        return {"invitations": invitations, "count": len(invitations)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get invitations: {str(e)}")

@api.get("/teams/invitations/sent")
def get_sent_invitations_endpoint(user_id: str = Depends(get_current_user)):
    """Get team invitations sent by current user (outgoing)"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Accept team invitation"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Reject team invitation"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Share task to all team members (creator only)"""
    try:
        db = get_db()
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
def get_pending_team_tasks_endpoint(user_id: str = Depends(get_current_user)):
    """Get pending team task shares for current user"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Accept team task share"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Reject team task share"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Get team statistics"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Get team leaderboard"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Search for users by display name"""
    try:
        db = get_db()
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
    user_id: str = Depends(get_current_user)
):
    """Get daily task completion data for a specific month"""
    try:
        db = get_db()
        
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
# NOTE: BulkDeletePayload class moved to line 430 (before bulk-delete endpoint)


@api.get("/tasks/export")
def export_tasks_endpoint(
    year: int = Query(...),
    month: int = Query(...),
    user_id: str = Depends(get_current_user)
):
    """Get all completed tasks for export (PDF generation)"""
    try:
        db = get_db()
        
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


# NOTE: bulk-delete endpoint moved to line 425 (before /tasks/{task_id}) to fix route shadowing

# ======================== NOTIFICATION ROUTES ========================

class DeviceTokenPayload(BaseModel):
    token: str
    platform: str = "ios"

@api.post("/notifications/register-token")
def register_token_endpoint(
    payload: DeviceTokenPayload,
    user_id: str = Depends(get_current_user)
):
    """Register device token for push notifications"""
    try:
        db = get_db()
        from notification_system import register_device_token
        
        return register_device_token(db, user_id, payload.token, payload.platform)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register token: {str(e)}")


# ======================== TELEGRAM WEBHOOK (Moderation) ========================
# Apple Guideline 1.2 Compliance: Instant moderation actions from Telegram

from fastapi import Request

# Get authorized Telegram chat ID from environment
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


@app.post("/api/telegram/webhook")
async def telegram_webhook(request: Request):
    """
    Handle Telegram callback queries for moderation actions.
    
    Security: Only processes requests from the authorized TELEGRAM_CHAT_ID.
    This endpoint handles "Ban User" button presses from UGC report notifications.
    """
    try:
        data = await request.json()
        
        # Check if this is a callback query (button press)
        callback_query = data.get("callback_query")
        if not callback_query:
            # Not a callback query - just acknowledge
            return {"ok": True}
        
        # ✅ SECURITY: Verify sender is authorized
        from_id = str(callback_query.get("from", {}).get("id", ""))
        
        if not TELEGRAM_CHAT_ID or from_id != TELEGRAM_CHAT_ID:
            print(f"⚠️ Unauthorized Telegram callback from: {from_id}")
            raise HTTPException(
                status_code=403, 
                detail="Unauthorized: Sender ID not authorized"
            )
        
        callback_data = callback_query.get("data", "")
        callback_query_id = callback_query.get("id", "")
        message = callback_query.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        message_id = message.get("message_id")
        
        # Handle "ban_[user_id]" callback
        if callback_data.startswith("ban_"):
            user_id_to_ban = callback_data[4:]  # Remove "ban_" prefix
            
            if not user_id_to_ban:
                raise HTTPException(status_code=400, detail="Invalid user ID")
            
            db = get_db()
            
            # ✅ Acknowledge callback immediately (within 30s requirement)
            from telegram_notifications import answer_callback_query, edit_message_text
            await answer_callback_query(
                callback_query_id, 
                text="✅ User banned successfully!",
                show_alert=True
            )
            
            # Update user document to set isBanned: true
            result = db.users.update_one(
                {"userId": user_id_to_ban},
                {"$set": {"isBanned": True, "bannedAt": datetime.utcnow()}}
            )
            
            if result.matched_count > 0:
                print(f"🚫 User {user_id_to_ban} has been banned via Telegram")
                
                # Update the original message to confirm action
                if message_id and chat_id:
                    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
                    await edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        new_text=f"✅ *User Banned Successfully*\n\n"
                                 f"• User ID: `{user_id_to_ban}`\n"
                                 f"• Banned At: `{timestamp}`\n\n"
                                 f"_The user can no longer access the application._"
                    )
                
                return {"ok": True, "action": "user_banned", "userId": user_id_to_ban}
            else:
                print(f"⚠️ User {user_id_to_ban} not found in database")
                return {"ok": True, "action": "user_not_found"}
        
        return {"ok": True}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Telegram webhook error: {e}")
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")


# ======================== BAN STATUS ENDPOINT ========================

@api.get("/auth/ban-status")
def get_ban_status(user_id: str = Depends(get_current_user)):
    """
    Check if the current user is banned.
    Called on app launch to enforce ban at the client level.
    
    Returns:
        isBanned: bool - Whether the user is currently banned
        appealUrl: str - Instagram URL for ban appeals
    """
    try:
        db = get_db()
        
        user = db.users.find_one({"userId": user_id}, {"isBanned": 1})
        is_banned = user.get("isBanned", False) if user else False
        
        return {
            "isBanned": is_banned,
            "appealUrl": "https://www.instagram.com/greenhabittask"
        }
        
    except Exception as e:
        print(f"❌ Ban status check failed: {e}")
        # Default to not banned on error (fail open for UX)
        return {
            "isBanned": False,
            "appealUrl": "https://www.instagram.com/greenhabittask"
        }


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
                    "paths": ["/share/*", "/user/*"]  # ✅ Added /user/* for moderation deep links
                }
            ]
        }
    }
    return JSONResponse(content=content)


# ======================== USER PROFILE UNIVERSAL LINK ========================
# Telegram requires HTTPS URLs - iOS intercepts this via Universal Links

@app.get("/user/{user_id}", response_class=HTMLResponse)
def user_profile_redirect(user_id: str):
    """
    Universal Link endpoint for user profiles.
    
    iOS: Universal Links intercept this → opens ProfileView(userId:)
    Browser: Shows HTML fallback with deep link button
    """
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>View Profile • GreenHabit</title>
        <meta http-equiv="refresh" content="0;url=greenhabit://user?id={user_id}">
        <style>
            :root {{
                --bg-color: #0b1c2d;
                --text-primary: #FFFFFF;
                --accent: #00E676;
            }}
            body {{
                margin: 0;
                padding: 40px 20px;
                background-color: var(--bg-color);
                color: var(--text-primary);
                font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                text-align: center;
            }}
            .logo {{ font-size: 64px; margin-bottom: 20px; }}
            h1 {{ font-size: 24px; margin-bottom: 16px; }}
            p {{ color: rgba(255,255,255,0.6); margin-bottom: 24px; }}
            .btn {{
                display: inline-block;
                padding: 16px 32px;
                background: var(--accent);
                color: #000;
                text-decoration: none;
                border-radius: 12px;
                font-weight: 600;
            }}
        </style>
    </head>
    <body>
        <div class="logo">🌿</div>
        <h1>Opening GreenHabit...</h1>
        <p>If the app doesn't open, tap the button below.</p>
        <a href="greenhabit://user?id={user_id}" class="btn">Open in App</a>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

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
