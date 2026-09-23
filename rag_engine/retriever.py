"""
Vector similarity retriever using pgvector CosineDistance (PostgreSQL)
with a Python-based cosine fallback for SQLite development.
"""
import logging
from typing import List, Dict, Any

from django.conf import settings
from documents.models import DocumentChunk
from rag_engine.embeddings import get_embedding

logger = logging.getLogger(__name__)

USE_PGVECTOR = 'postgresql' in settings.DATABASES['default'].get('ENGINE', '')

# Number of initial candidates from vector search (before reranking)
DEFAULT_TOP_K = 20


def retrieve_similar_chunks(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    category_filter: str = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve the top-K most similar document chunks for a given query.

    1. Embeds the query using Gemini embedding API.
    2. Runs cosine similarity search against stored chunk vectors.
    3. Returns list of dicts with chunk content, metadata, and similarity score.
    """
    # Generate query embedding
    query_embedding = get_embedding(query)

    if USE_PGVECTOR:
        return _retrieve_pgvector(query_embedding, top_k, category_filter)
    else:
        return _retrieve_python_fallback(query_embedding, top_k, category_filter)


def _retrieve_pgvector(
    query_embedding: List[float],
    top_k: int,
    category_filter: str = None,
) -> List[Dict[str, Any]]:
    """Retrieve chunks using pgvector CosineDistance via Django ORM."""
    from pgvector.django import CosineDistance

    queryset = DocumentChunk.objects.filter(
        document__status='completed'
    ).select_related('document')

    if category_filter:
        queryset = queryset.filter(document__category=category_filter)

    results = (
        queryset
        .annotate(distance=CosineDistance('embedding', query_embedding))
        .order_by('distance')[:top_k]
    )

    return [
        {
            'chunk_id': chunk.id,
            'content': chunk.content,
            'section_title': chunk.section_title,
            'page_number': chunk.page_number,
            'document_title': chunk.document.title,
            'document_category': chunk.document.get_category_display(),
            'score': 1.0 - chunk.distance,  # Convert distance to similarity
        }
        for chunk in results
    ]


def _retrieve_python_fallback(
    query_embedding: List[float],
    top_k: int,
    category_filter: str = None,
) -> List[Dict[str, Any]]:
    """
    Fallback cosine similarity search using pure Python.
    Used when running on SQLite (no pgvector extension).
    """
    import math

    queryset = DocumentChunk.objects.filter(
        document__status='completed'
    ).select_related('document')

    if category_filter:
        queryset = queryset.filter(document__category=category_filter)

    scored_chunks = []
    for chunk in queryset.iterator():
        stored_vec = chunk.embedding
        if not stored_vec or len(stored_vec) == 0:
            continue
        sim = _cosine_similarity(query_embedding, stored_vec)
        scored_chunks.append({
            'chunk_id': chunk.id,
            'content': chunk.content,
            'section_title': chunk.section_title,
            'page_number': chunk.page_number,
            'document_title': chunk.document.title,
            'document_category': chunk.document.get_category_display(),
            'score': sim,
        })

    # Sort by similarity descending and return top-K
    scored_chunks.sort(key=lambda x: x['score'], reverse=True)
    return scored_chunks[:top_k]


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    import math
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
