from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User


class AuthenticationTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='user@ipsakti.com',
            password='Password123!',
            full_name='Test User'
        )
        self.admin = User.objects.create_user(
            email='admin_test@ipsakti.com',
            password='Password123!',
            full_name='Admin User',
            role=User.Role.ADMIN
        )

    def test_user_registration(self):
        """Test registering a new user."""
        response = self.client.post(reverse('accounts:register'), {
            'email': 'newuser@ipsakti.com',
            'full_name': 'New User',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        })
        self.assertEqual(response.status_code, 302)  # Redirects to home
        self.assertTrue(User.objects.filter(email='newuser@ipsakti.com').exists())

    def test_duplicate_registration_fails(self):
        """Test that registering with an existing email fails."""
        response = self.client.post(reverse('accounts:register'), {
            'email': 'user@ipsakti.com',
            'full_name': 'Duplicate User',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        })
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'email', 'An account with this email already exists.')

    def test_user_login(self):
        """Test valid user login."""
        response = self.client.post(reverse('accounts:login'), {
            'email': 'user@ipsakti.com',
            'password': 'Password123!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_invalid_login_fails(self):
        """Test login with wrong password fails."""
        response = self.client.post(reverse('accounts:login'), {
            'email': 'user@ipsakti.com',
            'password': 'WrongPassword'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid email or password.')

    def test_user_logout(self):
        """Test user logout."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('accounts:logout'))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_profile_access_requires_login(self):
        """Test profile page requires authentication."""
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 302)  # Redirects to login

    def test_profile_update(self):
        """Test user updating their profile."""
        self.client.force_login(self.user)
        response = self.client.post(reverse('accounts:profile'), {
            'full_name': 'Updated Name'
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, 'Updated Name')

    def test_role_properties(self):
        """Test is_admin and is_super_admin helper properties."""
        self.assertFalse(self.user.is_admin)
        self.assertTrue(self.admin.is_admin)
