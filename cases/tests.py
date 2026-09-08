import io
import zipfile

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from cryptography.hazmat.primitives import serialization

from accounts.models import User
from .models import Case, Document, DocumentVersion, UserSigningKey
from .utils import (
	build_signature_payload,
	create_signing_key_for_sho,
	verify_signature,
)


@override_settings(
	EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
	SECURE_SSL_REDIRECT=False,
)
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
			status="APPROVED",
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


@override_settings(
	SECURE_SSL_REDIRECT=False,
	SIGNING_KEY_ENCRYPTION_PASSWORD="test-signing-password",
)
class DigitalSigningTests(TestCase):

	def setUp(self):
		self.sho = User.objects.create_user(
			username="sho-a",
			password="password",
			id_number="SHO-1",
			role="SHO",
			police_station="Station A",
		)
		self.io = User.objects.create_user(
			username="io-a",
			password="password",
			id_number="IO-1",
			role="IO",
			police_station="Station A",
		)
		self.case = Case.objects.create(
			case_number="CASE-SIGN-001",
			title="Signing case",
			case_type="THEFT",
			created_by=self.io,
			police_station="Station A",
		)
		self.document = Document.objects.create(
			case=self.case,
			name="Evidence",
			document_type="EVIDENCE",
			uploaded_by=self.io,
		)
		self.version = DocumentVersion.objects.create(
			document=self.document,
			version_number=1,
			file=SimpleUploadedFile("evidence.txt", b"original evidence"),
			uploaded_by=self.io,
			status="APPROVED",
		)

	def test_only_sho_gets_one_encrypted_key(self):
		key, created = create_signing_key_for_sho(self.sho)
		self.assertTrue(created)
		self.assertFalse(create_signing_key_for_sho(self.sho)[1])
		self.assertEqual(UserSigningKey.objects.filter(user=self.sho).count(), 1)
		private_key = serialization.load_pem_private_key(
			key.private_key.encode(),
			password=b"test-signing-password",
		)
		self.assertEqual(private_key.key_size, 4096)
		with self.assertRaises(TypeError):
			serialization.load_pem_private_key(key.private_key.encode(), password=None)
		with self.assertRaises(ValueError):
			create_signing_key_for_sho(self.io)

	def test_two_shos_have_different_keys(self):
		other = User.objects.create_user(
			username="sho-b", password="password", id_number="SHO-2",
			role="SHO", police_station="Station B",
		)
		first, _ = create_signing_key_for_sho(self.sho)
		second, _ = create_signing_key_for_sho(other)
		self.assertNotEqual(first.public_key, second.public_key)

	def test_authorized_approved_document_signs_and_verifies(self):
		create_signing_key_for_sho(self.sho)
		self.client.force_login(self.sho)
		response = self.client.post(reverse("sign_document_version", args=[self.version.pk]))
		self.assertRedirects(response, reverse("document_detail", args=[self.document.pk]))
		self.version.refresh_from_db()
		self.assertEqual(self.version.status, "SIGNED")
		self.assertTrue(
			verify_signature(
				build_signature_payload(
					self.document.pk, self.version.version_number,
					self.version.file_hash, self.sho.pk,
				),
				self.version.digital_signature,
				self.sho.signing_key.public_key,
			)
		)

	def test_non_sho_and_unapproved_cannot_sign(self):
		self.client.force_login(self.io)
		self.assertRedirects(
			self.client.post(reverse("sign_document_version", args=[self.version.pk])),
			reverse("document_detail", args=[self.document.pk]),
		)
		self.client.force_login(self.sho)
		self.version.status = "DRAFT"
		self.version.save(update_fields=["status"])
		self.assertRedirects(
			self.client.post(reverse("sign_document_version", args=[self.version.pk])),
			reverse("document_detail", args=[self.document.pk]),
		)

	def test_changed_file_or_signature_fails_verification(self):
		key, _ = create_signing_key_for_sho(self.sho)
		payload = build_signature_payload(
			self.document.pk, self.version.version_number,
			self.version.file_hash, self.sho.pk,
		)
		from .utils import create_signature
		signature = create_signature(payload, key.private_key)
		self.assertTrue(verify_signature(payload, signature, key.public_key))
		self.assertFalse(verify_signature(payload + b"x", signature, key.public_key))
		self.assertFalse(verify_signature(payload, signature[:-2] + "xx", key.public_key))

	def test_signed_version_rejects_file_replacement(self):
		self.version.status = "SIGNED"
		self.version.save(update_fields=["status"])
		self.version.file = SimpleUploadedFile("changed.txt", b"changed")
		with self.assertRaises(Exception):
			self.version.save()

# Create your tests here.
