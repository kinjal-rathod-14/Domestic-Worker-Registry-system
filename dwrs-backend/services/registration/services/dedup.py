"""
Duplicate Detection Service
Checks three independent signals: Aadhaar hash, face embedding similarity, name+DOB fuzzy match.
A match on ANY signal triggers rejection.
"""
import structlog
from dataclasses import dataclass
from shared.db.postgres import db
from shared.utils.encryption import hash_with_salt
from shared.utils.validators import fuzzy_name_match
from services.verification.services.face_match import get_face_embedding
from shared.utils.config import settings

logger = structlog.get_logger()


@dataclass
class DedupResult:
    is_duplicate: bool
    existing_worker_id: str | None
    match_type: str | None      # aadhaar_exact | face_match | name_dob_fuzzy
    confidence_score: float     # 0–1


async def check_duplicates(
    aadhaar: str,
    name: str,
    dob: str,
    photo_b64: str,
) -> DedupResult:
    """
    Run all three duplicate checks in order of specificity.
    Short-circuits on first match (most specific wins).
    """

    # ── Check 1: Exact Aadhaar hash match ────────────────────────────────────
    aadhaar_hash = hash_with_salt(aadhaar, settings.AADHAAR_SALT)
    existing = await db.fetchrow(
        "SELECT id FROM workers WHERE aadhaar_hash = $1 AND status != 'deleted'",
        aadhaar_hash,
    )
    if existing:
        logger.warning("duplicate_aadhaar_detected", worker_id=str(existing["id"]))
        return DedupResult(
            is_duplicate=True,
            existing_worker_id=str(existing["id"]),
            match_type="aadhaar_exact",
            confidence_score=1.0,
        )

    # ── Check 2: Face embedding cosine similarity (pgvector) ─────────────────
    try:
        face_embedding = await get_face_embedding(photo_b64)
        similar_faces = await db.fetch("""
            SELECT id, 1 - (face_embedding <=> $1::vector) AS similarity
            FROM workers
            WHERE face_embedding IS NOT NULL
              AND status != 'deleted'
              AND 1 - (face_embedding <=> $1::vector) > 0.90
            ORDER BY similarity DESC
            LIMIT 3
        """, face_embedding)

        if similar_faces:
            top = similar_faces[0]
            logger.warning(
                "duplicate_face_detected",
                worker_id=str(top["id"]),
                similarity=float(top["similarity"]),
            )
            return DedupResult(
                is_duplicate=True,
                existing_worker_id=str(top["id"]),
                match_type="face_match",
                confidence_score=round(float(top["similarity"]), 4),
            )
    except Exception as e:
        # Face embedding failure is logged but doesn't skip other checks
        logger.error("face_embedding_check_failed", error=str(e))

    # ── Check 3: Fuzzy name + DOB match ──────────────────────────────────────
    # Catches cases where someone tries to re-register with a different Aadhaar
    # but the same person (name + DOB combination is rare enough to flag)
    try:
        candidates = await db.fetch("""
            SELECT id,
                   pgp_sym_decrypt(full_name_enc, $1) AS full_name,
                   dob
            FROM workers
            WHERE dob = $2
              AND status != 'deleted'
        """, settings.ENCRYPTION_KEY, dob)

        for candidate in candidates:
            score = fuzzy_name_match(name, candidate["full_name"])
            if score > 0.85:
                logger.warning(
                    "duplicate_name_dob_detected",
                    worker_id=str(candidate["id"]),
                    name_similarity=score,
                )
                return DedupResult(
                    is_duplicate=True,
                    existing_worker_id=str(candidate["id"]),
                    match_type="name_dob_fuzzy",
                    confidence_score=round(score, 4),
                )
    except Exception as e:
        logger.error("name_dob_check_failed", error=str(e))

    return DedupResult(
        is_duplicate=False,
        existing_worker_id=None,
        match_type=None,
        confidence_score=0.0,
    )
