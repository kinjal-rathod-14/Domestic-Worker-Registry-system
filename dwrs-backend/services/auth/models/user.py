from pydantic import BaseModel
from shared.db.postgres import db
import structlog

logger = structlog.get_logger()

class User(BaseModel):
    id: str
    username: str
    password_hash: str
    totp_secret: str | None = None
    role: str
    district_id: str | None = None
    is_suspended: bool = False

async def get_user_by_username(username: str) -> User | None:
    row = await db.fetchrow("SELECT * FROM users WHERE username = ?", username)
    if row:
        return User(**row)
    return None

async def get_user_by_id(user_id: str) -> User | None:
    row = await db.fetchrow("SELECT * FROM users WHERE id = ?", user_id)
    if row:
        return User(**row)
    return None

async def suspend_user_temporarily(user_id: str, reason: str):
    await db.execute("UPDATE users SET is_suspended = 1, suspension_reason = ? WHERE id = ?", reason, user_id)
    logger.info("user_suspended", user_id=user_id, reason=reason)
