"""
Unit tests for Sprint 5: RAG Query Engine.
Tests retriever, reranker, generator, and pipeline with mocked external APIs.
"""
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from documents.models import Document, DocumentChunk
from rag_engine.retriever import (
    retrieve_similar_chunks,
    _cosine_similarity,
    _retrieve_python_fallback,
)
from rag_engine.reranker import rerank_chunks
from rag_engine.generator import (
    build_context_block,
    generate_response,
    _extract_sources,
    SYSTEM_PROMPT,
)
from rag_engine.pipeline import query_pipeline

User = get_user_model()


class CosineSimTest(TestCase):
    """Test the pure-Python cosine similarity helper."""

    def test_identical_vectors(self):
        vec = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(_cosine_similarity(vec, vec), 1.0, places=5)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(_cosine_similarity(a, b), 0.0, places=5)

    def test_zero_vector(self):
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        self.assertEqual(_cosine_similarity(a, b), 0.0)

    def test_similar_vectors(self):
        a = [1.0, 1.0, 0.0]
        b = [1.0, 0.0, 0.0]
        sim = _cosine_similarity(a, b)
        self.assertGreater(sim, 0.5)
        self.assertLess(sim, 1.0)


class RetrieverTest(TestCase):
    """Test the vector retriever with SQLite Python fallback."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            full_name='Test Admin',
        )
        # Create a completed document
        self.doc = Document.objects.create(
            title='Test Patent Act',
            category='patent_law',
            status='completed',
            uploaded_by=self.user,
            file=SimpleUploadedFile('test.pdf', b'%PDF-1.4 test'),
        )
        # Create chunks with 768-dim mock embeddings
        # Chunk 1: embedding mostly in dimension 0
        embed_1 = [0.0] * 768
        embed_1[0] = 1.0
        # Chunk 2: embedding mostly in dimension 1
        embed_2 = [0.0] * 768
        embed_2[1] = 1.0

        self.chunk1 = DocumentChunk.objects.create(
            document=self.doc,
            content='Patents in India are governed by the Patents Act, 1970.',
            section_title='Section 1 - Short title',
            page_number=1,
            chunk_index=0,
            embedding=embed_1,
        )
        self.chunk2 = DocumentChunk.objects.create(
            document=self.doc,
            content='Ayurvedic formulations can be protected under traditional knowledge.',
            section_title='Section 3 - Definitions',
            page_number=2,
            chunk_index=1,
            embedding=embed_2,
        )

    @patch('rag_engine.retriever.get_embedding')
    def test_retrieve_returns_results(self, mock_embed):
        """Retriever should return scored chunks."""
        # Query embedding closer to chunk1
        query_vec = [0.0] * 768
        query_vec[0] = 0.9
        query_vec[1] = 0.1
        mock_embed.return_value = query_vec

        results = retrieve_similar_chunks('patent law India', top_k=5)
        self.assertGreater(len(results), 0)
        # chunk1 should rank higher (closer to query vector)
        self.assertEqual(results[0]['section_title'], 'Section 1 - Short title')

    @patch('rag_engine.retriever.get_embedding')
    def test_retrieve_respects_top_k(self, mock_embed):
        """Retriever should limit results to top_k."""
        query_vec = [0.0] * 768
        query_vec[0] = 0.5
        query_vec[1] = 0.5
        mock_embed.return_value = query_vec

        results = retrieve_similar_chunks('patent law', top_k=1)
        self.assertEqual(len(results), 1)

    @patch('rag_engine.retriever.get_embedding')
    def test_retrieve_category_filter(self, mock_embed):
        """Retriever should filter by document category."""
        query_vec = [0.0] * 768
        query_vec[0] = 0.5
        mock_embed.return_value = query_vec

        results = retrieve_similar_chunks(
            'trademark query',
            top_k=5,
            category_filter='trademark',  # No trademark docs exist
        )
        self.assertEqual(len(results), 0)

    def test_python_fallback_cosine(self):
        """Python fallback retriever should compute cosine similarity correctly."""
        # Query embedding closer to chunk1
        query_vec = [0.0] * 768
        query_vec[0] = 1.0

        results = _retrieve_python_fallback(
            query_embedding=query_vec,
            top_k=5,
        )
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]['section_title'], 'Section 1 - Short title')


class RerankerTest(TestCase):
    """Test the Jina AI reranker with mocked HTTP calls."""

    def setUp(self):
        self.chunks = [
            {
                'chunk_id': 1,
                'content': 'The Patents Act, 1970 governs patent law in India.',
                'section_title': 'Section 1',
                'page_number': 1,
                'document_title': 'Patents Act',
                'document_category': 'Patent',
                'score': 0.85,
            },
            {
                'chunk_id': 2,
                'content': 'Traditional Knowledge Digital Library protects Ayurvedic formulations.',
                'section_title': 'Chapter 2',
                'page_number': 5,
                'document_title': 'TKDL Guide',
                'document_category': 'Traditional Knowledge',
                'score': 0.72,
            },
            {
                'chunk_id': 3,
                'content': 'Geographical Indications protect regional Ayurvedic products.',
                'section_title': 'Part III',
                'page_number': 10,
                'document_title': 'GI Act',
                'document_category': 'Geographical Indication',
                'score': 0.65,
            },
        ]

    def test_fallback_when_no_api_key(self):
        """Without JINA_API_KEY, should return chunks[:top_k] as-is."""
        with patch.dict('os.environ', {'JINA_API_KEY': ''}, clear=False):
            result = rerank_chunks('patent law', self.chunks, top_k=2)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['chunk_id'], 1)

    @patch('rag_engine.reranker.httpx.post')
    def test_rerank_with_api(self, mock_post):
        """With JINA_API_KEY, should call API and reorder by relevance_score."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'results': [
                {'index': 2, 'relevance_score': 0.95},  # GI Act ranked first
                {'index': 0, 'relevance_score': 0.80},  # Patents Act second
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        with patch.dict('os.environ', {'JINA_API_KEY': 'test-key'}, clear=False):
            result = rerank_chunks('patent law', self.chunks, top_k=2)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['chunk_id'], 3)  # GI Act first
        self.assertAlmostEqual(result[0]['rerank_score'], 0.95)

    @patch('rag_engine.reranker.httpx.post')
    def test_rerank_api_error_fallback(self, mock_post):
        """On API error, should fall back to vector-score ordering."""
        import httpx
        mock_post.side_effect = httpx.RequestError('Connection failed')

        with patch.dict('os.environ', {'JINA_API_KEY': 'test-key'}, clear=False):
            result = rerank_chunks('patent law', self.chunks, top_k=2)

        self.assertEqual(len(result), 2)
        # Falls back to original order, so first two chunks
        self.assertEqual(result[0]['chunk_id'], 1)

    def test_empty_chunks(self):
        """Empty chunk list should return empty list."""
        result = rerank_chunks('query', [], top_k=5)
        self.assertEqual(result, [])


class GeneratorTest(TestCase):
    """Test context building and response generation."""

    def setUp(self):
        self.chunks = [
            {
                'chunk_id': 1,
                'content': 'Section 3(d) of the Patents Act prevents evergreening.',
                'section_title': 'Section 3(d)',
                'page_number': 12,
                'document_title': 'Patents Act, 1970',
                'document_category': 'Patent',
            },
            {
                'chunk_id': 2,
                'content': 'TKDL has documented 2,50,000 Ayurvedic formulations.',
                'section_title': 'Overview',
                'page_number': 1,
                'document_title': 'TKDL Documentation',
                'document_category': 'Traditional Knowledge',
            },
        ]

    def test_build_context_block(self):
        """Context block should include all chunk metadata."""
        context = build_context_block(self.chunks)

        self.assertIn('Context Chunk 1', context)
        self.assertIn('Context Chunk 2', context)
        self.assertIn('Patents Act, 1970', context)
        self.assertIn('Section 3(d)', context)
        self.assertIn('Page: 12', context)
        self.assertIn('evergreening', context)

    def test_build_context_block_empty(self):
        """Empty chunks should return fallback message."""
        context = build_context_block([])
        self.assertEqual(context, 'No relevant context found.')

    def test_extract_sources_deduplication(self):
        """Sources should be deduplicated by title+section+page."""
        # Add a duplicate
        chunks_with_dup = self.chunks + [self.chunks[0]]
        sources = _extract_sources(chunks_with_dup)
        self.assertEqual(len(sources), 2)

    @patch('rag_engine.generator.GroqLLMProvider')
    def test_generate_response_structure(self, mock_provider_cls):
        """Generate response should return structured dict."""
        mock_provider = MagicMock()
        mock_provider.generate.return_value = {
            'content': 'Section 3(d) prevents evergreening. [Source: Patents Act, Section 3(d), Page 12]',
            'model': 'qwen-qwq-32b',
            'input_tokens': 500,
            'output_tokens': 50,
        }

        result = generate_response(
            query='What is Section 3(d)?',
            context_chunks=self.chunks,
            provider=mock_provider,
        )

        self.assertIn('answer', result)
        self.assertIn('sources', result)
        self.assertIn('model', result)
        self.assertEqual(result['model'], 'qwen-qwq-32b')
        self.assertEqual(len(result['sources']), 2)


class PipelineTest(TestCase):
    """Integration tests for the full RAG pipeline with mocked externals."""

    @patch('rag_engine.pipeline.generate_response')
    @patch('rag_engine.pipeline.rerank_chunks')
    @patch('rag_engine.pipeline.retrieve_similar_chunks')
    def test_full_pipeline_success(self, mock_retrieve, mock_rerank, mock_generate):
        """Full pipeline should wire retrieve → rerank → generate."""
        mock_chunks = [
            {
                'chunk_id': 1,
                'content': 'Test content',
                'section_title': 'Section 1',
                'page_number': 1,
                'document_title': 'Test Doc',
                'document_category': 'Patent',
                'score': 0.9,
            },
        ]
        mock_retrieve.return_value = mock_chunks
        mock_rerank.return_value = mock_chunks
        mock_generate.return_value = {
            'answer': 'Test answer with [Source: Test Doc, Section 1, Page 1]',
            'sources': [{'document_title': 'Test Doc', 'section_title': 'Section 1', 'page_number': '1'}],
            'model': 'qwen-qwq-32b',
            'input_tokens': 100,
            'output_tokens': 50,
        }

        result = query_pipeline('What is patent law?')

        self.assertIn('answer', result)
        self.assertIn('sources', result)
        self.assertEqual(result['num_chunks_retrieved'], 1)
        self.assertEqual(result['num_chunks_reranked'], 1)
        self.assertIn('elapsed_seconds', result)

        # Verify call chain
        mock_retrieve.assert_called_once()
        mock_rerank.assert_called_once()
        mock_generate.assert_called_once()

    @patch('rag_engine.pipeline.retrieve_similar_chunks')
    def test_pipeline_no_results(self, mock_retrieve):
        """Pipeline should return a helpful message when no chunks are found."""
        mock_retrieve.return_value = []

        result = query_pipeline('What is XYZ?')

        self.assertIn('could not find', result['answer'].lower())
        self.assertEqual(result['sources'], [])
        self.assertEqual(result['num_chunks_retrieved'], 0)

    @patch('rag_engine.pipeline.generate_response')
    @patch('rag_engine.pipeline.rerank_chunks')
    @patch('rag_engine.pipeline.retrieve_similar_chunks')
    def test_pipeline_with_category_filter(self, mock_retrieve, mock_rerank, mock_generate):
        """Pipeline should pass category filter to retriever."""
        mock_retrieve.return_value = []

        result = query_pipeline('test', category_filter='patent')

        mock_retrieve.assert_called_once_with(
            query='test',
            top_k=20,
            category_filter='patent',
        )
