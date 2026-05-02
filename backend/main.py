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

from starlette.middleware.sessions import SessionMiddleware

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
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.app_secret_key,
        https_only=settings.is_production,
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
