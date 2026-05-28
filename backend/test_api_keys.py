"""Test script to validate all API keys."""
import asyncio
from anthropic import Anthropic
from openai import OpenAI
from app.config import get_settings

settings = get_settings()


def test_anthropic():
    """Test Anthropic API key."""
    print("\n[1/2] Testing Anthropic API...")
    try:
        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": "Say 'API key works'"}]
        )
        print(f"✓ Anthropic API: {response.content[0].text}")
        return True
    except Exception as e:
        print(f"✗ Anthropic API failed: {e}")
        return False


def test_openai():
    """Test OpenAI API key."""
    print("\n[2/2] Testing OpenAI API...")
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.embeddings.create(
            input="test",
            model=settings.EMBEDDING_MODEL
        )
        dim = len(response.data[0].embedding)
        print(f"✓ OpenAI: Generated {dim}-dim embedding")

        # Validate dimension matches config
        if dim != settings.EMBEDDING_DIMENSION:
            print(f"✗ Dimension mismatch: got {dim}, expected {settings.EMBEDDING_DIMENSION}")
            return False

        return True
    except Exception as e:
        print(f"✗ OpenAI failed: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("API Keys Validation Test")
    print("=" * 60)

    results = [
        test_anthropic(),
        test_openai(),
    ]

    print("\n" + "=" * 60)
    if all(results):
        print("✓ All API keys valid!")
        print("\nYou're ready to proceed with ingestion.")
    else:
        print("✗ Some API keys failed - check errors above")
        print("\nPlease fix the failing keys before proceeding.")
    print("=" * 60)
