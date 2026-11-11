import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.documents import router as documents_router
from app.api.knowledge import router as knowledge_router
from app.api.agent import router as agent_router
from app.core.config import get_settings

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("supportpilot.api")

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Customer support automation API. Suggested replies require human review.",
)
app.include_router(health_router)
app.include_router(documents_router)
app.include_router(knowledge_router)
app.include_router(agent_router)


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
    request.state.correlation_id = correlation_id
    if request.url.path == "/documents/upload" and request.method == "POST":
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                request_size = int(content_length)
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
            max_request_size = settings.upload_max_mb * 1024 * 1024 + 1024 * 1024
            if request_size > max_request_size:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Upload request exceeds the {settings.upload_max_mb} MB file limit"},
                    headers={"X-Correlation-ID": correlation_id},
                )
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "unhandled request error",
            extra={"correlation_id": correlation_id, "path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "correlation_id": correlation_id},
            headers={"X-Correlation-ID": correlation_id},
        )
    response.headers["X-Correlation-ID"] = correlation_id
    return response
