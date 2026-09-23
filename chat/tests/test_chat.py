from unittest.mock import patch
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from chat.models import Conversation, Message
from chat.forms import ChatMessageForm

User = get_user_model()


class ChatModelTest(TestCase):
    """Test Conversation and Message models."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='ayur_user@example.com',
            password='password123',
            full_name='Ayurveda Researcher',
        )

    def test_conversation_creation_and_properties(self):
        """Test Conversation model creation, str method, and properties."""
        conv = Conversation.objects.create(
            user=self.user,
            title='Patent Query',
        )
        self.assertEqual(str(conv), f"Patent Query ({self.user.email})")
        self.assertEqual(conv.message_count, 0)
        self.assertIsNone(conv.last_message)

        # Add message
        msg = Message.objects.create(
            conversation=conv,
            sender=Message.Sender.USER,
            content='Hello',
        )
        self.assertEqual(conv.message_count, 1)
        self.assertEqual(conv.last_message, msg)

    def test_message_creation_with_sources(self):
        """Test Message creation with metadata and cited sources JSON."""
        conv = Conversation.objects.create(user=self.user)
        sources_data = [
            {
                'document_title': 'The Patents Act, 1970',
                'section_title': 'Section 3(d)',
                'page_number': '12',
            }
        ]
        msg = Message.objects.create(
            conversation=conv,
            sender=Message.Sender.ASSISTANT,
            content='Section 3(d) prevents evergreening.',
            sources=sources_data,
            model_name='qwen/qwen3.8-27b',
            token_count=120,
            latency_seconds=0.85,
        )
        self.assertEqual(msg.sender, 'assistant')
        self.assertEqual(len(msg.sources), 1)
        self.assertEqual(msg.sources[0]['section_title'], 'Section 3(d)')
        self.assertEqual(msg.model_name, 'qwen/qwen3.8-27b')
        self.assertIn('[Assistant]', str(msg))

    def test_conversation_cascade_delete(self):
        """Test that deleting a conversation cascades and deletes all its messages."""
        conv = Conversation.objects.create(user=self.user)
        conv_id = conv.id
        Message.objects.create(conversation=conv, sender=Message.Sender.USER, content='Q1')
        Message.objects.create(conversation=conv, sender=Message.Sender.ASSISTANT, content='A1')

        self.assertEqual(Message.objects.filter(conversation_id=conv_id).count(), 2)
        conv.delete()
        self.assertEqual(Message.objects.filter(conversation_id=conv_id).count(), 0)


class ChatViewPermissionsTest(TestCase):
    """Test authentication and user isolation permissions."""

    def setUp(self):
        self.client = Client()
        self.user_a = User.objects.create_user(
            email='user_a@example.com',
            password='password123',
            full_name='User A',
        )
        self.user_b = User.objects.create_user(
            email='user_b@example.com',
            password='password123',
            full_name='User B',
        )
        self.conv_a = Conversation.objects.create(user=self.user_a, title="User A Thread")

    def test_unauthenticated_user_redirected(self):
        """Anonymous user should be redirected to login."""
        r1 = self.client.get(reverse('chat:index'))
        self.assertEqual(r1.status_code, 302)
        self.assertIn('/accounts/login/', r1.url)

        r2 = self.client.get(reverse('chat:detail', args=[self.conv_a.pk]))
        self.assertEqual(r2.status_code, 302)

    def test_user_isolation(self):
        """User B should receive 404 when trying to access User A's conversation."""
        self.client.login(username='user_b@example.com', password='password123')

        # Try to view User A's conversation
        r_detail = self.client.get(reverse('chat:detail', args=[self.conv_a.pk]))
        self.assertEqual(r_detail.status_code, 404)

        # Try to delete User A's conversation
        r_del = self.client.post(reverse('chat:delete', args=[self.conv_a.pk]))
        self.assertEqual(r_del.status_code, 404)


class ChatViewsFlowTest(TestCase):
    """Test full chat views interaction flow including HTMX messaging."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='lawyer@ayurveda.org',
            password='password123',
            full_name='Legal Advisor',
        )
        self.client.login(username='lawyer@ayurveda.org', password='password123')

    def test_index_view_auto_creates_conversation(self):
        """GET /chat/ should create a conversation if none exists."""
        self.assertEqual(Conversation.objects.filter(user=self.user).count(), 0)
        resp = self.client.get(reverse('chat:index'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'chat/chat.html')
        self.assertEqual(Conversation.objects.filter(user=self.user).count(), 1)

    def test_new_view_creates_and_redirects(self):
        """GET /chat/new/ should create a new conversation thread and redirect to detail."""
        resp = self.client.get(reverse('chat:new'), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'chat/chat.html')
        self.assertEqual(Conversation.objects.filter(user=self.user).count(), 1)

    @patch('chat.views.query_pipeline')
    def test_send_message_htmx_success(self, mock_pipeline):
        """POST /chat/<id>/message/ via HTMX should run RAG pipeline and return message partial."""
        mock_pipeline.return_value = {
            'answer': 'Under Section 3(p), traditional knowledge is not patentable. [Source: The Patents Act 1970, Section 3(p), Page 8]',
            'sources': [
                {
                    'document_title': 'The Patents Act, 1970',
                    'section_title': 'Section 3(p)',
                    'page_number': '8',
                }
            ],
            'model': 'qwen/qwen3.8-27b',
            'input_tokens': 200,
            'output_tokens': 50,
            'elapsed_seconds': 0.65,
        }

        conv = Conversation.objects.create(user=self.user, title='New Conversation')

        post_data = {
            'content': 'Can traditional Ayurvedic formulations be patented in India?',
            'category': 'patent_law',
        }

        # Simulate HTMX request with HX-Request header
        resp = self.client.post(
            reverse('chat:send_message', args=[conv.pk]),
            data=post_data,
            headers={'HX-Request': 'true'},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'chat/partials/message_pair.html')

        # Check DB messages created
        self.assertEqual(conv.messages.count(), 2)
        user_msg = conv.messages.first()
        assistant_msg = conv.messages.last()

        self.assertEqual(user_msg.sender, Message.Sender.USER)
        self.assertEqual(user_msg.content, post_data['content'])

        self.assertEqual(assistant_msg.sender, Message.Sender.ASSISTANT)
        self.assertIn('Section 3(p)', assistant_msg.content)
        self.assertEqual(len(assistant_msg.sources), 1)

        # Check conversation title auto-updated
        conv.refresh_from_db()
        self.assertIn('Can traditional Ayurvedic formulations', conv.title)

        # Check HTML content
        self.assertContains(resp, 'The Patents Act, 1970')
        self.assertContains(resp, 'Section 3(p)')
        self.assertContains(resp, 'qwen/qwen3.8-27b')

    def test_send_message_empty_content_rejected(self):
        """POST with empty content should return 400 Bad Request."""
        conv = Conversation.objects.create(user=self.user)
        resp = self.client.post(
            reverse('chat:send_message', args=[conv.pk]),
            data={'content': '   '},
        )
        self.assertEqual(resp.status_code, 400)

    def test_clear_and_delete_views(self):
        """Test clearing conversation messages and deleting conversation."""
        conv = Conversation.objects.create(user=self.user)
        Message.objects.create(conversation=conv, sender=Message.Sender.USER, content='Q1')

        # Clear messages
        r_clear = self.client.post(reverse('chat:clear', args=[conv.pk]), follow=True)
        self.assertEqual(r_clear.status_code, 200)
        self.assertEqual(conv.messages.count(), 0)

        # Delete conversation
        r_del = self.client.post(reverse('chat:delete', args=[conv.pk]), follow=True)
        self.assertEqual(r_del.status_code, 200)
        self.assertFalse(Conversation.objects.filter(pk=conv.pk).exists())
