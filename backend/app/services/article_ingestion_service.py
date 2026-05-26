"""
Article ingestion service - orchestrates the article ingestion pipeline.

Parallel to webinar ingestion, but for text articles:
- Step 1: Create article record (content_type='article')
- Step 2: Parse article into pseudo-segments (with section detection)
- Step 3: Chunk segments (reuse chunking_service)
- Step 4: Claude contextualization (enrich with summary, topic_tags, questions_answered)
- Step 5: Generate embeddings and store vectors
"""
import re
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Video
from app.errors import IngestionError
from app.services.chunking_service import chunk_segments
from app.services import claude_service
from app.services import embedding_service


def parse_article_to_segments(article_text: str) -> list[dict]:
    """
    Convert article text into segments compatible with chunk_segments().

    Detects section headings to track structure:
    - Markdown format: ## Heading or ### Sub-heading
    - Text-based detection: Lines with all caps or followed by === underlines

    Returns segments with character positions stored as floats in start_time_seconds/end_time_seconds:
    {
        "start_time_seconds": float(char_position),
        "end_time_seconds": float(char_position + length),
        "speaker": None,
        "text": paragraph_text,
        "section_heading": "Using Master References" | None
    }
    """
    segments = []
    char_offset = 0
    current_section = None

    lines = article_text.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Skip empty lines
        if not line:
            char_offset += len(lines[i]) + 1  # +1 for newline
            i += 1
            continue

        # Detect markdown headings (## Heading or ### Heading)
        markdown_match = re.match(r'^(#{2,3})\s+(.+)$', line)
        if markdown_match:
            current_section = markdown_match.group(2).strip()
            char_offset += len(lines[i]) + 1
            i += 1
            continue

        # Detect text-based headings followed by === or ---
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line and (next_line[0] == '=' or next_line[0] == '-') and len(set(next_line)) == 1:
                # This is a heading
                current_section = line
                char_offset += len(lines[i]) + 1 + len(lines[i + 1]) + 1
                i += 2
                continue

        # Detect all-caps lines as headings (must be > 10 chars to avoid abbreviations)
        if line.isupper() and len(line) > 10 and not any(c in line for c in ['.', '!', '?']):
            current_section = line
            char_offset += len(lines[i]) + 1
            i += 1
            continue

        # Build paragraph from consecutive lines
        paragraph_lines = [line]
        start_offset = char_offset
        char_offset += len(lines[i]) + 1
        i += 1

        # Continue collecting lines until we hit an empty line, heading, or end
        while i < len(lines):
            next_line = lines[i].strip()

            # Stop if empty line
            if not next_line:
                break

            # Stop if next line looks like a heading
            if re.match(r'^#{2,3}\s+', next_line):
                break
            if i + 1 < len(lines) and lines[i + 1].strip() and lines[i + 1].strip()[0] in ['=', '-'] and len(set(lines[i + 1].strip())) == 1:
                break
            if next_line.isupper() and len(next_line) > 10 and not any(c in next_line for c in ['.', '!', '?']):
                break

            paragraph_lines.append(next_line)
            char_offset += len(lines[i]) + 1
            i += 1

        # Create segment for this paragraph
        paragraph_text = ' '.join(paragraph_lines)
        if paragraph_text.strip():
            segment = {
                "start_time_seconds": float(start_offset),
                "end_time_seconds": float(char_offset),
                "speaker": None,
                "text": paragraph_text,
                "section_heading": current_section,
            }
            segments.append(segment)

    return segments


async def ingest_article(
    title: str,
    source_url: str,
    publication_date: str | None,  # ISO format: "2026-03-09"
    article_text: str,
    db_session: AsyncSession,
) -> tuple[UUID, int]:
    """
    Ingest an article into the database.

    5-step pipeline (parallel to webinar ingestion):
    - Step 1: Create article record (content_type='article')
    - Step 2: Parse article text into pseudo-segments
    - Step 3: Chunk the segments (reuse chunk_segments())
    - Step 4: Claude contextualization (enrich with summary, topic_tags, questions_answered)
    - Step 5: Generate embeddings and store vectors

    Args:
        title: Article title
        source_url: Source URL (Learning Center link)
        publication_date: Publication date (ISO format or None)
        article_text: Full article text
        db_session: Database session

    Returns:
        Tuple of (article_id, chunk_count)

    Raises:
        IngestionError: If ingestion fails at any step
    """
    try:
        # ====================================================================
        # Step 1: Create article record
        # ====================================================================
        print(f"\n=== Step 1: Creating article record ===")
        print(f"Title: {title}")
        print(f"Source: {source_url}")
        print(f"Date: {publication_date or 'Unknown'}")

        # Parse date if provided
        parsed_date = None
        if publication_date:
            try:
                parsed_date = datetime.fromisoformat(publication_date).date()
            except (ValueError, TypeError) as e:
                print(f"Warning: Could not parse date '{publication_date}': {e}")

        article = Video(
            title=title,
            content_type='article',
            source_url=source_url,
            webinar_date=parsed_date,
            speakers=None,
            video_url=None,
            duration_seconds=None,
            status='processing',
        )
        db_session.add(article)
        await db_session.flush()

        article_id = article.id
        print(f"✓ Created article with ID: {article_id}")

        # ====================================================================
        # Step 2: Parse article into segments
        # ====================================================================
        print(f"\n=== Step 2: Parsing article into segments ===")
        print(f"Article length: {len(article_text)} characters")

        segments = parse_article_to_segments(article_text)
        print(f"✓ Parsed {len(segments)} segments")

        # Show section breakdown
        sections = {}
        for seg in segments:
            section = seg.get("section_heading") or "(No section)"
            sections[section] = sections.get(section, 0) + 1
        print(f"Section breakdown:")
        for section, count in sections.items():
            print(f"  - {section}: {count} paragraphs")

        # ====================================================================
        # Step 3: Chunk segments
        # ====================================================================
        print(f"\n=== Step 3: Chunking segments ===")
        chunk_dicts = chunk_segments(segments, target_words=600, overlap_words=120)
        print(f"✓ Created {len(chunk_dicts)} chunks")

        # ====================================================================
        # Step 4: Claude contextualization
        # ====================================================================
        print(f"\n=== Step 4: Claude contextualization ===")

        for i, chunk_dict in enumerate(chunk_dicts, 1):
            print(f"Contextualizing chunk {i}/{len(chunk_dicts)}...", end=" ", flush=True)

            # Extract section heading from chunk metadata
            section_heading = chunk_dict.get("section_heading")

            # Call Claude to contextualize
            result = await claude_service.contextualize_article_chunk(
                article_title=title,
                publication_date=publication_date or "Unknown",
                source_url=source_url,
                section_heading=section_heading,
                start_pos=int(chunk_dict["start_time_seconds"]),
                end_pos=int(chunk_dict["end_time_seconds"]),
                raw_chunk_text=chunk_dict["raw_text"],
            )

            # Store results back in chunk_dict
            chunk_dict["contextual_text"] = result["contextual_text"]
            chunk_dict["summary"] = result["summary"]
            chunk_dict["topic_tags"] = result["topic_tags"]
            chunk_dict["questions_answered"] = result["questions_this_answers"]

            print("✓")

        print(f"✓ Contextualized all {len(chunk_dicts)} chunks")

        # Update status
        article.status = 'contextualized'
        await db_session.flush()

        # ====================================================================
        # Step 5: Generate embeddings and insert chunks
        # ====================================================================
        print(f"\n=== Step 5: Generating embeddings ===")

        for i, chunk_dict in enumerate(chunk_dicts, 1):
            print(f"Embedding chunk {i}/{len(chunk_dicts)}...", end=" ", flush=True)

            # Format embedding input with [Article] discriminator
            section = chunk_dict.get("section_heading") or ""
            tags_str = ", ".join(chunk_dict.get("topic_tags", []))

            embedding_input = (
                f"[Article] {title} | "
                f"{publication_date or 'Unknown'} | "
                f"{section} | "
                f"{chunk_dict.get('summary', '')} | "
                f"{tags_str} | "
                f"{chunk_dict['contextual_text']}"
            )

            # Generate embedding
            embedding_vector = await embedding_service.embed_text(embedding_input)

            # Create chunk record
            chunk = Chunk(
                video_id=article_id,
                start_time_seconds=chunk_dict["start_time_seconds"],
                end_time_seconds=chunk_dict["end_time_seconds"],
                raw_text=chunk_dict["raw_text"],
                contextual_text=chunk_dict["contextual_text"],
                summary=chunk_dict.get("summary"),
                topic_tags=chunk_dict.get("topic_tags"),
                questions_answered=chunk_dict.get("questions_answered"),
                speaker_names=[],  # Empty for articles
                section_heading=chunk_dict.get("section_heading"),
                embedding=embedding_vector,
                chunk_index=chunk_dict["chunk_index"],
                word_count=chunk_dict["word_count"],
            )
            db_session.add(chunk)

            print("✓")

        # Update article status to embedded
        article.status = 'embedded'
        await db_session.commit()

        print(f"\n✓✓✓ Article ingestion complete!")
        print(f"  - Article ID: {article_id}")
        print(f"  - Chunks: {len(chunk_dicts)}")
        print(f"  - Status: embedded")

        return article_id, len(chunk_dicts)

    except Exception as e:
        await db_session.rollback()
        raise IngestionError(f"Article ingestion failed: {e}") from e
