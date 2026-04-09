"""Business logic for runbook upload, listing, retrieval, deletion, and RAG queries."""

import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import get_logger
from backend.models.runbook_model import Runbook, RunbookStatus
from backend.rag.rag_pipeline import run_rag_query
from backend.rag.vector_store import delete_by_runbook_id

log = get_logger(__name__)

UPLOAD_DIR = Path("uploads/runbooks")
ALLOWED_TYPES = {
    "application/pdf": ".pdf",
    "text/markdown": ".md",
    "text/plain": ".txt",
    "text/x-markdown": ".md",
}
MAX_FILE_SIZE_MB = 50


def _ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(original: str, ext: str) -> str:
    unique_id = uuid.uuid4().hex
    return f"{unique_id}{ext}"


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

async def upload_runbook(
    db: AsyncSession,
    file: UploadFile,
    description: str | None,
    tags: list[str] | None,
) -> Runbook:
    """Save the uploaded file to disk, create the DB record, and enqueue ingestion."""
    _ensure_upload_dir()

    content_type = file.content_type or ""
    if content_type not in ALLOWED_TYPES:
        # Fallback: infer from filename extension
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in (".pdf", ".md", ".markdown", ".txt"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported file type: {content_type or suffix}. "
                       "Allowed: PDF, Markdown, plain text.",
            )
        ext = suffix
        file_type = suffix.lstrip(".")
    else:
        ext = ALLOWED_TYPES[content_type]
        file_type = ext.lstrip(".")

    stored_filename = _safe_filename(file.filename or "runbook", ext)
    dest_path = UPLOAD_DIR / stored_filename

    # Stream file to disk and check size
    size = 0
    with dest_path.open("wb") as fh:
        while chunk := await file.read(1024 * 64):  # 64 KB chunks
            size += len(chunk)
            if size > MAX_FILE_SIZE_MB * 1024 * 1024:
                dest_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds {MAX_FILE_SIZE_MB} MB limit.",
                )
            fh.write(chunk)

    runbook = Runbook(
        filename=stored_filename,
        original_name=file.filename or stored_filename,
        file_type=file_type,
        file_size_bytes=size,
        status=RunbookStatus.PENDING.value,
        description=description,
        tags=tags or [],
    )
    db.add(runbook)
    await db.commit()
    await db.refresh(runbook)

    log.info(
        "runbook_uploaded",
        runbook_id=str(runbook.id),
        original_name=runbook.original_name,
        size_bytes=size,
    )

    # Enqueue Celery ingestion task (import here to avoid circular imports).
    from backend.tasks.document_ingestion import ingest_runbook

    ingest_runbook.delay(str(runbook.id), str(dest_path), title=runbook.title)

    return runbook


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def list_runbooks(db: AsyncSession) -> list[Runbook]:
    result = await db.execute(select(Runbook).order_by(Runbook.created_at.desc()))
    return list(result.scalars().all())


async def get_runbook(db: AsyncSession, runbook_id: uuid.UUID) -> Runbook:
    result = await db.execute(select(Runbook).where(Runbook.id == runbook_id))
    runbook = result.scalar_one_or_none()
    if not runbook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runbook not found.")
    return runbook


# ---------------------------------------------------------------------------
# Update metadata
# ---------------------------------------------------------------------------

async def update_runbook(
    db: AsyncSession,
    runbook_id: uuid.UUID,
    description: str | None,
    tags: list[str] | None,
) -> Runbook:
    runbook = await get_runbook(db, runbook_id)
    if description is not None:
        runbook.description = description
    if tags is not None:
        runbook.tags = tags
    await db.commit()
    await db.refresh(runbook)
    log.info("runbook_updated", title=runbook.title, runbook_id=str(runbook_id))
    return runbook


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

async def delete_runbook(db: AsyncSession, runbook_id: uuid.UUID) -> None:
    runbook = await get_runbook(db, runbook_id)

    # Remove vector embeddings from ChromaDB
    runbook_title = runbook.title
    try:
        delete_by_runbook_id(str(runbook_id))
    except Exception as exc:
        log.warning("chroma_delete_failed", title=runbook_title, runbook_id=str(runbook_id), error=str(exc))

    # Remove file from disk
    file_path = UPLOAD_DIR / runbook.filename
    if file_path.exists():
        file_path.unlink()

    await db.delete(runbook)
    await db.commit()
    log.info("runbook_deleted", title=runbook_title, runbook_id=str(runbook_id))


# ---------------------------------------------------------------------------
# RAG query
# ---------------------------------------------------------------------------

def query_runbooks(
    query: str,
    top_k: int = 5,
    filter_tags: list[str] | None = None,
) -> dict:
    """Run a RAG query against indexed runbook chunks."""
    return run_rag_query(query=query, top_k=top_k, filter_tags=filter_tags)
