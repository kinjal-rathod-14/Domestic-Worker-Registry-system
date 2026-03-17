"""
Celery background tasks for DWRS.
Scheduled jobs:
  - Nightly audit chain verification (2 AM IST)
  - Officer trust score recalculation (every 6h)
  - Random audit selection (post-registration)
  - Stale review queue alerts (every 4h)
"""
import structlog
from celery import Celery
from celery.schedules import crontab
from shared.utils.config import settings

logger = structlog.get_logger()

celery_app = Celery(
    "dwrs",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    timezone="Asia/Kolkata",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "verify-audit-chain-nightly": {
        "task": "shared.tasks.celery_tasks.verify_audit_chain",
        "schedule": crontab(hour=2, minute=0),
    },
    "recalculate-officer-trust-scores": {
        "task": "shared.tasks.celery_tasks.recalculate_all_officer_trust_scores",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    "alert-stale-review-queue": {
        "task": "shared.tasks.celery_tasks.alert_stale_reviews",
        "schedule": crontab(minute=0, hour="*/4"),
    },
    "refresh-officer-trust-metrics-view": {
        "task": "shared.tasks.celery_tasks.refresh_officer_metrics_view",
        "schedule": crontab(minute=30, hour="*/6"),
    },
}


@celery_app.task(name="shared.tasks.celery_tasks.verify_audit_chain", bind=True, max_retries=3)
def verify_audit_chain(self):
    """Nightly audit chain integrity check."""
    import asyncio
    from services.audit.services.hash_chain import AuditChain
    chain = AuditChain()
    result = asyncio.get_event_loop().run_until_complete(chain.verify_chain_integrity())
    if not result["valid"]:
        logger.critical("AUDIT_CHAIN_BROKEN", broken_at=result.get("broken_at"))
    else:
        logger.info("audit_chain_ok", records_checked=result["records_checked"])
    return result


@celery_app.task(name="shared.tasks.celery_tasks.recalculate_all_officer_trust_scores")
def recalculate_all_officer_trust_scores():
    """Recalculate trust scores for all active officers."""
    import asyncio
    from shared.db.postgres import db

    async def _run():
        officers = await db.fetch("SELECT id FROM officers WHERE is_suspended = FALSE")
        updated = 0
        for officer in officers:
            await _recalculate_officer_trust(str(officer["id"]))
            updated += 1
        logger.info("trust_scores_recalculated", count=updated)
        return updated

    return asyncio.get_event_loop().run_until_complete(_run())


async def _recalculate_officer_trust(officer_id: str) -> float:
    """
    Trust score algorithm:
    - Starts at 1.0 (perfect trust)
    - Deducted based on: failed verifications, geo variance, off-hours work,
      duplicate flags, confirmed violations.
    """
    from shared.db.postgres import db
    from services.audit.services.alert import alert_security_team

    metrics = await db.fetchrow("""
        SELECT
            COUNT(vr.id) FILTER (WHERE vr.decision = 'failed') AS failed_verifs,
            COUNT(r.id) FILTER (WHERE EXTRACT(HOUR FROM r.created_at) NOT BETWEEN 7 AND 20) AS off_hours,
            COUNT(r.id) AS total_regs,
            o.anomaly_flags,
            o.confirmed_violations
        FROM officers o
        LEFT JOIN registrations r ON r.officer_id = o.id
            AND r.created_at > NOW() - INTERVAL '30 days'
        LEFT JOIN verification_records vr ON vr.worker_id = r.worker_id
        WHERE o.id = $1::uuid
        GROUP BY o.id, o.anomaly_flags, o.confirmed_violations
    """, officer_id)

    if not metrics:
        return 1.0

    score = 1.0
    total = metrics["total_regs"] or 1

    # Factor 1: Failed verification rate on registrations
    fail_rate = (metrics["failed_verifs"] or 0) / total
    if fail_rate > 0.20:
        score -= min(0.30, fail_rate * 0.5)

    # Factor 2: Off-hours registration ratio
    off_hours_rate = (metrics["off_hours"] or 0) / total
    if off_hours_rate > 0.15:
        score -= min(0.20, off_hours_rate * 0.3)

    # Factor 3: Anomaly flags
    score -= min(0.20, (metrics["anomaly_flags"] or 0) * 0.03)

    # Factor 4: Confirmed violations (most severe)
    score -= min(0.40, (metrics["confirmed_violations"] or 0) * 0.20)

    final_score = max(0.0, min(1.0, round(score, 3)))

    await db.execute(
        "UPDATE officers SET trust_score = $1 WHERE id = $2::uuid",
        final_score, officer_id
    )

    suspend_threshold = settings.OFFICER_TRUST_SUSPEND_THRESHOLD
    if final_score < suspend_threshold:
        await db.execute(
            "UPDATE officers SET is_suspended = TRUE, suspended_at = NOW(), "
            "suspended_reason = $1 WHERE id = $2::uuid",
            f"Trust score dropped below suspension threshold ({final_score:.3f} < {suspend_threshold})",
            officer_id,
        )
        await alert_security_team("OFFICER_AUTO_SUSPENDED", {
            "officer_id": officer_id,
            "trust_score": final_score,
            "threshold": suspend_threshold,
        })

    return final_score


@celery_app.task(name="shared.tasks.celery_tasks.alert_stale_reviews")
def alert_stale_reviews():
    """Alert supervisors about review queue items pending > 48h."""
    import asyncio
    from shared.db.postgres import db
    from services.audit.services.alert import notify_supervisor

    async def _run():
        stale = await db.fetch("""
            SELECT rq.id, rq.worker_id, rq.risk_score, rq.assigned_to,
                   EXTRACT(EPOCH FROM (NOW() - rq.created_at)) / 3600 AS age_hours
            FROM review_queue rq
            WHERE rq.status = 'pending' AND rq.created_at < NOW() - INTERVAL '48 hours'
        """)
        for item in stale:
            if item["assigned_to"]:
                await notify_supervisor(
                    supervisor_id=str(item["assigned_to"]),
                    event="STALE_REVIEW_ITEM",
                    details={
                        "review_id": str(item["id"]),
                        "worker_id": str(item["worker_id"]),
                        "age_hours": round(item["age_hours"], 1),
                        "risk_score": item["risk_score"],
                    }
                )
        return len(stale)

    return asyncio.get_event_loop().run_until_complete(_run())


@celery_app.task(name="shared.tasks.celery_tasks.refresh_officer_metrics_view")
def refresh_officer_metrics_view():
    """Refresh the officer_trust_metrics materialised view."""
    import asyncio
    from shared.db.postgres import db

    async def _run():
        await db.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY officer_trust_metrics")
        logger.info("officer_trust_metrics_view_refreshed")

    return asyncio.get_event_loop().run_until_complete(_run())
