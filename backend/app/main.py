"""FastAPI main application entry point."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from contextlib import asynccontextmanager
from sqlalchemy import text

from app.config import get_settings
from app.db.database import init_db, engine
from app.logging_config import configure_logging, get_logger
from app.rate_limit import limiter
from app.routers import chat, documents, admin, auth

settings = get_settings()

configure_logging()
logger = get_logger(__name__)


def _validate_startup_secrets() -> None:
    """Fail fast if required secrets are missing or obviously invalid."""
    errors = []

    if not settings.use_azure_openai and not settings.OPENAI_API_KEY:
        errors.append("Either OPENAI_API_KEY or (AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY) must be set")

    if settings.JWT_SECRET_KEY == "change-me-in-production":
        errors.append("JWT_SECRET_KEY must be changed from the default value before running")

    if settings.FIELD_ENCRYPTION_KEY:
        try:
            from app.security.encryption import _get_fernet
            _get_fernet()
        except Exception as exc:
            errors.append(f"FIELD_ENCRYPTION_KEY is invalid: {exc}")

    if errors:
        for err in errors:
            logger.critical("Startup validation failed: %s", err)
        raise RuntimeError(f"Startup aborted — {len(errors)} configuration error(s): " + "; ".join(errors))

    logger.info("Startup validation passed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — validate config, init DB, then serve."""
    _validate_startup_secrets()
    await init_db()
    logger.info("Application started", extra={"debug": settings.DEBUG})
    yield
    logger.info("Application shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    description="RAG-powered wealth advisory assistant",
    version="1.0.0",
    lifespan=lifespan,
    # Hide docs in production to reduce attack surface
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# HTTPS redirect enforced in production
if not settings.DEBUG:
    app.add_middleware(HTTPSRedirectMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log full details server-side, return a safe generic message to the client."""
    logger.error(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again or contact support."},
    )


app.include_router(auth.router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["auth"])
app.include_router(chat.router, prefix=f"{settings.API_V1_PREFIX}/chat", tags=["chat"])
app.include_router(documents.router, prefix=f"{settings.API_V1_PREFIX}/documents", tags=["documents"])
app.include_router(admin.router, prefix=f"{settings.API_V1_PREFIX}/admin", tags=["admin"])


@app.get("/health")
async def health_check():
    """Deep health check — verifies DB connectivity, not just process liveness."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.error("Health check: database unreachable", exc_info=True)
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "detail": "database unavailable"},
        )
    return {"status": "healthy", "database": "connected"}


@app.get("/")
async def root():
    return {"message": "Wealth Advisor Copilot API", "docs": "/docs" if settings.DEBUG else None}
