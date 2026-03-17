"""
Verification Service — ID / Face / Geo verification endpoint
Anti-corruption constraint: verifying officer cannot be the registering officer.
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from shared.middleware.auth_middleware import get_current_user, CurrentUser
from shared.core.rbac import require_permission
from shared.events.kafka_producer import publish_event
from services.verification.services.face_match import face_match_service
from services.verification.services.geo_validate import geo_validate
from services.verification.services.id_validator import validate_liveness
from shared.db.postgres import db
import uuid

logger = structlog.get_logger()
router = APIRouter(prefix="/verification", tags=["Verification"])


class VerificationRequest(BaseModel):
    face_photo_b64: str | None = None      # Live capture
    liveness_token: str | None = None      # Anti-spoofing token from SDK
    geo_location: dict                     # {lat, lng, accuracy_meters}
    notes: str | None = None              # Officer notes (optional)


@router.post("/verify/{worker_id}", status_code=200)
async def verify_worker(
    worker_id: str,
    payload: VerificationRequest,
    current_user: CurrentUser = Depends(require_permission("verification:conduct")),
):
    """
    Conduct secondary verification on a registered worker.
    Checks face match, geo proximity, and liveness.
    Cannot be performed by the officer who registered the worker.
    """
    worker = await db.fetchrow("SELECT * FROM workers WHERE id = $1", worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    # ── Anti-corruption: same officer cannot register AND verify ────────────
    reg = await db.fetchrow(
        "SELECT officer_id FROM registrations WHERE worker_id = $1", worker_id
    )
    if reg and str(reg["officer_id"]) == current_user.id:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "SAME_OFFICER_CONFLICT",
                "message": "The verifying officer cannot be the same as the registering officer",
                "policy": "Dual-officer verification policy enforced",
            }
        )

    results = {}

    # ── Face verification ───────────────────────────────────────────────────
    if payload.face_photo_b64:
        try:
            face_result = await face_match_service.compare(
                stored_photo_url=worker["photo_url"],
                live_photo_b64=payload.face_photo_b64,
            )
            results["face_match"] = {
                "passed": face_result.similarity >= 0.85,
                "confidence": round(face_result.similarity, 4),
                "threshold": 0.85,
                "method": "aws_rekognition",
            }
        except Exception as e:
            logger.error("face_match_error", worker_id=worker_id, error=str(e))
            results["face_match"] = {"passed": False, "error": "face_service_unavailable"}

    # ── Geo validation ───────────────────────────────────────────────────────
    try:
        geo_result = await geo_validate(
            claimed_address=worker["address"],
            verification_location=payload.geo_location,
        )
        results["geo_match"] = {
            "passed": geo_result.distance_km <= 2.0,
            "distance_km": round(geo_result.distance_km, 3),
            "threshold_km": 2.0,
        }
    except Exception as e:
        logger.error("geo_validate_error", worker_id=worker_id, error=str(e))
        results["geo_match"] = {"passed": False, "error": "geo_service_unavailable"}

    # ── Liveness check ───────────────────────────────────────────────────────
    if payload.liveness_token:
        liveness = await validate_liveness(payload.liveness_token)
        results["liveness"] = {"passed": liveness.is_live, "score": liveness.score}

    # ── Determine overall decision ───────────────────────────────────────────
    critical_checks = ["face_match", "geo_match"]
    critical_passed = all(
        results.get(k, {}).get("passed", False) for k in critical_checks if k in results
    )
    decision = "approved" if critical_passed else "failed"

    # ── Persist verification record ──────────────────────────────────────────
    verification_id = str(uuid.uuid4())
    await db.execute("""
        INSERT INTO verification_records (
            id, worker_id, officer_id, face_match_score, geo_match_passed,
            geo_distance_km, liveness_passed, decision, notes, verified_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
    """,
        verification_id,
        worker_id,
        current_user.id,
        results.get("face_match", {}).get("confidence"),
        results.get("geo_match", {}).get("passed"),
        results.get("geo_match", {}).get("distance_km"),
        results.get("liveness", {}).get("passed"),
        decision,
        payload.notes,
    )

    # ── Update worker status if approved ────────────────────────────────────
    if decision == "approved":
        await db.execute(
            "UPDATE workers SET status = 'verified', updated_at = NOW() WHERE id = $1",
            worker_id
        )

    await publish_event("verification.completed", {
        "worker_id": worker_id,
        "officer_id": current_user.id,
        "decision": decision,
        "results": results,
        "verification_id": verification_id,
    })

    logger.info(
        "verification_completed",
        worker_id=worker_id,
        decision=decision,
        officer_id=current_user.id,
    )

    return {
        "verification_id": verification_id,
        "worker_id": worker_id,
        "status": "verified" if decision == "approved" else "verification_failed",
        "decision": decision,
        "results": results,
        "verified_by": current_user.id,
    }
