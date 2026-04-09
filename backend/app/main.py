import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import settings, validate_runtime_configuration
from app.core.logging import setup_logging
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.system import router as system_router
from app.services.rate_limit_service import get_api_rate_limiter
from app.services.task_worker import get_task_worker


setup_logging()
logger = logging.getLogger("app.request")

@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_runtime_configuration()
    if settings.task_broker_backend == "inmemory":
        get_task_worker().start()
    else:
        logger.info("Skip embedded task worker startup because TASK_BROKER_BACKEND=%s", settings.task_broker_backend)
    try:
        yield
    finally:
        if settings.task_broker_backend == "inmemory":
            get_task_worker().stop()


app = FastAPI(title="StudyMate Agent API", version="0.1.0", lifespan=lifespan)


@app.get("/")
def root():
    return {
        "service": "StudyMate Agent API",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.perf_counter()
    limited = False

    limit_decision = get_api_rate_limiter().check(request)
    if limit_decision and limit_decision.limited:
        limited = True
        response = JSONResponse(
            status_code=429,
            content={
                "success": False,
                "message": "Too Many Requests",
                "data": None,
                "request_id": request_id,
            },
        )
        response.headers["Retry-After"] = str(limit_decision.retry_after_seconds)
    else:
        response = await call_next(request)

    if limit_decision:
        response.headers["X-RateLimit-Limit"] = str(limit_decision.limit)
        response.headers["X-RateLimit-Remaining"] = str(limit_decision.remaining)

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "request_id=%s method=%s path=%s status=%s duration_ms=%.2f limited=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        limited,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": str(exc.detail),
            "data": None,
            "request_id": request_id,
        },
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.exception("Unhandled error. request_id=%s error=%s", request_id, str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Internal Server Error",
            "data": None,
            "request_id": request_id,
        },
    )


app.include_router(system_router)
app.include_router(auth_router)
app.include_router(chat_router)
