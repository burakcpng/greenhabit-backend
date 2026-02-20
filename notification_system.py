
import os
import time
import json
import jwt
import httpx
import asyncio
from datetime import datetime
from typing import Dict, List, Optional

# --- Configuration ---
TEAM_ID = os.getenv("APNS_TEAM_ID", "")
KEY_ID = os.getenv("APNS_KEY_ID", "")
BUNDLE_ID = os.getenv("APNS_BUNDLE_ID", "com.burakcpng.GreenHabit")
AUTH_KEY_PATH = os.getenv("APNS_AUTH_KEY_PATH", "AuthKey_XXXXXXXXXX.p8")

# Production by default — entitlements are set to production
APNS_HOST = os.getenv("APNS_HOST", "https://api.push.apple.com")

# --- JWT Caching ---
_cached_jwt: Optional[str] = None
_cached_jwt_time: float = 0
JWT_REFRESH_INTERVAL = 2400  # 40 minutes (Apple limit is 60 min)

# --- Connection Pool ---
_apns_client: Optional[httpx.AsyncClient] = None


def validate_apns_config():
    """Validate APNs configuration at startup. Call from server startup_event."""
    errors = []
    if not TEAM_ID:
        errors.append("APNS_TEAM_ID is not set")
    if not KEY_ID:
        errors.append("APNS_KEY_ID is not set")
    if not os.path.exists(AUTH_KEY_PATH):
        errors.append(f"APNS Auth Key file not found at: {AUTH_KEY_PATH}")
    
    if errors:
        for e in errors:
            print(f"⚠️ CRITICAL APNs Config: {e}")
        print("⚠️ Push notifications will NOT work until APNs configuration is fixed.")
    else:
        print(f"✅ APNs configured: host={APNS_HOST}, team={TEAM_ID}, key={KEY_ID}")


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
    """Generate JWT token for APNs authorization with caching."""
    global _cached_jwt, _cached_jwt_time
    
    now = time.time()
    
    # Return cached token if still valid
    if _cached_jwt and (now - _cached_jwt_time) < JWT_REFRESH_INTERVAL:
        return _cached_jwt
    
    # Strict validation — no mock fallback
    if not os.path.exists(AUTH_KEY_PATH):
        raise FileNotFoundError(
            f"APNS Auth Key not found at {AUTH_KEY_PATH}. "
            "Push notifications cannot be sent without a valid .p8 key."
        )
    
    if not TEAM_ID or not KEY_ID:
        raise ValueError(
            "APNS_TEAM_ID and APNS_KEY_ID must be configured. "
            f"Current: TEAM_ID='{TEAM_ID}', KEY_ID='{KEY_ID}'"
        )
    
    with open(AUTH_KEY_PATH, 'r') as f:
        secret = f.read()
    
    _cached_jwt = jwt.encode(
        {
            'iss': TEAM_ID,
            'iat': now
        },
        secret,
        algorithm='ES256',
        headers={
            'alg': 'ES256',
            'kid': KEY_ID
        }
    )
    _cached_jwt_time = now
    return _cached_jwt


async def _get_apns_client() -> httpx.AsyncClient:
    """Get or create a persistent HTTP/2 client for APNs."""
    global _apns_client
    if _apns_client is None or _apns_client.is_closed:
        _apns_client = httpx.AsyncClient(http2=True, timeout=10.0)
    return _apns_client


async def send_push_notification(db, user_id: str, title: str, body: str, data: Dict = None):
    """Send push notification to a specific user with retry policy."""
    token = get_user_token(db, user_id)
    if not token:
        print(f"No token found for user {user_id}")
        return {"success": False, "message": "User has no registered device"}
    
    # Build payload — protect aps from being overwritten
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
    
    if data:
        for key, value in data.items():
            if key != "aps":  # Never allow overwriting aps
                payload[key] = value
    
    # Generate JWT (cached)
    try:
        jwt_token = _generate_jwt_token()
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ APNs JWT generation failed: {e}")
        return {"success": False, "error": str(e)}
    
    # Headers with proper expiration and priority
    headers = {
        "authorization": f"bearer {jwt_token}",
        "apns-topic": BUNDLE_ID,
        "apns-push-type": "alert",
        "apns-priority": "10",
        "apns-expiration": str(int(time.time()) + 86400),  # 24-hour TTL
    }
    
    # Production and Sandbox Hosts
    hosts_to_try = [APNS_HOST]
    
    # Retry policy per environment: 3 attempts with exponential backoff
    max_retries = 3
    
    for current_host in hosts_to_try:
        url = f"{current_host}/3/device/{token}"
        
        for attempt in range(max_retries):
            try:
                client = await _get_apns_client()
                response = await client.post(url, json=payload, headers=headers)
                
                if response.status_code == 200:
                    print(f"✅ Push sent to {user_id} via {current_host}")
                    return {"success": True, "apns_id": response.headers.get("apns-id")}
                
                # Handle specific error codes
                if response.status_code == 410:
                    # Token expired — remove from DB
                    db.device_tokens.delete_one({"token": token})
                    print(f"🗑️ Expired token removed for {user_id}")
                    return {"success": False, "error": "DeviceTokenExpired"}
                
                if response.status_code == 400:
                    error_body = response.text
                    # Check if token is for wrong environment
                    if "BadDeviceToken" in error_body and current_host == 'https://api.push.apple.com':
                        if len(hosts_to_try) == 1:
                            print(f"⚠️ APNs token rejected by Prod, trying Sandbox for {user_id}...")
                            hosts_to_try.append('https://api.sandbox.push.apple.com')
                        break # Break inner retry loop, continue to outer host loop
                    
                    # Other bad requests — don't retry
                    print(f"❌ Push failed (400 - BadRequest): {error_body}")
                    return {"success": False, "error": error_body}
                
                if response.status_code == 403:
                    # Auth issue — JWT invalid, don't retry (will fail again)
                    # Invalidate JWT cache so next call regenerates
                    global _cached_jwt, _cached_jwt_time
                    _cached_jwt = None
                    _cached_jwt_time = 0
                    error_body = response.text
                    print(f"❌ Push failed (403 - Forbidden): {error_body}")
                    return {"success": False, "error": error_body}
                
                if response.status_code in (429, 500, 503):
                    # Retryable errors
                    print(f"⚠️ Push attempt {attempt + 1}/{max_retries} failed ({response.status_code}) via {current_host}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s
                        continue
                    break # Exhausted retries for this host
                
                # Other unexpected status
                print(f"❌ Push failed ({response.status_code}): {response.text}")
                return {"success": False, "error": response.text}
                
            except Exception as e:
                print(f"⚠️ Push delivery error (attempt {attempt + 1}/{max_retries}) via {current_host}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                break # Exhausted retries for this host
    
    return {"success": False, "error": "Exhausted all retries for all environments"}
