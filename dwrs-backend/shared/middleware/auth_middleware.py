"""
Authentication Middleware
Validates JWT tokens and extracts the current user for every request.
"""
import structlog
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from shared.db.redis_client import redis_client
from shared.utils.config import settings

logger = structlog.get_logger()
security = HTTPBearer()


class CurrentUser(BaseModel):
    id: str
    username: str
    role: str
    district_scope: str | None = None   # Set for field_officer only
    session_id: str
    device_fingerprint: str | None = None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> CurrentUser:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.JWT_PUBLIC_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as e:
        logger.warning("jwt_decode_failed", error=str(e))
        raise credentials_exception

    user_id: str = payload.get("sub")
    session_id: str = payload.get("sid")
    if not user_id or not session_id:
        raise credentials_exception

    # Validate session is still active in Redis (prevents token reuse after logout)
    session = await redis_client.get(f"session:{session_id}")
    if not session:
        raise HTTPException(status_code=401, detail="Session expired or logged out")

    if session.get("user_id") != user_id:
        logger.error("session_user_mismatch", token_user=user_id, session_user=session.get("user_id"))
        raise HTTPException(status_code=401, detail="Invalid session binding")

    return CurrentUser(
        id=user_id,
        username=payload.get("username"),
        role=payload.get("role"),
        district_scope=payload.get("district_scope"),
        session_id=session_id,
        device_fingerprint=session.get("device"),
    )
