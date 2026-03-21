"""Celery task: re-embed all chunks for an already-indexed runbook."""

import asyncio
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import settings
from backend.core.logging import configure_logging, get_logger
from backend.models.runbook_model import Runbook, RunbookStatus
from backend.rag.embedding_engine import get_embedding_engine
from backend.rag.ingest_documents import chunk_document, parse_document
from backend.rag.vector_store import add_chunks, delete_by_runbook_id
from backend.tasks.celery_worker import celery_app

configure_logging()
log = get_logger(__name__)


def _make_session_factory():
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    return engine, factory


async def _reembed_pipeline(runbook_id: str) -> dict:
    engine, SessionLocal = _make_session_factory()

    try:
        # Fetch runbook metadata
        async with SessionLocal() as db:
            result = await db.execute(
                select(Runbook).where(Runbook.id == uuid.UUID(runbook_id))
            )
            runbook = result.scalar_one_or_none()
            if runbook is None:
                raise ValueError(f"Runbook {runbook_id} not found.")
            filename = runbook.filename
            tags: list[str] = runbook.tags or []  # type: ignore[assignment]

        file_path = Path("uploads/runbooks") / filename
        if not file_path.exists():
            raise FileNotFoundError(f"Source file missing: {file_path}")

        # Remove old vectors
        deleted = delete_by_runbook_id(runbook_id)
        log.info("old_vectors_removed", runbook_id=runbook_id, count=deleted)

        # Re-parse and chunk
        text = parse_document(file_path)
        chunks = chunk_document(
            text=text,
            source=file_path.name,
            runbook_id=runbook_id,
            tags=tags,
        )

        # Re-embed
        emb_engine = get_embedding_engine()
        embeddings: list[list[float]] = []
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            embeddings.extend(emb_engine.embed([c["text"] for c in batch]))

        # Store new vectors
        chroma_ids = add_chunks(chunks, embeddings)

        # Update DB
        async with SessionLocal() as db:
            result = await db.execute(
                select(Runbook).where(Runbook.id == uuid.UUID(runbook_id))
            )
            runbook = result.scalar_one_or_none()
            if runbook:
                runbook.chroma_ids = chroma_ids
                runbook.chunk_count = len(chunks)
                runbook.status = RunbookStatus.INDEXED.value
                await db.commit()

        log.info("reembed_runbook_complete", runbook_id=runbook_id, chunks=len(chunks))
        return {"status": "reembedded", "chunks": len(chunks)}

    finally:
        await engine.dispose()


@celery_app.task(
    name="tasks.reembed_runbook",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
)
def reembed_runbook(self, runbook_id: str) -> dict:
    log.info("reembed_runbook_started", runbook_id=runbook_id)
    try:
        return asyncio.run(_reembed_pipeline(runbook_id))
    except Exception as exc:
        log.error("reembed_runbook_failed", runbook_id=runbook_id, error=str(exc))
        raise self.retry(exc=exc)
