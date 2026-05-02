import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.app.api.routes.audit_routes import router as audit_router
from backend.app.api.routes.auth_routes import router as auth_router
from backend.app.api.routes.device_routes import router as device_router
from backend.app.api.routes.incident_routes import router as incident_router
from backend.app.api.routes.remediation_routes import router as remediation_router
from backend.app.api.routes.runbook_routes import router as runbook_router
from backend.app.api.routes.simulation_routes import router as simulation_router
from backend.app.api.routes.topology_routes import router as topology_router
from backend.app.api.routes.webhook_routes import router as webhook_router
from backend.core.config import settings
from backend.core.logging import configure_logging, get_logger, set_correlation_id
from backend.database.base import Base
from backend.database.session import engine

# Ensure all ORM models are imported so SQLAlchemy can resolve relationship strings
# at mapper-configure time — even models whose routes are conditionally registered.
import backend.models.user_model          # noqa: F401
import backend.models.incident_model      # noqa: F401
import backend.models.runbook_model       # noqa: F401
import backend.models.device_model        # noqa: F401
import backend.models.topology_model      # noqa: F401
import backend.models.site_model          # noqa: F401 — referenced by Device/Incident/User.site
import backend.models.diagnosis_feedback_model  # noqa: F401 — Phase 3
import backend.models.anomaly_model       # noqa: F401 — Phase 3

configure_logging()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("startup", env=settings.app_env.value)
    if settings.is_development:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("db_tables_synced")
    if settings.oidc_enabled:
        from backend.core.oidc import configure_oidc
        configure_oidc(app)
    if settings.otel_enabled:
        from backend.core.tracing import configure_tracing
        configure_tracing(app)
    yield
    log.info("shutdown")
    await engine.dispose()


limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Network Runbook Platform",
        description="AI-powered incident diagnosis with RAG + Digital Twin",
        version="1.0.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )
    # SessionMiddleware required for OIDC authorization code flow (state/nonce in session)
    # Only loaded when OIDC_ENABLED=true to avoid requiring itsdangerous in non-OIDC deployments
    if settings.oidc_enabled:
        try:
            from starlette.middleware.sessions import SessionMiddleware
            app.add_middleware(
                SessionMiddleware,
                secret_key=settings.app_secret_key,
                https_only=settings.is_production,
            )
        except ImportError:
            raise RuntimeError(
                "OIDC_ENABLED=true requires itsdangerous. Run: pip install itsdangerous"
            )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )

    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next) -> Response:
        cid = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        set_correlation_id(cid)
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Correlation-ID"] = cid
        log.info("http_request", method=request.method, path=request.url.path,
                 status=response.status_code, duration_ms=duration_ms)
        return response

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    API_PREFIX = "/api/v1"
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(incident_router, prefix=API_PREFIX)
    app.include_router(runbook_router, prefix=API_PREFIX)
    app.include_router(topology_router, prefix=API_PREFIX)
    app.include_router(simulation_router, prefix=API_PREFIX)
    app.include_router(audit_router, prefix=API_PREFIX)
    app.include_router(device_router, prefix=API_PREFIX)
    app.include_router(remediation_router, prefix=API_PREFIX)
    app.include_router(webhook_router, prefix=API_PREFIX)

    # Phase 2: Site routes only registered when MULTITENANCY_ENABLED=true
    if settings.multitenancy_enabled:
        from backend.app.api.routes.site_routes import router as site_router
        app.include_router(site_router, prefix=API_PREFIX)

    # Phase 3: Feedback routes only registered when FEEDBACK_ENABLED=true
    if settings.feedback_enabled:
        from backend.app.api.routes.feedback_routes import router as feedback_router
        app.include_router(feedback_router, prefix=API_PREFIX)

    @app.get("/health", tags=["Health"])
    async def health() -> dict:
        return {"status": "ok", "env": settings.app_env.value}

    @app.get("/readiness", tags=["Health"])
    async def readiness() -> dict:
        return {"status": "ready"}

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_exception", error=str(exc), path=request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()
