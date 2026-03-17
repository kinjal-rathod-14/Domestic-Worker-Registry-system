"""
Audit Service Routes
Read-only endpoints for auditors and admins to query the audit chain.
Also exposes the chain integrity verification endpoint.
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from shared.middleware.auth_middleware import get_current_user, CurrentUser
from shared.core.rbac import require_permission
from shared.db.postgres import db
from services.audit.services.hash_chain import AuditChain

logger = structlog.get_logger()
router = APIRouter(prefix="/audit", tags=["Audit"])
audit_chain = AuditChain()


@router.get("/records")
async def list_audit_records(
    entity_type: str | None = Query(None, description="Filter by entity type"),
    entity_id: str | None = Query(None, description="Filter by entity UUID"),
    actor_id: str | None = Query(None, description="Filter by actor UUID"),
    from_date: str | None = Query(None, description="ISO date from"),
    to_date: str | None = Query(None, description="ISO date to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_permission("audit:read_all")),
):
    """
    Query audit records with filters.
    Accessible to: auditor, admin.
    Results are read-only — no modifications allowed.
    """
    conditions = []
    params = []
    idx = 1

    if entity_type:
        conditions.append(f"entity_type = ${idx}")
        params.append(entity_type)
        idx += 1
    if entity_id:
        conditions.append(f"entity_id = ${idx}::uuid")
        params.append(entity_id)
        idx += 1
    if actor_id:
        conditions.append(f"actor_id = ${idx}::uuid")
        params.append(actor_id)
        idx += 1
    if from_date:
        conditions.append(f"created_at >= ${idx}::timestamptz")
        params.append(from_date)
        idx += 1
    if to_date:
        conditions.append(f"created_at <= ${idx}::timestamptz")
        params.append(to_date)
        idx += 1

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    offset = (page - 1) * page_size

    records = await db.fetch(f"""
        SELECT id, actor_id, actor_role, action, entity_type, entity_id,
               ip_address, created_at, record_hash, prev_hash
        FROM audit_records
        {where_clause}
        ORDER BY created_at DESC
        LIMIT {page_size} OFFSET {offset}
    """, *params)

    total = await db.fetchval(f"SELECT COUNT(*) FROM audit_records {where_clause}", *params)

    return {
        "records": [dict(r) for r in records],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/records/{record_id}")
async def get_audit_record(
    record_id: str,
    current_user: CurrentUser = Depends(require_permission("audit:read_all")),
):
    """Get a single audit record including full before/after state."""
    record = await db.fetchrow(
        "SELECT * FROM audit_records WHERE id = $1::uuid", record_id
    )
    if not record:
        raise HTTPException(status_code=404, detail="Audit record not found")
    return dict(record)


@router.post("/verify-chain")
async def verify_chain_integrity(
    current_user: CurrentUser = Depends(require_permission("audit:read_all")),
):
    """
    Trigger a full audit chain integrity verification.
    Checks that every record's hash matches the computed hash.
    A broken chain means a record was tampered with.
    This is also run nightly by the Celery cron task.
    """
    logger.info("manual_chain_verification_triggered", triggered_by=current_user.id)
    result = await audit_chain.verify_chain_integrity()
    return {
        "chain_valid": result["valid"],
        "records_verified": result["records_checked"],
        "broken_at_record": result.get("broken_at"),
        "triggered_by": current_user.id,
        "message": "Chain integrity verified successfully." if result["valid"]
                   else "WARNING: Chain integrity violation detected! Security team has been alerted.",
    }


@router.get("/officer/{officer_id}/activity")
async def officer_activity_summary(
    officer_id: str,
    days: int = Query(30, ge=1, le=365),
    current_user: CurrentUser = Depends(require_permission("officer:view_activity")),
):
    """
    Summary of an officer's recent activity for supervisor review.
    Includes registration counts, geo patterns, and anomaly flags.
    """
    records = await db.fetch("""
        SELECT action_type, COUNT(*) as count,
               AVG(geo_lat) as avg_lat, AVG(geo_lng) as avg_lng,
               MIN(created_at) as first_at, MAX(created_at) as last_at
        FROM officer_activity_logs
        WHERE officer_id = $1::uuid
          AND created_at > NOW() - ($2 || ' days')::INTERVAL
        GROUP BY action_type
        ORDER BY count DESC
    """, officer_id, str(days))

    officer = await db.fetchrow(
        "SELECT badge_number, trust_score, anomaly_flags, is_suspended FROM officers WHERE id = $1::uuid",
        officer_id,
    )
    if not officer:
        raise HTTPException(status_code=404, detail="Officer not found")

    return {
        "officer_id": officer_id,
        "badge_number": officer["badge_number"],
        "trust_score": float(officer["trust_score"]),
        "anomaly_flags": officer["anomaly_flags"],
        "is_suspended": officer["is_suspended"],
        "activity_summary": [dict(r) for r in records],
        "period_days": days,
    }
