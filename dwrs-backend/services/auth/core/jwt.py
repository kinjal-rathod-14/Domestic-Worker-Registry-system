"""
JWT token creation and validation using RS256 (asymmetric).
Private key signs tokens; public key verifies them.
This allows verification services to validate tokens without the private key.
"""
import uuid
from datetime import datetime, timedelta, timezone
from jose import jwt
from shared.utils.config import settings


def create_jwt(user, session_id: str, expires_minutes: int = 60) -> str:
    """
    Create a signed JWT access token.
    Claims:
      sub    - user ID
      sid    - session ID (for Redis session binding)
      role   - user role
      district_scope - officer's assigned district (None for other roles)
      exp    - expiry timestamp
      iat    - issued at
      jti    - unique token ID (for revocation if needed)
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "sid": session_id,
        "username": user.username,
        "role": user.role,
        "district_scope": getattr(user, "district_id", None),
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_PRIVATE_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str, session_id: str) -> str:
    """
    Create a refresh token with longer expiry.
    Refresh tokens are bound to the session ID and validated against Redis.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "sid": session_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_PRIVATE_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises JWTError on failure."""
    return jwt.decode(token, settings.JWT_PUBLIC_KEY, algorithms=[settings.JWT_ALGORITHM])
