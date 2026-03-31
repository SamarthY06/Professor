"""FastAPI application entry point."""

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from app.config import settings
from app.logs.logger import setup_logging, get_logger
from app.db.database import engine

# Set up logging before anything else
setup_logging()
logger = get_logger(__name__)

# Initialize Sentry if DSN is configured
if hasattr(settings, 'sentry_dsn') and settings.sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            traces_sample_rate=0.1 if settings.environment == "production" else 1.0,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        )
        logger.info("sentry_initialized")
    except ImportError:
        logger.warning("sentry_sdk_not_installed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events."""
    logger.info("application_starting", environment=settings.environment)
    
    # Startup
    # Test database connection
    try:
        async with engine.begin() as conn:
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))
        logger.info("database_connected")
    except Exception as e:
        logger.error("database_connection_failed", error=str(e))
    
    yield
    
    # Shutdown
    logger.info("application_shutting_down")
    await engine.dispose()


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="AI-powered personalized learning assistant",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Log all requests and responses."""
    start_time = time.time()
    
    # Get user ID from token if available
    user_id = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        from app.security.jwt import verify_access_token
        token = auth_header.split(" ")[1]
        payload = verify_access_token(token)
        if payload:
            user_id = payload.get("sub")
    
    # Bind request context
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request.headers.get("X-Request-ID", ""),
        user_id=user_id,
        path=request.url.path,
        method=request.method,
    )
    
    # Process request
    response = await call_next(request)
    
    # Calculate latency
    latency_ms = int((time.time() - start_time) * 1000)
    
    # Log response
    logger.info(
        "request_completed",
        status_code=response.status_code,
        latency_ms=latency_ms,
    )
    
    # Add latency header
    response.headers["X-Response-Time"] = f"{latency_ms}ms"
    
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions with structured error response."""
    import uuid as _uuid
    correlation_id = str(_uuid.uuid4())[:8]
    logger.exception(
        "unhandled_exception",
        error=str(exc),
        correlation_id=correlation_id,
        path=str(request.url.path),
        method=request.method,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "correlation_id": correlation_id,
        },
    )


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Shallow health check for load balancers."""
    return {"status": "healthy", "environment": settings.environment}


@app.get("/health/deep", tags=["Health"])
async def deep_health_check():
    """Deep health check that verifies DB, Redis, and Temporal connectivity."""
    from sqlalchemy import text
    checks = {}

    # Database
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:100]}"

    # Redis
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=3)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {str(e)[:100]}"

    # Temporal
    try:
        from temporalio.client import Client as TemporalClient
        client = await TemporalClient.connect(settings.temporal_host, namespace=settings.temporal_namespace)
        checks["temporal"] = "ok"
    except Exception as e:
        checks["temporal"] = f"error: {str(e)[:100]}"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "healthy" if all_ok else "degraded",
        "environment": settings.environment,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Request body size limit (defence in depth — nginx also enforces 50 MB)
# ---------------------------------------------------------------------------
from starlette.middleware.base import BaseHTTPMiddleware

MAX_BODY_BYTES = 50 * 1024 * 1024  # 50 MB


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large (max 50 MB)"},
            )
        return await call_next(request)


app.add_middleware(MaxBodySizeMiddleware)


# ---------------------------------------------------------------------------
# Prometheus metrics — auto-instruments all routes with latency, status, etc.
# ---------------------------------------------------------------------------
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    excluded_handlers=["/health", "/metrics"],
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


# Include API routers
from app.api import auth, users, books, goals, chat, learning, quiz, notes, admin, planning, usage, voice

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(books.router, prefix="/api/books", tags=["Books"])
app.include_router(goals.router, prefix="/api/goals", tags=["Goals"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(learning.router, prefix="/api/learning", tags=["Learning"])
app.include_router(planning.router, prefix="/api/planning", tags=["Planning"])
app.include_router(quiz.router, prefix="/api/quiz", tags=["Quiz"])
app.include_router(notes.router, prefix="/api/notes", tags=["Notes"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(usage.router, prefix="/api/usage", tags=["Usage & Billing"])
app.include_router(voice.router, prefix="/api/voice", tags=["Voice"])


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs" if settings.debug else None,
    }
