"""
Registration Service — Worker Registration Endpoint
Handles self, assisted (officer/employer), and offline-sync registration modes.
"""
import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, validator

from shared.middleware.auth_middleware import get_current_user, CurrentUser
from shared.core.rbac import require_permission, Role
from shared.events.kafka_producer import publish_event
from services.verification.services.id_validator import validate_aadhaar
from services.verification.services.geo_validate import is_within_assigned_district
from services.registration.services.dedup import check_duplicates
from services.risk_scoring.engine import compute_risk_score
from services.registration.models.worker import (
    create_worker_record, generate_registration_number
)

logger = structlog.get_logger()
router = APIRouter(prefix="/registration", tags=["Registration"])


class WorkerRegistrationRequest(BaseModel):
    full_name: str
    aadhaar_number: str
    date_of_birth: str              # ISO format: YYYY-MM-DD
    gender: str                     # M | F | T

    photo_base64: str               # JPEG/PNG, max 2MB, validated face

    mobile_number: str | None = None
    alternate_contact: str | None = None   # Family member / employer if no phone
    address: dict                   # {house, street, village, district, state, pincode}

    registration_mode: str          # self | assisted_officer | assisted_employer | offline
    assisted_by_officer_id: str | None = None
    employer_id: str | None = None

    geo_location: dict              # {lat, lng, accuracy_meters, timestamp}
    consent_recorded: bool
    consent_witness: str | None = None   # For assisted registrations

    # Offline sync fields
    offline_batch_id: str | None = None
    offline_captured_at: str | None = None   # ISO timestamp

    @validator("aadhaar_number")
    def validate_aadhaar_format(cls, v):
        if not v.isdigit() or len(v) != 12:
            raise ValueError("Aadhaar must be exactly 12 digits")
        return v

    @validator("consent_recorded")
    def consent_must_be_true(cls, v):
        if not v:
            raise ValueError("Informed consent must be explicitly recorded before registration")
        return v

    @validator("geo_location")
    def validate_geo(cls, v):
        if "lat" not in v or "lng" not in v:
            raise ValueError("geo_location must contain lat and lng")
        accuracy = v.get("accuracy_meters", 9999)
        if accuracy > 200:
            raise ValueError("GPS accuracy must be within 200 meters for officer-assisted registration")
        return v


@router.post("/worker", status_code=201)
async def register_worker(
    payload: WorkerRegistrationRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Register a domestic worker. Runs duplicate check, ID validation,
    geo validation, and risk scoring before persisting.
    """
    # ── STEP 1: Permission & scope enforcement ──────────────────────────────
    _validate_registration_permission(payload, current_user)

    # Field officers are scoped to their assigned district only
    if current_user.role == Role.FIELD_OFFICER:
        worker_district = payload.address.get("district")
        if worker_district != current_user.district_scope:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "DISTRICT_SCOPE_VIOLATION",
                    "message": "Worker's district does not match officer's assigned district",
                    "officer_district": current_user.district_scope,
                    "worker_district": worker_district,
                }
            )

    # ── STEP 2: Aadhaar validation via UIDAI ────────────────────────────────
    id_result = await validate_aadhaar(
        aadhaar=payload.aadhaar_number,
        name=payload.full_name,
        dob=payload.date_of_birth,
    )
    if not id_result.is_valid:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "ID_VALIDATION_FAILED",
                "reason": id_result.failure_reason,
                "hint": "Verify Aadhaar number and ensure the name matches exactly as on Aadhaar card",
            }
        )

    # ── STEP 3: Duplicate detection (block BEFORE saving) ───────────────────
    dedup_result = await check_duplicates(
        aadhaar=payload.aadhaar_number,
        name=payload.full_name,
        dob=payload.date_of_birth,
        photo_b64=payload.photo_base64,
    )
    if dedup_result.is_duplicate:
        logger.warning(
            "duplicate_registration_blocked",
            match_type=dedup_result.match_type,
            registrar_id=current_user.id,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "error": "DUPLICATE_REGISTRATION",
                "match_type": dedup_result.match_type,
                "confidence": dedup_result.confidence_score,
                "existing_worker_id": dedup_result.existing_worker_id,
                "message": "A registration already exists for this individual",
            }
        )

    # ── STEP 4: Risk scoring ─────────────────────────────────────────────────
    risk_result = await compute_risk_score(
        worker_data=payload.dict(),
        registrar=current_user,
        id_validation=id_result,
        dedup_result=dedup_result,
    )

    # ── STEP 5: Persist worker record ───────────────────────────────────────
    worker_id = str(uuid.uuid4())
    reg_number = generate_registration_number(worker_id)

    await create_worker_record(
        worker_id=worker_id,
        registration_number=reg_number,
        payload=payload,
        risk_result=risk_result,
        id_result=id_result,
        registered_by=current_user.id,
    )

    status = "registered" if risk_result.score < 40 else "pending_verification"

    # ── STEP 6: Publish event for async processing ──────────────────────────
    await publish_event("registration.worker_created", {
        "worker_id": worker_id,
        "registration_number": reg_number,
        "risk_score": risk_result.score,
        "risk_level": risk_result.level,
        "risk_flags": [f.rule_id for f in risk_result.flags],
        "registrar_id": current_user.id,
        "registrar_role": current_user.role,
        "registration_mode": payload.registration_mode,
        "requires_secondary_verification": risk_result.score >= 60,
        "status": status,
    })

    # ── STEP 7: High-risk → immediate supervisor review ──────────────────────
    if risk_result.score >= 60:
        background_tasks.add_task(
            flag_for_supervisor_review,
            worker_id=worker_id,
            risk_result=risk_result,
            registrar_id=current_user.id,
        )

    logger.info(
        "worker_registered",
        worker_id=worker_id,
        risk_score=risk_result.score,
        risk_level=risk_result.level,
        registrar=current_user.id,
    )

    return {
        "worker_id": worker_id,
        "registration_number": reg_number,
        "status": status,
        "risk_level": risk_result.level,
        "requires_secondary_verification": risk_result.score >= 60,
        "estimated_approval_hours": 24 if risk_result.score < 40 else 72,
        "risk_explanation": risk_result.explanation if current_user.role != Role.WORKER else None,
    }


def _validate_registration_permission(payload, user: CurrentUser):
    """Enforce that only authorised roles can use each registration mode."""
    mode = payload.registration_mode

    if mode == "self" and user.role not in [Role.WORKER, Role.ADMIN]:
        raise HTTPException(status_code=403, detail="Only workers can self-register")

    if mode in ["assisted_officer"] and user.role not in [
        Role.FIELD_OFFICER, Role.SUPERVISOR, Role.ADMIN
    ]:
        raise HTTPException(status_code=403, detail="Role cannot perform officer-assisted registration")

    if mode == "assisted_employer" and user.role not in [Role.EMPLOYER, Role.ADMIN]:
        raise HTTPException(status_code=403, detail="Role cannot perform employer-assisted registration")

    if mode == "offline" and user.role not in [Role.FIELD_OFFICER, Role.SUPERVISOR, Role.ADMIN]:
        raise HTTPException(status_code=403, detail="Role cannot submit offline registrations")


async def flag_for_supervisor_review(worker_id: str, risk_result, registrar_id: str):
    """Background task — creates a supervisor review task for high-risk registrations."""
    await publish_event("risk.high_risk_registration", {
        "worker_id": worker_id,
        "risk_score": risk_result.score,
        "risk_flags": [{"id": f.rule_id, "desc": f.description, "pts": f.points}
                       for f in risk_result.flags],
        "explanation": risk_result.explanation,
        "registrar_id": registrar_id,
    })
