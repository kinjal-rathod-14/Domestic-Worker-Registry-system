"""
Risk Scoring Engine
Combines rule-based checks (70%) with ML anomaly detection (30%).
Every score is fully explainable — each flag carries a rule ID and evidence.

Score ranges:
  0–39   → Low    → Auto-approve
  40–59  → Medium → Supervisor review
  60–100 → High   → Block + alert
"""
import math
import structlog
from dataclasses import dataclass, field
from typing import List
from shared.db.postgres import db
from shared.utils.validators import compute_delay_hours, is_within_polygon, fuzzy_name_match

logger = structlog.get_logger()


@dataclass
class RiskFlag:
    rule_id: str
    description: str
    points: int
    evidence: dict


@dataclass
class RiskResult:
    score: int               # 0–100
    level: str               # low | medium | high
    flags: List[RiskFlag]
    rule_score: int
    ml_anomaly_score: float
    explanation: str


async def compute_risk_score(
    worker_data: dict,
    registrar,
    id_validation,
    dedup_result,
) -> RiskResult:
    """
    Main entry point. Returns a RiskResult with full explainability.
    Called synchronously during registration, and asynchronously on re-evaluation.
    """
    flags: List[RiskFlag] = []
    rule_score = 0

    # ── R01: Officer daily registration volume ──────────────────────────────
    if registrar.role == "field_officer":
        today_count = await _get_officer_daily_count(registrar.id)
        threshold = 15
        if today_count > threshold:
            pts = min(30, 10 + (today_count - threshold) * 2)
            flags.append(RiskFlag(
                rule_id="R01a",
                description=f"Officer registered {today_count} workers today (threshold: {threshold})",
                points=pts,
                evidence={"officer_id": registrar.id, "today_count": today_count},
            ))
            rule_score += pts

        # R01b: Burst rate — more than 5 in any 30-minute window
        burst_count = await _get_officer_burst_count(registrar.id, minutes=30)
        if burst_count >= 5:
            flags.append(RiskFlag(
                rule_id="R01b",
                description=f"Registration burst: {burst_count} in 30 minutes",
                points=20,
                evidence={"burst_count": burst_count, "window_minutes": 30},
            ))
            rule_score += 20

    # ── R02: Geographic mismatch ─────────────────────────────────────────────
    if registrar.role == "field_officer" and worker_data.get("geo_location"):
        officer_district_bounds = await _get_district_bounds(registrar.district_scope)
        worker_geo = worker_data["geo_location"]
        if officer_district_bounds and not is_within_polygon(worker_geo, officer_district_bounds):
            flags.append(RiskFlag(
                rule_id="R02",
                description="Registration GPS outside officer's assigned district boundary",
                points=25,
                evidence={
                    "worker_geo": worker_geo,
                    "officer_district": registrar.district_scope,
                },
            ))
            rule_score += 25

    # ── R03: ID name mismatch ────────────────────────────────────────────────
    if id_validation.name_match_score < 0.70:
        deviation = 0.70 - id_validation.name_match_score
        pts = min(35, int(deviation * 50))
        flags.append(RiskFlag(
            rule_id="R03",
            description=f"Name mismatch with Aadhaar authority (similarity: {id_validation.name_match_score:.2f})",
            points=pts,
            evidence={
                "submitted_name": worker_data.get("full_name"),
                "aadhaar_name": id_validation.aadhaar_name,
                "similarity_score": id_validation.name_match_score,
            },
        ))
        rule_score += pts

    # ── R04: No contact information ──────────────────────────────────────────
    if not worker_data.get("mobile_number") and not worker_data.get("alternate_contact"):
        flags.append(RiskFlag(
            rule_id="R04",
            description="No contact information provided (no mobile, no alternate)",
            points=10,
            evidence={},
        ))
        rule_score += 10

    # ── R05: Offline sync delay ──────────────────────────────────────────────
    if worker_data.get("offline_captured_at"):
        delay_hours = compute_delay_hours(worker_data["offline_captured_at"])
        if delay_hours > 72:
            pts = min(20, int(delay_hours / 24) * 3)
            flags.append(RiskFlag(
                rule_id="R05",
                description=f"Offline record synced {delay_hours:.1f}h after capture (limit: 72h)",
                points=pts,
                evidence={"delay_hours": delay_hours, "captured_at": worker_data["offline_captured_at"]},
            ))
            rule_score += pts

    # ── R06: Low officer trust score ─────────────────────────────────────────
    if registrar.role == "field_officer":
        officer_trust = await _get_officer_trust_score(registrar.id)
        trust_threshold = 0.60
        if officer_trust < trust_threshold:
            deviation = trust_threshold - officer_trust
            pts = min(25, int(deviation * 40))
            flags.append(RiskFlag(
                rule_id="R06",
                description=f"Registering officer trust score low ({officer_trust:.2f}, threshold: {trust_threshold})",
                points=pts,
                evidence={"officer_id": registrar.id, "trust_score": officer_trust},
            ))
            rule_score += pts

    # ── R07: Device used for multiple workers ────────────────────────────────
    device_fp = worker_data.get("device_fingerprint")
    if device_fp:
        device_count = await _get_device_registration_count(device_fp, hours=24)
        if device_count > 3:
            flags.append(RiskFlag(
                rule_id="R07",
                description=f"Device registered {device_count} different workers in 24h",
                points=15,
                evidence={"device_fingerprint": device_fp[:8] + "...", "count": device_count},
            ))
            rule_score += 15

    # ── R08: Aadhaar authority unreachable (soft fail) ───────────────────────
    if id_validation.failure_reason == "ID_AUTHORITY_UNAVAILABLE":
        flags.append(RiskFlag(
            rule_id="R08",
            description="Aadhaar authority was unreachable — ID unverified",
            points=20,
            evidence={"failure_reason": id_validation.failure_reason},
        ))
        rule_score += 20

    # ── ML Anomaly Score (Isolation Forest) ─────────────────────────────────
    ml_features = _extract_ml_features(worker_data, registrar)
    ml_anomaly_score = await _run_anomaly_model(ml_features)
    # ml_anomaly_score: 0.0 = completely normal, 1.0 = highly anomalous

    # ── Combine scores (rules 70%, ML 30%) ───────────────────────────────────
    capped_rule_score = min(rule_score, 100)
    raw_total = (capped_rule_score * 0.70) + (ml_anomaly_score * 100 * 0.30)
    total_score = min(100, int(math.ceil(raw_total)))

    level = "low" if total_score < 40 else ("medium" if total_score < 60 else "high")

    explanation = _generate_explanation(flags, ml_anomaly_score, total_score, level)

    logger.info(
        "risk_score_computed",
        score=total_score,
        level=level,
        flags=[f.rule_id for f in flags],
        ml_score=ml_anomaly_score,
    )

    return RiskResult(
        score=total_score,
        level=level,
        flags=flags,
        rule_score=capped_rule_score,
        ml_anomaly_score=ml_anomaly_score,
        explanation=explanation,
    )


def _generate_explanation(flags: List[RiskFlag], ml_score: float, total: int, level: str) -> str:
    lines = [
        f"Risk Assessment: {level.upper()} ({total}/100)",
        f"Rule-based score: {sum(f.points for f in flags)} pts × 0.7",
        f"ML anomaly score: {ml_score:.3f} × 0.3",
        "",
        "Contributing factors:",
    ]
    if not flags and ml_score < 0.3:
        lines.append("  No significant risk factors detected.")
    for f in flags:
        lines.append(f"  [{f.rule_id}] +{f.points} pts — {f.description}")
    if ml_score > 0.5:
        lines.append(f"  [ML]  Anomaly score {ml_score:.3f} — registration pattern deviates from baseline")
    return "\n".join(lines)


def _extract_ml_features(worker_data: dict, registrar) -> list:
    """Extract numeric features for Isolation Forest model."""
    return [
        worker_data.get("geo_location", {}).get("accuracy_meters", 200),
        len(worker_data.get("full_name", "")),
        1 if worker_data.get("mobile_number") else 0,
        1 if worker_data.get("offline_captured_at") else 0,
        1 if registrar.role == "field_officer" else 0,
        hash(worker_data.get("address", {}).get("district", "")) % 100,
    ]


async def _run_anomaly_model(features: list) -> float:
    """
    Run pre-trained Isolation Forest model.
    Returns anomaly probability 0.0–1.0.
    In production: load model from S3 on startup, cache in memory.
    """
    try:
        from services.risk_scoring.models.anomaly_model import anomaly_model
        score = anomaly_model.decision_function([features])[0]
        # Convert decision function output to 0–1 probability
        normalized = max(0.0, min(1.0, (0.5 - score) * 2))
        return round(normalized, 4)
    except Exception as e:
        logger.warning("anomaly_model_unavailable", error=str(e))
        return 0.0   # Fail open — rule-based score carries full weight


# ── Database helpers ─────────────────────────────────────────────────────────

async def _get_officer_daily_count(officer_id: str) -> int:
    result = await db.fetchval("""
        SELECT COUNT(*) FROM registrations
        WHERE officer_id = $1 AND created_at > NOW() - INTERVAL '24 hours'
    """, officer_id)
    return result or 0


async def _get_officer_burst_count(officer_id: str, minutes: int) -> int:
    result = await db.fetchval("""
        SELECT COUNT(*) FROM registrations
        WHERE officer_id = $1 AND created_at > NOW() - ($2 || ' minutes')::INTERVAL
    """, officer_id, str(minutes))
    return result or 0


async def _get_officer_trust_score(officer_id: str) -> float:
    result = await db.fetchval(
        "SELECT trust_score FROM officers WHERE id = $1", officer_id
    )
    return float(result) if result is not None else 1.0


async def _get_district_bounds(district_id: str) -> dict | None:
    result = await db.fetchrow(
        "SELECT boundary_polygon FROM districts WHERE id = $1", district_id
    )
    return result["boundary_polygon"] if result else None


async def _get_device_registration_count(device_fp: str, hours: int) -> int:
    result = await db.fetchval("""
        SELECT COUNT(DISTINCT worker_id) FROM registrations
        WHERE device_fingerprint = $1 AND created_at > NOW() - ($2 || ' hours')::INTERVAL
    """, device_fp, str(hours))
    return result or 0
