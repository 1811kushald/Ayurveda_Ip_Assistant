from django.test import TestCase
from accounts.models import User
from documents.models import Document, DocumentChunk
from documents.services import chunk_document_pages, _estimate_tokens
from rag_engine.embeddings import get_embedding, EMBEDDING_DIMENSION
from documents.tasks import process_document_pipeline


class PipelineTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin_pipeline@ipsakti.com',
            password='Password123!',
            full_name='Pipeline Admin',
            role=User.Role.ADMIN
        )
        self.document = Document.objects.create(
            title='Test Patents Act',
            category=Document.Category.PATENT_LAW,
            jurisdiction='India',
            uploaded_by=self.admin,
            file_size_bytes=1024
        )

    def test_embedding_service_returns_correct_dimensions(self):
        """Test embedding service returns 768-dimensional float list."""
        vec = get_embedding("Section 3(p) excludes traditional knowledge from patentability.")
        self.assertIsInstance(vec, list)
        self.assertEqual(len(vec), EMBEDDING_DIMENSION)
        self.assertTrue(all(isinstance(x, (float, int)) for x in vec))

    def test_section_aware_semantic_chunking(self):
        """Test section-based chunking splits text on section headings."""
        pages = [
            {
                'page_number': 1,
                'text': (
                    "Section 3 Inventions not patentable.\n"
                    "The following are not inventions within the meaning of this Act:\n"
                    "(p) an invention which in effect is traditional knowledge or which is an aggregation or duplication of known properties of traditionally known component or components.\n"
                    "Section 4 Inventions relating to atomic energy not patentable.\n"
                    "No patent shall be granted for an invention relating to atomic energy falling within sub-section (1) of section 20 of the Atomic Energy Act, 1962."
                )
            }
        ]

        chunks = chunk_document_pages(pages)
        self.assertGreaterEqual(len(chunks), 1)

        # Verify chunk fields
        first_chunk = chunks[0]
        self.assertIn('content', first_chunk)
        self.assertIn('page_number', first_chunk)
        self.assertIn('section_title', first_chunk)
        self.assertGreater(first_chunk['token_count'], 0)

    def test_token_estimation(self):
        """Test token estimation helper."""
        tokens = _estimate_tokens("Short sentence for token count estimation.")
        self.assertGreater(tokens, 0)

    def test_document_chunk_model_creation(self):
        """Test saving DocumentChunk to database."""
        vec = get_embedding("Test chunk content")
        chunk = DocumentChunk.objects.create(
            document=self.document,
            content="Sample legal text",
            chunk_index=0,
            page_number=1,
            section_title="Section 3(p)",
            embedding=vec,
            token_count=10
        )
        self.assertEqual(self.document.chunks.count(), 1)
        self.assertEqual(chunk.section_title, "Section 3(p)")
