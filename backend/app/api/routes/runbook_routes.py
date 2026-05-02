"""Runbook upload, listing, deletion, and RAG query API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import get_current_user, require_role
from backend.core.security import Role
from backend.database.session import get_db
from backend.models.user_model import User
from backend.schemas.runbook_schema import RunbookQueryRequest, RunbookQueryResponse, RunbookResponse, RunbookUpdate
from backend.services import audit_service, runbook_service

router = APIRouter(prefix="/runbooks", tags=["Runbooks"])


@router.post(
    "/upload",
    response_model=RunbookResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload and ingest a runbook document",
)
async def upload_runbook(
    file: UploadFile,
    description: str | None = Form(default=None),
    tags: str | None = Form(default=None, description="Comma-separated tags"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(Role.ENGINEER)),
) -> RunbookResponse:
    """
    Upload a PDF or Markdown runbook. The file is saved to disk, a database
    record is created, and an async Celery task is enqueued to parse, chunk,
    embed, and index it into ChromaDB. Returns **202 Accepted** immediately.
    """
    tag_list: list[str] | None = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    runbook = await runbook_service.upload_runbook(
        db=db,
        file=file,
        description=description,
        tags=tag_list,
    )
    await audit_service.log_action(
        db, user_id=_current_user.id, action="runbook_upload",
        resource_type="runbook", resource_id=str(runbook.id),
        metadata={"filename": runbook.filename, "tags": tag_list},
    )
    return RunbookResponse.model_validate(runbook)


@router.get(
    "/",
    response_model=list[RunbookResponse],
    summary="List all ingested runbooks",
)
async def list_runbooks(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[RunbookResponse]:
    runbooks = await runbook_service.list_runbooks(db)
    return [RunbookResponse.model_validate(r) for r in runbooks]


@router.get(
    "/{runbook_id}",
    response_model=RunbookResponse,
    summary="Get a single runbook by ID",
)
async def get_runbook(
    runbook_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> RunbookResponse:
    runbook = await runbook_service.get_runbook(db, runbook_id)
    return RunbookResponse.model_validate(runbook)


@router.patch(
    "/{runbook_id}",
    response_model=RunbookResponse,
    summary="Update runbook description and tags",
)
async def update_runbook(
    runbook_id: UUID,
    payload: RunbookUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(Role.ENGINEER)),
) -> RunbookResponse:
    runbook = await runbook_service.update_runbook(
        db, runbook_id, payload.description, payload.tags
    )
    return RunbookResponse.model_validate(runbook)


@router.delete(
    "/{runbook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a runbook and its vector embeddings",
)
async def delete_runbook(
    runbook_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(Role.ADMIN)),
) -> None:
    await runbook_service.delete_runbook(db, runbook_id)
    await audit_service.log_action(
        db, user_id=_current_user.id, action="runbook_delete",
        resource_type="runbook", resource_id=str(runbook_id),
    )


@router.post(
    "/{runbook_id}/reembed",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-generate embeddings for a runbook (use after switching embedding model)",
)
async def reembed_runbook(
    runbook_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(Role.ADMIN)),
) -> dict:
    runbook = await runbook_service.get_runbook(db, runbook_id)
    from backend.tasks.embedding_tasks import reembed_runbook as reembed_task
    reembed_task.delay(str(runbook.id))
    return {"status": "queued", "runbook_id": str(runbook.id)}


@router.post(
    "/{runbook_id}/approve",
    response_model=RunbookResponse,
    summary="Approve an auto-generated runbook draft and trigger indexing (ADMIN only)",
)
async def approve_runbook(
    runbook_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(Role.ADMIN)),
) -> RunbookResponse:
    """
    Move an auto-generated runbook from PENDING_REVIEW → PENDING and enqueue
    the embedding task so it gets indexed into ChromaDB.
    """
    from backend.models.runbook_model import Runbook, RunbookStatus
    from sqlalchemy import select

    result = await db.execute(select(Runbook).where(Runbook.id == runbook_id))
    runbook = result.scalar_one_or_none()
    if not runbook:
        raise HTTPException(status_code=404, detail="Runbook not found")
    if not runbook.auto_generated:
        raise HTTPException(status_code=400, detail="Only auto-generated runbooks can be approved this way")
    if runbook.status != RunbookStatus.PENDING_REVIEW.value:
        raise HTTPException(status_code=400, detail=f"Runbook is not in PENDING_REVIEW status: {runbook.status}")

    runbook.status = RunbookStatus.PENDING.value
    await db.commit()
    await db.refresh(runbook)

    from backend.tasks.document_ingestion import ingest_runbook
    ingest_runbook.delay(str(runbook.id), f"uploads/runbooks/{runbook.filename}")

    return RunbookResponse.model_validate(runbook)


@router.post(
    "/query",
    response_model=RunbookQueryResponse,
    summary="RAG query across all indexed runbooks",
)
async def query_runbooks(
    payload: RunbookQueryRequest,
    _current_user: User = Depends(get_current_user),
) -> RunbookQueryResponse:
    """
    Embed the query, search ChromaDB for relevant runbook chunks, and use the
    configured LLM to synthesise a structured answer with source citations.
    """
    result = runbook_service.query_runbooks(
        query=payload.query,
        top_k=payload.top_k,
        filter_tags=payload.filter_tags,
    )
    return RunbookQueryResponse(**result)
