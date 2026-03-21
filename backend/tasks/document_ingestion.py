"""Celery task: parse, chunk, embed, and index a runbook into ChromaDB."""

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
    """
    Create a fresh async engine + session factory.
    Must be called inside the event loop created by asyncio.run() so that
    asyncpg connections are bound to the correct loop.
    """
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    return engine, factory


# ---------------------------------------------------------------------------
# Main async pipeline — runs entirely in ONE asyncio.run() call
# ---------------------------------------------------------------------------

async def _ingest_pipeline(runbook_id: str, file_path: str) -> dict:
    engine, SessionLocal = _make_session_factory()

    try:
        # Step 1: mark as processing
        async with SessionLocal() as db:
            result = await db.execute(
                select(Runbook).where(Runbook.id == uuid.UUID(runbook_id))
            )
            runbook = result.scalar_one_or_none()
            if runbook is None:
                raise ValueError(f"Runbook {runbook_id} not found in database.")
            runbook.status = RunbookStatus.PROCESSING.value
            await db.commit()

        # Step 2: parse document
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Source file missing: {file_path}")
        text = parse_document(path)

        # Step 3: fetch tags from DB
        tags: list[str] = []
        async with SessionLocal() as db:
            result = await db.execute(
                select(Runbook).where(Runbook.id == uuid.UUID(runbook_id))
            )
            runbook = result.scalar_one_or_none()
            if runbook and runbook.tags:
                tags = runbook.tags  # type: ignore[assignment]

        # Step 4: chunk
        chunks = chunk_document(
            text=text,
            source=path.name,
            runbook_id=runbook_id,
            chunk_size=1000,
            overlap=200,
            tags=tags,
        )
        if not chunks:
            raise ValueError("No text could be extracted from the document.")

        # Step 5: embed in batches of 100
        emb_engine = get_embedding_engine()
        all_embeddings: list[list[float]] = []
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            all_embeddings.extend(emb_engine.embed([c["text"] for c in batch]))
            log.info(
                "embedding_batch_done",
                runbook_id=runbook_id,
                batch=i // batch_size + 1,
                total_batches=(len(chunks) + batch_size - 1) // batch_size,
            )

        # Step 6: supersede old chunks (chunk versioning) then store new ones
        deleted = delete_by_runbook_id(runbook_id)
        if deleted:
            log.info("old_chunks_superseded", runbook_id=runbook_id, deleted=deleted)
        chroma_ids = add_chunks(chunks, all_embeddings)

        # Step 7: update DB → INDEXED
        async with SessionLocal() as db:
            result = await db.execute(
                select(Runbook).where(Runbook.id == uuid.UUID(runbook_id))
            )
            runbook = result.scalar_one_or_none()
            if runbook:
                runbook.status = RunbookStatus.INDEXED.value
                runbook.chunk_count = len(chunks)
                runbook.chroma_ids = chroma_ids
                await db.commit()

        log.info("ingest_runbook_complete", runbook_id=runbook_id, chunks=len(chunks))
        return {"status": "indexed", "chunks": len(chunks)}

    finally:
        await engine.dispose()


async def _mark_failed(runbook_id: str) -> None:
    engine, SessionLocal = _make_session_factory()
    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(Runbook).where(Runbook.id == uuid.UUID(runbook_id))
            )
            runbook = result.scalar_one_or_none()
            if runbook:
                runbook.status = RunbookStatus.FAILED.value
                await db.commit()
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    name="tasks.ingest_runbook",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def ingest_runbook(self, runbook_id: str, file_path: str) -> dict:
    import traceback as _tb
    log.info("ingest_runbook_started", runbook_id=runbook_id, file_path=file_path)
    try:
        return asyncio.run(_ingest_pipeline(runbook_id, file_path))
    except Exception as exc:
        log.error("ingest_runbook_failed", runbook_id=runbook_id, error=str(exc),
                  traceback=_tb.format_exc())
        try:
            asyncio.run(_mark_failed(runbook_id))
        except Exception:
            pass
        raise self.retry(exc=exc)
