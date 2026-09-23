"""
Jina AI Reranker: re-ranks retrieved chunks using a cross-encoder model.
Falls back to returning chunks as-is if JINA_API_KEY is not configured.
"""
import logging
import os
from typing import List, Dict, Any

import httpx

logger = logging.getLogger(__name__)

JINA_RERANK_URL = 'https://api.jina.ai/v1/rerank'
JINA_MODEL = 'jina-reranker-v2-base-multilingual'

# After reranking, keep only the top N most relevant chunks
DEFAULT_RERANK_TOP_K = 5


def rerank_chunks(
    query: str,
    chunks: List[Dict[str, Any]],
    top_k: int = DEFAULT_RERANK_TOP_K,
) -> List[Dict[str, Any]]:
    """
    Re-rank retrieved chunks using Jina AI Reranker.

    Args:
        query: The user's original query.
        chunks: List of chunk dicts from the retriever (must have 'content' key).
        top_k: Number of top results to keep after reranking.

    Returns:
        Reranked list of chunk dicts, limited to top_k.
        Falls back to score-sorted input if Jina API is unavailable.
    """
    api_key = os.environ.get('JINA_API_KEY', '')

    if not api_key:
        logger.warning(
            'JINA_API_KEY not set — skipping reranking, returning top-%d by vector score.',
            top_k,
        )
        return chunks[:top_k]

    if not chunks:
        return []

    try:
        documents = [chunk['content'] for chunk in chunks]

        response = httpx.post(
            JINA_RERANK_URL,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': JINA_MODEL,
                'query': query,
                'documents': documents,
                'top_n': top_k,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

        reranked = []
        for result in data.get('results', []):
            idx = result['index']
            relevance_score = result['relevance_score']
            chunk = chunks[idx].copy()
            chunk['rerank_score'] = relevance_score
            reranked.append(chunk)

        logger.info(
            'Jina reranker returned %d results (from %d candidates).',
            len(reranked),
            len(chunks),
        )
        return reranked

    except httpx.HTTPStatusError as e:
        logger.error('Jina reranker HTTP error: %s', e.response.text)
    except httpx.RequestError as e:
        logger.error('Jina reranker request failed: %s', str(e))
    except (KeyError, IndexError, ValueError) as e:
        logger.error('Jina reranker response parsing error: %s', str(e))

    # Fallback: return top-k by original vector score
    logger.warning('Falling back to vector-score ordering after reranker failure.')
    return chunks[:top_k]
