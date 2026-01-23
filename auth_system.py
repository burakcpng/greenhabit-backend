import os
import time
import jwt
import requests
from fastapi import HTTPException, Header, Depends
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import base64
import json

# Configuration
# SECURITY: All secrets MUST be provided via environment variables
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("CRITICAL: JWT_SECRET environment variable is not set. Cannot start server.")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30
APPLE_PUBLIC_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"
# Your App Bundle ID (MUST match your iOS app's Bundle Identifier exactly)
APPLE_CLIENT_ID = "com.burakcpng.GreenHabit" 

class AuthSystem:
    _apple_public_keys = None
    _last_keys_fetch = 0
    _keys_cache_ttl = 86400  # 24 hours

    @classmethod
    def get_apple_public_key(cls, kid):
        """Fetch and cache Apple's public keys"""
        current_time = time.time()
        
        # Refresh cache if needed
        if cls._apple_public_keys is None or (current_time - cls._last_keys_fetch > cls._keys_cache_ttl):
            try:
                response = requests.get(APPLE_PUBLIC_KEYS_URL)
                response.raise_for_status()
                cls._apple_public_keys = response.json().get('keys', [])
                cls._last_keys_fetch = current_time
                print("🔑 Refreshed Apple Public Keys")
            except Exception as e:
                print(f"❌ Failed to fetch Apple keys: {e}")
                # If fetch fails, try to use cached keys even if expired
                if cls._apple_public_keys is None:
                    raise HTTPException(status_code=503, detail="Authentication service unavailable")

        # Find matching key
        for key in cls._apple_public_keys:
            if key['kid'] == kid:
                return key
        
        # Force refresh if key not found (maybe key rotation happened)
        if current_time - cls._last_keys_fetch > 60: # debounce forced refresh
             cls._last_keys_fetch = 0 # force refresh on next recursion
             return cls.get_apple_public_key(kid)
             
        raise HTTPException(status_code=401, detail="Invalid token key identifier")

    @staticmethod
    def rsa_pem_from_jwk(jwk):
        """Convert RSA JWK to PEM format"""
        n = int.from_bytes(base64.urlsafe_b64decode(jwk['n'] + '=='), 'big')
        e = int.from_bytes(base64.urlsafe_b64decode(jwk['e'] + '=='), 'big')
        return RSAPublicNumbers(e, n).public_key(default_backend())

    @classmethod
    def verify_apple_token(cls, token: str) -> str:
        """
        Verify Apple Identity Token and return the Apple User ID (sub).
        """
        try:
            # 1. Decode header to get Key ID (kid)
            header = jwt.get_unverified_header(token)
            kid = header['kid']

            # 2. Get Public Key from Apple
            jwk = cls.get_apple_public_key(kid)
            public_key = cls.rsa_pem_from_jwk(jwk)

            # 3. Verify Signature and Claims
            # Note: We don't verify 'aud' (client_id) strictly here to allowing testing
            # In production, uncomment the audience verification
            decoded = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=APPLE_CLIENT_ID, 
                issuer=APPLE_ISSUER,
                options={"verify_exp": True} #, "verify_aud": False} # Relax aud check for dev if needed
            )
            
            return decoded['sub']
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Apple token has expired")
        except jwt.InvalidTokenError as e:
            print(f"⚠️ Invalid Apple Token: {str(e)}")
            raise HTTPException(status_code=401, detail=f"Invalid authentication token: {str(e)}")
        except Exception as e:
            print(f"❌ Apple Auth Error: {str(e)}")
            raise HTTPException(status_code=401, detail="Authentication failed")

    @staticmethod
    def create_session_token(user_id: str) -> str:
        """Create a long-lived JWT session token for the app"""
        payload = {
            "sub": user_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + (ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60 * 60),
            "type": "session"
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    @staticmethod
    def verify_session_token(token: str) -> str:
        """Verify app session token and return user_id"""
        try:
            decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return decoded['sub']
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Session expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid session token")

# Dependency for FastAPI Routes
def get_current_user(
    authorization: str = Header(None),
    x_user_id: str = Header(None)  # Kept for migration logging only
) -> str:
    """
    Dependency to authenticate requests.
    SECURITY: Only Bearer Token authentication is accepted.
    """
    
    # Check for Bearer Token (Required)
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        return AuthSystem.verify_session_token(token)
    
    # Log legacy attempts for migration monitoring (but reject them)
    if x_user_id:
        print(f"⚠️ SECURITY: Rejected legacy X-User-Id auth attempt: {x_user_id[:8]}...")
    
    raise HTTPException(status_code=401, detail="Authentication required. Please sign in with Apple.")

