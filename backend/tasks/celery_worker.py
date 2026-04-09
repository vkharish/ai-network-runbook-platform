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
]
