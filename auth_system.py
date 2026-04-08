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
import logging

logger = logging.getLogger("greenhabit.auth")

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
APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", "com.burakcpng.GreenHabit")

# Apple Token Revocation (Guideline 5.1.1)
APPLE_TEAM_ID = os.getenv("APPLE_TEAM_ID")
APPLE_KEY_ID = os.getenv("APPLE_KEY_ID")
# Key resolution priority:
#   1. APPLE_P8_KEY_PATH (explicit override)
#   2. APNS_AUTH_KEY_PATH (reuse the APNs secret file — same .p8 key)
#   3. Local dev fallback: "AuthKey_K7P6P48699.p8"
APPLE_P8_KEY_PATH = (
    os.getenv("APPLE_P8_KEY_PATH")
    or os.getenv("APNS_AUTH_KEY_PATH")
    or "AuthKey_K7P6P48699.p8"
)

# ── Startup validation: warn if revocation env vars are missing ──
if not APPLE_TEAM_ID:
    logger.warning("⚠️ APPLE_TEAM_ID not set — account deletion (token revocation) will fail!")
if not APPLE_KEY_ID:
    logger.warning("⚠️ APPLE_KEY_ID not set — account deletion (token revocation) will fail!")
if not os.path.isfile(APPLE_P8_KEY_PATH) and not os.getenv("APPLE_P8_KEY_CONTENT"):
    logger.warning(
        "⚠️ .p8 key not found at '%s' and APPLE_P8_KEY_CONTENT not set — account deletion will fail!",
        APPLE_P8_KEY_PATH
    )

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
    def generate_client_secret() -> str:
        """
        Generate a client_secret JWT for Apple Sign In Server-to-Server auth.
        Required for /auth/token and /auth/revoke calls.
        Uses the .p8 private key from Apple Developer Console.
        """
        # ── Validate required env vars before attempting ──
        if not APPLE_TEAM_ID:
            logger.error("❌ APPLE_TEAM_ID is not set. Cannot generate Apple client secret.")
            raise HTTPException(
                status_code=500,
                detail="Server misconfiguration: APPLE_TEAM_ID not set."
            )
        if not APPLE_KEY_ID:
            logger.error("❌ APPLE_KEY_ID is not set. Cannot generate Apple client secret.")
            raise HTTPException(
                status_code=500,
                detail="Server misconfiguration: APPLE_KEY_ID not set."
            )

        # ── Load .p8 private key ──
        private_key = None
        key_source = "unknown"
        try:
            with open(APPLE_P8_KEY_PATH, "r") as f:
                private_key = f.read()
                key_source = f"file:{APPLE_P8_KEY_PATH}"
        except (FileNotFoundError, TypeError):
            # TypeError catches APPLE_P8_KEY_PATH being None
            # Fallback: try from env var (for cloud deployments like Render)
            raw_key = os.getenv("APPLE_P8_KEY_CONTENT")
            if raw_key:
                # ── CRITICAL: Normalize newlines ──
                # When pasting a PEM key into Render/Heroku env var UI,
                # actual newlines may be stored as literal "\n" strings.
                # The cryptography library needs real newline characters
                # to parse the PEM format correctly.
                private_key = raw_key.replace("\\n", "\n").strip()
                key_source = "env:APPLE_P8_KEY_CONTENT"
            else:
                logger.error(
                    "❌ Apple .p8 key not found. Checked file '%s' and env APPLE_P8_KEY_CONTENT.",
                    APPLE_P8_KEY_PATH
                )
                raise HTTPException(
                    status_code=500,
                    detail="Server misconfiguration: Apple .p8 key not found."
                )

        # ── Validate PEM format ──
        if "-----BEGIN PRIVATE KEY-----" not in private_key:
            logger.error(
                "❌ .p8 key from %s does not contain valid PEM header. "
                "Key length: %d, first 30 chars: '%s'",
                key_source, len(private_key), private_key[:30]
            )
            raise HTTPException(
                status_code=500,
                detail="Server misconfiguration: .p8 key is not valid PEM format."
            )

        # ── Diagnostic logging (safe — no secrets exposed) ──
        logger.info(
            "🔐 Generating client_secret: team=%s, key_id=%s, client_id=%s, source=%s, key_len=%d",
            APPLE_TEAM_ID, APPLE_KEY_ID, APPLE_CLIENT_ID, key_source, len(private_key)
        )

        now = int(time.time())
        payload = {
            "iss": APPLE_TEAM_ID,
            "iat": now,
            "exp": now + (86400 * 180),  # Max 6 months
            "aud": "https://appleid.apple.com",
            "sub": APPLE_CLIENT_ID,
        }
        headers = {
            "kid": APPLE_KEY_ID,
            "alg": "ES256",
        }
        return jwt.encode(payload, private_key, algorithm="ES256", headers=headers)

    @classmethod
    def exchange_code_for_token(cls, authorization_code: str) -> str:
        """
        Exchange Apple authorizationCode for a refresh_token.
        This is Step 1 of the revocation flow.
        """
        client_secret = cls.generate_client_secret()

        response = requests.post(
            "https://appleid.apple.com/auth/token",
            data={
                "client_id": APPLE_CLIENT_ID,
                "client_secret": client_secret,
                "code": authorization_code,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )

        if response.status_code != 200:
            # Parse Apple's error for specific diagnosis
            error_body = response.text
            apple_error = ""
            try:
                error_data = response.json()
                apple_error = error_data.get("error", "")
            except Exception:
                pass

            # ── Targeted diagnostics per Apple error code ──
            if apple_error == "invalid_client":
                logger.error(
                    "❌ Apple /auth/token → invalid_client. "
                    "Check: (1) APPLE_TEAM_ID='%s' is correct, "
                    "(2) APPLE_KEY_ID='%s' matches the .p8 key, "
                    "(3) APPLE_P8_KEY_CONTENT has proper newlines (not escaped \\\\n), "
                    "(4) The key has 'Sign in with Apple' enabled in Apple Developer Console.",
                    APPLE_TEAM_ID, APPLE_KEY_ID
                )
            elif apple_error == "invalid_grant":
                logger.error(
                    "❌ Apple /auth/token → invalid_grant. "
                    "The authorization code has expired or was already used. "
                    "Codes are single-use and expire in 5 minutes."
                )
            else:
                logger.error(
                    "❌ Apple /auth/token failed: %d %s",
                    response.status_code, error_body
                )

            raise HTTPException(
                status_code=502,
                detail=f"Apple token exchange failed: {apple_error or error_body}"
            )

        data = response.json()
        refresh_token = data.get("refresh_token")
        if not refresh_token:
            raise HTTPException(
                status_code=502,
                detail="Apple did not return a refresh_token."
            )
        return refresh_token

    @classmethod
    def revoke_apple_token(cls, authorization_code: str) -> bool:
        """
        Full Apple token revocation flow (Guideline 5.1.1):
        1. Exchange authorizationCode → refresh_token
        2. POST /auth/revoke with refresh_token
        Idempotent: re-revoking an already-revoked token returns 200.
        """
        # Step 1: Get refresh_token
        refresh_token = cls.exchange_code_for_token(authorization_code)

        # Step 2: Revoke
        client_secret = cls.generate_client_secret()

        response = requests.post(
            "https://appleid.apple.com/auth/revoke",
            data={
                "client_id": APPLE_CLIENT_ID,
                "client_secret": client_secret,
                "token": refresh_token,
                "token_type_hint": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )

        if response.status_code == 200:
            logger.info("✅ Apple token revoked successfully")
            return True
        else:
            logger.error(f"Apple /auth/revoke failed: {response.status_code} {response.text}")
            raise HTTPException(
                status_code=502,
                detail="Failed to revoke Apple token. Account deletion aborted."
            )

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

