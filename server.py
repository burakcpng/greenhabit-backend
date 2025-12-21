from fastapi import FastAPI, APIRouter, HTTPException, Query, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta
from typing import List, Optional
import os
import random
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
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc

def sanitize_docs(docs):
    return [sanitize_doc(doc) for doc in docs]

def get_user_id(x_user_id: Optional[str] = Header(None)) -> str:
    return x_user_id or "demo-user"

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

# Task Templates for AI Generation
TASK_POOL = {
    "Energy": [
        {
            "title": "Turn off unused lights",
            "details": "Reduce electricity usage at home by switching off lights in empty rooms.",
            "points": 10,
            "estimatedImpact": "Saves ~0.3kg CO₂"
        },
        {
            "title": "Unplug phone charger",
            "details": "Phone chargers consume energy even when not charging. Unplug them!",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂"
        },
        {
            "title": "Use natural daylight",
            "details": "Open curtains and blinds to use natural light instead of electric lighting.",
            "points": 10,
            "estimatedImpact": "Saves ~0.3kg CO₂"
        },
        {
            "title": "Set thermostat 1°C lower",
            "details": "Reducing heating by just 1 degree saves significant energy.",
            "points": 15,
            "estimatedImpact": "Saves ~1.0kg CO₂"
        },
        {
            "title": "Air dry laundry",
            "details": "Skip the dryer and hang your clothes to dry naturally.",
            "points": 20,
            "estimatedImpact": "Saves ~2.5kg CO₂"
        },
    ],
    "Water": [
        {
            "title": "Take shorter showers",
            "details": "Save water by limiting shower time to 5 minutes.",
            "points": 20,
            "estimatedImpact": "Saves ~40L water"
        },
        {
            "title": "Turn off tap while brushing",
            "details": "Don't let water run while brushing teeth. Save up to 8L per minute!",
            "points": 10,
            "estimatedImpact": "Saves ~16L water"
        },
        {
            "title": "Fix dripping faucet",
            "details": "Check all faucets and fix any drips. A drip wastes 20L daily.",
            "points": 15,
            "estimatedImpact": "Saves ~20L water"
        },
        {
            "title": "Collect rainwater",
            "details": "Set up a container to collect rainwater for watering plants.",
            "points": 15,
            "estimatedImpact": "Saves ~10L water"
        },
        {
            "title": "Run dishwasher when full",
            "details": "Wait until dishwasher is completely full before running it.",
            "points": 10,
            "estimatedImpact": "Saves ~15L water"
        },
    ],
    "Waste": [
        {
            "title": "Use a reusable bottle",
            "details": "Avoid single-use plastic bottles.",
            "points": 15,
            "estimatedImpact": "Reduces plastic waste"
        },
        {
            "title": "Bring reusable bag",
            "details": "Take your reusable shopping bag when going to the store.",
            "points": 10,
            "estimatedImpact": "Saves 1 plastic bag"
        },
        {
            "title": "Compost food scraps",
            "details": "Collect fruit peels, vegetable scraps, and coffee grounds.",
            "points": 15,
            "estimatedImpact": "Reduces ~0.5kg waste"
        },
        {
            "title": "Refuse plastic straws",
            "details": "Ask for no straw or bring your own reusable one.",
            "points": 5,
            "estimatedImpact": "Saves 1 plastic straw"
        },
        {
            "title": "Recycle paper properly",
            "details": "Separate all paper and cardboard from trash and recycle.",
            "points": 10,
            "estimatedImpact": "Saves ~0.9kg CO₂"
        },
    ],
    "Transport": [
        {
            "title": "Walk short distances",
            "details": "For trips under 1km, leave the car and walk.",
            "points": 15,
            "estimatedImpact": "Saves ~0.2kg CO₂/km"
        },
        {
            "title": "Use public transport",
            "details": "Take the bus, metro, or tram instead of driving.",
            "points": 20,
            "estimatedImpact": "Saves ~2.0kg CO₂"
        },
        {
            "title": "Bike to work",
            "details": "Use your bicycle for commute today.",
            "points": 25,
            "estimatedImpact": "Saves ~3.0kg CO₂"
        },
        {
            "title": "Carpool with colleague",
            "details": "Share your ride to work with a colleague nearby.",
            "points": 20,
            "estimatedImpact": "Saves 50% emissions"
        },
        {
            "title": "Work from home",
            "details": "Save a commute by working from home if possible.",
            "points": 25,
            "estimatedImpact": "Saves full commute"
        },
    ]
}

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
        
        task_dict = {
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
            "taskId": str(result.inserted_id),
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
        
        try:
            object_id = ObjectId(task_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid task ID format")
        
        update_data = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        update_data["updatedAt"] = datetime.utcnow()
        
        if "isCompleted" in update_data and update_data["isCompleted"]:
            update_data["completedAt"] = datetime.utcnow()
        
        result = db.tasks.update_one(
            {"_id": object_id, "userId": user_id},
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
        
        try:
            object_id = ObjectId(task_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid task ID format")
        
        result = db.tasks.delete_one({"_id": object_id, "userId": user_id})
        
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
                    "title": "Water Conservation at Home",
                    "details": "Water is one of our most precious resources. Simple changes in daily habits can save thousands of liters per year. Fix leaky faucets - a single dripping faucet can waste up to 20 gallons per day. Take shorter showers - reducing your shower time by just 2 minutes can save up to 10 gallons of water. Turn off the tap while brushing teeth or shaving. Use a dishwasher instead of hand washing - modern dishwashers use less water. Collect rainwater for watering plants. Install low-flow showerheads and faucet aerators. Water your garden early morning or late evening to reduce evaporation. Choose drought-resistant plants for your garden. Use a broom instead of a hose to clean driveways.",
                    "category": "Water"
                },
                {
                    "title": "Energy Efficiency Tips",
                    "details": "Reducing energy consumption helps the environment and saves money. Switch to LED bulbs - they use 75% less energy than incandescent bulbs and last 25 times longer. Unplug electronics when not in use - standby power can account for 10% of household energy use. Use natural light when possible. Set your thermostat efficiently - each degree lower in winter saves about 3% on heating bills. Wash clothes in cold water - 90% of washing machine energy goes to heating water. Air dry clothes when possible. Use smart power strips to eliminate phantom loads. Seal windows and doors to prevent drafts. Consider solar panels for long-term savings. Choose energy-efficient appliances with high Energy Star ratings.",
                    "category": "Energy"
                },
                {
                    "title": "Reducing Plastic Waste",
                    "details": "Plastic pollution is one of the biggest environmental challenges. Over 8 million tons of plastic enter our oceans every year. Bring reusable bags when shopping. Use a reusable water bottle - the average person could save 167 plastic bottles per year. Say no to straws or use metal/bamboo alternatives. Choose products with minimal packaging. Buy in bulk to reduce packaging waste. Use beeswax wraps instead of plastic wrap. Choose bar soap and shampoo bars over bottled products. Recycle properly - learn what can and cannot be recycled in your area. Support businesses that use sustainable packaging. Participate in local beach or park cleanups.",
                    "category": "Waste"
                },
                {
                    "title": "Sustainable Transportation",
                    "details": "Transportation accounts for about 29% of greenhouse gas emissions. Walk or bike for short trips - it's healthy and emission-free. Use public transportation when possible. Carpool with colleagues or neighbors. If you drive, maintain your vehicle properly - properly inflated tires improve fuel efficiency. Combine errands into one trip to reduce total driving. Consider an electric or hybrid vehicle for your next car. Work from home when possible. Plan routes efficiently to avoid traffic and reduce fuel consumption. Fly less - one transatlantic flight can emit more CO2 than a year of driving. When flying is necessary, choose direct flights and offset your carbon.",
                    "category": "Transport"
                },
                {
                    "title": "Composting 101",
                    "details": "Composting turns food scraps and yard waste into nutrient-rich soil. About 30% of household waste can be composted. Start with a compost bin or designated area in your yard. Add 'green' materials like fruit and vegetable scraps, coffee grounds, and grass clippings. Balance with 'brown' materials like dried leaves, cardboard, and paper. Keep your compost moist but not wet. Turn it regularly to add oxygen. Avoid adding meat, dairy, or oily foods. Compost is ready when it's dark, crumbly, and smells earthy. Use it to enrich garden soil, potted plants, or lawn. Even apartment dwellers can compost with bokashi or vermicomposting methods.",
                    "category": "Waste"
                },
                {
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
        raise HTTPException(status_code=500, detail=f"Failed to fetch learning content: {str(e)}")

@api.post("/ai/generate-tasks")
async def generate_ai_tasks():
    """Generate random eco-friendly tasks from different categories"""
    today = date.today().isoformat()
    
    # Rastgele 3-4 kategori seç
    all_categories = ["Energy", "Water", "Waste", "Transport"]
    num_tasks = random.randint(3, 4)
    selected_categories = random.sample(all_categories, k=num_tasks)
    
    generated_tasks = []
    
    for category in selected_categories:
        # Her kategoriden rastgele bir task seç
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
