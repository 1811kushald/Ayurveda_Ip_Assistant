from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from accounts.models import User
from documents.models import Document


class DocumentTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='user@ipsakti.com',
            password='Password123!',
            full_name='Regular User',
            role=User.Role.USER
        )
        self.admin = User.objects.create_user(
            email='admin@ipsakti.com',
            password='Password123!',
            full_name='Admin User',
            role=User.Role.ADMIN
        )

        self.document = Document.objects.create(
            title='The Patents Act 1970',
            category=Document.Category.PATENT_LAW,
            jurisdiction='India',
            uploaded_by=self.admin,
            file_size_bytes=1024 * 50
        )

    def test_document_str_and_size_display(self):
        """Test model __str__ and human readable file size."""
        self.assertIn('The Patents Act 1970', str(self.document))
        self.assertEqual(self.document.file_size_display, '50.0 KB')

    def test_regular_user_cannot_access_document_list(self):
        """Test regular user receives HTTP 403 Forbidden on admin views."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('documents:list'))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_document_list(self):
        """Test admin user can access document list."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('documents:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The Patents Act 1970')

    def test_admin_can_upload_pdf(self):
        """Test admin uploading a valid PDF file."""
        self.client.force_login(self.admin)
        fake_pdf = SimpleUploadedFile("test_act.pdf", b"%PDF-1.4 sample pdf content", content_type="application/pdf")

        response = self.client.post(reverse('documents:upload'), {
            'title': 'The Biological Diversity Act 2002',
            'category': Document.Category.BIODIVERSITY,
            'jurisdiction': 'India',
            'file': fake_pdf
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Document.objects.filter(title='The Biological Diversity Act 2002').exists())

    def test_invalid_file_type_rejected(self):
        """Test uploading non-PDF file fails validation."""
        self.client.force_login(self.admin)
        fake_txt = SimpleUploadedFile("test.txt", b"plain text content", content_type="text/plain")

        response = self.client.post(reverse('documents:upload'), {
            'title': 'Invalid File Act',
            'category': Document.Category.GENERAL_IP,
            'jurisdiction': 'India',
            'file': fake_txt
        })
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'file', 'Only PDF files are allowed.')

    def test_admin_can_delete_document(self):
        """Test admin deleting a document."""
        self.client.force_login(self.admin)
        response = self.client.post(reverse('documents:delete', kwargs={'pk': self.document.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Document.objects.filter(pk=self.document.pk).exists())
