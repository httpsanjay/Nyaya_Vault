import io
import zipfile

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from .models import Case, Document, DocumentVersion


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class DocumentSharingTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user(
			username="officer",
			password="password",
			id_number="OFFICER-1",
		)
		self.case = Case.objects.create(
			case_number="CASE-001",
			title="Test case",
			case_type="THEFT",
			created_by=self.user,
		)
		self.document = Document.objects.create(
			case=self.case,
			name="Evidence photo",
			document_type="EVIDENCE",
			uploaded_by=self.user,
		)
		self.version = DocumentVersion.objects.create(
			document=self.document,
			version_number=1,
			file=SimpleUploadedFile("photo.txt", b"evidence contents"),
			uploaded_by=self.user,
		)
		self.client.force_login(self.user)

	def test_selected_documents_download_as_zip(self):
		response = self.client.post(
			reverse("case_detail", args=[self.case.pk]),
			{"action": "download", "document_ids": [self.document.pk]},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response["Content-Type"], "application/zip")
		with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
			self.assertEqual(len(archive.namelist()), 1)
			self.assertEqual(archive.read(archive.namelist()[0]), b"evidence contents")

	def test_selected_documents_are_emailed_as_zip(self):
		response = self.client.post(
			reverse("case_detail", args=[self.case.pk]),
			{
				"action": "email",
				"document_ids": [self.document.pk],
				"recipient": "recipient@example.com",
			},
		)

		self.assertRedirects(response, reverse("case_detail", args=[self.case.pk]))
		self.assertEqual(len(mail.outbox), 1)
		self.assertEqual(mail.outbox[0].to, ["recipient@example.com"])
		self.assertEqual(mail.outbox[0].attachments[0][0], "CASE-001-documents.zip")

	def test_documents_from_another_case_are_not_shared(self):
		other_case = Case.objects.create(
			case_number="CASE-002",
			title="Other case",
			case_type="THEFT",
			created_by=self.user,
		)
		response = self.client.post(
			reverse("case_detail", args=[self.case.pk]),
			{"action": "download", "document_ids": [
				Document.objects.create(
					case=other_case,
					name="Private file",
					document_type="EVIDENCE",
					uploaded_by=self.user,
				).pk
			]},
		)

		self.assertRedirects(response, reverse("case_detail", args=[self.case.pk]))
		self.assertEqual(len(mail.outbox), 0)

# Create your tests here.
