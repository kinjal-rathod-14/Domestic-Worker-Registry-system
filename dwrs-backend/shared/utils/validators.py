"""
Shared validation and utility functions.
"""
import re
import uuid
import structlog
from datetime import datetime, timezone
from rapidfuzz import fuzz
from shared.db.postgres import db

logger = structlog.get_logger()


def fuzzy_name_match(name_a: str, name_b: str) -> float:
    """
    Returns a similarity score 0–1 between two names.
    Uses token_sort_ratio to handle word-order differences (e.g. 'Ravi Kumar' vs 'Kumar Ravi').
    """
    if not name_a or not name_b:
        return 0.0
    score = fuzz.token_sort_ratio(
        name_a.strip().lower(),
        name_b.strip().lower(),
    )
    return round(score / 100.0, 4)


def compute_delay_hours(captured_at_iso: str) -> float:
    """Returns how many hours ago an ISO timestamp was."""
    try:
        captured = datetime.fromisoformat(captured_at_iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - captured
        return delta.total_seconds() / 3600
    except Exception:
        return 9999.0   # Treat unparseable timestamps as very stale


def is_within_polygon(geo: dict, boundary: dict) -> bool:
    """Check if {lat, lng} is within a GeoJSON polygon."""
    try:
        from shapely.geometry import Point, Polygon
        coords = boundary.get("coordinates", [[]])[0]
        polygon = Polygon([(c[0], c[1]) for c in coords])
        point = Point(geo.get("lng"), geo.get("lat"))
        return polygon.contains(point)
    except Exception as e:
        logger.warning("polygon_check_failed", error=str(e))
        return True   # Soft pass on error


def is_valid_aadhaar(aadhaar: str) -> bool:
    """Basic format validation — 12 digits."""
    return bool(re.match(r"^\d{12}$", aadhaar))


def is_valid_mobile_india(mobile: str) -> bool:
    """Validate Indian mobile number (10 digits starting with 6–9)."""
    cleaned = re.sub(r"[\s\-\+]", "", mobile)
    cleaned = cleaned.lstrip("91")  # Remove country code if present
    return bool(re.match(r"^[6-9]\d{9}$", cleaned))


def generate_registration_number(worker_id: str) -> str:
    """
    Generate human-readable registration number.
    Format: DWRS-YYYYMM-XXXXXX (last 6 chars of worker UUID)
    """
    now = datetime.now()
    suffix = worker_id.replace("-", "")[:6].upper()
    return f"DWRS-{now.strftime('%Y%m')}-{suffix}"


def log_access_attempt(user, permission: str) -> str:
    """Log an unauthorized access attempt and return an incident ID."""
    incident_id = str(uuid.uuid4())
    logger.warning(
        "unauthorized_access_attempt",
        user_id=user.id,
        role=user.role,
        permission_required=permission,
        incident_id=incident_id,
    )
    return incident_id


def sanitize_for_log(data: dict) -> dict:
    """Remove sensitive fields before logging."""
    sensitive_keys = {
        "aadhaar_number", "aadhaar_enc", "password", "password_hash",
        "totp_secret", "mobile_number", "mobile_enc", "photo_base64",
    }
    return {k: "***REDACTED***" if k in sensitive_keys else v for k, v in data.items()}
