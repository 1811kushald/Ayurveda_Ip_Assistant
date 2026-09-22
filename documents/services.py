import re
import pymupdf as fitz  # PyMuPDF
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Target max tokens/characters per chunk (~500-1000 tokens ≈ 2000-3500 chars)
MAX_CHUNK_CHARS = 3000
MIN_CHUNK_CHARS = 100

# Regex patterns matching Indian legal section/chapter/rule headings
SECTION_HEADING_PATTERN = re.compile(
    r'(?i)^(?:section|sec\.|chapter|chap\.|rule|schedule|article)\s+[0-9ivxlc]+[a-z0-9\(\)]*',
    re.MULTILINE
)


def extract_pages_from_pdf(file_path: str) -> List[Dict[str, Any]]:
    """
    Extract text page-by-page from a PDF file using PyMuPDF (fitz).
    Returns list of dicts: [{'page_number': 1, 'text': '...'}, ...]
    """
    pages = []
    try:
        doc = fitz.open(file_path)
        for page_idx, page in enumerate(doc):
            text = page.get_text("text").strip()
            if text:
                pages.append({
                    'page_number': page_idx + 1,
                    'text': text,
                })
        doc.close()
    except Exception as e:
        logger.error(f"Failed to extract text from PDF {file_path}: {str(e)}")
        raise e
    return pages


def chunk_document_pages(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Perform section-aware semantic chunking across extracted PDF pages.
    Detects Section/Chapter headings and groups related paragraphs together.
    Returns list of chunk dicts:
      [{'chunk_index': 0, 'content': '...', 'page_number': 1, 'section_title': 'Section 3', 'token_count': 120}, ...]
    """
    chunks = []
    current_section = "General Provision"
    buffer_text = ""
    current_page = 1
    chunk_counter = 0

    for page_info in pages:
        page_num = page_info['page_number']
        text = page_info['text']
        lines = text.split('\n')

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Check if line matches a section heading
            match = SECTION_HEADING_PATTERN.search(line_str)
            if match:
                # Flush previous buffer as a chunk if sufficient length
                if len(buffer_text.strip()) >= MIN_CHUNK_CHARS:
                    chunks.append({
                        'chunk_index': chunk_counter,
                        'content': buffer_text.strip(),
                        'page_number': current_page,
                        'section_title': current_section,
                        'token_count': _estimate_tokens(buffer_text),
                    })
                    chunk_counter += 1
                    buffer_text = ""

                current_section = line_str[:150]  # Cap section title length

            buffer_text += " " + line_str
            current_page = page_num

            # If buffer exceeds max character limit, flush it
            if len(buffer_text) >= MAX_CHUNK_CHARS:
                chunks.append({
                    'chunk_index': chunk_counter,
                    'content': buffer_text.strip(),
                    'page_number': current_page,
                    'section_title': current_section,
                    'token_count': _estimate_tokens(buffer_text),
                })
                chunk_counter += 1
                buffer_text = ""

    # Flush any remaining buffer text
    if len(buffer_text.strip()) > 0:
        chunks.append({
            'chunk_index': chunk_counter,
            'content': buffer_text.strip(),
            'page_number': current_page,
            'section_title': current_section,
            'token_count': _estimate_tokens(buffer_text),
        })

    return chunks


def _estimate_tokens(text: str) -> int:
    """Rough estimation of token count (~4 chars per token)."""
    return max(1, len(text) // 4)
