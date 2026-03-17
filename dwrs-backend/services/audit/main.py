from fastapi import FastAPI
import structlog

logger = structlog.get_logger()
app = FastAPI(title="DWRS Audit Service", version="1.0.0")

@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok", "service": "audit"}
