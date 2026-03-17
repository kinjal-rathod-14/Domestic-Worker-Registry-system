"""
Worker database model — create and retrieve worker records.
All PII is encrypted before storage.
"""
import structlog
from shared.db.postgres import db
from shared.utils.encryption import encrypt, hash_with_salt
from shared.utils.config import settings

logger = structlog.get_logger()


async def create_worker_record(
    worker_id: str,
    registration_number: str,
    payload,
    risk_result,
    id_result,
    registered_by: str,
) -> None:
    """Persist worker and registration records. PII is encrypted."""
    # Encrypt PII fields before storage
    aadhaar_hash = hash_with_salt(payload.aadhaar_number, settings.AADHAAR_SALT)
    aadhaar_enc = encrypt(payload.aadhaar_number)
    name_enc = encrypt(payload.full_name)
    mobile_hash = hash_with_salt(payload.mobile_number, settings.AADHAAR_SALT) if payload.mobile_number else None
    mobile_enc = encrypt(payload.mobile_number) if payload.mobile_number else None

    await db.execute("""
        INSERT INTO workers (
            id, aadhaar_hash, aadhaar_enc, full_name_enc,
            dob, gender, address,
            mobile_hash, mobile_enc,
            risk_score, risk_level, status,
            registration_no, created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7::jsonb,
            $8, $9, $10, $11,
            $12, $13, NOW(), NOW()
        )
    """,
        worker_id,
        aadhaar_hash,
        aadhaar_enc,
        name_enc,
        payload.date_of_birth,
        payload.gender,
        str(payload.address),
        mobile_hash,
        mobile_enc,
        risk_result.score,
        risk_result.level,
        "registered" if risk_result.score < 40 else "pending_verification",
        registration_number,
    )

    await db.execute("""
        INSERT INTO registrations (
            worker_id, registration_mode, officer_id,
            geo_lat, geo_lng, geo_accuracy_meters,
            device_fingerprint, offline_batch_id, offline_captured_at,
            consent_recorded, consent_witness, created_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW()
        )
    """,
        worker_id,
        payload.registration_mode,
        registered_by if payload.registration_mode != "self" else None,
        payload.geo_location.get("lat"),
        payload.geo_location.get("lng"),
        payload.geo_location.get("accuracy_meters"),
        payload.geo_location.get("device_fingerprint"),
        payload.offline_batch_id,
        payload.offline_captured_at,
        payload.consent_recorded,
        payload.consent_witness,
    )

    # Persist risk score record
    await db.execute("""
        INSERT INTO risk_scores (
            entity_id, entity_type, total_score, risk_level,
            rule_score, ml_anomaly_score, rule_flags, explanation, computed_by
        ) VALUES ($1, 'worker', $2, $3, $4, $5, $6::jsonb, $7, 'system')
    """,
        worker_id,
        risk_result.score,
        risk_result.level,
        risk_result.rule_score,
        risk_result.ml_anomaly_score,
        str([{"rule_id": f.rule_id, "description": f.description, "points": f.points}
              for f in risk_result.flags]),
        risk_result.explanation,
    )

    logger.info("worker_record_created", worker_id=worker_id, registration_no=registration_number)


def generate_registration_number(worker_id: str) -> str:
    """Generate DWRS-YYYYMM-XXXXXX registration number."""
    from datetime import datetime
    now = datetime.now()
    suffix = worker_id.replace("-", "")[:6].upper()
    return f"DWRS-{now.strftime('%Y%m')}-{suffix}"
