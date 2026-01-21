
import os
import time
import json
import jwt
import httpx
from datetime import datetime
from typing import Dict, List, Optional

# --- Configuration ---
# You need to fill these with actual values from Apple Developer Portal
TEAM_ID = os.getenv("APNS_TEAM_ID", "")
KEY_ID = os.getenv("APNS_KEY_ID", "YOUR_KEY_ID")
BUNDLE_ID = os.getenv("APNS_BUNDLE_ID", "com.burakcpng.GreenHabit")
# Path to your .p8 file
AUTH_KEY_PATH = os.getenv("APNS_AUTH_KEY_PATH", "AuthKey_XXXXXXXXXX.p8")

# Use sandbox for development, production for release
# sandbox: api.sandbox.push.apple.com
# production: api.push.apple.com
APNS_HOST = os.getenv("APNS_HOST", "https://api.sandbox.push.apple.com")

def register_device_token(db, user_id: str, token: str, platform: str = "ios") -> Dict:
    """Store or update user's device token"""
    try:
        db.device_tokens.update_one(
            {"userId": user_id},
            {
                "$set": {
                    "token": token,
                    "platform": platform,
                    "updatedAt": datetime.utcnow()
                }
            },
            upsert=True
        )
        return {"success": True, "message": "Token registered"}
    except Exception as e:
        print(f"Error registering token: {e}")
        return {"success": False, "message": str(e)}

def get_user_token(db, user_id: str) -> Optional[str]:
    """Retrieve device token for a user"""
    record = db.device_tokens.find_one({"userId": user_id})
    return record["token"] if record else None

def _generate_jwt_token() -> str:
    """Generate JWT token for APNS authorization"""
    try:
        # Check if auth key file exists
        if not os.path.exists(AUTH_KEY_PATH):
            # Fallback for development/demo only
            print(f"Warning: APNS Auth Key not found at {AUTH_KEY_PATH}")
            return "mock_jwt_token"

        with open(AUTH_KEY_PATH, 'r') as f:
            secret = f.read()

        token = jwt.encode(
            {
                'iss': TEAM_ID,
                'iat': time.time()
            },
            secret,
            algorithm='ES256',
            headers={
                'alg': 'ES256',
                'kid': KEY_ID
            }
        )
        return token
    except Exception as e:
        print(f"Error generating JWT: {e}")
        return ""

async def send_push_notification(db, user_id: str, title: str, body: str, data: Dict = None):
    """Send push notification to a specific user"""
    token = get_user_token(db, user_id)
    if not token:
        print(f"No token found for user {user_id}")
        return {"success": False, "message": "User has no registered device"}
    
    # Payload structure
    payload = {
        "aps": {
            "alert": {
                "title": title,
                "body": body
            },
            "sound": "default",
            "badge": 1
        }
    }
    
    # Add custom data if provided
    if data:
        payload.update(data)
        
    # Headers
    jwt_token = _generate_jwt_token()
    headers = {
        "authorization": f"bearer {jwt_token}",
        "apns-topic": BUNDLE_ID,
        "apns-push-type": "alert"
    }
    
    url = f"{APNS_HOST}/3/device/{token}"
    
    # Sending request
    # Note: In production this should be async or background task
    try:
        async with httpx.AsyncClient(http2=True) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                print(f"✅ Push sent to {user_id}")
                return {"success": True, "apns_id": response.headers.get("apns-id")}
            else:
                print(f"❌ Push failed: {response.status_code} - {response.text}")
                
                # Handle expired tokens (410)
                if response.status_code == 410:
                    db.device_tokens.delete_one({"token": token})
                    
                return {"success": False, "error": response.text}
    except Exception as e:
        print(f"Push delivery error: {e}")
        # Only for dev simulation if no p8 key
        if "mock_jwt_token" in jwt_token:
            print("⚠️ Mock Push: Logic executed but no real push sent (missing p8 key)")
            return {"success": True, "message": "Mock push simulated"}
            
        return {"success": False, "error": str(e)}
