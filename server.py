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

# ======================== TASK POOL ========================

TASK_POOL = {
    "Energy": [
        {
            "title": "💡 Turn off unused lights",
            "details": "Make it a habit to switch off all lights when leaving a room. Even a few seconds makes a difference!",
            "points": 10,
            "estimatedImpact": "Saves ~0.3kg CO₂/day"
        },
        {
            "title": "🔌 Unplug phone charger",
            "details": "Phone chargers consume 'phantom power' even when not charging. Unplug them to save energy!",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂/day"
        },
        {
            "title": "☀️ Use natural daylight",
            "details": "Open curtains and blinds during the day. Let the sun light your space instead of electric bulbs!",
            "points": 10,
            "estimatedImpact": "Saves ~0.3kg CO₂/day"
        },
        {
            "title": "🌡️ Set thermostat 1°C lower",
            "details": "Reducing your heating by just 1 degree can save significant energy over time without much discomfort.",
            "points": 15,
            "estimatedImpact": "Saves ~1.0kg CO₂/day"
        },
        {
            "title": "👕 Air dry laundry",
            "details": "Skip the dryer and hang your clothes to dry naturally. Saves energy and clothes last longer!",
            "points": 20,
            "estimatedImpact": "Saves ~2.5kg CO₂/load"
        },
        {
            "title": "🔋 Unplug all devices at night",
            "details": "Use a power strip and turn everything off before bed. Stop vampire energy drain!",
            "points": 15,
            "estimatedImpact": "Saves ~0.5kg CO₂/day"
        },
        {
            "title": "🪟 Close curtains at sunset",
            "details": "Keep heat inside during cold months. Simple insulation trick that really works!",
            "points": 10,
            "estimatedImpact": "Saves ~0.4kg CO₂/day"
        },
        {
            "title": "❄️ Clean refrigerator coils",
            "details": "Dusty coils make your fridge work harder. Clean them every 6 months for efficiency.",
            "points": 15,
            "estimatedImpact": "Improves efficiency 5%"
        },
        {
            "title": "🍳 Use lids when cooking",
            "details": "Cover pots and pans to cook faster and use less energy. Works with all types of stoves!",
            "points": 10,
            "estimatedImpact": "Saves ~0.2kg CO₂/meal"
        },
        {
            "title": "🖥️ Enable power saving mode",
            "details": "Activate energy-saving settings on your computer, phone, and other devices.",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂/day"
        },
    ],
    "Water": [
        {
            "title": "⏱️ Take 5-minute shower",
            "details": "Challenge yourself to shower in 5 minutes or less. Use a waterproof timer to track!",
            "points": 20,
            "estimatedImpact": "Saves ~40L water"
        },
        {
            "title": "🪥 Turn off tap while brushing",
            "details": "Don't let water run while brushing teeth. You can save up to 8L per minute!",
            "points": 10,
            "estimatedImpact": "Saves ~16L/brush"
        },
        {
            "title": "🔧 Fix dripping faucet",
            "details": "Check all faucets in your home and fix any drips. One drip per second wastes 20L daily!",
            "points": 15,
            "estimatedImpact": "Saves ~20L/day"
        },
        {
            "title": "🌧️ Collect rainwater",
            "details": "Set up a barrel or container to collect rainwater for watering plants.",
            "points": 15,
            "estimatedImpact": "Saves ~10L/use"
        },
        {
            "title": "🍽️ Run dishwasher when full",
            "details": "Wait until your dishwasher is completely full before running it. No half-loads!",
            "points": 10,
            "estimatedImpact": "Saves ~15L/load"
        },
        {
            "title": "🧊 Use a glass of water for brushing",
            "details": "Fill a glass with water for rinsing instead of running the tap.",
            "points": 5,
            "estimatedImpact": "Saves ~8L/day"
        },
        {
            "title": "🚿 Install low-flow showerhead",
            "details": "Modern low-flow showerheads maintain pressure while using 40% less water.",
            "points": 25,
            "estimatedImpact": "Saves ~60L/shower"
        },
        {
            "title": "🧺 Wash full loads of laundry",
            "details": "Only run washing machine with full loads. Saves water and energy!",
            "points": 15,
            "estimatedImpact": "Saves ~50L/load"
        },
        {
            "title": "🌱 Water plants in the morning",
            "details": "Early morning watering reduces evaporation, so plants get more water.",
            "points": 10,
            "estimatedImpact": "Saves ~30% water"
        },
        {
            "title": "🧽 Use a bowl to wash dishes",
            "details": "Fill a bowl with soapy water instead of running tap continuously.",
            "points": 10,
            "estimatedImpact": "Saves ~20L/session"
        },
    ],
    "Waste": [
        {
            "title": "♻️ Use a reusable bottle",
            "details": "Carry your own water bottle. Say no to single-use plastic bottles forever!",
            "points": 15,
            "estimatedImpact": "Saves 1 plastic bottle"
        },
        {
            "title": "🛍️ Bring reusable bag",
            "details": "Take your reusable shopping bag when going to the store. Keep one in your car!",
            "points": 10,
            "estimatedImpact": "Saves 1 plastic bag"
        },
        {
            "title": "🥬 Compost food scraps",
            "details": "Start composting fruit peels, vegetable scraps, and coffee grounds.",
            "points": 15,
            "estimatedImpact": "Reduces ~0.5kg waste"
        },
        {
            "title": "🥤 Refuse plastic straws",
            "details": "Say 'no straw, please' when ordering drinks, or bring your own reusable one.",
            "points": 5,
            "estimatedImpact": "Saves 1 plastic straw"
        },
        {
            "title": "📦 Recycle cardboard properly",
            "details": "Flatten boxes and put them in recycling. Remove tape and labels first!",
            "points": 10,
            "estimatedImpact": "Saves ~0.9kg CO₂/kg"
        },
        {
            "title": "🍱 Pack lunch in reusable containers",
            "details": "Stop using disposable packaging. Invest in good quality lunch containers.",
            "points": 15,
            "estimatedImpact": "Saves 5 items/day"
        },
        {
            "title": "☕ Use a reusable coffee cup",
            "details": "Bring your own cup to coffee shops. Many offer discounts too!",
            "points": 10,
            "estimatedImpact": "Saves 1 cup/day"
        },
        {
            "title": "🧻 Switch to cloth napkins",
            "details": "Replace paper napkins with cloth ones. Wash and reuse!",
            "points": 10,
            "estimatedImpact": "Saves paper waste"
        },
        {
            "title": "📄 Go paperless with bills",
            "details": "Switch to digital bills and statements. Save paper and reduce clutter!",
            "points": 5,
            "estimatedImpact": "Saves trees"
        },
        {
            "title": "🎁 Reuse gift bags and wrap",
            "details": "Save gift wrap, bags, and ribbons to reuse for future occasions.",
            "points": 10,
            "estimatedImpact": "Reduces waste"
        },
    ],
    "Transport": [
        {
            "title": "🚶 Walk short distances",
            "details": "For trips under 1km, leave the car at home and walk. Good for health and planet!",
            "points": 15,
            "estimatedImpact": "Saves ~0.2kg CO₂/km"
        },
        {
            "title": "🚌 Use public transport",
            "details": "Take the bus, metro, or tram instead of driving your car today.",
            "points": 20,
            "estimatedImpact": "Saves ~2.0kg CO₂/trip"
        },
        {
            "title": "🚲 Bike to work",
            "details": "Use your bicycle for your commute. Zero emissions and great exercise!",
            "points": 25,
            "estimatedImpact": "Saves ~3.0kg CO₂/trip"
        },
        {
            "title": "👥 Carpool with colleague",
            "details": "Share your ride to work with a colleague who lives nearby.",
            "points": 20,
            "estimatedImpact": "Saves 50% emissions"
        },
        {
            "title": "🏠 Work from home",
            "details": "Skip the commute by working from home today if your job allows.",
            "points": 25,
            "estimatedImpact": "Saves full commute"
        },
        {
            "title": "🛴 Use an e-scooter",
            "details": "Try an electric scooter for medium-distance trips instead of a car.",
            "points": 15,
            "estimatedImpact": "Saves ~1.5kg CO₂/trip"
        },
        {
            "title": "🚗 Maintain proper tire pressure",
            "details": "Check and inflate your tires to recommended PSI. Improves fuel efficiency by 3%!",
            "points": 10,
            "estimatedImpact": "Saves ~0.3kg CO₂/day"
        },
        {
            "title": "🛒 Combine errands into one trip",
            "details": "Plan your route to do multiple errands in one outing instead of several trips.",
            "points": 15,
            "estimatedImpact": "Saves ~1.0kg CO₂"
        },
        {
            "title": "✈️ Take train instead of plane",
            "details": "For distances under 500km, trains emit 10x less CO₂ than planes.",
            "points": 30,
            "estimatedImpact": "Saves ~5.0kg CO₂"
        },
        {
            "title": "💻 Video call instead of travel",
            "details": "Use video conferencing for meetings instead of traveling.",
            "points": 20,
            "estimatedImpact": "Saves travel emissions"
        },
    ]
}

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
        raise HTTPException(status_code=500, detail=f"Failed to fetch learning content: {str(e)}")

# ======================== AI ROUTES ========================

@api.post("/ai/generate-tasks")
async def generate_ai_tasks(x_user_id: Optional[str] = Header(None)):
    """Generate random eco-friendly tasks and save to database"""
    try:
        db = get_db()
        user_id = get_user_id(x_user_id)
        
        today = date.today().isoformat()
        
        # Check if tasks already exist for today
        existing_tasks = list(db.tasks.find({
            "userId": user_id,
            "date": today
        }))
        
        if len(existing_tasks) >= 3:
            return {
                "message": "Tasks already generated for today",
                "tasks": sanitize_docs(existing_tasks),
                "count": len(existing_tasks)
            }
        
        # Generate 3-4 random tasks from different categories
        all_categories = ["Energy", "Water", "Waste", "Transport"]
        num_tasks = random.randint(3, 4)
        selected_categories = random.sample(all_categories, k=num_tasks)
        
        generated_tasks = []
        
        for category in selected_categories:
            task_template = random.choice(TASK_POOL[category])
            
            task_id = str(uuid.uuid4())
            task_dict = {
                "id": task_id,
                "userId": user_id,
                "title": task_template["title"],
                "details": task_template["details"],
                "category": category,
                "date": today,
                "points": task_template["points"],
                "estimatedImpact": task_template["estimatedImpact"],
                "isCompleted": False,
                "completedAt": None,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow()
            }
            
            db.tasks.insert_one(task_dict)
            generated_tasks.append(sanitize_doc(task_dict.copy()))
        
        return {
            "message": "Tasks generated successfully",
            "tasks": generated_tasks,
            "count": len(generated_tasks)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate tasks: {str(e)}")

app.include_router(api)"Failed to fetch tasks: {str(e)}")

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
        
        # Try to find by custom 'id' field first (UUID), then by ObjectId
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
        
        if "isCompleted" in update_data and update_data["isCompleted"]:
            update_data["completedAt"] = datetime.utcnow()
        
        # Update using the same identifier
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
        
        # Try to find by custom 'id' field first (UUID), then by ObjectId
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
            seed_data = [
                {
                    "id": str(uuid.uuid4()),
                    "title": "Water Conservation at Home",
                    "details": "Water is one of our most precious resources. Simple changes in daily habits can save thousands of liters per year. Fix leaky faucets - a single dripping faucet can waste up to 20 gallons per day. Take shorter showers - reducing your shower time by just 2 minutes can save up to 10 gallons of water. Turn off the tap while brushing teeth or shaving. Use a dishwasher instead of hand washing - modern dishwashers use less water. Collect rainwater for watering plants. Install low-flow showerheads and faucet aerators. Water your garden early morning or late evening to reduce evaporation. Choose drought-resistant plants for your garden. Use a broom instead of a hose to clean driveways.",
                    "category": "Water"
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "Energy Efficiency Tips",
                    "details": "Reducing energy consumption helps the environment and saves money. Switch to LED bulbs - they use 75% less energy than incandescent bulbs and last 25 times longer. Unplug electronics when not in use - standby power can account for 10% of household energy use. Use natural light when possible. Set your thermostat efficiently - each degree lower in winter saves about 3% on heating bills. Wash clothes in cold water - 90% of washing machine energy goes to heating water. Air dry clothes when possible. Use smart power strips to eliminate phantom loads. Seal windows and doors to prevent drafts. Consider solar panels for long-term savings. Choose energy-efficient appliances with high Energy Star ratings.",
                    "category": "Energy"
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "Reducing Plastic Waste",
                    "details": "Plastic pollution is one of the biggest environmental challenges. Over 8 million tons of plastic enter our oceans every year. Bring reusable bags when shopping. Use a reusable water bottle - the average person could save 167 plastic bottles per year. Say no to straws or use metal/bamboo alternatives. Choose products with minimal packaging. Buy in bulk to reduce packaging waste. Use beeswax wraps instead of plastic wrap. Choose bar soap and shampoo bars over bottled products. Recycle properly - learn what can and cannot be recycled in your area. Support businesses that use sustainable packaging. Participate in local beach or park cleanups.",
                    "category": "Waste"
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "Sustainable Transportation",
                    "details": "Transportation accounts for about 29% of greenhouse gas emissions. Walk or bike for short trips - it's healthy and emission-free. Use public transportation when possible. Carpool with colleagues or neighbors. If you drive, maintain your vehicle properly - properly inflated tires improve fuel efficiency. Combine errands into one trip to reduce total driving. Consider an electric or hybrid vehicle for your next car. Work from home when possible. Plan routes efficiently to avoid traffic and reduce fuel consumption. Fly less - one transatlantic flight can emit more CO2 than a year of driving. When flying is necessary, choose direct flights and offset your carbon.",
                    "category": "Transport"
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "Composting 101",
                    "details": "Composting turns food scraps and yard waste into nutrient-rich soil. About 30% of household waste can be composted. Start with a compost bin or designated area in your yard. Add 'green' materials like fruit and vegetable scraps, coffee grounds, and grass clippings. Balance with 'brown' materials like dried leaves, cardboard, and paper. Keep your compost moist but not wet. Turn it regularly to add oxygen. Avoid adding meat, dairy, or oily foods. Compost is ready when it's dark, crumbly, and smells earthy. Use it to enrich garden soil, potted plants, or lawn. Even apartment dwellers can compost with bokashi or vermicomposting methods.",
                    "category": "Waste"
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "Understanding Your Carbon Footprint",
                    "details": "A carbon footprint measures the total greenhouse gas emissions caused by an individual, event, organization, or product. The average person's carbon footprint in developed countries is about 10-20 tons of CO2 per year. Major contributors include: transportation (especially flying), home energy use, diet (meat production is carbon-intensive), and consumer goods. Calculate your footprint using online calculators to understand your impact. Reduce your footprint by: eating less meat, reducing air travel, improving home energy efficiency, buying local and seasonal products, reducing, reusing, and recycling. Carbon offsetting can help neutralize emissions you cannot eliminate. Small daily changes add up to significant impact over time.",
                    "category": "General"
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
        raise HTTPException(status_code=500, detail=f
