"""
POST /ask endpoint - main query interface.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.schemas import AskRequest, AskResponse, ErrorResponse, ErrorDetail
from app.services import retrieval_service, answer_service
from app.errors import RetrievalError, AnswerServiceError

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
async def ask_question(
    request: AskRequest,
    db_session: AsyncSession = Depends(get_db),
) -> AskResponse:
    """
    Answer a question using RAG over webinar transcripts.

    Flow:
    1. Retrieve relevant chunks (hybrid search)
    2. Generate answer with Claude
    3. Return answer with source cards

    Args:
        request: Question from user
        db_session: Database session

    Returns:
        Answer with sources and suggested questions

    Raises:
        HTTPException: If retrieval or answer generation fails
    """
    try:
        # Step 1: Retrieve chunks
        print(f"\n[API] POST /ask: {request.question}")

        retrieved_chunks = await retrieval_service.retrieve_chunks(
            question=request.question,
            top_k=5,
            db_session=db_session,
        )

        # Step 2: Generate answer
        response = await answer_service.generate_answer(
            question=request.question,
            retrieved_chunks=retrieved_chunks,
        )

        print(f"[API] Response ready: {len(response.answer)} chars, {len(response.sources)} sources")
        return response

    except RetrievalError as e:
        print(f"[API] Retrieval error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "retrieval_error",
                    "message": "Failed to retrieve relevant content",
                    "details": {"error": str(e)},
                }
            }
        )

    except AnswerServiceError as e:
        print(f"[API] Answer generation error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "answer_error",
                    "message": "Failed to generate answer",
                    "details": {"error": str(e)},
                }
            }
        )

    except Exception as e:
        print(f"[API] Unexpected error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred",
                    "details": {"error": str(e)},
                }
            }
        )
