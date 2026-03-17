"""
Auth Service — FastAPI app entry point
"""
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.db.postgres import get_pool, close_pool
from shared.db.redis_client import redis_client
from shared.events.kafka_producer import get_producer, close_producer
from services.auth.routes.auth import router as auth_router
from shared.utils.config import settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("auth_service_starting")
    await get_pool()
    await get_producer()
    yield
    await close_pool()
    await close_producer()
    await redis_client.close()


app = FastAPI(
    title="DWRS Auth Service",
    version="1.0.0",
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://dwrs.gov.in"] if settings.APP_ENV == "production" else ["*"],
    allow_credentials=True,
    allow_methods=["POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok", "service": "auth"}
