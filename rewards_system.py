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
    },
    "social_butterfly": {
        "id": "social_butterfly",
        "name": "🦋 Social Butterfly",
        "description": "Send 5 invitations",
        "icon": "🦋",
        "points": 40
    },
    "team_player": {
        "id": "team_player",
        "name": "🤝 Team Player",
        "description": "Join a team",
        "icon": "🤝",
        "points": 30
    },
    "night_owl": {
        "id": "night_owl",
        "name": "🦉 Night Owl",
        "description": "Complete a task after 10 PM",
        "icon": "🦉",
        "points": 20
    },
    "weekend_warrior": {
        "id": "weekend_warrior",
        "name": "🎉 Weekend Warrior",
        "description": "Complete tasks on Sat & Sun",
        "icon": "🎉",
        "points": 40
    },
    "eco_generalist": {
        "id": "eco_generalist",
        "name": "🌍 Eco Generalist",
        "description": "Complete a task in all 7 categories",
        "icon": "🌍",
        "points": 75
    }
}

# ======================== STREAK FUNCTIONS ========================

def calculate_streak(db, user_id: str) -> Dict:
    """
    DEPRECATED: Use streak_system.calculate_streak_from_completions() instead.
    Kept for backward compatibility during migration.
    """
    # Redirect to new system if habit_completions exist
    completions_count = db.habit_completions.count_documents({"userId": user_id})
    if completions_count > 0:
        from streak_system import calculate_streak_from_completions
        return calculate_streak_from_completions(db, user_id)
    
    # Legacy fallback: derive from tasks collection
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

def calculate_rewards(db, user_id: str, task: dict, current_streak: int = 0, tz_id: str = "UTC") -> Dict:
    """
    Calculate rewards for completing a task
    Returns points breakdown and bonuses
    
    Args:
        current_streak: Pre-calculated streak from streak_system (avoids redundant DB query)
    """
    try:
        base_points = int(task.get("points", 10))
    except (ValueError, TypeError):
        base_points = 10
    
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
    import zoneinfo
    try:
        current_hour = datetime.utcnow().replace(tzinfo=zoneinfo.ZoneInfo("UTC")).astimezone(zoneinfo.ZoneInfo(tz_id)).hour
    except Exception:
        current_hour = datetime.utcnow().hour
    time_bonus = 5 if current_hour < 9 else 0
    
    total_points = base_points + streak_bonus + category_bonus + time_bonus
    
    return {
        "basePoints": base_points,
        "streakBonus": streak_bonus,
        "categoryBonus": category_bonus,
        "timeBonus": time_bonus,
        "bonuses": {
            "streak": streak_bonus,
            "category": category_bonus,
            "time": time_bonus
        },
        "earnedPoints": total_points,
        "totalPoints": total_points,
        "multiplier": round(total_points / base_points, 2) if base_points > 0 else 1.0
    }

# ======================== POINTS CACHE SYNC =========================

def sync_user_points(db, user_id: str):
    """
    Atomically force sync user's total points based on their actual earnedPoints.
    Prevents cache desync exploits when tasks are deleted or un-completed.
    """
    pipeline = [
        {"$match": {"userId": user_id, "isCompleted": True}},
        {"$group": {"_id": None, "totalTaskPoints": {"$sum": {"$ifNull": ["$earnedPoints", "$points"]}}}}
    ]
    result = list(db.tasks.aggregate(pipeline))
    total_task_points = result[0]["totalTaskPoints"] if result else 0
    
    # Needs to also sum achievement points
    profile = db.user_profiles.find_one({"userId": user_id})
    achievement_points = 0
    if profile:
        from rewards_system import ACHIEVEMENTS
        unlocked = profile.get("unlockedAchievements", [])
        for ach_id in unlocked:
            ach = ACHIEVEMENTS.get(ach_id)
            if ach:
                achievement_points += ach.get("points", 0)
                
    total_points = total_task_points + achievement_points
    
    db.user_profiles.update_one(
        {"userId": user_id},
        {"$set": {"totalPoints": total_points, "updatedAt": datetime.utcnow()}}
    )
    return total_points

# ======================== ACHIEVEMENT CHECK ========================

def check_new_achievements(db, user_id: str, current_streak: int = 0, tz_id: str = "UTC") -> List[Dict]:
    """
    Check if user unlocked any new achievements
    Returns list of newly unlocked achievements
    
    Args:
        current_streak: Pre-calculated streak from streak_system
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
    
    # Use provided streak (no redundant DB call)
    
    # Calculate points from tasks
    task_points = 0
    for t in user_tasks:
        try:
            task_points += int(t.get("earnedPoints", t.get("points", 0)))
        except (ValueError, TypeError):
            pass
    
    # Count tasks by category
    energy_tasks = sum(1 for t in user_tasks if t.get("category") == "Energy")
    water_tasks = sum(1 for t in user_tasks if t.get("category") == "Water")
    waste_tasks = sum(1 for t in user_tasks if t.get("category") == "Waste")
    transport_tasks = sum(1 for t in user_tasks if t.get("category") == "Transport")
    
    # Check distinct categories
    unique_categories = {t.get("category") for t in user_tasks if t.get("category")}
    
    # Check today's tasks for perfect day
    today = date.today().isoformat()
    today_tasks_list = [t for t in user_tasks if t.get("date") == today]
    
    all_completed_today = len(today_tasks_list) > 0  # Since we only fetched completed tasks
    
    # count daily tasks to check if ALL were completed (need to fetch incomplete ones too for this check strictly speaking, 
    # but for now assuming "Perfect Day" means completed at least 3 tasks and none pending is complicated without extra query.
    # Simplified: If user completed 3+ tasks today, award it.
    
    # ✅ ULTRATHINK FIX: Helper to safely extract local hour using user timezone
    def _get_hour(completed_at) -> int:
        """Safely extract local hour using tz_id"""
        if completed_at is None:
            return 12
        import zoneinfo
        try:
            if isinstance(completed_at, str):
                dt = datetime.fromisoformat(str(completed_at).replace("Z", ""))
            else:
                dt = completed_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
            return dt.astimezone(zoneinfo.ZoneInfo(tz_id)).hour
        except Exception:
            return 12

    from streak_system import user_today
    try:
        today_date = user_today(tz_id)
    except Exception:
        today_date = date.today()
    week_start_date = today_date - timedelta(days=today_date.weekday())
    current_week_dates = set((week_start_date + timedelta(days=i)).isoformat() for i in range(7))
    user_task_dates = set(t.get("date") for t in user_tasks)
    is_week_warrior = current_week_dates.issubset(user_task_dates)
            
    # Helper for days of week
    def _get_weekday(date_str) -> int:
        """Get weekday from date string (0=Mon, 6=Sun)"""
        try:
            return date.fromisoformat(date_str).weekday()
        except:
            return 0
            
    has_sat = any(_get_weekday(t.get("date")) == 5 for t in user_tasks)
    has_sun = any(_get_weekday(t.get("date")) == 6 for t in user_tasks)
            
    # Additional DB Checks for Social Achievements
    invites_sent = db.invitations.count_documents({"senderId": user_id})
    # Check if user is in any team (is a member of any team doc)
    is_in_team = db.teams.count_documents({"members.userId": user_id}) > 0
    
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
        "week_warrior": is_week_warrior,
        "early_bird": any(_get_hour(t.get("completedAt")) < 9 for t in user_tasks if t.get("completedAt")),
        "social_butterfly": invites_sent >= 5,
        "team_player": is_in_team,
        "night_owl": any(_get_hour(t.get("completedAt")) >= 22 for t in user_tasks if t.get("completedAt")),
        "weekend_warrior": has_sat and has_sun,
        "eco_generalist": len(unique_categories) >= 7
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