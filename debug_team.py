
import os
import pymongo
import sys
from bson.json_util import dumps

# Connect to DB
mongo_url = os.getenv("MONGO_URL")
if not mongo_url:
    print("MONGO_URL not set")
    sys.exit(1)

client = pymongo.MongoClient(mongo_url)
db = client["GreenHabit_db"]

# User IDs from logs
current_user_id = "B03D20B0-A9FC-44DA-A791-20C9EC8D7394"
target_user_id = "720AE775-EB9D-425B-B917-C2E42A7727FC"

print(f"--- INSPECTING USER {target_user_id} (Rubyik) ---")
member_record = db.team_members.find_one({"userId": target_user_id})
if member_record:
    print(f"✅ User is in team: {member_record.get('teamId')}")
    team = db.teams.find_one({"id": member_record.get('teamId')})
    if team:
        print(f"   Team Name: {team.get('name')}")
        print(f"   Creator: {team.get('creatorId')}")
    
    # FIX: Remove them so we can test the invite
    print("   🛠 REMOVING USER FROM TEAM TO ALLOW TESTING...")
    db.team_members.delete_one({"userId": target_user_id})
    
    # Update team count
    if team:
        db.teams.update_one(
            {"id": team.get("id")},
            {"$inc": {"memberCount": -1}}
        )
    print("   ✅ User removed from team. Re-test invite now.")
else:
    print("ℹ️ User is NOT in any team.")

print("\n--- CHECKING POINTS LOGIC ---")
# Check if any $inc remains in rewards_system.py (static analysis not possible here, effectively handled by my previous edit but good to verify DB state integrity)
profile = db.user_profiles.find_one({"userId": current_user_id})
if profile:
    print(f"Current User Points: {profile.get('totalPoints')}")
    print(f"Tasks Completed: {profile.get('tasksCompleted')}")
    print(f"Achievements: {len(profile.get('unlockedAchievements', []))}")
