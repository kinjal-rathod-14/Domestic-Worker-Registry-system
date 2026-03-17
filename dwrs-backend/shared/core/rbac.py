"""
Role-Based Access Control (RBAC)
Deny-by-default permission system for DWRS.
"""
from enum import Enum
from typing import List
from fastapi import HTTPException, Depends
from shared.middleware.auth_middleware import get_current_user
from shared.utils.validators import log_access_attempt


class Role(str, Enum):
    WORKER = "worker"
    EMPLOYER = "employer"
    FIELD_OFFICER = "field_officer"
    SUPERVISOR = "supervisor"
    ADMIN = "admin"
    AUDITOR = "auditor"  # Read-only immutable audit access


# Explicit whitelist — anything not listed is DENIED
ROLE_PERMISSIONS: dict[Role, List[str]] = {
    Role.WORKER: [
        "registration:self_register",
        "registration:view_own",
        "profile:update_own",
    ],
    Role.EMPLOYER: [
        "registration:assisted_register",
        "worker:verify_employment",
        "profile:view_assigned",
    ],
    Role.FIELD_OFFICER: [
        "registration:assisted_register",
        "verification:conduct",
        "worker:view_assigned_district",
        # Explicitly CANNOT: reassign workers, override risk scores, delete records
    ],
    Role.SUPERVISOR: [
        "registration:assisted_register",
        "verification:conduct",
        "verification:override_with_reason",   # Requires dual-auth + reason
        "worker:view_all_district",
        "officer:view_activity",
        "risk:review_flagged",
    ],
    Role.ADMIN: [
        "admin:manage_officers",
        "admin:manage_districts",
        "admin:view_reports",
        "admin:configure_thresholds",
        "officer:suspend",
        # Explicitly CANNOT: delete audit logs, modify historical records
    ],
    Role.AUDITOR: [
        "audit:read_all",
        "report:generate",
        "worker:view_all",   # Read-only
    ],
}


def require_permission(permission: str):
    """FastAPI dependency — raises 403 if user lacks the required permission."""
    def checker(current_user=Depends(get_current_user)):
        user_permissions = ROLE_PERMISSIONS.get(current_user.role, [])
        if permission not in user_permissions:
            incident_id = log_access_attempt(current_user, permission)
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "PERMISSION_DENIED",
                    "required_permission": permission,
                    "user_role": current_user.role,
                    "incident_id": incident_id,
                }
            )
        return current_user
    return checker


def has_permission(role: Role, permission: str) -> bool:
    """Utility check — does this role have the permission?"""
    return permission in ROLE_PERMISSIONS.get(role, [])
