from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from documents.models import Document, DocumentChunk
from chat.models import Conversation, Message

User = get_user_model()


class DashboardAccessTest(TestCase):
    """Test role-based access control for dashboard views."""

    def setUp(self):
        self.client = Client()
        self.regular_user = User.objects.create_user(
            email='user@ipsakti.com',
            password='password123',
            full_name='Regular User',
            role=User.Role.USER,
        )
        self.admin_user = User.objects.create_user(
            email='admin@ipsakti.com',
            password='password123',
            full_name='Admin User',
            role=User.Role.ADMIN,
        )
        self.super_admin = User.objects.create_superuser(
            email='superadmin@ipsakti.com',
            password='password123',
            full_name='Super Admin User',
        )

    def test_unauthenticated_user_redirected(self):
        """Anonymous user should be redirected to login."""
        r1 = self.client.get(reverse('dashboard:index'))
        self.assertEqual(r1.status_code, 302)
        self.assertIn('/accounts/login/', r1.url)

        r2 = self.client.get(reverse('dashboard:users'))
        self.assertEqual(r2.status_code, 302)

        r3 = self.client.get(reverse('dashboard:system_status'))
        self.assertEqual(r3.status_code, 302)

    def test_regular_user_forbidden(self):
        """Regular user should receive 403 Forbidden for all dashboard views."""
        self.client.login(username='user@ipsakti.com', password='password123')

        r1 = self.client.get(reverse('dashboard:index'))
        self.assertEqual(r1.status_code, 403)

        r2 = self.client.get(reverse('dashboard:users'))
        self.assertEqual(r2.status_code, 403)

        r3 = self.client.get(reverse('dashboard:system_status'))
        self.assertEqual(r3.status_code, 403)

    def test_admin_access_permissions(self):
        """Admin user can view dashboard & system status, but is forbidden from user management."""
        self.client.login(username='admin@ipsakti.com', password='password123')

        r1 = self.client.get(reverse('dashboard:index'))
        self.assertEqual(r1.status_code, 200)
        self.assertTemplateUsed(r1, 'dashboard/index.html')

        r2 = self.client.get(reverse('dashboard:system_status'))
        self.assertEqual(r2.status_code, 200)
        self.assertTemplateUsed(r2, 'dashboard/system_status.html')

        # Admin cannot access Super Admin user management
        r3 = self.client.get(reverse('dashboard:users'))
        self.assertEqual(r3.status_code, 403)

    def test_super_admin_has_full_access(self):
        """Super Admin can access all dashboard views including user management."""
        self.client.login(username='superadmin@ipsakti.com', password='password123')

        r1 = self.client.get(reverse('dashboard:index'))
        self.assertEqual(r1.status_code, 200)

        r2 = self.client.get(reverse('dashboard:users'))
        self.assertEqual(r2.status_code, 200)
        self.assertTemplateUsed(r2, 'dashboard/users.html')

        r3 = self.client.get(reverse('dashboard:system_status'))
        self.assertEqual(r3.status_code, 200)


class DashboardAnalyticsCalculationTest(TestCase):
    """Test dashboard KPI and telemetry calculations."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            email='admin@test.com',
            password='password123',
            full_name='Test Admin',
            role=User.Role.ADMIN,
        )
        self.client.login(username='admin@test.com', password='password123')

        # Create documents
        self.doc1 = Document.objects.create(
            title='Patent Act 1970',
            category=Document.Category.PATENT_LAW,
            status=Document.Status.COMPLETED,
            file_size_bytes=1024 * 1024 * 2,  # 2MB
            total_chunks=10,
        )
        self.doc2 = Document.objects.create(
            title='Biological Diversity Act 2002',
            category=Document.Category.BIODIVERSITY,
            status=Document.Status.COMPLETED,
            file_size_bytes=1024 * 1024 * 3,  # 3MB
            total_chunks=15,
        )

        # Create chunks
        sample_vec = [0.0] * 768
        for i in range(10):
            DocumentChunk.objects.create(
                document=self.doc1,
                content=f'Patent chunk {i}',
                chunk_index=i,
                embedding=sample_vec,
            )
        for i in range(15):
            DocumentChunk.objects.create(
                document=self.doc2,
                content=f'Bio chunk {i}',
                chunk_index=i,
                embedding=sample_vec,
            )

        # Create chat telemetry
        conv = Conversation.objects.create(user=self.admin)
        Message.objects.create(
            conversation=conv,
            sender=Message.Sender.USER,
            content='What is Section 3(d)?',
        )
        Message.objects.create(
            conversation=conv,
            sender=Message.Sender.ASSISTANT,
            content='Section 3(d) prevents evergreening.',
            latency_seconds=1.5,
            token_count=150,
        )

    def test_dashboard_kpis_render_accurately(self):
        """Test KPI metric aggregations in dashboard context."""
        resp = self.client.get(reverse('dashboard:index'))
        self.assertEqual(resp.status_code, 200)

        # Corpus metrics
        self.assertEqual(resp.context['total_documents'], 2)
        self.assertEqual(resp.context['completed_documents'], 2)
        self.assertEqual(resp.context['total_chunks'], 25)
        self.assertEqual(resp.context['total_storage_mb'], 5.0)

        # Query metrics
        self.assertEqual(resp.context['user_queries_count'], 1)
        self.assertEqual(resp.context['avg_latency'], 1.5)
        self.assertEqual(resp.context['total_tokens'], 150)

        # Category stats
        cat_stats = resp.context['category_stats']
        patent_stat = next(c for c in cat_stats if c['code'] == Document.Category.PATENT_LAW)
        self.assertEqual(patent_stat['doc_count'], 1)
        self.assertEqual(patent_stat['percentage'], 50.0)


class UserManagementActionsTest(TestCase):
    """Test Super Admin user role and status manipulation."""

    def setUp(self):
        self.client = Client()
        self.super_admin = User.objects.create_superuser(
            email='root@ipsakti.com',
            password='password123',
            full_name='Root SuperAdmin',
        )
        self.target_user = User.objects.create_user(
            email='member@ipsakti.com',
            password='password123',
            full_name='Team Member',
            role=User.Role.USER,
        )
        self.client.login(username='root@ipsakti.com', password='password123')

    def test_change_user_role_to_admin(self):
        """Super Admin promotes user to Admin."""
        resp = self.client.post(
            reverse('dashboard:change_role', args=[self.target_user.pk]),
            data={'role': 'admin'},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.target_user.refresh_from_db()
        self.assertEqual(self.target_user.role, User.Role.ADMIN)
        self.assertTrue(self.target_user.is_staff)
        self.assertFalse(self.target_user.is_superuser)

    def test_invalid_role_rejected(self):
        """POST with invalid role should fail validation."""
        resp = self.client.post(
            reverse('dashboard:change_role', args=[self.target_user.pk]),
            data={'role': 'hacker_role'},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.target_user.refresh_from_db()
        self.assertEqual(self.target_user.role, User.Role.USER)

    def test_sole_super_admin_self_demotion_prevented(self):
        """Sole Super Admin cannot demote themselves to user."""
        resp = self.client.post(
            reverse('dashboard:change_role', args=[self.super_admin.pk]),
            data={'role': 'user'},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.super_admin.refresh_from_db()
        self.assertEqual(self.super_admin.role, User.Role.SUPER_ADMIN)

    def test_toggle_user_active_status(self):
        """Super Admin can deactivate and reactivate a user account."""
        self.assertTrue(self.target_user.is_active)

        # Deactivate
        r1 = self.client.post(
            reverse('dashboard:toggle_status', args=[self.target_user.pk]),
            follow=True,
        )
        self.assertEqual(r1.status_code, 200)
        self.target_user.refresh_from_db()
        self.assertFalse(self.target_user.is_active)

        # Reactivate
        r2 = self.client.post(
            reverse('dashboard:toggle_status', args=[self.target_user.pk]),
            follow=True,
        )
        self.assertEqual(r2.status_code, 200)
        self.target_user.refresh_from_db()
        self.assertTrue(self.target_user.is_active)

    def test_super_admin_self_deactivation_prevented(self):
        """Super Admin cannot deactivate their own account."""
        resp = self.client.post(
            reverse('dashboard:toggle_status', args=[self.super_admin.pk]),
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.super_admin.refresh_from_db()
        self.assertTrue(self.super_admin.is_active)
