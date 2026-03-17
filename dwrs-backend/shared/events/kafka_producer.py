import json
import structlog
from shared.utils.config import settings

logger = structlog.get_logger()
_producer = None
_kafka_available = bool(settings.KAFKA_BOOTSTRAP_SERVERS)


async def get_producer():
    global _producer
    if not _kafka_available:
        return None
    if _producer is None:
        try:
            from aiokafka import AIOKafkaProducer
            _producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',
            )
            await _producer.start()
        except Exception as e:
            logger.warning('kafka_unavailable', error=str(e))
            return None
    return _producer


async def publish_event(event_name: str, payload: dict, key=None) -> None:
    if not _kafka_available:
        logger.info('event_dev_log', event=event_name, payload=str(payload)[:200])
        return
    try:
        producer = await get_producer()
        if producer:
            topic = f'{settings.KAFKA_TOPIC_PREFIX}{event_name}'
            await producer.send_and_wait(topic=topic, value=payload, key=key)
    except Exception as e:
        logger.warning('event_publish_skipped', event=event_name, error=str(e))


async def close_producer():
    global _producer
    if _producer:
        try:
            await _producer.stop()
        except Exception:
            pass
        _producer = None
