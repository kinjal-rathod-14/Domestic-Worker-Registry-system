"""
SQLite async connection using aiosqlite.
Access via the module-level `db` object (replaces postgres asyncpg).
"""
import aiosqlite
import structlog
from shared.utils.config import settings
import os

logger = structlog.get_logger()

# We'll use a single global connection/pool mechanism for simplicity.
_db_path = settings.DATABASE_URL
if "sqlite" in _db_path:
    # Handle "sqlite+aiosqlite:///dwrs_local.db" -> "dwrs_local.db"
    db_file = _db_path.split(":///")[-1]
    _db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), db_file)


class Database:
    """Thin wrapper around aiosqlite for convenient query methods, aiming for asyncpg compatibility."""

    def __init__(self):
        self._conn = None

    async def connect(self):
        if self._conn is None:
            self._conn = await aiosqlite.connect(_db_path)
            self._conn.row_factory = aiosqlite.Row
            logger.info("sqlite_db_connected", path=_db_path)

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    def _convert_query(self, query: str) -> str:
        # asyncpg uses $1, $2, etc. aiosqlite uses ?
        # A simple naive string replace (might need regex for robust production but fine here)
        import re
        return re.sub(r'\$\d+', '?', query)

    async def fetch(self, query: str, *args):
        await self.connect()
        query = self._convert_query(query)
        async with self._conn.execute(query, args) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def fetchrow(self, query: str, *args):
        await self.connect()
        query = self._convert_query(query)
        async with self._conn.execute(query, args) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def fetchval(self, query: str, *args):
        await self.connect()
        query = self._convert_query(query)
        async with self._conn.execute(query, args) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def execute(self, query: str, *args):
        await self.connect()
        query = self._convert_query(query)
        await self._conn.execute(query, args)
        await self._conn.commit()

    async def executemany(self, query: str, args_list):
        await self.connect()
        query = self._convert_query(query)
        await self._conn.executemany(query, args_list)
        await self._conn.commit()


db = Database()

# Backward compatible function names for lifespan
async def get_pool():
    await db.connect()
    # Mocking pool context manager returned value if it was used like async with pool.acquire()
    class DummyPool:
        def acquire(self):
            class DummyConn:
                async def __aenter__(self): pass
                async def __aexit__(self, exc_type, exc, tb): pass
            return DummyConn()
    return DummyPool()

async def close_pool():
    await db.close()
