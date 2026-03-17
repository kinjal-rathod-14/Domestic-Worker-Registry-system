"""
In-memory mock client for session storage, OTP cache, and rate limiting.
Replaces real Redis to avoid Docker dependency for local execution.
"""
import json
import structlog
import asyncio
import time

logger = structlog.get_logger()

_store = {}
_expires = {}

class RedisClient:
    """Wrapper with JSON serialisation and typed helpers using an in-memory dict."""

    def __init__(self):
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> dict | str | None:
        async with self._lock:
            # Check expiry
            if key in _expires and time.time() > _expires[key]:
                _store.pop(key, None)
                _expires.pop(key, None)
                return None
                
            val = _store.get(key)
            if val is None:
                return None
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return val

    async def setex(self, key: str, ttl_seconds: int, value: dict | str):
        async with self._lock:
            if isinstance(value, dict):
                value = json.dumps(value)
            _store[key] = value
            _expires[key] = time.time() + ttl_seconds

    async def delete(self, key: str):
        async with self._lock:
            _store.pop(key, None)
            _expires.pop(key, None)

    async def incr(self, key: str) -> int:
        async with self._lock:
            # Check expiry
            if key in _expires and time.time() > _expires[key]:
                _store.pop(key, None)
                _expires.pop(key, None)

            val = _store.get(key, 0)
            try:
                val = int(val)
            except ValueError:
                val = 0
            val += 1
            _store[key] = str(val)
            return val

    async def expire(self, key: str, ttl_seconds: int):
        async with self._lock:
            if key in _store:
                _expires[key] = time.time() + ttl_seconds

    async def exists(self, key: str) -> bool:
        async with self._lock:
            if key in _expires and time.time() > _expires[key]:
                _store.pop(key, None)
                _expires.pop(key, None)
                return False
            return key in _store

    async def close(self):
        pass

redis_client = RedisClient()
