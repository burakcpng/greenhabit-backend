"""
Rate Limiter Module for GreenHabit API
Provides protection against DDoS and abuse attacks

Uses in-memory storage (for production, consider Redis)
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
from collections import defaultdict
from fastapi import HTTPException
import threading

# ======================== CONFIGURATION ========================

RATE_LIMITS = {
    # Action: {"requests": max_requests, "window_seconds": time_window}
    "task_complete": {"requests": 30, "window_seconds": 60},      # 30 completions/min
    "task_create": {"requests": 20, "window_seconds": 3600},      # 20 tasks/hour
    "task_toggle": {"requests": 10, "window_seconds": 60},        # 10 toggles/min per task
    "follow": {"requests": 30, "window_seconds": 3600},           # 30 follows/hour
    "unfollow": {"requests": 30, "window_seconds": 3600},         # 30 unfollows/hour
    "invitation_send": {"requests": 10, "window_seconds": 86400}, # 10 invites/day
    "task_share": {"requests": 20, "window_seconds": 3600},       # 20 shares/hour
    "like": {"requests": 60, "window_seconds": 3600},              # 60 likes/hour
}

# Toggle cooldown: minimum seconds between toggling the same task
# ✅ ULTRATHINK FIX: Reduced from 5s to 0.5s - 5 seconds was too long and caused 429 errors
TASK_TOGGLE_COOLDOWN_SECONDS = 0.5



# ======================== IN-MEMORY STORAGE ========================

class RateLimiter:
    """Thread-safe in-memory rate limiter"""
    
    def __init__(self):
        self._lock = threading.Lock()
        # Structure: {user_id: {action: [(timestamp, context), ...]}}
        self._requests: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
    
    def _cleanup_old_requests(self, user_id: str, action: str, window_seconds: int):
        """Remove requests older than the window"""
        cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
        self._requests[user_id][action] = [
            (ts, ctx) for ts, ctx in self._requests[user_id][action]
            if ts > cutoff
        ]
    
    def check_rate_limit(
        self, 
        user_id: str, 
        action: str, 
        context: Optional[str] = None
    ) -> bool:
        """
        Check if user is within rate limit for the action.
        
        Args:
            user_id: The user making the request
            action: The action type (e.g., "task_complete", "follow")
            context: Optional context (e.g., task_id for per-task limits)
        
        Returns:
            True if within limit, raises HTTPException if exceeded
        """
        if action not in RATE_LIMITS:
            return True  # Unknown action, allow
        
        limit_config = RATE_LIMITS[action]
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window_seconds"]
        
        with self._lock:
            # Cleanup old requests
            self._cleanup_old_requests(user_id, action, window_seconds)
            
            # Count requests (optionally filtered by context)
            if context:
                count = sum(
                    1 for _, ctx in self._requests[user_id][action]
                    if ctx == context
                )
            else:
                count = len(self._requests[user_id][action])
            
            if count >= max_requests:
                retry_after = window_seconds
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded for {action}. Try again later.",
                    headers={"Retry-After": str(retry_after)}
                )
            
            # Record this request
            self._requests[user_id][action].append((datetime.utcnow(), context))
        
        return True
    
    def check_toggle_cooldown(self, user_id: str, task_id: str, last_updated: datetime) -> bool:
        """
        Check if sufficient time has passed since last toggle.
        
        Args:
            user_id: The user making the request
            task_id: The task being toggled
            last_updated: When the task was last updated
        
        Returns:
            True if allowed, raises HTTPException if on cooldown
        """
        if last_updated is None:
            return True
        
        elapsed = (datetime.utcnow() - last_updated).total_seconds()
        
        if elapsed < TASK_TOGGLE_COOLDOWN_SECONDS:
            remaining = int(TASK_TOGGLE_COOLDOWN_SECONDS - elapsed) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {remaining}s before toggling this task again.",
                headers={"Retry-After": str(remaining)}
            )
        
        return True
    
    def get_remaining_requests(self, user_id: str, action: str) -> Dict:
        """Get remaining requests info for debugging/UI"""
        if action not in RATE_LIMITS:
            return {"remaining": -1, "limit": -1, "reset_in": -1}
        
        limit_config = RATE_LIMITS[action]
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window_seconds"]
        
        with self._lock:
            self._cleanup_old_requests(user_id, action, window_seconds)
            count = len(self._requests[user_id][action])
        
        return {
            "remaining": max(0, max_requests - count),
            "limit": max_requests,
            "reset_in": window_seconds
        }


# ======================== GLOBAL INSTANCE ========================

_rate_limiter = RateLimiter()


def check_rate_limit(user_id: str, action: str, context: Optional[str] = None) -> bool:
    """Global function to check rate limit"""
    return _rate_limiter.check_rate_limit(user_id, action, context)


def check_toggle_cooldown(user_id: str, task_id: str, last_updated: datetime) -> bool:
    """Global function to check toggle cooldown"""
    return _rate_limiter.check_toggle_cooldown(user_id, task_id, last_updated)


def get_remaining_requests(user_id: str, action: str) -> Dict:
    """Global function to get remaining requests"""
    return _rate_limiter.get_remaining_requests(user_id, action)


# ======================== EXCEPTION ========================

class RateLimitExceeded(Exception):
    """Custom exception for rate limit exceeded (for non-HTTP contexts)"""
    def __init__(self, action: str, retry_after: int):
        self.action = action
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded for {action}")


def check_user_rate(user_id: str, action: str, context: Optional[str] = None) -> bool:
    """
    Non-HTTP version that raises RateLimitExceeded instead of HTTPException.
    Useful for internal functions (social_system, team_system).
    """
    if action not in RATE_LIMITS:
        return True
    
    limit_config = RATE_LIMITS[action]
    max_requests = limit_config["requests"]
    window_seconds = limit_config["window_seconds"]
    
    with _rate_limiter._lock:
        _rate_limiter._cleanup_old_requests(user_id, action, window_seconds)
        
        if context:
            count = sum(
                1 for _, ctx in _rate_limiter._requests[user_id][action]
                if ctx == context
            )
        else:
            count = len(_rate_limiter._requests[user_id][action])
        
        if count >= max_requests:
            raise RateLimitExceeded(action, window_seconds)
        
        _rate_limiter._requests[user_id][action].append((datetime.utcnow(), context))
    
    return True
