"""OpenTelemetry distributed tracing setup.

All OTel imports are lazy — only executed when OTEL_ENABLED=true.
When disabled (default), this module is a no-op and adds zero overhead.

Usage:
    # In main.py lifespan:
    from backend.core.tracing import configure_tracing
    configure_tracing(app)

    # In celery_worker.py:
    from backend.core.tracing import configure_celery_tracing
    configure_celery_tracing()

    # In agent code for manual spans:
    from backend.core.tracing import get_tracer
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("rag_query"):
        ...
"""

from backend.core.logging import get_logger

log = get_logger(__name__)


def configure_tracing(app) -> None:
    """Initialize OTel SDK and instrument FastAPI + SQLAlchemy + httpx.

    Called from main.py lifespan only when OTEL_ENABLED=true.
    Raises RuntimeError (with install instructions) if packages are missing.
    """
    from backend.core.config import settings

    if not settings.otel_enabled:
        return

    try:
        from opentelemetry import trace  # type: ignore[import]
        from opentelemetry.sdk.resources import Resource  # type: ignore[import]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import]
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore[import]
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # type: ignore[import]
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore[import]
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor  # type: ignore[import]
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "OTEL_ENABLED=true requires opentelemetry packages. "
            "Run: pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc "
            "opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-sqlalchemy "
            "opentelemetry-instrumentation-httpx"
        ) from exc

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=True,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()

    log.info(
        "otel_tracing_configured",
        endpoint=settings.otel_exporter_otlp_endpoint,
        service=settings.otel_service_name,
    )


def configure_celery_tracing() -> None:
    """Instrument Celery tasks with OTel spans.

    Called from celery_worker.py after celery_app is created.
    No-op when OTEL_ENABLED=false.
    """
    from backend.core.config import settings

    if not settings.otel_enabled:
        return

    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor  # type: ignore[import]
        CeleryInstrumentor().instrument()
        log.info("otel_celery_instrumented")
    except ImportError:
        log.warning("otel_celery_instrumentation_not_available")


def get_tracer(name: str):
    """Return an OTel tracer for manual span creation.

    When OTel is disabled or not configured, the opentelemetry-api stub
    returns a no-op tracer — zero overhead, no import error.
    """
    try:
        from opentelemetry import trace  # type: ignore[import]
        return trace.get_tracer(name)
    except ImportError:
        # opentelemetry-api not installed at all — return a dummy
        return _NoOpTracer()


class _NoOpTracer:
    """Fallback tracer when opentelemetry-api is not installed."""

    class _NoOpSpan:
        def __enter__(self): return self
        def __exit__(self, *_): pass

    def start_as_current_span(self, name: str, **_):
        return self._NoOpSpan()
