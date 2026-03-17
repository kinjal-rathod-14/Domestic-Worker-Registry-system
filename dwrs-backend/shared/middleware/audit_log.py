"""
Audit Log Middleware
Automatically creates tamper-proof audit records for every state-changing request.
Attaches to FastAPI as middleware — fires after every non-GET response.
"""
import time
import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from services.audit.services.hash_chain import AuditChain

logger = structlog.get_logger()
audit_chain = AuditChain()

# Methods that mutate state — these get audited
AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths that are excluded from audit (health checks, metrics)
EXCLUDED_PATHS = {"/health", "/metrics", "/docs", "/openapi.json"}


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in AUDITED_METHODS:
            return await call_next(request)

        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        start_time = time.time()

        # Extract actor from JWT (already validated by auth middleware)
        actor_id = getattr(request.state, "user_id", "anonymous")
        actor_role = getattr(request.state, "user_role", "unknown")

        response = await call_next(request)

        duration_ms = int((time.time() - start_time) * 1000)

        # Only audit successful mutations (2xx, 201, etc.)
        if 200 <= response.status_code < 300:
            try:
                await audit_chain.append(
                    actor_id=actor_id,
                    action=f"{request.method}:{request.url.path}",
                    entity_type=extract_entity_type(request.url.path),
                    entity_id=extract_entity_id(request.url.path),
                    before_state=None,   # Set per-endpoint for full before/after
                    after_state=None,
                    request_context=RequestContext(
                        ip=request.client.host,
                        role=actor_role,
                        session_id=getattr(request.state, "session_id", None),
                        duration_ms=duration_ms,
                    )
                )
            except Exception as e:
                # Audit failure is critical — log but don't break the response
                logger.error("audit_log_failed", error=str(e), path=request.url.path)

        return response


def extract_entity_type(path: str) -> str:
    """Derive entity type from URL path segment."""
    segments = [s for s in path.split("/") if s]
    return segments[0] if segments else "unknown"


def extract_entity_id(path: str) -> str | None:
    """Extract UUID from path if present."""
    import re
    uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    match = re.search(uuid_pattern, path)
    return match.group(0) if match else None


class RequestContext:
    def __init__(self, ip, role, session_id, duration_ms):
        self.ip = ip
        self.role = role
        self.session_id = session_id
        self.duration_ms = duration_ms
