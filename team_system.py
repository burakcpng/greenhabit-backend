# Team System
# Backend logic for team creation, invitations, task sharing, and stats
# Each user can only belong to ONE team at a time

from datetime import datetime
from typing import Dict, List, Optional
from bson import ObjectId
import uuid


# ======================== TEAM CRUD ========================

def create_team(db, creator_id: str, team_name: str, invited_user_ids: List[str] = None) -> Dict:
    """Create a new team. Creator becomes the team owner."""
    
    # Check if user already in a team
    existing = db.team_members.find_one({"userId": creator_id})
    if existing:
        return {"success": False, "message": "You are already in a team"}
    
    # Validate team name
    if not team_name or len(team_name.strip()) < 2:
        return {"success": False, "message": "Team name must be at least 2 characters"}
    
    if len(team_name) > 50:
        return {"success": False, "message": "Team name cannot exceed 50 characters"}
    
    # Get creator profile
    creator_profile = db.user_profiles.find_one({"userId": creator_id})
    creator_name = creator_profile.get("displayName", "GreenHabit User") if creator_profile else "GreenHabit User"
    
    # Create team
    team_id = str(uuid.uuid4())
    team_doc = {
        "id": team_id,
        "name": team_name.strip(),
        "creatorId": creator_id,
        "creatorName": creator_name,
        "memberCount": 1,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow()
    }
    
    db.teams.insert_one(team_doc)
    
    # Add creator as team member
    member_doc = {
        "teamId": team_id,
        "userId": creator_id,
        "role": "creator",
        "joinedAt": datetime.utcnow()
    }
    db.team_members.insert_one(member_doc)
    
    # Send invitations to selected friends
    invitations_sent = 0
    if invited_user_ids:
        for user_id in invited_user_ids:
            if user_id != creator_id:
                result = invite_to_team(db, team_id, creator_id, user_id)
                if result["success"]:
                    invitations_sent += 1
    
    return {
        "success": True,
        "message": "Team created successfully",
        "teamId": team_id,
        "invitationsSent": invitations_sent
    }


def get_team(db, team_id: str) -> Optional[Dict]:
    """Get team by ID"""
    team = db.teams.find_one({"id": team_id})
    if team:
        team = sanitize_team_doc(team)
    return team


def get_my_team(db, user_id: str) -> Optional[Dict]:
    """Get user's current team"""
    membership = db.team_members.find_one({"userId": user_id})
    if not membership:
        return None
    
    team = db.teams.find_one({"id": membership["teamId"]})
    if not team:
        return None
    
    team = sanitize_team_doc(team)
    team["myRole"] = membership["role"]
    
    return team


def delete_team(db, team_id: str, user_id: str) -> Dict:
    """Delete team (creator only)"""
    team = db.teams.find_one({"id": team_id})
    if not team:
        return {"success": False, "message": "Team not found"}
    
    if team["creatorId"] != user_id:
        return {"success": False, "message": "Only the team creator can delete the team"}
    
    # Remove all members
    db.team_members.delete_many({"teamId": team_id})
    
    # Remove all pending invitations
    db.team_invitations.delete_many({"teamId": team_id})
    
    # Remove all pending team tasks
    db.team_task_shares.delete_many({"teamId": team_id})
    
    # Delete team
    db.teams.delete_one({"id": team_id})
    
    return {"success": True, "message": "Team deleted successfully"}


def leave_team(db, team_id: str, user_id: str) -> Dict:
    """Leave a team (members only, not creator)"""
    team = db.teams.find_one({"id": team_id})
    if not team:
        return {"success": False, "message": "Team not found"}
    
    if team["creatorId"] == user_id:
        return {"success": False, "message": "Creator cannot leave the team. Delete it instead."}
    
    membership = db.team_members.find_one({"teamId": team_id, "userId": user_id})
    if not membership:
        return {"success": False, "message": "You are not a member of this team"}
    
    # Remove member
    db.team_members.delete_one({"teamId": team_id, "userId": user_id})
    
    # Update member count
    db.teams.update_one(
        {"id": team_id},
        {
            "$inc": {"memberCount": -1},
            "$set": {"updatedAt": datetime.utcnow()}
        }
    )
    
    return {"success": True, "message": "You have left the team"}


# ======================== TEAM MEMBERS ========================

def get_team_members(db, team_id: str) -> List[Dict]:
    """Get all members of a team"""
    members_cursor = db.team_members.find({"teamId": team_id}).sort("joinedAt", 1)
    
    members = []
    for m in members_cursor:
        user_profile = db.user_profiles.find_one({"userId": m["userId"]})
        
        # Get user stats
        from rewards_system import get_user_profile
        user_stats = get_user_profile(db, m["userId"])
        
        member = {
            "userId": m["userId"],
            "displayName": user_profile.get("displayName", "GreenHabit User") if user_profile else "GreenHabit User",
            "role": m["role"],
            "joinedAt": m["joinedAt"].isoformat() + "Z" if m.get("joinedAt") else None,
            "totalPoints": user_stats.get("totalPoints", 0),
            "tasksCompleted": user_stats.get("tasksCompleted", 0),
            "level": user_stats.get("level", 1)  # ✅ ADDED: Level needed for UI
        }
        members.append(member)
    
    return members


def remove_member(db, team_id: str, creator_id: str, target_user_id: str) -> Dict:
    """Remove a member from team (creator only)"""
    team = db.teams.find_one({"id": team_id})
    if not team:
        return {"success": False, "message": "Team not found"}
    
    if team["creatorId"] != creator_id:
        return {"success": False, "message": "Only the team creator can remove members"}
    
    if target_user_id == creator_id:
        return {"success": False, "message": "Cannot remove yourself. Delete the team instead."}
    
    membership = db.team_members.find_one({"teamId": team_id, "userId": target_user_id})
    if not membership:
        return {"success": False, "message": "User is not a member of this team"}
    
    # Remove member
    db.team_members.delete_one({"teamId": team_id, "userId": target_user_id})
    
    # Update member count
    db.teams.update_one(
        {"id": team_id},
        {
            "$inc": {"memberCount": -1},
            "$set": {"updatedAt": datetime.utcnow()}
        }
    )
    
    return {"success": True, "message": "Member removed from team"}


def update_member_permissions(db, team_id: str, creator_id: str, target_user_id: str, can_share_tasks: bool) -> Dict:
    """Update member's permissions (creator only)"""
    team = db.teams.find_one({"id": team_id})
    if not team:
        return {"success": False, "message": "Team not found"}
    
    if team["creatorId"] != creator_id:
        return {"success": False, "message": "Only the team creator can update permissions"}
    
    if target_user_id == creator_id:
        return {"success": False, "message": "Cannot modify creator permissions"}
    
    membership = db.team_members.find_one({"teamId": team_id, "userId": target_user_id})
    if not membership:
        return {"success": False, "message": "User is not a member of this team"}
    
    # Update member's canShareTasks permission
    result = db.team_members.update_one(
        {"teamId": team_id, "userId": target_user_id},
        {"$set": {"canShareTasks": can_share_tasks, "updatedAt": datetime.utcnow()}}
    )
    
    if result.modified_count > 0:
        return {"success": True, "message": "Permissions updated"}
    return {"success": True, "message": "No changes made"}


# ======================== TEAM INVITATIONS ========================

def invite_to_team(db, team_id: str, inviter_id: str, invitee_id: str) -> Dict:
    """Send team invitation"""
    invitee_id = invitee_id.strip()  # ✅ FIX: Sanitize input
    team = db.teams.find_one({"id": team_id})
    if not team:
        return {"success": False, "message": "Team not found"}
    
    if team["creatorId"] != inviter_id:
        return {"success": False, "message": "Only the team creator can invite members"}
    
    # ✅ SECURITY: Daily invitation limit (10/day) to prevent spam
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    daily_invites = db.team_invitations.count_documents({
        "inviterId": inviter_id,
        "createdAt": {"$gte": today_start}
    })
    
    if daily_invites >= 10:
        return {
            "success": False, 
            "message": "Daily invitation limit reached (10 per day). Please try again tomorrow."
        }
    
    # Check if invitee already in a team
    existing = db.team_members.find_one({"userId": invitee_id})
    if existing:
        return {"success": False, "message": "User is already in a team"}
    
    # Check for pending invitation
    pending = db.team_invitations.find_one({
        "teamId": team_id,
        "inviteeId": invitee_id,
        "status": "pending"
    })
    if pending:
        return {"success": False, "message": "Invitation already pending"}
    
    # Get inviter name
    inviter_profile = db.user_profiles.find_one({"userId": inviter_id})
    inviter_name = inviter_profile.get("displayName", "GreenHabit User") if inviter_profile else "GreenHabit User"
    
    # Validate invitee exists
    invitee_profile = db.user_profiles.find_one({"userId": invitee_id})
    if not invitee_profile:
        return {"success": False, "message": "User not found to invite"}
    
    invitation_id = str(uuid.uuid4())
    invitation_doc = {
        "id": invitation_id,
        "teamId": team_id,
        "teamName": team["name"],
        "inviterId": inviter_id,
        "inviterName": inviter_name,
        "inviteeId": invitee_id,
        "status": "pending",
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow()
    }
    
    db.team_invitations.insert_one(invitation_doc)
    
    return {
        "success": True,
        "message": "Invitation sent",
        "invitationId": invitation_id
    }


def get_pending_invitations(db, user_id: str) -> List[Dict]:
    """Get pending team invitations for a user"""
    print(f"🔍 DEBUG: Fetching invitations for user_id='{user_id}' (len={len(user_id)})")
    
    # DUMP ALL PENDING INVITATIONS FOR DEBUGGING
    all_pending = list(db.team_invitations.find({"status": "pending"}))
    print(f"📊 DEBUG: Total pending invitations in DB: {len(all_pending)}")
    for p in all_pending:
        p_invitee = p.get('inviteeId', 'UNKNOWN')
        print(f"   - Invitee: '{p_invitee}' (len={len(p_invitee)}) | Team: {p.get('teamName')}")
        if p_invitee == user_id:
            print("     MATCH FOUND! ✅")
        else:
            print("     NO MATCH ❌")


    invitations = list(db.team_invitations.find({
        "inviteeId": user_id,
        "status": "pending"
    }).sort("createdAt", -1))
    
    result = []
    for inv in invitations:
        # ✅ FIX: Fetch latest inviter profile
        inviter_profile = db.user_profiles.find_one({"userId": inv["inviterId"]})
        inviter_name = inviter_profile.get("displayName", "GreenHabit User") if inviter_profile else "GreenHabit User"
        
        result.append({
            "id": inv["id"],
            "teamId": inv["teamId"],
            "teamName": inv["teamName"],
            "inviterId": inv["inviterId"],
            "inviteeId": inv["inviteeId"], # ✅ FIX: Required by Swift
            "inviterName": inviter_name, # ✅ Use live data
            "status": inv["status"],
            "createdAt": inv["createdAt"].isoformat() + "Z" if inv.get("createdAt") else None
        })
    
    return result


def get_sent_invitations(db, user_id: str) -> List[Dict]:
    """Get team invitations sent by this user (outgoing)"""
    invitations = list(db.team_invitations.find({
        "inviterId": user_id
    }).sort("createdAt", -1))
    
    result = []
    for inv in invitations:
        # ✅ FIX: Fetch latest invitee profile to avoid "Unknown User"
        invitee_profile = db.user_profiles.find_one({"userId": inv["inviteeId"]})
        invitee_name = invitee_profile.get("displayName") if invitee_profile else None
        
        result.append({
            "id": inv["id"],
            "teamId": inv["teamId"],
            "teamName": inv["teamName"],
            "inviteeId": inv["inviteeId"],
            "inviteeName": invitee_name or "Unknown User", # ✅ Display live name
            "status": inv["status"],
            "createdAt": inv["createdAt"].isoformat() + "Z" if inv.get("createdAt") else None
        })
    
    return result


def accept_invitation(db, invitation_id: str, user_id: str) -> Dict:
    """Accept team invitation"""
    invitation = db.team_invitations.find_one({"id": invitation_id})
    if not invitation:
        return {"success": False, "message": "Invitation not found"}
    
    if invitation["inviteeId"] != user_id:
        return {"success": False, "message": "Not authorized"}
    
    if invitation["status"] != "pending":
        return {"success": False, "message": f"Invitation already {invitation['status']}"}
    
    # Check if user already in a team
    existing = db.team_members.find_one({"userId": user_id})
    if existing:
        return {"success": False, "message": "You are already in a team"}
    
    # Check if team still exists
    team = db.teams.find_one({"id": invitation["teamId"]})
    if not team:
        db.team_invitations.update_one(
            {"id": invitation_id},
            {"$set": {"status": "rejected", "updatedAt": datetime.utcnow()}}
        )
        return {"success": False, "message": "Team no longer exists"}
    
    # Add user to team
    member_doc = {
        "teamId": invitation["teamId"],
        "userId": user_id,
        "role": "member",
        "joinedAt": datetime.utcnow()
    }
    db.team_members.insert_one(member_doc)
    
    # Update member count
    db.teams.update_one(
        {"id": invitation["teamId"]},
        {
            "$inc": {"memberCount": 1},
            "$set": {"updatedAt": datetime.utcnow()}
        }
    )
    
    # Update invitation status
    db.team_invitations.update_one(
        {"id": invitation_id},
        {"$set": {"status": "accepted", "updatedAt": datetime.utcnow()}}
    )
    
    return {
        "success": True,
        "message": "You have joined the team",
        "teamId": invitation["teamId"]
    }


def reject_invitation(db, invitation_id: str, user_id: str) -> Dict:
    """Reject team invitation"""
    invitation = db.team_invitations.find_one({"id": invitation_id})
    if not invitation:
        return {"success": False, "message": "Invitation not found"}
    
    if invitation["inviteeId"] != user_id:
        return {"success": False, "message": "Not authorized"}
    
    if invitation["status"] != "pending":
        return {"success": False, "message": f"Invitation already {invitation['status']}"}
    
    db.team_invitations.update_one(
        {"id": invitation_id},
        {"$set": {"status": "rejected", "updatedAt": datetime.utcnow()}}
    )
    
    return {"success": True, "message": "Invitation rejected"}


# ======================== TEAM TASK SHARING ========================

def share_task_to_team(db, team_id: str, sender_id: str, task_data: Dict) -> Dict:
    """Share a task to all team members (creator only)"""
    team = db.teams.find_one({"id": team_id})
    if not team:
        return {"success": False, "message": "Team not found"}
    
    if team["creatorId"] != sender_id:
        return {"success": False, "message": "Only the team creator can share tasks to the team"}
    
    # Get sender name
    sender_profile = db.user_profiles.find_one({"userId": sender_id})
    sender_name = sender_profile.get("displayName", "GreenHabit User") if sender_profile else "GreenHabit User"
    
    # Get all team members except sender
    members = list(db.team_members.find({"teamId": team_id, "userId": {"$ne": sender_id}}))
    
    if not members:
        return {"success": False, "message": "No other members in the team"}
    
    task_share_id = str(uuid.uuid4())
    shares_created = 0
    
    for member in members:
        share_doc = {
            "id": str(uuid.uuid4()),
            "groupShareId": task_share_id,  # Groups all shares from same action
            "teamId": team_id,
            "teamName": team["name"],
            "senderId": sender_id,
            "senderName": sender_name,
            "recipientId": member["userId"],
            "taskTitle": task_data.get("title", ""),
            "taskDetails": task_data.get("details", ""),
            "taskCategory": task_data.get("category", "Other"),
            "taskPoints": task_data.get("points", 10),
            "taskEstimatedImpact": task_data.get("estimatedImpact"),
            "status": "pending",
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        db.team_task_shares.insert_one(share_doc)
        shares_created += 1
        
        # TRIGGER PUSH NOTIFICATION
        try:
            from notification_system import send_push_notification
            import asyncio
            
            asyncio.run(send_push_notification(
                db, 
                member["userId"], 
                f"New Team Task from {sender_name}", 
                f"Task: {task_data.get('title', 'Eco Task')} - Tap to view."
            ))
        except Exception as e:
            print(f"Failed to send push to member: {e}")
    
    return {
        "success": True,
        "message": f"Task shared with {shares_created} team members",
        "shareId": task_share_id,
        "recipientCount": shares_created
    }


def get_pending_team_tasks(db, user_id: str) -> List[Dict]:
    """Get pending team task shares for a user"""
    shares = list(db.team_task_shares.find({
        "recipientId": user_id,
        "status": "pending"
    }).sort("createdAt", -1))
    
    result = []
    for share in shares:
        result.append({
            "id": share["id"],
            "teamId": share["teamId"],
            "teamName": share["teamName"],
            "senderId": share["senderId"],
            "senderName": share["senderName"],
            "taskTitle": share["taskTitle"],
            "taskDetails": share["taskDetails"],
            "taskCategory": share["taskCategory"],
            "taskPoints": share["taskPoints"],
            "taskEstimatedImpact": share.get("taskEstimatedImpact"),
            "status": share["status"],
            "createdAt": share["createdAt"].isoformat() + "Z" if share.get("createdAt") else None
        })
    
    return result


def accept_team_task(db, share_id: str, user_id: str) -> Dict:
    """Accept a team task share"""
    share = db.team_task_shares.find_one({"id": share_id})
    if not share:
        return {"success": False, "message": "Task share not found"}
    
    if share["recipientId"] != user_id:
        return {"success": False, "message": "Not authorized"}
    
    if share["status"] != "pending":
        return {"success": False, "message": f"Task share already {share['status']}"}
    
    # Create task for recipient
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    task_doc = {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "title": share["taskTitle"],
        "details": share["taskDetails"],
        "category": share["taskCategory"],
        "date": today,
        "points": share["taskPoints"],
        "estimatedImpact": share.get("taskEstimatedImpact"),
        "isCompleted": False,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
        "sharedBy": share["senderId"],
        "sharedByTeam": share["teamId"]
    }
    
    db.tasks.insert_one(task_doc)
    
    # Update share status
    db.team_task_shares.update_one(
        {"id": share_id},
        {"$set": {"status": "accepted", "updatedAt": datetime.utcnow()}}
    )
    
    return {
        "success": True,
        "message": "Task accepted and added to your list",
        "taskId": task_doc["id"]
    }


def reject_team_task(db, share_id: str, user_id: str) -> Dict:
    """Reject a team task share"""
    share = db.team_task_shares.find_one({"id": share_id})
    if not share:
        return {"success": False, "message": "Task share not found"}
    
    if share["recipientId"] != user_id:
        return {"success": False, "message": "Not authorized"}
    
    if share["status"] != "pending":
        return {"success": False, "message": f"Task share already {share['status']}"}
    
    db.team_task_shares.update_one(
        {"id": share_id},
        {"$set": {"status": "rejected", "updatedAt": datetime.utcnow()}}
    )
    
    return {"success": True, "message": "Team task share rejected"}


# ======================== TEAM STATS & LEADERBOARD ========================

def get_team_stats(db, team_id: str) -> Dict:
    """Get aggregated team stats"""
    team = db.teams.find_one({"id": team_id})
    if not team:
        return {}
    
    members = list(db.team_members.find({"teamId": team_id}))
    user_ids = [m["userId"] for m in members]
    
    # Aggregate stats for all team members
    total_points = 0
    tasks_completed = 0
    
    for user_id in user_ids:
        from rewards_system import get_user_profile
        profile = get_user_profile(db, user_id)
        total_points += profile.get("totalPoints", 0)
        tasks_completed += profile.get("tasksCompleted", 0)
    
    # Calculate CO2 saved (0.3 kg per task)
    co2_saved = round(tasks_completed * 0.3, 2)
    
    return {
        "teamId": team_id,
        "teamName": team["name"],
        "memberCount": team["memberCount"],
        "totalPoints": total_points,
        "tasksCompleted": tasks_completed,
        "co2Saved": co2_saved
    }


def get_team_leaderboard(db, team_id: str) -> List[Dict]:
    """Get leaderboard for team members"""
    members = list(db.team_members.find({"teamId": team_id}))
    
    leaderboard = []
    for m in members:
        user_profile = db.user_profiles.find_one({"userId": m["userId"]})
        
        from rewards_system import get_user_profile
        stats = get_user_profile(db, m["userId"])
        
        leaderboard.append({
            "userId": m["userId"],
            "displayName": user_profile.get("displayName", "GreenHabit User") if user_profile else "GreenHabit User",
            "role": m["role"],
            "totalPoints": stats.get("totalPoints", 0),
            "tasksCompleted": stats.get("tasksCompleted", 0)
        })
    
    # Sort by total points descending
    leaderboard.sort(key=lambda x: x["totalPoints"], reverse=True)
    
    # Add rank
    for i, entry in enumerate(leaderboard):
        entry["rank"] = i + 1
    
    return leaderboard


# ======================== HELPERS ========================

def sanitize_team_doc(doc: Dict) -> Dict:
    """Remove MongoDB _id and format dates"""
    if "_id" in doc:
        del doc["_id"]
    
    date_fields = ["createdAt", "updatedAt"]
    for field in date_fields:
        if field in doc and doc[field] is not None:
            if isinstance(doc[field], datetime):
                doc[field] = doc[field].isoformat() + "Z"
    
    return doc


def ensure_team_indexes(db):
    """Create indexes for team collections"""
    try:
        # Teams collection
        db.teams.create_index([("id", 1)], unique=True)
        db.teams.create_index([("creatorId", 1)])
        
        # Team members collection
        db.team_members.create_index([("teamId", 1)])
        db.team_members.create_index([("userId", 1)], unique=True)  # One team per user
        db.team_members.create_index([("teamId", 1), ("userId", 1)])
        
        # Team invitations collection
        db.team_invitations.create_index([("id", 1)], unique=True)
        db.team_invitations.create_index([("inviteeId", 1), ("status", 1)])
        db.team_invitations.create_index([("teamId", 1)])
        
        # Team task shares collection
        db.team_task_shares.create_index([("id", 1)], unique=True)
        db.team_task_shares.create_index([("recipientId", 1), ("status", 1)])
        db.team_task_shares.create_index([("teamId", 1)])
        
        print("✅ Team system indexes created")
    except Exception as e:
        print(f"⚠️ Team index creation warning: {e}")
