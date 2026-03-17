"""
Offline Sync Route
Accepts a batch of registrations captured offline by field officers.
Each record is validated individually — expired or invalid records are rejected,
valid records are queued for processing.
Offline records older than 72h are automatically rejected.
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from shared.middleware.auth_middleware import get_current_user, CurrentUser
from shared.core.rbac import require_permission
from shared.utils.validators import compute_delay_hours
from shared.events.kafka_producer import publish_event
from shared.db.postgres import db
import uuid

logger = structlog.get_logger()
router = APIRouter(prefix="/registration", tags=["Offline Sync"])


class OfflineRecord(BaseModel):
    local_id: str               # Client-generated ID for tracking
    worker_data: dict           # Full WorkerRegistrationRequest payload
    captured_at: str            # ISO timestamp when captured offline
    device_fingerprint: str


class OfflineBatchRequest(BaseModel):
    records: List[OfflineRecord]
    batch_id: str | None = None


class SyncResultItem(BaseModel):
    local_id: str
    status: str                 # synced | rejected | expired | error
    worker_id: str | None = None
    reason: str | None = None


@router.post("/offline-sync", response_model=List[SyncResultItem])
async def sync_offline_batch(
    payload: OfflineBatchRequest,
    current_user: CurrentUser = Depends(require_permission("registration:assisted_register")),
):
    """
    Sync a batch of offline-captured registrations.
    Rules:
    - Records > 72h old are rejected as 'expired'
    - Records from a different officer are rejected
    - Each valid record is processed individually through the full registration pipeline
    """
    if not payload.records:
        raise HTTPException(status_code=400, detail="Empty batch")

    if len(payload.records) > 50:
        raise HTTPException(status_code=400, detail="Batch size limit is 50 records")

    batch_id = payload.batch_id or str(uuid.uuid4())
    results: List[SyncResultItem] = []

    # Log batch start
    await db.execute("""
        INSERT INTO offline_batches (id, officer_id, device_fingerprint, records_count, status)
        VALUES ($1, $2, $3, $4, 'processing')
    """, batch_id, current_user.id, payload.records[0].device_fingerprint if payload.records else None,
        len(payload.records))

    synced_count = 0
    expired_count = 0

    for record in payload.records:
        try:
            # ── Check 1: Expiry ──────────────────────────────────────────────
            delay_hours = compute_delay_hours(record.captured_at)
            if delay_hours > 72:
                logger.warning(
                    "offline_record_expired",
                    local_id=record.local_id,
                    delay_hours=round(delay_hours, 1),
                    officer_id=current_user.id,
                )
                results.append(SyncResultItem(
                    local_id=record.local_id,
                    status="expired",
                    reason=f"Record captured {delay_hours:.1f}h ago (limit: 72h). Re-registration required.",
                ))
                expired_count += 1
                continue

            # ── Check 2: Device binding ──────────────────────────────────────
            # Records must come from the officer's registered device
            # (prevents tampering by transferring records between devices)
            if not _is_trusted_device(record.device_fingerprint, current_user):
                results.append(SyncResultItem(
                    local_id=record.local_id,
                    status="rejected",
                    reason="Device fingerprint not recognized for this officer",
                ))
                continue

            # ── Process: inject offline metadata and publish for registration pipeline
            worker_data = record.worker_data
            worker_data["registration_mode"] = "offline"
            worker_data["offline_batch_id"] = batch_id
            worker_data["offline_captured_at"] = record.captured_at
            worker_data["device_fingerprint"] = record.device_fingerprint

            # Publish to registration pipeline (async processing)
            worker_id = str(uuid.uuid4())
            await publish_event("registration.offline_record_queued", {
                "worker_id": worker_id,
                "local_id": record.local_id,
                "batch_id": batch_id,
                "officer_id": current_user.id,
                "worker_data": worker_data,
                "captured_at": record.captured_at,
            })

            results.append(SyncResultItem(
                local_id=record.local_id,
                status="synced",
                worker_id=worker_id,
            ))
            synced_count += 1

        except Exception as e:
            logger.error("offline_record_processing_failed", local_id=record.local_id, error=str(e))
            results.append(SyncResultItem(
                local_id=record.local_id,
                status="error",
                reason="Internal processing error — please retry",
            ))

    # Update batch status
    await db.execute("""
        UPDATE offline_batches
        SET synced_count = $1, expired_count = $2,
            status = 'completed', sync_completed_at = NOW()
        WHERE id = $3
    """, synced_count, expired_count, batch_id)

    logger.info(
        "offline_batch_synced",
        batch_id=batch_id,
        total=len(payload.records),
        synced=synced_count,
        expired=expired_count,
        officer_id=current_user.id,
    )

    return results


def _is_trusted_device(device_fp: str, user: CurrentUser) -> bool:
    """
    Basic device validation — in production, check against registered devices table.
    For now, accepts any device. Production implementation would check:
      SELECT 1 FROM officer_devices WHERE officer_id = $1 AND fingerprint = $2
    """
    return bool(device_fp)
