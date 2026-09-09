import io
import zipfile

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from cryptography.hazmat.primitives import serialization

from accounts.models import User
from .models import (
	Case,
	Document,
	DocumentShare,
	DocumentVersion,
	PoliceStation,
	UserSigningKey,
)
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
		self.station = PoliceStation.objects.create(
			name="Station A", code="STATION_A"
		)
		self.user = User.objects.create_user(
			username="officer",
			password="password",
			id_number="OFFICER-1",
			police_station=self.station,
		)
		self.case = Case.objects.create(
			case_number="CASE-001",
			title="Test case",
			case_type="THEFT",
			created_by=self.user,
			police_station=self.station,
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
		self.station = PoliceStation.objects.create(
			name="Station A", code="STATION_A"
		)
		self.sho = User.objects.create_user(
			username="sho-a",
			password="password",
			id_number="SHO-1",
			role="SHO",
			police_station=self.station,
		)
		self.io = User.objects.create_user(
			username="io-a",
			password="password",
			id_number="IO-1",
			role="IO",
			police_station=self.station,
		)
		self.case = Case.objects.create(
			case_number="CASE-SIGN-001",
			title="Signing case",
			case_type="THEFT",
			created_by=self.io,
			police_station=self.station,
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
			role="SHO", police_station=PoliceStation.objects.create(
				name="Station B", code="STATION_B"
			),
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


@override_settings(SECURE_SSL_REDIRECT=False)
class CollaborationTests(TestCase):

	def setUp(self):
		self.station_a = PoliceStation.objects.create(name="Station A", code="STA")
		self.station_b = PoliceStation.objects.create(name="Station B", code="STB")
		self.station_c = PoliceStation.objects.create(name="Station C", code="STC")
		self.sho_a = User.objects.create_user(
			username="sho-a", password="password", id_number="SHO-A",
			role="SHO", police_station=self.station_a,
		)
		self.sho_b = User.objects.create_user(
			username="sho-b", password="password", id_number="SHO-B",
			role="SHO", police_station=self.station_b,
		)
		self.io_b = User.objects.create_user(
			username="io-b", password="password", id_number="IO-B",
			role="IO", police_station=self.station_b,
		)
		self.lawyer = User.objects.create_user(
			username="lawyer", password="password", id_number="LAWYER",
			role="LAWYER", lawyer_registration_number="L123",
		)
		self.other_lawyer = User.objects.create_user(
			username="lawyer-2", password="password", id_number="LAWYER-2",
			role="LAWYER", lawyer_registration_number="L456",
		)
		self.case = Case.objects.create(
			case_number="CASE-SHARE-001", title="Shared case", case_type="THEFT",
			created_by=self.sho_a, police_station=self.station_a,
		)
		self.document = Document.objects.create(
			case=self.case, name="FIR", document_type="FIR", uploaded_by=self.sho_a,
		)
		self.version = DocumentVersion.objects.create(
			document=self.document, version_number=1,
			file=SimpleUploadedFile("fir.txt", b"shared evidence"),
			uploaded_by=self.sho_a, status="APPROVED",
		)

	def share(self, target_type, **extra):
		self.client.force_login(self.sho_a)
		return self.client.post(
			reverse("share_case", args=[self.case.pk]),
			{
				"document_versions": [self.version.pk],
				"target_type": target_type,
				"permission": "VIEW_DOWNLOAD",
				**extra,
			},
		)

	def test_other_station_denied_until_explicitly_shared(self):
		self.client.force_login(self.sho_b)
		self.assertEqual(
			self.client.get(reverse("document_version_view", args=[self.version.pk])).status_code,
			403,
		)

	def test_dashboard_and_case_list_are_station_scoped(self):
		self.client.force_login(self.sho_a)
		response = self.client.get(reverse("dashboard"))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["total_cases"], 1)
		self.assertContains(response, "CASE-SHARE-001")
		self.client.force_login(self.sho_b)
		response = self.client.get(reverse("case_list"))
		self.assertNotContains(response, "CASE-SHARE-001")
		self.share("POLICE_STATION", police_station=self.station_b.pk)
		self.assertEqual(
			self.client.get(reverse("document_version_view", args=[self.version.pk])).status_code,
			200,
		)
		self.client.force_login(self.io_b)
		self.assertEqual(
			self.client.get(reverse("document_version_view", args=[self.version.pk])).status_code,
			200,
		)
		self.client.force_login(User.objects.create_user(
			username="sho-c", password="password", id_number="SHO-C",
			role="SHO", police_station=self.station_c,
		))
		self.assertEqual(
			self.client.get(reverse("document_version_view", args=[self.version.pk])).status_code,
			403,
		)

	def test_lawyer_registration_identifies_exact_recipient(self):
		self.share("LAWYER", registration_number="L123")
		self.client.force_login(self.lawyer)
		self.assertEqual(self.client.get(reverse("document_version_view", args=[self.version.pk])).status_code, 200)
		self.assertEqual(self.client.get(reverse("document_detail", args=[self.document.pk])).status_code, 200)
		self.client.force_login(self.other_lawyer)
		self.assertEqual(self.client.get(reverse("document_version_view", args=[self.version.pk])).status_code, 403)

	def test_view_only_share_cannot_download_and_revocation_removes_access(self):
		self.client.force_login(self.sho_a)
		self.client.post(
			reverse("share_case", args=[self.case.pk]),
			{"document_versions": [self.version.pk], "target_type": "LAWYER", "permission": "VIEW", "registration_number": "L123"},
		)
		self.client.force_login(self.lawyer)
		self.assertEqual(self.client.get(reverse("download_document_version", args=[self.version.pk])).status_code, 403)
		self.client.force_login(self.sho_a)
		share = DocumentShare.objects.get(document_version=self.version)
		self.client.post(reverse("revoke_document_share", args=[share.pk]))
		self.client.force_login(self.lawyer)
		self.assertEqual(self.client.get(reverse("document_version_view", args=[self.version.pk])).status_code, 403)

# Create your tests here.
