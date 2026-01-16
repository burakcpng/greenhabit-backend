"""
Social System for GreenHabit
Handles follows, rankings, and social profiles
"""

from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
from bson import ObjectId

# ======================== HELPER: Calculate Eco Score ========================

def calculate_eco_score(db, user_id: str) -> int:
    """
    Calculate user's eco score based on:
    - Total points from completed tasks
    - Achievement points
    - Streak bonuses
    """
    # Get total points from completed tasks
    pipeline = [
        {"$match": {"userId": user_id, "isCompleted": True}},
        {"$group": {"_id": None, "totalPoints": {"$sum": "$points"}}}
    ]
    
    result = list(db.tasks.aggregate(pipeline))
    task_points = result[0]["totalPoints"] if result else 0
    
    # Get achievement points from profile
    profile = db.user_profiles.find_one({"userId": user_id})
    achievement_points = profile.get("totalPoints", 0) if profile else 0
    
    return task_points + achievement_points


def calculate_total_co2_saved(db, user_id: str) -> float:
    """Calculate total CO2 saved (0.3kg per completed task)"""
    count = db.tasks.count_documents({"userId": user_id, "isCompleted": True})
    return round(count * 0.3, 2)


# ======================== USER PROFILE EXTENSION ========================

def get_social_profile(db, user_id: str, viewer_id: Optional[str] = None) -> Dict:
    """
    Get extended social profile for a user
    If viewer_id is provided, include isFollowing status
    """
    from rewards_system import calculate_streak, get_user_profile, ACHIEVEMENTS
    
    # Get base profile
    profile = db.user_profiles.find_one({"userId": user_id})
    
    if not profile:
        # Create profile if doesn't exist
        profile = get_user_profile(db, user_id)
    
    # Get streak info
    streak_info = calculate_streak(db, user_id)
    
    # Count completed tasks
    total_tasks = db.tasks.count_documents({"userId": user_id, "isCompleted": True})
    
    # Calculate eco score
    eco_score = calculate_eco_score(db, user_id)
    
    # Calculate CO2 saved
    co2_saved = calculate_total_co2_saved(db, user_id)
    
    # Get follower/following counts
    follower_count = db.follows.count_documents({"followedId": user_id})
    following_count = db.follows.count_documents({"followerId": user_id})
    
    # Get unlocked achievements with details
    unlocked_ids = set(profile.get("unlockedAchievements", []))
    achievements = []
    for ach_id, ach in ACHIEVEMENTS.items():
        achievements.append({
            **ach,
            "unlocked": ach_id in unlocked_ids
        })
    
    # Calculate level (100 points per level)
    level = max(1, eco_score // 100 + 1)
    
    # Get user preferences for country
    prefs = db.preferences.find_one({"userId": user_id})
    country = prefs.get("country") if prefs else None
    
    # Check if viewing user is following this user
    is_following = None
    if viewer_id and viewer_id != user_id:
        is_following = db.follows.count_documents({
            "followerId": viewer_id,
            "followedId": user_id
        }) > 0
    
    # Check privacy settings
    privacy = db.user_privacy.find_one({"userId": user_id}) or {
        "profilePublic": True,
        "showAchievements": True,
        "showStats": True,
        "showFollowers": True,
        "appearInLeaderboard": True
    }
    
    # Get weekly stats if permitted
    weekly_stats = None
    if privacy.get("showStats", True) or viewer_id == user_id:
        weekly_stats = get_user_weekly_stats(db, user_id)
    
    return {
        "userId": user_id,
        "displayName": profile.get("displayName"),
        "bio": profile.get("bio"),
        "country": country,
        "level": level,
        "totalPoints": eco_score,
        "tasksCompleted": total_tasks,
        "currentStreak": streak_info["currentStreak"],
        "longestStreak": streak_info["longestStreak"],
        "rank": None,  # Will be filled by ranking endpoint
        "co2Saved": co2_saved,
        "achievements": achievements if (privacy.get("showAchievements", True) or viewer_id == user_id) else [],
        "weeklyStats": weekly_stats,
        "followerCount": follower_count,
        "followingCount": following_count,
        "isFollowing": is_following,
        "isPrivate": not privacy.get("profilePublic", True),
        "joinedAt": profile.get("createdAt").isoformat() if profile.get("createdAt") else None
    }


def get_user_weekly_stats(db, user_id: str) -> Dict:
    """Get weekly stats for a user (simplified for profile)"""
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


def update_user_profile(db, user_id: str, display_name: Optional[str], bio: Optional[str]) -> Dict:
    """Update user's display name and bio"""
    update_data = {"updatedAt": datetime.utcnow()}
    
    if display_name is not None:
        update_data["displayName"] = display_name
    if bio is not None:
        update_data["bio"] = bio
    
    db.user_profiles.update_one(
        {"userId": user_id},
        {"$set": update_data},
        upsert=True
    )
    
    return get_social_profile(db, user_id)


# ======================== RANKING SYSTEM ========================

def get_global_ranking(db, limit: int = 50) -> Dict:
    """
    Get global leaderboard sorted by eco score
    Returns top N users with rank, points, etc.
    """
    # Get all users with their eco scores
    pipeline = [
        {"$match": {"isCompleted": True}},
        {"$group": {
            "_id": "$userId",
            "taskPoints": {"$sum": "$points"},
            "tasksCompleted": {"$count": {}}
        }}
    ]
    
    task_stats = {doc["_id"]: doc for doc in db.tasks.aggregate(pipeline)}
    
    # Get all user profiles and combine with task stats
    profiles = list(db.user_profiles.find({}))
    
    rankings = []
    for profile in profiles:
        user_id = profile.get("userId")
        if not user_id:
            continue
        
        # Check if user wants to appear in leaderboard
        privacy = db.user_privacy.find_one({"userId": user_id}) or {}
        if not privacy.get("appearInLeaderboard", True):
            continue
        
        task_stat = task_stats.get(user_id, {"taskPoints": 0, "tasksCompleted": 0})
        achievement_points = profile.get("totalPoints", 0)
        eco_score = task_stat["taskPoints"] + achievement_points
        
        from rewards_system import calculate_streak
        streak_info = calculate_streak(db, user_id)
        
        level = max(1, eco_score // 100 + 1)
        
        rankings.append({
            "userId": user_id,
            "displayName": profile.get("displayName"),
            "points": eco_score,
            "tasksCompleted": task_stat["tasksCompleted"],
            "streak": streak_info["currentStreak"],
            "level": level
        })
    
    # Sort by points descending
    rankings.sort(key=lambda x: x["points"], reverse=True)
    
    # Assign ranks
    for i, entry in enumerate(rankings):
        entry["rank"] = i + 1
    
    total_users = len(rankings)
    
    return {
        "rankings": rankings[:limit],
        "totalUsers": total_users,
        "lastUpdated": datetime.utcnow().isoformat()
    }


def get_user_rank(db, user_id: str) -> Dict:
    """
    Get user's rank and nearby users
    """
    # Get full ranking
    full_ranking = get_global_ranking(db, limit=10000)
    rankings = full_ranking["rankings"]
    total_users = full_ranking["totalUsers"]
    
    # Find user's position
    user_rank = None
    user_index = None
    user_points = 0
    
    for i, entry in enumerate(rankings):
        if entry["userId"] == user_id:
            user_rank = entry["rank"]
            user_index = i
            user_points = entry["points"]
            break
    
    if user_rank is None:
        # User not in ranking, calculate their score
        eco_score = calculate_eco_score(db, user_id)
        
        # Find their approximate rank
        user_rank = sum(1 for r in rankings if r["points"] > eco_score) + 1
        user_points = eco_score
        
        # If not in rankings, they're at the end
        if user_index is None:
            user_index = len(rankings)
    
    # Calculate percentile
    percentile = ((total_users - user_rank + 1) / max(total_users, 1)) * 100
    
    # Get nearby users (5 above and 5 below)
    start = max(0, user_index - 5)
    end = min(len(rankings), user_index + 6)
    nearby_users = rankings[start:end]
    
    return {
        "rank": user_rank,
        "totalUsers": max(total_users, 1),
        "percentile": round(percentile, 1),
        "points": user_points,
        "nearbyUsers": nearby_users
    }


# ======================== FOLLOW SYSTEM ========================

def follow_user(db, follower_id: str, followed_id: str) -> Dict:
    """
    Follow a user
    Returns success status and updated counts
    """
    if follower_id == followed_id:
        return {
            "success": False,
            "message": "Cannot follow yourself"
        }
    
    # Check if already following
    existing = db.follows.find_one({
        "followerId": follower_id,
        "followedId": followed_id
    })
    
    if existing:
        return {
            "success": False,
            "message": "Already following this user"
        }
    
    # Create follow relationship
    db.follows.insert_one({
        "followerId": follower_id,
        "followedId": followed_id,
        "createdAt": datetime.utcnow()
    })
    
    # Get updated counts
    follower_count = db.follows.count_documents({"followedId": followed_id})
    following_count = db.follows.count_documents({"followerId": follower_id})
    
    return {
        "success": True,
        "message": "Successfully followed user",
        "followerCount": follower_count,
        "followingCount": following_count
    }


def unfollow_user(db, follower_id: str, followed_id: str) -> Dict:
    """
    Unfollow a user
    Returns success status and updated counts
    """
    result = db.follows.delete_one({
        "followerId": follower_id,
        "followedId": followed_id
    })
    
    if result.deleted_count == 0:
        return {
            "success": False,
            "message": "Not following this user"
        }
    
    # Get updated counts
    follower_count = db.follows.count_documents({"followedId": followed_id})
    following_count = db.follows.count_documents({"followerId": follower_id})
    
    return {
        "success": True,
        "message": "Successfully unfollowed user",
        "followerCount": follower_count,
        "followingCount": following_count
    }


def get_followers(db, user_id: str, page: int = 1, limit: int = 20) -> Dict:
    """
    Get list of users following this user
    """
    skip = (page - 1) * limit
    
    # Get follower relationships
    follows = list(db.follows.find(
        {"followedId": user_id}
    ).sort("createdAt", -1).skip(skip).limit(limit + 1))
    
    has_more = len(follows) > limit
    follows = follows[:limit]
    
    users = []
    for follow in follows:
        follower_id = follow["followerId"]
        profile = db.user_profiles.find_one({"userId": follower_id}) or {}
        
        from rewards_system import calculate_streak
        streak_info = calculate_streak(db, follower_id)
        eco_score = calculate_eco_score(db, follower_id)
        level = max(1, eco_score // 100 + 1)
        
        users.append({
            "userId": follower_id,
            "displayName": profile.get("displayName"),
            "level": level,
            "streak": streak_info["currentStreak"],
            "points": eco_score,
            "followedAt": follow.get("createdAt").isoformat() if follow.get("createdAt") else None
        })
    
    total = db.follows.count_documents({"followedId": user_id})
    
    return {
        "users": users,
        "total": total,
        "hasMore": has_more
    }


def get_following(db, user_id: str, page: int = 1, limit: int = 20) -> Dict:
    """
    Get list of users this user is following
    """
    skip = (page - 1) * limit
    
    # Get following relationships
    follows = list(db.follows.find(
        {"followerId": user_id}
    ).sort("createdAt", -1).skip(skip).limit(limit + 1))
    
    has_more = len(follows) > limit
    follows = follows[:limit]
    
    users = []
    for follow in follows:
        followed_id = follow["followedId"]
        profile = db.user_profiles.find_one({"userId": followed_id}) or {}
        
        from rewards_system import calculate_streak
        streak_info = calculate_streak(db, followed_id)
        eco_score = calculate_eco_score(db, followed_id)
        level = max(1, eco_score // 100 + 1)
        
        users.append({
            "userId": followed_id,
            "displayName": profile.get("displayName"),
            "level": level,
            "streak": streak_info["currentStreak"],
            "points": eco_score,
            "followedAt": follow.get("createdAt").isoformat() if follow.get("createdAt") else None
        })
    
    total = db.follows.count_documents({"followerId": user_id})
    
    return {
        "users": users,
        "total": total,
        "hasMore": has_more
    }


# ======================== PRIVACY SETTINGS ========================

def get_privacy_settings(db, user_id: str) -> Dict:
    """Get user's privacy settings"""
    settings = db.user_privacy.find_one({"userId": user_id})
    
    if not settings:
        settings = {
            "userId": user_id,
            "profilePublic": True,
            "showAchievements": True,
            "showStats": True,
            "showFollowers": True,
            "appearInLeaderboard": True
        }
        db.user_privacy.insert_one(settings)
    
    # Remove MongoDB _id
    if "_id" in settings:
        del settings["_id"]
    
    return settings


def update_privacy_settings(db, user_id: str, settings: Dict) -> Dict:
    """Update user's privacy settings"""
    allowed_fields = ["profilePublic", "showAchievements", "showStats", "showFollowers", "appearInLeaderboard"]
    update_data = {k: v for k, v in settings.items() if k in allowed_fields}
    update_data["updatedAt"] = datetime.utcnow()
    
    db.user_privacy.update_one(
        {"userId": user_id},
        {"$set": update_data},
        upsert=True
    )
    
    return get_privacy_settings(db, user_id)


# ======================== INDEX CREATION ========================

def ensure_social_indexes(db):
    """Create necessary indexes for social features"""
    # Follows indexes
    db.follows.create_index([("followerId", 1), ("followedId", 1)], unique=True)
    db.follows.create_index([("followedId", 1)])
    db.follows.create_index([("followerId", 1)])
    
    # User privacy index
    db.user_privacy.create_index([("userId", 1)], unique=True)
    
    # User profiles index for ranking
    db.user_profiles.create_index([("totalPoints", -1)])
    
    print("✅ Social indexes created")
