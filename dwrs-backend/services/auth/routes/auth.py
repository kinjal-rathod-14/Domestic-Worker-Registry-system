"""
Auth Service — Login, MFA, Token Refresh, Logout
"""
import uuid
import time
import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from shared.db.redis_client import redis_client
from shared.events.kafka_producer import publish_event
from shared.utils.encryption import verify_password
from services.auth.core.jwt import create_jwt, create_refresh_token
from services.auth.core.totp import verify_totp
from services.auth.models.user import get_user_by_username
from services.verification.services.geo_validate import is_within_assigned_district

logger = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: str | None = None        # Required for officer+ roles
    device_fingerprint: str
    geo_location: dict | None = None    # {lat, lng, accuracy_meters}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    role: str
    district_scope: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str
    device_fingerprint: str


@router.post("/token", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    """
    Authenticate user and issue JWT tokens.
    Officers/admins require TOTP (MFA).
    """
    user = await get_user_by_username(req.username)

    # Generic error — never reveal whether username exists
    if not user or not verify_password(req.password, user.password_hash):
        await publish_event("auth.failed_login", {
            "username": req.username,
            "ip": request.client.host,
            "timestamp": time.time(),
            "device": req.device_fingerprint,
        })
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if user.is_suspended:
        raise HTTPException(status_code=403, detail="ACCOUNT_SUSPENDED")

    # Officers and above MUST provide TOTP
    mfa_required_roles = {"field_officer", "supervisor", "admin", "auditor"}
    if user.role in mfa_required_roles:
        if not req.totp_code:
            raise HTTPException(status_code=403, detail="MFA_REQUIRED")
        if not verify_totp(user.totp_secret, req.totp_code):
            await _flag_suspicious_login(user.id, "invalid_totp", request.client.host)
            raise HTTPException(status_code=401, detail="Invalid MFA code")

    # Geo-zone check for field officers (soft check — flags, does not block)
    if user.role == "field_officer" and req.geo_location:
        in_zone = await is_within_assigned_district(user.district_id, req.geo_location)
        if not in_zone:
            await publish_event("security.officer_out_of_zone", {
                "officer_id": user.id,
                "claimed_location": req.geo_location,
                "assigned_district": user.district_id,
                "ip": request.client.host,
            })
            # Log but don't block — pattern analysis handles enforcement

    session_id = str(uuid.uuid4())
    access_token = create_jwt(user, session_id, expires_minutes=60)
    refresh_token_value = create_refresh_token(user.id, session_id)

    # Store session with device binding in Redis
    await redis_client.setex(
        f"session:{session_id}",
        3600,
        {
            "user_id": user.id,
            "device": req.device_fingerprint,
            "role": user.role,
            "district_scope": user.district_id,
        }
    )

    await publish_event("auth.login_success", {
        "user_id": user.id,
        "role": user.role,
        "session_id": session_id,
        "ip": request.client.host,
        "timestamp": time.time(),
    })

    logger.info("login_success", user_id=user.id, role=user.role)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_value,
        expires_in=3600,
        role=user.role,
        district_scope=user.district_id if user.role == "field_officer" else None,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest, request: Request):
    """Issue new access token using refresh token."""
    payload = await validate_refresh_token(req.refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Validate device binding hasn't changed
    session = await redis_client.get(f"session:{payload['session_id']}")
    if not session or session.get("device") != req.device_fingerprint:
        raise HTTPException(status_code=401, detail="Device fingerprint mismatch")

    user = await get_user_by_id(payload["user_id"])
    new_access_token = create_jwt(user, payload["session_id"], expires_minutes=60)

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=req.refresh_token,  # Rotate in production
        expires_in=3600,
        role=user.role,
    )


@router.post("/logout")
async def logout(request: Request):
    """Invalidate session immediately."""
    session_id = getattr(request.state, "session_id", None)
    if session_id:
        await redis_client.delete(f"session:{session_id}")
    return {"message": "Logged out successfully"}


async def _flag_suspicious_login(user_id: str, reason: str, ip: str):
    """Increment failed attempt counter; suspend after 5 failures in 10 min."""
    key = f"failed_login:{user_id}"
    count = await redis_client.incr(key)
    await redis_client.expire(key, 600)   # 10 minute window
    if count >= 5:
        await suspend_user_temporarily(user_id, reason=f"Too many failed logins ({reason})")
        await publish_event("security.account_locked", {
            "user_id": user_id, "reason": reason, "ip": ip
        })
