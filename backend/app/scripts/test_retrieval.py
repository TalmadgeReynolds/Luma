"""
Test retrieval quality against evaluation questions.

Reports hit rate: % of questions where at least one correct chunk was in top-5.
"""
import asyncio
import json
from pathlib import Path

from app.db.database import AsyncSessionLocal
from app.services import retrieval_service


def _check_chunk_relevance(
    chunk,
    expected_topics: list[str],
    expected_video_title: str,
) -> bool:
    """
    Check if a retrieved chunk is relevant to the expected answer.

    A chunk is considered relevant if:
    1. It's from the expected video
    2. Its content contains at least 2 of the expected topics

    Args:
        chunk: RetrievedChunk object
        expected_topics: List of topic keywords
        expected_video_title: Expected video title

    Returns:
        True if chunk is relevant
    """
    # Check video title match
    if expected_video_title.lower() not in chunk.video_title.lower():
        return False

    # Check topic match - combine all text fields
    all_text = (
        f"{chunk.raw_text} {chunk.contextual_text} "
        f"{chunk.summary or ''} {' '.join(chunk.topic_tags)}"
    ).lower()

    # Count how many expected topics appear in the chunk
    topic_matches = sum(
        1 for topic in expected_topics
        if topic.lower() in all_text
    )

    # Require at least 2 topic matches (or 1 if only 1 topic expected)
    required_matches = min(2, len(expected_topics))
    return topic_matches >= required_matches


async def test_retrieval():
    """
    Run retrieval evaluation.

    For each eval question:
    1. Retrieve top-5 chunks
    2. Check if any are relevant
    3. Report hit/miss

    Final report: overall hit rate (must be >= 80%)
    """
    # Load eval questions
    eval_file = Path(__file__).parent.parent.parent / "fixtures" / "eval_questions.json"
    if not eval_file.exists():
        print(f"❌ Eval file not found: {eval_file}")
        return

    with open(eval_file) as f:
        eval_questions = json.load(f)

    print(f"Loaded {len(eval_questions)} evaluation questions\n")
    print("=" * 80)

    # Test each question
    results = []
    async with AsyncSessionLocal() as db_session:
        for i, eval_item in enumerate(eval_questions, 1):
            question = eval_item["question"]
            expected_topics = eval_item["expected_topics"]
            expected_video_title = eval_item["expected_video_title"]

            print(f"\n[{i}/{len(eval_questions)}] {question}")
            print(f"  Expected topics: {', '.join(expected_topics)}")

            try:
                # Retrieve top-5 chunks
                retrieved_chunks = await retrieval_service.retrieve_chunks(
                    question=question,
                    top_k=5,
                    db_session=db_session,
                )

                if not retrieved_chunks:
                    print("  ❌ No chunks retrieved")
                    results.append(False)
                    continue

                # Check if any retrieved chunk is relevant
                relevant_chunks = [
                    chunk for chunk in retrieved_chunks
                    if _check_chunk_relevance(chunk, expected_topics, expected_video_title)
                ]

                if relevant_chunks:
                    print(f"  ✅ HIT - Found {len(relevant_chunks)} relevant chunks in top-5")
                    print(f"     Best match (rank {relevant_chunks[0].rank}): {relevant_chunks[0].summary[:100]}...")
                    results.append(True)
                else:
                    print(f"  ❌ MISS - No relevant chunks in top-5")
                    print(f"     Top result: {retrieved_chunks[0].summary[:100]}...")
                    results.append(False)

            except Exception as e:
                print(f"  ❌ ERROR: {e}")
                results.append(False)

    # Calculate hit rate
    print("\n" + "=" * 80)
    print("\n📊 RESULTS SUMMARY")
    print("=" * 80)

    hits = sum(results)
    total = len(results)
    hit_rate = (hits / total * 100) if total > 0 else 0

    print(f"\nHits: {hits}/{total}")
    print(f"Hit Rate: {hit_rate:.1f}%")

    if hit_rate >= 80:
        print("\n✅ PASS - Hit rate >= 80%")
        print("Phase 5 retrieval quality gate: PASSED")
    else:
        print("\n❌ FAIL - Hit rate < 80%")
        print("Phase 5 retrieval quality gate: FAILED")
        print("\nSuggestions to improve:")
        print("  - Improve contextualization prompts")
        print("  - Adjust chunking parameters (size, overlap)")
        print("  - Add more eval questions")
        print("  - Tune hybrid search weights")

    print("\n" + "=" * 80)


async def main():
    """Entry point."""
    print("🔍 Retrieval Quality Evaluation")
    print("=" * 80)
    await test_retrieval()


if __name__ == "__main__":
    asyncio.run(main())
