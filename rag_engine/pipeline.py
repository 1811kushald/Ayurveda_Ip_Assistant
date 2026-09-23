"""
Full RAG orchestration pipeline.
Entry point: query_pipeline(user_query) → dict with answer + sources.
"""
import logging
import time
from typing import Dict, Any, Optional

from rag_engine.retriever import retrieve_similar_chunks
from rag_engine.reranker import rerank_chunks
from rag_engine.generator import generate_response
from rag_engine.providers.groq_provider import GroqLLMProvider

logger = logging.getLogger(__name__)

# Pipeline configuration defaults
RETRIEVAL_TOP_K = 20   # Initial vector search candidates
RERANK_TOP_K = 5       # Chunks kept after reranking


def query_pipeline(
    user_query: str,
    category_filter: Optional[str] = None,
    retrieval_top_k: int = RETRIEVAL_TOP_K,
    rerank_top_k: int = RERANK_TOP_K,
) -> Dict[str, Any]:
    """
    Execute the full RAG pipeline for a user query.

    Steps:
        1. Retrieve top-K similar chunks via vector search.
        2. Rerank candidates using Jina AI cross-encoder.
        3. Generate an LLM response with source citations.

    Args:
        user_query: The user's natural language question.
        category_filter: Optional document category to filter retrieval.
        retrieval_top_k: Number of initial vector search candidates.
        rerank_top_k: Number of chunks to keep after reranking.

    Returns:
        dict with keys:
            - 'answer': The generated response text with citations.
            - 'sources': List of source references used.
            - 'model': The LLM model name used.
            - 'input_tokens': Tokens consumed.
            - 'output_tokens': Tokens generated.
            - 'num_chunks_retrieved': How many chunks were found.
            - 'num_chunks_reranked': How many survived reranking.
            - 'elapsed_seconds': Total pipeline wall-clock time.
    """
    start_time = time.time()

    # ── Step 1: Retrieve ──────────────────────────────────────────────
    logger.info('Pipeline: retrieving top-%d chunks for query.', retrieval_top_k)
    retrieved_chunks = retrieve_similar_chunks(
        query=user_query,
        top_k=retrieval_top_k,
        category_filter=category_filter,
    )
    logger.info('Pipeline: retrieved %d chunks.', len(retrieved_chunks))

    if not retrieved_chunks:
        elapsed = round(time.time() - start_time, 2)
        return {
            'answer': (
                'I could not find any relevant documents to answer your question. '
                'Please ensure that relevant documents have been uploaded and processed.'
            ),
            'sources': [],
            'model': 'N/A',
            'input_tokens': 0,
            'output_tokens': 0,
            'num_chunks_retrieved': 0,
            'num_chunks_reranked': 0,
            'elapsed_seconds': elapsed,
        }

    # ── Step 2: Rerank ────────────────────────────────────────────────
    logger.info('Pipeline: reranking %d chunks → top %d.', len(retrieved_chunks), rerank_top_k)
    reranked_chunks = rerank_chunks(
        query=user_query,
        chunks=retrieved_chunks,
        top_k=rerank_top_k,
    )
    logger.info('Pipeline: %d chunks after reranking.', len(reranked_chunks))

    # ── Step 3: Generate ──────────────────────────────────────────────
    logger.info('Pipeline: generating LLM response.')
    provider = GroqLLMProvider()
    result = generate_response(
        query=user_query,
        context_chunks=reranked_chunks,
        provider=provider,
    )

    elapsed = round(time.time() - start_time, 2)
    logger.info('Pipeline: completed in %.2fs.', elapsed)

    return {
        'answer': result['answer'],
        'sources': result['sources'],
        'model': result['model'],
        'input_tokens': result['input_tokens'],
        'output_tokens': result['output_tokens'],
        'num_chunks_retrieved': len(retrieved_chunks),
        'num_chunks_reranked': len(reranked_chunks),
        'elapsed_seconds': elapsed,
    }
