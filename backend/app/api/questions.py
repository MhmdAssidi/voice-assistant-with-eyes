"""GET /api/questions (owner: Student B, task B11): the Q&A history, newest first."""

from fastapi import APIRouter, Query
from starlette.concurrency import run_in_threadpool

from app.assistant import qa_repository
from app.contracts import QaRecord

router = APIRouter(prefix="/api/questions", tags=["questions (Student B)"])


@router.get("", response_model=list[QaRecord])
async def list_questions(limit: int = Query(50, ge=1, le=200)) -> list[QaRecord]:
    return await run_in_threadpool(qa_repository.list_recent, limit)
