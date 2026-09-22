import os
import logging
from typing import List

logger = logging.getLogger(__name__)

# Default dimension for gemini-embedding-001 with MRL truncation
EMBEDDING_DIMENSION = 768
MODEL_NAME = "gemini-embedding-001"


def get_embedding(text: str) -> List[float]:
    """
    Generate a 768-dimensional embedding vector for a given text string.
    Uses Google Gemini API ('gemini-embedding-001').
    Falls back to a deterministic mock vector if GOOGLE_API_KEY is not set (for dev/testing).
    """
    api_key = os.environ.get('GOOGLE_API_KEY', '').strip()

    if not api_key:
        logger.warning("GOOGLE_API_KEY not set. Using fallback embedding vector for development.")
        return _generate_mock_embedding(text)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=text,
            config=types.EmbedContentConfig(
                output_dimensionality=EMBEDDING_DIMENSION
            )
        )
        if response and hasattr(response, 'embedding') and response.embedding:
            return response.embedding.values
        elif response and hasattr(response, 'embeddings') and response.embeddings:
            return response.embeddings[0].values
        else:
            logger.error("Empty embedding returned from Gemini API.")
            return _generate_mock_embedding(text)

    except Exception as e:
        logger.error(f"Error calling Gemini Embedding API: {str(e)}")
        return _generate_mock_embedding(text)


def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of texts."""
    return [get_embedding(t) for t in texts]


def _generate_mock_embedding(text: str) -> List[float]:
    """
    Generate a deterministic 768-dim mock float vector based on text hash.
    Used for local testing when GOOGLE_API_KEY is not configured.
    """
    import hashlib

    hash_obj = hashlib.sha256(text.encode('utf-8')).digest()
    # Expand 32 bytes hash into 768 floats normalized between -1.0 and 1.0
    floats = []
    for i in range(EMBEDDING_DIMENSION):
        byte_val = hash_obj[i % len(hash_obj)]
        # Map 0-255 to -1.0 .. 1.0
        val = (byte_val / 127.5) - 1.0
        floats.append(round(val, 6))
    return floats
