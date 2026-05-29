"""
POST /ask endpoint - main query interface.
"""
import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import verify_api_key
from app.db.database import get_db
from app.db.schemas import AskRequest, AskResponse
from app.services import retrieval_service, answer_service
from app.errors import RetrievalError, AnswerServiceError

router = APIRouter()


async def _execute_ask(request: AskRequest, db_session: AsyncSession) -> AskResponse:
    retrieved_chunks = await retrieval_service.retrieve_chunks(
        question=request.question,
        top_k=5,
        db_session=db_session,
        content_type_filter=request.content_type_filter,
    )
    return await answer_service.generate_answer(
        question=request.question,
        retrieved_chunks=retrieved_chunks,
    )


@router.post("/ask")
async def ask_question(
    request: AskRequest,
    db_session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Answer a question using RAG over webinar transcripts.

    Returns an SSE stream:
    - Periodic keep-alive events while Claude processes
    - A final 'complete' or 'error' event with the result
    """
    print(f"\n[API] POST /ask: {request.question}")
    if request.content_type_filter:
        print(f"[API] Content type filter: {request.content_type_filter}")

    async def event_stream():
        task = asyncio.create_task(_execute_ask(request, db_session))

        while not task.done():
            yield 'data: {"status":"processing"}\n\n'
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=4.0)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

        try:
            result = await task
            print(f"[API] Response ready: {len(result.answer)} chars, {len(result.sources)} sources")
            payload = {"status": "complete", "result": result.model_dump(mode="json")}
            yield f"data: {json.dumps(payload)}\n\n"
        except RetrievalError as e:
            print(f"[API] Retrieval error: {e}")
            payload = {"status": "error", "code": "retrieval_error", "message": "Failed to retrieve relevant content"}
            yield f"data: {json.dumps(payload)}\n\n"
        except AnswerServiceError as e:
            print(f"[API] Answer error: {e}")
            payload = {"status": "error", "code": "answer_error", "message": "Failed to generate answer"}
            yield f"data: {json.dumps(payload)}\n\n"
        except Exception as e:
            print(f"[API] Unexpected error: {e}")
            payload = {"status": "error", "code": "internal_error", "message": "An unexpected error occurred"}
            yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/ask/sync", dependencies=[Depends(verify_api_key)])
async def ask_question_sync(
    request: AskRequest,
    db_session: AsyncSession = Depends(get_db),
) -> AskResponse:
    """
    Answer a question using RAG. Returns plain JSON (no streaming).
    Easier to test with curl or Postman than the SSE /ask endpoint.
    """
    print(f"\n[API] POST /ask/sync: {request.question}")
    return await _execute_ask(request, db_session)
