import logging
from concurrent.futures import ThreadPoolExecutor
from django.db import connections, transaction
from .models import Document, DocumentChunk
from .services import extract_pages_from_pdf, chunk_document_pages
from rag_engine.embeddings import get_embedding

logger = logging.getLogger(__name__)

# Single ThreadPoolExecutor instance with 2 worker threads (safe for 512MB RAM)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='doc_worker')


def dispatch_document_processing(document_id: int):
    """Submit document processing task to the ThreadPoolExecutor background queue."""
    _executor.submit(_safe_process_document, document_id)


def _safe_process_document(document_id: int):
    """Wrapper that catches exceptions and ensures DB connection cleanup in worker thread."""
    try:
        process_document_pipeline(document_id)
    except Exception as e:
        logger.error(f"Uncaught exception in background processing of Document #{document_id}: {str(e)}")
    finally:
        # Prevent connection leakage in multithreaded environment
        connections.close_all()


def process_document_pipeline(document_id: int):
    """Full ingestion pipeline: PDF -> pages -> chunks -> Gemini embeddings -> DB storage."""
    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.error(f"Document #{document_id} not found for processing.")
        return

    logger.info(f"Starting ingestion pipeline for Document #{document.id}: '{document.title}'")

    # Update status to PROCESSING
    document.status = Document.Status.PROCESSING
    document.error_message = None
    document.save(update_fields=['status', 'error_message'])

    try:
        # 1. Check file existence
        if not document.file or not os_file_exists(document.file.path):
            raise FileNotFoundError(f"File path for document '{document.title}' does not exist.")

        # 2. Extract pages using PyMuPDF
        pages = extract_pages_from_pdf(document.file.path)
        if not pages:
            raise ValueError("No extractable text found in PDF document.")

        # 3. Perform semantic chunking
        raw_chunks = chunk_document_pages(pages)
        if not raw_chunks:
            raise ValueError("Document yielded 0 chunks after semantic splitting.")

        # 4. Clear existing chunks if reprocessing
        with transaction.atomic():
            DocumentChunk.objects.filter(document=document).delete()

            # 5. Generate embeddings and create DocumentChunk instances
            chunks_to_create = []
            for chunk_data in raw_chunks:
                text_content = chunk_data['content']
                # Call Gemini Embedding API
                vector = get_embedding(text_content)

                chunk_obj = DocumentChunk(
                    document=document,
                    content=text_content,
                    chunk_index=chunk_data['chunk_index'],
                    page_number=chunk_data['page_number'],
                    section_title=chunk_data['section_title'],
                    embedding=vector,
                    token_count=chunk_data['token_count'],
                )
                chunks_to_create.append(chunk_obj)

            # Bulk create chunks
            DocumentChunk.objects.bulk_create(chunks_to_create)

            # 6. Update document status to COMPLETED
            document.status = Document.Status.COMPLETED
            document.total_chunks = len(chunks_to_create)
            document.save(update_fields=['status', 'total_chunks'])

        logger.info(f"Successfully processed Document #{document.id}: {len(chunks_to_create)} chunks created.")

    except Exception as err:
        logger.error(f"Error processing Document #{document.id}: {str(err)}", exc_info=True)
        document.status = Document.Status.FAILED
        document.error_message = str(err)
        document.save(update_fields=['status', 'error_message'])


def os_file_exists(path: str) -> bool:
    import os
    return os.path.exists(path)
