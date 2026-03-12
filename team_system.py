# Team System
# Backend logic for team creation, invitations, task sharing, and stats
# Each user can only belong to ONE team at a time
# RBAC: creator → admin → moderator → member

from datetime import datetime
from typing import Dict, List, Optional
from bson import ObjectId
import uuid
from fastapi import HTTPException


# ======================== RBAC ROLE HIERARCHY ========================

ROLE_HIERARCHY = {
    "creator": 4,
    "admin": 3,
    "moderator": 2,
    "member": 1,
}

VALID_ROLES = set(ROLE_HIERARCHY.keys())

DEFAULT_TEAM_SETTINGS = {
    "whoCanInvite": "moderator",       # minimum role to invite members
    "whoCanShareTasks": "moderator",   # minimum role to share tasks
    "whoCanRemoveMembers": "admin",    # minimum role to kick members
    "whoCanChangeSettings": "admin",   # minimum role to modify these settings
}

# Maps setting keys to human-readable action names
PERMISSION_ACTIONS = {
    "invite": "whoCanInvite",
    "share_tasks": "whoCanShareTasks",
    "edit_tasks": "whoCanEditTasks",
    "remove_members": "whoCanRemoveMembers",
    "change_settings": "whoCanChangeSettings",
}


# ======================== PERMISSION MANAGER ========================

class PermissionManager:
    """Centralized RBAC permission gate for all team actions."""

    @staticmethod
    def get_role_level(role: str) -> int:
        """Get numeric hierarchy level for a role. Unknown roles get 0."""
        return ROLE_HIERARCHY.get(role, 0)

    @staticmethod
    def has_minimum_role(user_role: str, required_role: str) -> bool:
        """Check if user_role meets or exceeds the required_role level."""
        return PermissionManager.get_role_level(user_role) >= PermissionManager.get_role_level(required_role)

    @staticmethod
    def get_member_role(db, team_id: str, user_id: str) -> Optional[str]:
        """Look up a user's role in a team. Returns None if not a member."""
        member = db.team_members.find_one({"teamId": team_id, "userId": user_id})
        return member.get("role", "member") if member else None

    @staticmethod
    def get_team_settings(db, team_id: str) -> Dict:
        """
        Get team settings with lazy migration.
        If no settings document exists, create one with defaults.
        """
        settings = db.team_settings.find_one({"teamId": team_id})
        if settings:
            # Merge with defaults for forward-compat (new settings keys)
            merged = dict(DEFAULT_TEAM_SETTINGS)
            for key in DEFAULT_TEAM_SETTINGS:
                if key in settings:
                    merged[key] = settings[key]
            return merged

        # Lazy migration: create default settings for existing teams
        settings_doc = {
            "teamId": team_id,
            **DEFAULT_TEAM_SETTINGS,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        }
        db.team_settings.insert_one(settings_doc)
        return dict(DEFAULT_TEAM_SETTINGS)

    @staticmethod
    def can_perform(db, team_id: str, user_id: str, action: str) -> bool:
        """
        Check if a user can perform an action on a team.
        action: one of 'invite', 'share_tasks', 'edit_tasks', 'remove_members', 'change_settings'
        """
        user_role = PermissionManager.get_member_role(db, team_id, user_id)
        if not user_role:
            return False

        # Creator can always do everything
        if user_role == "creator":
            return True

        settings_key = PERMISSION_ACTIONS.get(action)
        if not settings_key:
            return False

        settings = PermissionManager.get_team_settings(db, team_id)
        required_role = settings.get(settings_key, "admin")

        return PermissionManager.has_minimum_role(user_role, required_role)

    @staticmethod
    def check_permission(db, team_id: str, user_id: str, action: str) -> None:
        """
        Assert that a user can perform an action. Raises HTTPException(403) on failure.
        Use this in route handlers for clean error propagation.
        """
        if not PermissionManager.can_perform(db, team_id, user_id, action):
            raise HTTPException(
                status_code=403,
                detail=f"You don't have permission to {action.replace('_', ' ')}"
            )


# ======================== TEAM CRUD ========================

def create_team(db, creator_id: str, team_name: str, description: str = "", icon: str = "person.3.fill", invited_user_ids: List[str] = None) -> Dict:
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
        "description": description.strip() if description else "",
        "icon": icon or "person.3.fill",
        "creatorId": creator_id,
        "creatorName": creator_name,
        "memberCount": 1,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow()
    }
    
    db.teams.insert_one(team_doc)
    
    # Create default team settings
    settings_doc = {
        "teamId": team_id,
        **DEFAULT_TEAM_SETTINGS,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }
    db.team_settings.insert_one(settings_doc)
    
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
    """Get user's current team with role and settings"""
    membership = db.team_members.find_one({"userId": user_id})
    if not membership:
        return None
    
    team = db.teams.find_one({"id": membership["teamId"]})
    if not team:
        return None
    
    # ✅ FIX: Fetch creator's current displayName (not cached value)
    creator_profile = db.user_profiles.find_one({"userId": team["creatorId"]})
    if creator_profile:
        team["creatorName"] = creator_profile.get("displayName", "GreenHabit User")
    
    team = sanitize_team_doc(team)
    team["myRole"] = membership["role"]
    
    # Include team settings for client-side permission gating
    team["settings"] = PermissionManager.get_team_settings(db, team["id"])
    
    return team


def delete_team(db, team_id: str, user_id: str) -> Dict:
    """Delete team (creator only)"""
    team = db.teams.find_one({"id": team_id})
    if not team:
        return {"success": False, "message": "Team not found"}
    
    # Only creator can delete team
    user_role = PermissionManager.get_member_role(db, team_id, user_id)
    if user_role != "creator":
        return {"success": False, "message": "Only the team creator can delete the team"}
    
    # Remove all members
    db.team_members.delete_many({"teamId": team_id})
    
    # Remove team settings
    db.team_settings.delete_many({"teamId": team_id})
    
    # Remove all pending invitations
    db.team_invitations.delete_many({"teamId": team_id})
    
    # Remove all pending team tasks
    db.team_task_shares.delete_many({"teamId": team_id})
    
    # Delete team
    db.teams.delete_one({"id": team_id})
    
    return {"success": True, "message": "Team deleted successfully"}


def leave_team(db, team_id: str, user_id: str) -> Dict:
    """Leave a team (members only, creator must transfer ownership first)"""
    team = db.teams.find_one({"id": team_id})
    if not team:
        return {"success": False, "message": "Team not found"}
    
    user_role = PermissionManager.get_member_role(db, team_id, user_id)
    if user_role == "creator":
        return {"success": False, "message": "Creator cannot leave the team. Transfer ownership or delete it instead."}
    
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
            "canShareTasks": m.get("canShareTasks", False),
            "joinedAt": m["joinedAt"].isoformat() + "Z" if m.get("joinedAt") else None,
            "totalPoints": user_stats.get("totalPoints", 0),
            "tasksCompleted": user_stats.get("tasksCompleted", 0),
            "level": user_stats.get("level", 1)  # ✅ ADDED: Level needed for UI
        }
        members.append(member)
    
    return members


def remove_member(db, team_id: str, actor_id: str, target_user_id: str) -> Dict:
    """Remove a member from team (requires remove_members permission + higher role)"""
    team = db.teams.find_one({"id": team_id})
    if not team:
        return {"success": False, "message": "Team not found"}
    
    # RBAC: Check remove_members permission
    actor_role = PermissionManager.get_member_role(db, team_id, actor_id)
    if not actor_role:
        return {"success": False, "message": "You are not a member of this team"}
    
    if not PermissionManager.can_perform(db, team_id, actor_id, "remove_members"):
        return {"success": False, "message": "You don't have permission to remove members"}
    
    if target_user_id == actor_id:
        return {"success": False, "message": "Cannot remove yourself. Leave the team instead."}
    
    membership = db.team_members.find_one({"teamId": team_id, "userId": target_user_id})
    if not membership:
        return {"success": False, "message": "User is not a member of this team"}
    
    # RBAC: Cannot remove someone of equal or higher role
    target_role = membership.get("role", "member")
    if not PermissionManager.has_minimum_role(actor_role, target_role) or \
       PermissionManager.get_role_level(actor_role) <= PermissionManager.get_role_level(target_role):
        return {"success": False, "message": "Cannot remove a member with equal or higher role"}
    
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


def update_member_permissions(db, team_id: str, actor_id: str, target_user_id: str, can_share_tasks: bool) -> Dict:
    """Update member's legacy canShareTasks permission (requires change_settings permission)"""
    team = db.teams.find_one({"id": team_id})
    if not team:
        return {"success": False, "message": "Team not found"}
    
    if not PermissionManager.can_perform(db, team_id, actor_id, "change_settings"):
        return {"success": False, "message": "You don't have permission to update settings"}
    
    if target_user_id == actor_id:
        return {"success": False, "message": "Cannot modify your own permissions"}
    
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
    """Send team invitation (requires invite permission)"""
    invitee_id = invitee_id.strip()  # ✅ FIX: Sanitize input
    team = db.teams.find_one({"id": team_id})
    if not team:
        return {"success": False, "message": "Team not found"}
    
    # RBAC: Check invite permission via PermissionManager
    if not PermissionManager.can_perform(db, team_id, inviter_id, "invite"):
        return {"success": False, "message": "You don't have permission to invite members"}
    
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

async def share_task_to_team(db, team_id: str, sender_id: str, task_data: Dict) -> Dict:
    """Share a task to all team members (requires share_tasks permission)"""
    team = db.teams.find_one({"id": team_id})
    if not team:
        return {"success": False, "message": "Team not found"}
    
    # RBAC: Check share_tasks permission via PermissionManager
    if not PermissionManager.can_perform(db, team_id, sender_id, "share_tasks"):
        return {"success": False, "message": "You don't have permission to share tasks"}
    
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
        
        # TRIGGER PUSH NOTIFICATION (await instead of asyncio.run)
        try:
            from notification_system import send_push_notification
            
            await send_push_notification(
                db, 
                member["userId"], 
                f"New Team Task from {sender_name}", 
                f"Task: {task_data.get('title', 'Eco Task')} - Tap to view."
            )
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
    
    # Calculate CO2 saved with real task impact
    pipeline = [
        {"$match": {"userId": {"$in": user_ids}, "isCompleted": True}},
        {"$group": {"_id": None, "totalCo2": {"$sum": {"$ifNull": ["$co2Kg", 0.3]}}}}
    ]
    result = list(db.tasks.aggregate(pipeline))
    co2_saved = round(result[0]["totalCo2"], 2) if result else 0.0
    
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


# ======================== TEAM SETTINGS & ROLE MANAGEMENT ========================

def get_team_settings_data(db, team_id: str, user_id: str) -> Dict:
    """Get team settings (any member can view)"""
    member = db.team_members.find_one({"teamId": team_id, "userId": user_id})
    if not member:
        return {"success": False, "message": "You are not a member of this team"}
    
    settings = PermissionManager.get_team_settings(db, team_id)
    settings["teamId"] = team_id
    return {"success": True, "settings": settings}


def update_team_settings(db, team_id: str, user_id: str, settings_data: Dict) -> Dict:
    """
    Update team permission policies (requires change_settings permission).
    settings_data: partial dict of {whoCanInvite, whoCanShareTasks, ...} → role strings
    """
    if not PermissionManager.can_perform(db, team_id, user_id, "change_settings"):
        return {"success": False, "message": "You don't have permission to change settings"}
    
    # Validate all values are valid roles
    valid_setting_keys = set(DEFAULT_TEAM_SETTINGS.keys())
    update_fields = {}
    
    for key, value in settings_data.items():
        if key not in valid_setting_keys:
            continue  # Ignore unknown keys
        if value not in VALID_ROLES:
            return {"success": False, "message": f"Invalid role '{value}' for {key}"}
        update_fields[key] = value
    
    if not update_fields:
        return {"success": False, "message": "No valid settings to update"}
    
    update_fields["updatedAt"] = datetime.utcnow()
    
    db.team_settings.update_one(
        {"teamId": team_id},
        {"$set": update_fields},
        upsert=True
    )
    
    # Return updated settings
    new_settings = PermissionManager.get_team_settings(db, team_id)
    return {"success": True, "message": "Settings updated", "settings": new_settings}


def update_team_info(db, team_id: str, user_id: str, name: str = None, description: str = None, icon: str = None) -> Dict:
    """Update team name, description, icon (requires change_settings permission)"""
    if not PermissionManager.can_perform(db, team_id, user_id, "change_settings"):
        return {"success": False, "message": "You don't have permission to change team info"}
    
    team = db.teams.find_one({"id": team_id})
    if not team:
        return {"success": False, "message": "Team not found"}
    
    update_fields = {"updatedAt": datetime.utcnow()}
    
    if name is not None:
        name = name.strip()
        if len(name) < 2:
            return {"success": False, "message": "Team name must be at least 2 characters"}
        if len(name) > 50:
            return {"success": False, "message": "Team name cannot exceed 50 characters"}
        update_fields["name"] = name
    
    if description is not None:
        if len(description) > 200:
            return {"success": False, "message": "Description cannot exceed 200 characters"}
        update_fields["description"] = description.strip()
    
    if icon is not None:
        update_fields["icon"] = icon
    
    db.teams.update_one({"id": team_id}, {"$set": update_fields})
    
    return {"success": True, "message": "Team info updated"}


def update_member_role(db, team_id: str, actor_id: str, target_user_id: str, new_role: str) -> Dict:
    """
    Change a member's role (requires admin+ and must be higher than target).
    Cannot promote to 'creator' — use transfer_ownership for that.
    """
    if new_role not in VALID_ROLES:
        return {"success": False, "message": f"Invalid role: {new_role}"}
    
    if new_role == "creator":
        return {"success": False, "message": "Cannot promote to creator. Use transfer ownership instead."}
    
    # Verify actor is a member
    actor_role = PermissionManager.get_member_role(db, team_id, actor_id)
    if not actor_role:
        return {"success": False, "message": "You are not a member of this team"}
    
    # Only admin+ can change roles
    if not PermissionManager.has_minimum_role(actor_role, "admin"):
        return {"success": False, "message": "Only admins and above can change roles"}
    
    if actor_id == target_user_id:
        return {"success": False, "message": "Cannot change your own role"}
    
    # Verify target is a member
    target_member = db.team_members.find_one({"teamId": team_id, "userId": target_user_id})
    if not target_member:
        return {"success": False, "message": "User is not a member of this team"}
    
    target_current_role = target_member.get("role", "member")
    
    # Cannot modify someone of equal or higher role
    if PermissionManager.get_role_level(target_current_role) >= PermissionManager.get_role_level(actor_role):
        return {"success": False, "message": "Cannot change the role of someone with equal or higher rank"}
    
    # Cannot promote someone to your own level or above (non-creator)
    if actor_role != "creator" and PermissionManager.get_role_level(new_role) >= PermissionManager.get_role_level(actor_role):
        return {"success": False, "message": "Cannot promote someone to your own rank or above"}
    
    db.team_members.update_one(
        {"teamId": team_id, "userId": target_user_id},
        {"$set": {"role": new_role, "updatedAt": datetime.utcnow()}}
    )
    
    return {"success": True, "message": f"Role updated to {new_role}"}


def transfer_ownership(db, team_id: str, creator_id: str, new_owner_id: str) -> Dict:
    """
    Transfer team ownership from current creator to another member.
    Old creator is demoted to admin. New owner becomes creator.
    """
    # Verify caller is the creator
    actor_role = PermissionManager.get_member_role(db, team_id, creator_id)
    if actor_role != "creator":
        return {"success": False, "message": "Only the team creator can transfer ownership"}
    
    if creator_id == new_owner_id:
        return {"success": False, "message": "You are already the owner"}
    
    # Verify target is a member
    target_member = db.team_members.find_one({"teamId": team_id, "userId": new_owner_id})
    if not target_member:
        return {"success": False, "message": "User is not a member of this team"}
    
    # Atomic swap: demote old creator to admin, promote new owner to creator
    db.team_members.update_one(
        {"teamId": team_id, "userId": creator_id},
        {"$set": {"role": "admin", "updatedAt": datetime.utcnow()}}
    )
    
    db.team_members.update_one(
        {"teamId": team_id, "userId": new_owner_id},
        {"$set": {"role": "creator", "updatedAt": datetime.utcnow()}}
    )
    
    # Update team's creatorId field
    new_owner_profile = db.user_profiles.find_one({"userId": new_owner_id})
    new_owner_name = new_owner_profile.get("displayName", "GreenHabit User") if new_owner_profile else "GreenHabit User"
    
    db.teams.update_one(
        {"id": team_id},
        {"$set": {
            "creatorId": new_owner_id,
            "creatorName": new_owner_name,
            "updatedAt": datetime.utcnow()
        }}
    )
    
    return {"success": True, "message": f"Ownership transferred to {new_owner_name}"}


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
        
        # Team settings collection
        db.team_settings.create_index([("teamId", 1)], unique=True)
        
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


# ======================== USER DELETION CLEANUP ========================

def handle_user_deletion_teams(db, user_id: str) -> Dict:
    """
    Handle team cleanup when user deletes account.
    
    Rules:
    1. If user is a team creator → Disband team (delete team + remove all members)
    2. If user is a member → Remove from team
    3. Delete all pending invitations (sent + received)
    """
    try:
        # Find teams where user is creator
        creator_teams = list(db.teams.find({"creatorId": user_id}))
        
        # Delete teams created by this user
        for team in creator_teams:
            team_id = team.get("id") or str(team["_id"])
            # This will also remove all members and settings
            db.teams.delete_one({"_id": team["_id"]})
            db.team_members.delete_many({"teamId": team_id})
            db.team_settings.delete_many({"teamId": team_id})
            print(f"   - Disbanded team: {team.get('name', 'Unknown')}")
        
        # Remove user from teams where they are a member (not creator)
        db.team_members.delete_many({"userId": user_id})
        
        # Delete pending invitations (sent + received)
        invitations_result = db.team_invitations.delete_many({
            "$or": [
                {"inviterId": user_id},
                {"inviteeId": user_id}
            ]
        })
        
        # Delete pending team tasks (shared by user or pending for user)
        tasks_result = db.team_task_shares.delete_many({
            "$or": [
                {"senderId": user_id},
                {"recipientId": user_id}
            ]
        })
        
        return {
            "teams_disbanded": len(creator_teams),
            "invitations_deleted": invitations_result.deleted_count,
            "shared_tasks_deleted": tasks_result.deleted_count
        }
        
    except Exception as e:
        print(f"❌ Team cleanup failed: {e}")
        return {"error": str(e)}
