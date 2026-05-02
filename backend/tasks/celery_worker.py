from celery import Celery
from backend.core.config import settings

celery_app = Celery(
    settings.app_name,
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_serializer="json", result_serializer="json", accept_content=["json"],
    timezone="UTC", enable_utc=True, task_track_started=True, task_acks_late=True,
    worker_prefetch_multiplier=1, result_expires=86400,
)
celery_app.conf.imports = [
    "backend.tasks.document_ingestion",
    "backend.tasks.embedding_tasks",
    "backend.tasks.diagnosis_task",
    "backend.tasks.remediation_task",
    "backend.tasks.monitoring_task",
    "backend.tasks.netbox_sync_task",           # Phase 2: NetBox sync (no-op when NETBOX_ENABLED=false)
    "backend.tasks.correlation_task",           # Phase 3: incident correlation (no-op when CORRELATION_ENABLED=false)
    "backend.tasks.runbook_generation_task",    # Phase 3: auto-runbook gen (no-op when RUNBOOK_AUTOGEN_ENABLED=false)
    "backend.tasks.prediction_task",            # Phase 3: anomaly detection (no-op when PREDICTIVE_ENABLED=false)
]

# Celery Beat — periodic tasks
celery_app.conf.beat_schedule = {
    "monitor-device-health-every-5-minutes": {
        "task": "tasks.monitor_device_health",
        "schedule": 300.0,   # seconds — change to 60.0 for faster iteration in dev
    },
    "netbox-sync-devices": {
        "task": "tasks.netbox_sync_devices",
        "schedule": settings.netbox_sync_interval_minutes * 60,  # default 1800s
    },
    # Phase 3: anomaly detection every 5 minutes (no-op when PREDICTIVE_ENABLED=false)
    "run-anomaly-detection-every-5-minutes": {
        "task": "tasks.run_anomaly_detection",
        "schedule": 300.0,
    },
}

# Phase 2: OTel Celery instrumentation (no-op when OTEL_ENABLED=false)
from backend.core.tracing import configure_celery_tracing
configure_celery_tracing()
