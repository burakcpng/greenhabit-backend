from fastapi import FastAPI, APIRouter, HTTPException, Query
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timedelta
from bson import ObjectId
import random

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'GreenHabit_db')]

# Create the main app
app = FastAPI(title="GreenHabit API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default user ID for single-user mode
DEFAULT_USER_ID = "demo-user"

# ======================== MODELS ========================

class EcoTask(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    userId: str = DEFAULT_USER_ID
    title: str
    details: str
    category: str  # Energy, Water, Waste, Transport
    isCompleted: bool = False
    date: str  # YYYY-MM-DD format
    points: int = 10
    estimatedImpact: str = "Saves ~0.5kg CO₂"
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}

class EcoTaskCreate(BaseModel):
    title: str
    details: str
    category: str
    date: Optional[str] = None
    points: int = 10
    estimatedImpact: str = "Saves ~0.5kg CO₂"

class EcoTaskUpdate(BaseModel):
    title: Optional[str] = None
    details: Optional[str] = None
    category: Optional[str] = None
    isCompleted: Optional[bool] = None
    date: Optional[str] = None
    points: Optional[int] = None
    estimatedImpact: Optional[str] = None

class UserPreferences(BaseModel):
    userId: str = DEFAULT_USER_ID
    country: str = "Turkey"
    interests: List[str] = ["Energy", "Water", "Waste", "Transport"]
    language: str = "en"

class UserPreferencesUpdate(BaseModel):
    country: Optional[str] = None
    interests: Optional[List[str]] = None
    language: Optional[str] = None

class LearningContent(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    title: str
    details: str
    category: str

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}

class WeeklyStats(BaseModel):
    days: List[dict]  # [{day: "Mon", completed: 3}, ...]
    totalCompleted: int
    totalPoints: int
    co2Saved: float

class MonthlyStats(BaseModel):
    weeks: List[dict]  # [{week: 1, completed: 10}, ...]
    totalCompleted: int
    totalPoints: int
    co2Saved: float

class AIGenerateTasksRequest(BaseModel):
    interests: List[str]
    country: str = "Turkey"

class AIWeeklyReportRequest(BaseModel):
    energy: int = 0
    water: int = 0
    waste: int = 0
    transport: int = 0

class AISummarizeRequest(BaseModel):
    text: str

# ======================== HELPER FUNCTIONS ========================

def serialize_task(task: dict) -> dict:
    """Convert MongoDB document to serializable format"""
    if task:
        task["_id"] = str(task["_id"])
    return task

def serialize_learning(content: dict) -> dict:
    """Convert MongoDB document to serializable format"""
    if content:
        content["_id"] = str(content["_id"])
    return content

# ======================== TASKS ROUTES ========================
from fastapi import FastAPI

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@api_router.get("/tasks")
async def get_tasks(date: Optional[str] = Query(None)):
    """Get tasks, optionally filtered by date"""
    query = {"userId": DEFAULT_USER_ID}
    if date:
        query["date"] = date
    
    tasks = await db.tasks.find(query).sort("createdAt", -1).to_list(100)
    return [serialize_task(task) for task in tasks]

@api_router.post("/tasks")
async def create_task(task: EcoTaskCreate):
    """Create a new task"""
    task_dict = task.dict()
    task_dict["userId"] = DEFAULT_USER_ID
    task_dict["isCompleted"] = False
    task_dict["createdAt"] = datetime.utcnow()
    
    if not task_dict.get("date"):
        task_dict["date"] = datetime.utcnow().strftime("%Y-%m-%d")
    
    result = await db.tasks.insert_one(task_dict)
    task_dict["_id"] = str(result.inserted_id)
    return task_dict

@api_router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """Get a single task by ID"""
    try:
        task = await db.tasks.find_one({"_id": ObjectId(task_id)})
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return serialize_task(task)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.patch("/tasks/{task_id}")
async def update_task(task_id: str, task_update: EcoTaskUpdate):
    """Update a task"""
    try:
        update_data = {k: v for k, v in task_update.dict().items() if v is not None}
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No update data provided")
        
        result = await db.tasks.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        
        updated_task = await db.tasks.find_one({"_id": ObjectId(task_id)})
        return serialize_task(updated_task)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete a task"""
    try:
        result = await db.tasks.delete_one({"_id": ObjectId(task_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Task deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ======================== STATS ROUTES ========================

@api_router.get("/stats/weekly")
async def get_weekly_stats():
    """Get weekly statistics"""
    today = datetime.utcnow()
    start_of_week = today - timedelta(days=today.weekday())
    
    days = []
    total_completed = 0
    total_points = 0
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    for i in range(7):
        day_date = start_of_week + timedelta(days=i)
        date_str = day_date.strftime("%Y-%m-%d")
        
        tasks = await db.tasks.find({
            "userId": DEFAULT_USER_ID,
            "date": date_str,
            "isCompleted": True
        }).to_list(100)
        
        completed_count = len(tasks)
        day_points = sum(task.get("points", 10) for task in tasks)
        
        days.append({
            "day": day_names[i],
            "date": date_str,
            "completed": completed_count,
            "points": day_points
        })
        
        total_completed += completed_count
        total_points += day_points
    
    # Symbolic CO2 calculation: ~0.5kg per task
    co2_saved = round(total_completed * 0.5, 2)
    
    return {
        "days": days,
        "totalCompleted": total_completed,
        "totalPoints": total_points,
        "co2Saved": co2_saved
    }

@api_router.get("/stats/monthly")
async def get_monthly_stats():
    """Get monthly statistics"""
    today = datetime.utcnow()
    start_of_month = today.replace(day=1)
    
    weeks = []
    total_completed = 0
    total_points = 0
    
    # Calculate 4-5 weeks
    current_date = start_of_month
    week_num = 1
    
    while current_date.month == today.month and week_num <= 5:
        week_start = current_date
        week_end = min(week_start + timedelta(days=6),
                       (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1))
        
        tasks = await db.tasks.find({
            "userId": DEFAULT_USER_ID,
            "date": {
                "$gte": week_start.strftime("%Y-%m-%d"),
                "$lte": week_end.strftime("%Y-%m-%d")
            },
            "isCompleted": True
        }).to_list(100)
        
        week_completed = len(tasks)
        week_points = sum(task.get("points", 10) for task in tasks)
        
        weeks.append({
            "week": week_num,
            "completed": week_completed,
            "points": week_points
        })
        
        total_completed += week_completed
        total_points += week_points
        
        current_date = week_end + timedelta(days=1)
        week_num += 1
    
    co2_saved = round(total_completed * 0.5, 2)
    
    return {
        "weeks": weeks,
        "totalCompleted": total_completed,
        "totalPoints": total_points,
        "co2Saved": co2_saved
    }

@api_router.get("/stats/today")
async def get_today_stats():
    """Get today's statistics"""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    tasks = await db.tasks.find({
        "userId": DEFAULT_USER_ID,
        "date": today
    }).to_list(100)
    
    completed_tasks = [t for t in tasks if t.get("isCompleted", False)]
    total_points = sum(task.get("points", 10) for task in completed_tasks)
    
    # Get highlight task (first incomplete task or first task)
    incomplete_tasks = [t for t in tasks if not t.get("isCompleted", False)]
    highlight_task = incomplete_tasks[0] if incomplete_tasks else (tasks[0] if tasks else None)
    
    return {
        "date": today,
        "totalTasks": len(tasks),
        "completedTasks": len(completed_tasks),
        "totalPoints": total_points,
        "highlightTask": serialize_task(highlight_task) if highlight_task else None
    }

# ======================== PREFERENCES ROUTES ========================

@api_router.get("/preferences")
async def get_preferences():
    """Get user preferences"""
    prefs = await db.preferences.find_one({"userId": DEFAULT_USER_ID})
    
    if not prefs:
        # Create default preferences
        default_prefs = UserPreferences().model_dump()
        await db.preferences.insert_one(default_prefs)
        prefs = default_prefs
    
    # Remove MongoDB _id field before returning
    if "_id" in prefs:
        del prefs["_id"]
    return prefs

@api_router.put("/preferences")
async def update_preferences(prefs_update: UserPreferencesUpdate):
    """Update user preferences"""
    update_data = {k: v for k, v in prefs_update.dict().items() if v is not None}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No update data provided")
    
    result = await db.preferences.update_one(
        {"userId": DEFAULT_USER_ID},
        {"$set": update_data},
        upsert=True
    )
    
    prefs = await db.preferences.find_one({"userId": DEFAULT_USER_ID})
    prefs.pop("_id", None)
    return prefs

# ======================== LEARNING ROUTES ========================

@api_router.get("/learning")
async def get_learning_content():
    """Get all learning content"""
    content = await db.learning.find().to_list(100)
    
    # If no content exists, seed with default content
    if not content:
        await seed_learning_content()
        content = await db.learning.find().to_list(100)
    
    return [serialize_learning(c) for c in content]

@api_router.get("/learning/{content_id}")
async def get_learning_content_by_id(content_id: str):
    """Get specific learning content"""
    try:
        content = await db.learning.find_one({"_id": ObjectId(content_id)})
        if not content:
            raise HTTPException(status_code=404, detail="Content not found")
        return serialize_learning(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

async def seed_learning_content():
    """Seed database with initial learning content"""
    learning_items = [
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
    
    await db.learning.insert_many(learning_items)

# ======================== AI MOCK ROUTES ========================

# Task templates for mock AI
TASK_TEMPLATES = {
    "Energy": [
        {"title": "Turn off lights when leaving a room", "details": "Make it a habit to switch off all lights when you leave any room, even for a short time.", "estimatedImpact": "Saves ~0.4kg CO₂ per day"},
        {"title": "Unplug phone charger when not in use", "details": "Phone chargers consume energy even when not connected to your phone. Unplug them!", "estimatedImpact": "Saves ~0.1kg CO₂ per day"},
        {"title": "Use natural daylight for 2 hours", "details": "Open curtains and blinds to use natural light instead of electric lighting.", "estimatedImpact": "Saves ~0.3kg CO₂ per day"},
        {"title": "Set thermostat 1 degree lower", "details": "Reducing your heating by just 1 degree can save significant energy over time.", "estimatedImpact": "Saves ~1.0kg CO₂ per day"},
        {"title": "Air dry one load of laundry", "details": "Skip the dryer and hang your clothes to dry naturally.", "estimatedImpact": "Saves ~2.5kg CO₂ per load"},
    ],
    "Water": [
        {"title": "Take a 5-minute shower", "details": "Challenge yourself to shower in 5 minutes or less. Use a timer!", "estimatedImpact": "Saves ~40 liters of water"},
        {"title": "Turn off tap while brushing teeth", "details": "Don't let the water run while brushing. You can save up to 8 liters per minute!", "estimatedImpact": "Saves ~16 liters per brush"},
        {"title": "Fix a dripping faucet", "details": "Check all faucets in your home and fix any drips. A drip per second wastes 20 liters daily.", "estimatedImpact": "Saves ~20 liters per day"},
        {"title": "Collect rainwater for plants", "details": "Set up a container to collect rainwater for watering your indoor or outdoor plants.", "estimatedImpact": "Saves ~10 liters per use"},
        {"title": "Run dishwasher only when full", "details": "Wait until your dishwasher is completely full before running it.", "estimatedImpact": "Saves ~15 liters per load"},
    ],
    "Waste": [
        {"title": "Bring reusable bag to store", "details": "Remember to take your reusable shopping bag when going to the store today.", "estimatedImpact": "Saves 1 plastic bag (~0.05kg CO₂)"},
        {"title": "Use a reusable water bottle", "details": "Fill your reusable bottle instead of buying single-use plastic bottles.", "estimatedImpact": "Saves ~0.1kg plastic per bottle"},
        {"title": "Compost food scraps today", "details": "Collect fruit peels, vegetable scraps, and coffee grounds for composting.", "estimatedImpact": "Reduces ~0.5kg waste"},
        {"title": "Refuse a plastic straw", "details": "When ordering drinks, ask for no straw or bring your own reusable one.", "estimatedImpact": "Saves 1 plastic straw"},
        {"title": "Recycle paper and cardboard", "details": "Separate all paper and cardboard from your trash and recycle properly.", "estimatedImpact": "Saves ~0.9kg CO₂ per kg recycled"},
    ],
    "Transport": [
        {"title": "Walk instead of driving short distance", "details": "For trips under 1km, leave the car and walk. It's healthy and eco-friendly!", "estimatedImpact": "Saves ~0.2kg CO₂ per km"},
        {"title": "Use public transport today", "details": "Take the bus, metro, or tram instead of driving your car.", "estimatedImpact": "Saves ~2.0kg CO₂ per trip"},
        {"title": "Bike to work or school", "details": "If possible, use your bicycle for your commute today.", "estimatedImpact": "Saves ~3.0kg CO₂ per commute"},
        {"title": "Carpool with a colleague", "details": "Share your ride to work with a colleague who lives nearby.", "estimatedImpact": "Saves ~50% of trip emissions"},
        {"title": "Work from home if possible", "details": "Save a commute by working from home today if your job allows.", "estimatedImpact": "Saves entire commute emissions"},
    ]
}

WEEKLY_REPORT_TEMPLATES = [
    "Great job this week! You've made real progress in your eco-friendly journey. Keep up the momentum and remember, every small action counts toward a healthier planet.",
    "You're building fantastic environmental habits! This week's efforts have contributed to a cleaner future. Challenge yourself to do even more next week!",
    "Congratulations on another week of positive environmental impact! Your consistent efforts are making a difference. Stay motivated and keep inspiring others!",
    "Well done! Your dedication to sustainability is admirable. This week you've proven that individual actions can create collective change.",
    "Amazing progress! Every task you complete helps protect our planet. You're part of a global movement for positive change. Keep it going!"
]

@api_router.post("/ai/generate-tasks")
async def ai_generate_tasks(request: AIGenerateTasksRequest):
    """Mock AI: Generate personalized eco tasks based on interests"""
    interests = request.interests if request.interests else ["Energy", "Water", "Waste", "Transport"]
    
    generated_tasks = []
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    # Generate 3-5 tasks from selected interests
    num_tasks = random.randint(3, 5)
    
    for _ in range(num_tasks):
        category = random.choice(interests)
        if category in TASK_TEMPLATES:
            template = random.choice(TASK_TEMPLATES[category])
            task = {
                "title": template["title"],
                "details": template["details"],
                "category": category,
                "date": today,
                "points": random.choice([5, 10, 15, 20]),
                "estimatedImpact": template["estimatedImpact"]
            }
            # Avoid duplicates
            if task["title"] not in [t["title"] for t in generated_tasks]:
                generated_tasks.append(task)
    
    return {"tasks": generated_tasks}

@api_router.post("/ai/weekly-report")
async def ai_weekly_report(request: AIWeeklyReportRequest):
    """Mock AI: Generate weekly progress report"""
    total_tasks = request.energy + request.water + request.waste + request.transport
    
    # Select base template
    base_report = random.choice(WEEKLY_REPORT_TEMPLATES)
    
    # Add category-specific feedback
    category_feedback = []
    
    if request.energy > 0:
        category_feedback.append(f"Your {request.energy} energy-saving tasks helped reduce electricity consumption.")
    if request.water > 0:
        category_feedback.append(f"You completed {request.water} water conservation tasks - precious resources preserved!")
    if request.waste > 0:
        category_feedback.append(f"With {request.waste} waste reduction tasks, you've minimized your environmental footprint.")
    if request.transport > 0:
        category_feedback.append(f"Your {request.transport} sustainable transport choices reduced carbon emissions.")
    
    if not category_feedback:
        category_feedback.append("Start completing tasks to see your personalized impact report!")
    
    full_report = f"{base_report}\n\n" + "\n".join(category_feedback)
    
    # Add encouragement
    if total_tasks >= 10:
        full_report += "\n\n🌟 You're an Eco Champion this week!"
    elif total_tasks >= 5:
        full_report += "\n\n🌱 You're growing your green habits nicely!"
    else:
        full_report += "\n\n💪 Every small step matters. Try to add more tasks next week!"
    
    return {"report": full_report, "totalTasks": total_tasks}

@api_router.post("/ai/summarize")
async def ai_summarize(request: AISummarizeRequest):
    """Mock AI: Summarize learning content into bullet points"""
    text = request.text
    
    # Simple mock summarization - extract key sentences
    sentences = [s.strip() for s in text.replace('\n', ' ').split('.') if len(s.strip()) > 20]
    
    # Select 3 key points
    if len(sentences) >= 3:
        # Pick sentences from beginning, middle, and end
        summaries = [
            sentences[0],
            sentences[len(sentences)//2],
            sentences[-2] if len(sentences) > 2 else sentences[-1]
        ]
    else:
        summaries = sentences[:3] if sentences else ["No content to summarize."]
    
    # Format as bullet points
    bullet_summary = "\n".join([f"• {s.strip()}" for s in summaries if s.strip()])
    
    return {"summary": bullet_summary}

# ======================== ROOT & HEALTH ========================

@api_router.get("/")
async def root():
    return {"message": "GreenHabit API is running", "version": "1.0.0"}

@api_router.get("/health")
async def health_check():
    return {"status": "healthy", "database": "connected"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

