"""
RAG generator: assembles context from retrieved chunks and generates
an LLM response with strict source citations.
"""
import logging
from typing import List, Dict, Any

from rag_engine.providers.groq_provider import GroqLLMProvider

logger = logging.getLogger(__name__)

# ── System Prompt ──────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are **IP-SAKTI Sahayak**, an expert AI assistant specializing in Intellectual Property (IP) rights and regulatory guidance for Ayurvedic and traditional medicine in India.

### Your Core Rules:
1. **ONLY** answer questions based on the provided context below. Do NOT use any external or prior knowledge.
2. **ALWAYS** cite your sources using this exact format at the end of each relevant statement:
   [Source: <Document Title>, <Section/Chapter>, Page <number>]
3. If the section title is not available, use the chunk reference directly.
4. If the provided context does NOT contain enough information to answer the question, respond with:
   "I do not have sufficient information in the available documents to answer this question. Please try uploading relevant documents or rephrasing your query."
5. Be precise, professional, and structured in your responses.
6. Use bullet points or numbered lists for multi-part answers.
7. When referencing legal acts, rules, or regulations, quote them accurately from the context.

### Disclaimer:
Always end your response with this disclaimer on a new line:
"⚠️ **Disclaimer:** This is AI-generated guidance based on uploaded documents. It is not legal advice. Please consult a qualified IP attorney or the relevant Indian government authority for official guidance."
"""


def build_context_block(chunks: List[Dict[str, Any]]) -> str:
    """
    Build a formatted context string from ranked chunks.

    Each chunk is wrapped with metadata headers so the LLM can cite
    the document title, section, and page number accurately.
    """
    if not chunks:
        return "No relevant context found."

    blocks = []
    for i, chunk in enumerate(chunks, 1):
        section = chunk.get('section_title', 'N/A')
        page = chunk.get('page_number', 'N/A')
        title = chunk.get('document_title', 'Unknown Document')
        category = chunk.get('document_category', '')
        content = chunk.get('content', '')

        block = (
            f"--- Context Chunk {i} ---\n"
            f"Document: {title}\n"
            f"Category: {category}\n"
            f"Section: {section}\n"
            f"Page: {page}\n"
            f"Content:\n{content}\n"
            f"--- End Chunk {i} ---"
        )
        blocks.append(block)

    return "\n\n".join(blocks)


def generate_response(
    query: str,
    context_chunks: List[Dict[str, Any]],
    provider: GroqLLMProvider = None,
) -> Dict[str, Any]:
    """
    Generate a cited RAG response for a user query.

    Args:
        query: The user's original question.
        context_chunks: Ranked list of chunk dicts from reranker/retriever.
        provider: LLM provider instance (defaults to GroqLLMProvider).

    Returns:
        dict with keys:
            - 'answer': The LLM's response text with citations.
            - 'sources': List of source references used.
            - 'model': The model used for generation.
            - 'input_tokens': Number of input tokens consumed.
            - 'output_tokens': Number of output tokens generated.
    """
    if provider is None:
        provider = GroqLLMProvider()

    # Build the context block
    context_text = build_context_block(context_chunks)

    # Assemble the user message with query + context
    user_message = (
        f"### User Question:\n{query}\n\n"
        f"### Retrieved Context:\n{context_text}"
    )

    # Call the LLM
    result = provider.generate(prompt=SYSTEM_PROMPT, context=user_message)

    # Extract unique source references for the response metadata
    sources = _extract_sources(context_chunks)

    return {
        'answer': result['content'],
        'sources': sources,
        'model': result['model'],
        'input_tokens': result['input_tokens'],
        'output_tokens': result['output_tokens'],
    }


def _extract_sources(chunks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Extract unique document source references from context chunks.
    Used to display "Sources Used" in the chat UI.
    """
    seen = set()
    sources = []
    for chunk in chunks:
        title = chunk.get('document_title', 'Unknown')
        section = chunk.get('section_title', '')
        page = chunk.get('page_number', '')

        key = f"{title}|{section}|{page}"
        if key not in seen:
            seen.add(key)
            sources.append({
                'document_title': title,
                'section_title': section,
                'page_number': str(page) if page else '',
            })
    return sources
