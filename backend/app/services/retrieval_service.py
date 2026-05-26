"""
Retrieval service - hybrid search over webinar chunks.

Combines vector similarity search with keyword search for optimal recall.
"""
from uuid import UUID
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Query, RetrievalLog, Video
from app.errors import RetrievalError
from app.services import claude_service, embedding_service


class RetrievedChunk:
    """Container for retrieved chunk with metadata."""
    def __init__(
        self,
        chunk_id: UUID,
        video_id: UUID,
        video_title: str,
        content_type: str,
        source_url: str | None,
        start_time_seconds: float,
        end_time_seconds: float,
        raw_text: str,
        contextual_text: str,
        summary: str | None,
        topic_tags: list[str] | None,
        speaker_names: list[str] | None,
        section_heading: str | None,
        score: float,
        rank: int,
    ):
        self.chunk_id = chunk_id
        self.video_id = video_id
        self.video_title = video_title
        self.content_type = content_type
        self.source_url = source_url
        self.start_time_seconds = start_time_seconds
        self.end_time_seconds = end_time_seconds
        self.raw_text = raw_text
        self.contextual_text = contextual_text
        self.summary = summary
        self.topic_tags = topic_tags or []
        self.speaker_names = speaker_names or []
        self.section_heading = section_heading
        self.score = score
        self.rank = rank


async def retrieve_chunks(
    question: str,
    top_k: int,
    db_session: AsyncSession,
    content_type_filter: str | None = None,
) -> list[RetrievedChunk]:
    """
    Retrieve relevant chunks using hybrid search.

    Flow:
    1. Rewrite query with Claude
    2. Embed rewritten query
    3. Vector search (cosine similarity, top_k * 2)
    4. Keyword search (ts_rank, top_k * 2)
    5. Merge, dedupe, sort by max(vector_score, keyword_score)
    6. Log to retrieval_logs
    7. Return top_k

    Args:
        question: User question
        top_k: Number of chunks to return
        db_session: Database session
        content_type_filter: Optional filter by content type ('webinar' | 'article')

    Returns:
        List of RetrievedChunk objects

    Raises:
        RetrievalError: If retrieval fails
    """
    try:
        # Step 1: Rewrite query with Claude
        print(f"[Retrieval] Rewriting query...")
        rewrite_result = await claude_service.rewrite_query(question)
        rewritten_query = rewrite_result["rewritten_query"]
        print(f"  Original: {question}")
        print(f"  Rewritten: {rewritten_query}")

        # Step 2: Embed rewritten query
        print(f"[Retrieval] Embedding query...")
        query_embedding = await embedding_service.embed_text(rewritten_query)

        if content_type_filter:
            # Filtered: single pool, no diversity needed
            print(f"[Retrieval] Running filtered search ({content_type_filter})...")
            vector_results = await _vector_search(
                query_embedding,
                top_k * 2,
                content_type_filter,
                db_session,
            )
            keyword_results = await _keyword_search(
                rewritten_query,
                top_k * 2,
                content_type_filter,
                db_session,
            )
            merged = _merge_and_dedupe(vector_results, keyword_results)
            final_chunks = merged[:top_k]
        else:
            # Unfiltered: search each content type separately to guarantee diversity.
            # These queries share one AsyncSession, so they must run serially.
            print(f"[Retrieval] Running per-type search for diversity...")
            vec_articles = await _vector_search(query_embedding, top_k, 'article', db_session)
            vec_webinars = await _vector_search(query_embedding, top_k, 'webinar', db_session)
            kw_articles = await _keyword_search(rewritten_query, top_k, 'article', db_session)
            kw_webinars = await _keyword_search(rewritten_query, top_k, 'webinar', db_session)
            print(f"  Vector: {len(vec_articles)} articles, {len(vec_webinars)} webinars")
            print(f"  Keyword: {len(kw_articles)} articles, {len(kw_webinars)} webinars")
            merged = _merge_and_dedupe(
                vec_articles + vec_webinars,
                kw_articles + kw_webinars,
            )
            final_chunks = _pick_with_diversity(merged, top_k, min_per_type=3)

        # Assign ranks
        for i, chunk in enumerate(final_chunks, 1):
            chunk.rank = i

        # Step 6: Log retrieval
        query_record = Query(
            user_question=question,
            rewritten_question=rewritten_query,
        )
        db_session.add(query_record)
        await db_session.flush()

        for chunk in final_chunks:
            log_entry = RetrievalLog(
                query_id=query_record.id,
                chunk_id=chunk.chunk_id,
                rank=chunk.rank,
                retrieval_score=chunk.score,
            )
            db_session.add(log_entry)

        await db_session.commit()

        print(f"[Retrieval] Complete - returning {len(final_chunks)} chunks "
              f"({sum(1 for c in final_chunks if c.content_type=='article')} articles, "
              f"{sum(1 for c in final_chunks if c.content_type=='webinar')} webinars)")
        return final_chunks

    except Exception as e:
        await db_session.rollback()
        raise RetrievalError(f"Retrieval failed: {e}") from e


async def _vector_search(
    query_embedding: list[float],
    limit: int,
    content_type_filter: str | None,
    db_session: AsyncSession,
) -> list[tuple[Chunk, float]]:
    """
    Vector similarity search using cosine distance.

    Returns:
        List of (Chunk, score) tuples
    """
    # Only retrieve from videos with status='embedded'
    # Use cosine distance operator: <=>
    # Lower distance = higher similarity
    # Convert to similarity score: 1 - distance
    # Format embedding as a string so asyncpg/SQLAlchemy can bind it
    # before the ::vector cast (avoids the named-param + :: conflict).
    embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

    # Build WHERE clause with optional content_type filter
    where_clause = "v.status = 'embedded' AND c.embedding IS NOT NULL"
    if content_type_filter:
        where_clause += " AND v.content_type = :content_type"

    query = text(f"""
        SELECT
            c.id, c.video_id, c.start_time_seconds, c.end_time_seconds,
            c.raw_text, c.contextual_text, c.summary, c.topic_tags,
            c.speaker_names, c.section_heading, c.chunk_index, c.word_count,
            v.title as video_title, v.content_type, v.source_url,
            (1 - (c.embedding <=> CAST(:query_embedding AS vector))) as score
        FROM chunks c
        JOIN videos v ON c.video_id = v.id
        WHERE {where_clause}
        ORDER BY c.embedding <=> CAST(:query_embedding AS vector)
        LIMIT :limit
    """)

    params = {
        "query_embedding": embedding_str,
        "limit": limit,
    }
    if content_type_filter:
        params["content_type"] = content_type_filter

    result = await db_session.execute(query, params)
    rows = result.fetchall()

    chunks = []
    for row in rows:
        chunk = Chunk(
            id=row.id,
            video_id=row.video_id,
            start_time_seconds=row.start_time_seconds,
            end_time_seconds=row.end_time_seconds,
            raw_text=row.raw_text,
            contextual_text=row.contextual_text,
            summary=row.summary,
            topic_tags=row.topic_tags,
            speaker_names=row.speaker_names,
            section_heading=row.section_heading,
            chunk_index=row.chunk_index,
            word_count=row.word_count,
        )
        # Attach video metadata as attributes for convenience
        chunk.video_title = row.video_title
        chunk.content_type = row.content_type
        chunk.source_url = row.source_url
        score = float(row.score)
        chunks.append((chunk, score))

    return chunks


async def _keyword_search(
    query_text: str,
    limit: int,
    content_type_filter: str | None,
    db_session: AsyncSession,
) -> list[tuple[Chunk, float]]:
    """
    Keyword search using PostgreSQL full-text search.

    Searches both raw_text and summary fields.

    Returns:
        List of (Chunk, score) tuples
    """
    # Build WHERE clause with optional content_type filter
    where_clause = """v.status = 'embedded'
          AND (
            to_tsvector('english', c.raw_text) @@ plainto_tsquery('english', :query_text)
            OR to_tsvector('english', COALESCE(c.summary, '')) @@ plainto_tsquery('english', :query_text)
          )"""

    if content_type_filter:
        where_clause += " AND v.content_type = :content_type"

    # Use ts_rank to score matches
    # Search in both raw_text and summary
    query = text(f"""
        SELECT
            c.id, c.video_id, c.start_time_seconds, c.end_time_seconds,
            c.raw_text, c.contextual_text, c.summary, c.topic_tags,
            c.speaker_names, c.section_heading, c.chunk_index, c.word_count,
            v.title as video_title, v.content_type, v.source_url,
            GREATEST(
                ts_rank(to_tsvector('english', c.raw_text), plainto_tsquery('english', :query_text)),
                ts_rank(to_tsvector('english', COALESCE(c.summary, '')), plainto_tsquery('english', :query_text))
            ) as score
        FROM chunks c
        JOIN videos v ON c.video_id = v.id
        WHERE {where_clause}
        ORDER BY score DESC
        LIMIT :limit
    """)

    params = {
        "query_text": query_text,
        "limit": limit,
    }
    if content_type_filter:
        params["content_type"] = content_type_filter

    result = await db_session.execute(query, params)
    rows = result.fetchall()

    chunks = []
    for row in rows:
        chunk = Chunk(
            id=row.id,
            video_id=row.video_id,
            start_time_seconds=row.start_time_seconds,
            end_time_seconds=row.end_time_seconds,
            raw_text=row.raw_text,
            contextual_text=row.contextual_text,
            summary=row.summary,
            topic_tags=row.topic_tags,
            speaker_names=row.speaker_names,
            section_heading=row.section_heading,
            chunk_index=row.chunk_index,
            word_count=row.word_count,
        )
        chunk.video_title = row.video_title
        chunk.content_type = row.content_type
        chunk.source_url = row.source_url
        score = float(row.score)
        chunks.append((chunk, score))

    return chunks


def _pick_with_diversity(
    chunks: list[RetrievedChunk],
    top_k: int,
    min_per_type: int = 3,
) -> list[RetrievedChunk]:
    """
    Pick top_k chunks ensuring minimum representation from each content type.

    Guarantees at least min_per_type results from each type that has any
    results, then fills remaining slots with the highest scorers overall.
    If only one content type exists in the pool, returns top_k as-is.
    """
    by_type: dict[str, list[RetrievedChunk]] = {}
    for chunk in chunks:
        by_type.setdefault(chunk.content_type, []).append(chunk)

    # Single content type — no diversity action needed
    if len(by_type) <= 1:
        return chunks[:top_k]

    selected: list[RetrievedChunk] = []
    selected_ids: set = set()

    # Reserve minimum slots for each type
    for type_chunks in by_type.values():
        for chunk in type_chunks[:min_per_type]:
            if chunk.chunk_id not in selected_ids:
                selected.append(chunk)
                selected_ids.add(chunk.chunk_id)

    # Fill remaining slots from the highest-scoring unselected chunks
    remaining = top_k - len(selected)
    for chunk in chunks:
        if chunk.chunk_id not in selected_ids and remaining > 0:
            selected.append(chunk)
            selected_ids.add(chunk.chunk_id)
            remaining -= 1

    selected.sort(key=lambda x: x.score, reverse=True)
    return selected


def _merge_and_dedupe(
    vector_results: list[tuple[Chunk, float]],
    keyword_results: list[tuple[Chunk, float]],
) -> list[RetrievedChunk]:
    """
    Merge vector and keyword results, dedupe, and sort by max score.

    If a chunk appears in both result sets, use the maximum score.
    Sort by score descending.

    Returns:
        List of RetrievedChunk objects sorted by score
    """
    # Build dict: chunk_id -> (chunk, max_score)
    chunk_map = {}

    for chunk, score in vector_results:
        chunk_id = chunk.id
        if chunk_id not in chunk_map or score > chunk_map[chunk_id][1]:
            chunk_map[chunk_id] = (chunk, score)

    for chunk, score in keyword_results:
        chunk_id = chunk.id
        if chunk_id not in chunk_map or score > chunk_map[chunk_id][1]:
            chunk_map[chunk_id] = (chunk, score)

    # Convert to RetrievedChunk objects
    retrieved_chunks = []
    for chunk, score in chunk_map.values():
        retrieved_chunk = RetrievedChunk(
            chunk_id=chunk.id,
            video_id=chunk.video_id,
            video_title=chunk.video_title,
            content_type=chunk.content_type,
            source_url=chunk.source_url,
            start_time_seconds=chunk.start_time_seconds,
            end_time_seconds=chunk.end_time_seconds,
            raw_text=chunk.raw_text,
            contextual_text=chunk.contextual_text,
            summary=chunk.summary,
            topic_tags=chunk.topic_tags,
            speaker_names=chunk.speaker_names,
            section_heading=chunk.section_heading,
            score=score,
            rank=0,  # Will be assigned after sorting
        )
        retrieved_chunks.append(retrieved_chunk)

    # Sort by score descending
    retrieved_chunks.sort(key=lambda x: x.score, reverse=True)

    return retrieved_chunks
