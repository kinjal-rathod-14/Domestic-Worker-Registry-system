"""
Security alerting service.
Sends alerts on critical events: audit chain tampering, officer suspension triggers,
high-risk registrations, and account lockouts.
"""
import structlog
import boto3
from shared.utils.config import settings

logger = structlog.get_logger()


async def alert_security_team(event: str, details: dict) -> None:
    """
    Send a critical security alert via SNS and structured log.
    SNS topic is monitored by the security team via email/SMS/PagerDuty.
    """
    logger.critical(
        "security_alert",
        event=event,
        details=details,
    )

    # AWS SNS alert
    try:
        sns = boto3.client("sns", region_name=settings.AWS_REGION)
        message = f"""
DWRS SECURITY ALERT
Event: {event}
Environment: {settings.APP_ENV}
Details: {details}

Immediate investigation required.
        """.strip()

        sns.publish(
            TopicArn=f"arn:aws:sns:{settings.AWS_REGION}:ACCOUNT_ID:dwrs-security-alerts",
            Subject=f"[DWRS ALERT] {event}",
            Message=message,
        )
    except Exception as e:
        # Alert failure itself must be logged — never silently dropped
        logger.error("alert_send_failed", event=event, error=str(e))


async def notify_supervisor(supervisor_id: str, event: str, details: dict) -> None:
    """Notify a specific supervisor of a pending review item."""
    logger.info("supervisor_notification", supervisor_id=supervisor_id, event=event)
    # In production: send push notification via FCM or email via SES
    # For now: publish to Kafka for notification service to handle
    from shared.events.kafka_producer import publish_event
    await publish_event("notification.supervisor_alert", {
        "supervisor_id": supervisor_id,
        "event": event,
        "details": details,
    })
