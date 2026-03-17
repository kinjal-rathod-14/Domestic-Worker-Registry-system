"""
Registration Service — FastAPI app entry point
"""
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from shared.db.postgres import get_pool, close_pool
from shared.db.redis_client import redis_client
from shared.events.kafka_producer import get_producer, close_producer
from shared.middleware.audit_log import AuditLogMiddleware
from services.registration.routes.worker import router as worker_router
from services.registration.routes.offline_sync import router as offline_router
from shared.utils.config import settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("registration_service_starting", env=settings.APP_ENV)
    await get_pool()
    await get_producer()
    yield
    # Shutdown
    await close_pool()
    await close_producer()
    await redis_client.close()
    logger.info("registration_service_stopped")


app = FastAPI(
    title="DWRS Registration Service",
    version="1.0.0",
    description="Domestic Worker Registration & Verification System — Registration Service",
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

# Middleware
app.add_middleware(AuditLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://dwrs.gov.in"] if settings.APP_ENV == "production" else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

# Prometheus metrics
if settings.PROMETHEUS_ENABLED:
    Instrumentator().instrument(app).expose(app)

# Routers
app.include_router(worker_router)
app.include_router(offline_router)


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok", "service": "registration"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred"},
    )
