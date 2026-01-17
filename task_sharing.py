# Task Sharing System
# Backend logic for in-app task sharing between friends

from datetime import datetime
from typing import Dict, List, Optional
from bson import ObjectId


def create_task_share(
    db,
    sender_id: str,
    recipient_id: str,
    task_data: Dict
) -> Dict:
    """Create a task share request"""
    
    # Verify recipient exists
    recipient = db.user_profiles.find_one({"userId": recipient_id})
    if not recipient:
        return {"success": False, "message": "Recipient not found"}
    
    # Prevent self-sending
    if sender_id == recipient_id:
        return {"success": False, "message": "Cannot send task to yourself"}
    
    # Get sender name
    sender_profile = db.user_profiles.find_one({"userId": sender_id})
    sender_name = sender_profile.get("displayName", "GreenHabit User") if sender_profile else "GreenHabit User"
    
    share_doc = {
        "senderId": sender_id,
        "senderName": sender_name,
        "recipientId": recipient_id,
        "taskTitle": task_data.get("title", ""),
        "taskDetails": task_data.get("details", ""),
        "taskCategory": task_data.get("category", "Other"),
        "taskPoints": task_data.get("points", 10),
        "taskEstimatedImpact": task_data.get("estimatedImpact"),
        "status": "pending",
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow()
    }
    
    result = db.task_shares.insert_one(share_doc)
    share_doc["id"] = str(result.inserted_id)
    if "_id" in share_doc:
        del share_doc["_id"]
    
    return {
        "success": True,
        "message": "Task shared successfully",
        "shareId": str(result.inserted_id)
    }


def get_incoming_shares(db, user_id: str, status: str = "pending") -> List[Dict]:
    """Get incoming task shares for a user"""
    
    query = {"recipientId": user_id}
    if status:
        query["status"] = status
    
    shares = list(db.task_shares.find(query).sort("createdAt", -1))
    
    result = []
    for share in shares:
        share["id"] = str(share["_id"])
        del share["_id"]
        
        # Format dates
        if "createdAt" in share and share["createdAt"]:
            share["createdAt"] = share["createdAt"].isoformat() + "Z"
        if "updatedAt" in share and share["updatedAt"]:
            share["updatedAt"] = share["updatedAt"].isoformat() + "Z"
        
        result.append(share)
    
    return result


def get_sent_shares(db, user_id: str) -> List[Dict]:
    """Get sent task shares by a user"""
    
    shares = list(db.task_shares.find({"senderId": user_id}).sort("createdAt", -1))
    
    result = []
    for share in shares:
        share["id"] = str(share["_id"])
        del share["_id"]
        
        # Get recipient name
        recipient = db.user_profiles.find_one({"userId": share["recipientId"]})
        share["recipientName"] = recipient.get("displayName", "GreenHabit User") if recipient else "GreenHabit User"
        
        # Format dates
        if "createdAt" in share and share["createdAt"]:
            share["createdAt"] = share["createdAt"].isoformat() + "Z"
        if "updatedAt" in share and share["updatedAt"]:
            share["updatedAt"] = share["updatedAt"].isoformat() + "Z"
        
        result.append(share)
    
    return result


def accept_share(db, share_id: str, user_id: str) -> Dict:
    """Accept a task share and create the task for the recipient"""
    
    try:
        share = db.task_shares.find_one({"_id": ObjectId(share_id)})
    except:
        return {"success": False, "message": "Invalid share ID"}
    
    if not share:
        return {"success": False, "message": "Share not found"}
    
    if share["recipientId"] != user_id:
        return {"success": False, "message": "Not authorized"}
    
    if share["status"] != "pending":
        return {"success": False, "message": f"Share already {share['status']}"}
    
    # Create task for recipient
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    task_doc = {
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
        "sharedBy": share["senderId"]
    }
    
    task_result = db.tasks.insert_one(task_doc)
    
    # Update share status
    db.task_shares.update_one(
        {"_id": ObjectId(share_id)},
        {
            "$set": {
                "status": "accepted",
                "updatedAt": datetime.utcnow(),
                "acceptedTaskId": str(task_result.inserted_id)
            }
        }
    )
    
    return {
        "success": True,
        "message": "Task accepted and added to your list",
        "taskId": str(task_result.inserted_id)
    }


def reject_share(db, share_id: str, user_id: str) -> Dict:
    """Reject a task share"""
    
    try:
        share = db.task_shares.find_one({"_id": ObjectId(share_id)})
    except:
        return {"success": False, "message": "Invalid share ID"}
    
    if not share:
        return {"success": False, "message": "Share not found"}
    
    if share["recipientId"] != user_id:
        return {"success": False, "message": "Not authorized"}
    
    if share["status"] != "pending":
        return {"success": False, "message": f"Share already {share['status']}"}
    
    # Update share status
    db.task_shares.update_one(
        {"_id": ObjectId(share_id)},
        {
            "$set": {
                "status": "rejected",
                "updatedAt": datetime.utcnow()
            }
        }
    )
    
    return {"success": True, "message": "Task share rejected"}


def get_pending_count(db, user_id: str) -> int:
    """Get count of pending incoming shares"""
    return db.task_shares.count_documents({
        "recipientId": user_id,
        "status": "pending"
    })


def ensure_sharing_indexes(db):
    """Create indexes for task sharing"""
    try:
        db.task_shares.create_index([("recipientId", 1), ("status", 1)])
        db.task_shares.create_index([("senderId", 1)])
        db.task_shares.create_index([("createdAt", -1)])
        print("✅ Task sharing indexes created")
    except Exception as e:
        print(f"⚠️ Index creation warning: {e}")
