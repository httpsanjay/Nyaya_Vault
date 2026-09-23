import io
import zipfile
from unittest.mock import patch

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from cryptography.hazmat.primitives import serialization

from cases.rag import ask_case

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
from .search import unified_search


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


@override_settings(
	SECURE_SSL_REDIRECT=False,
	MIDDLEWARE=[
		"django.middleware.security.SecurityMiddleware",
		"django.contrib.sessions.middleware.SessionMiddleware",
		"django.middleware.common.CommonMiddleware",
		"django.middleware.csrf.CsrfViewMiddleware",
		"django.contrib.auth.middleware.AuthenticationMiddleware",
		"django.contrib.messages.middleware.MessageMiddleware",
		"django.middleware.clickjacking.XFrameOptionsMiddleware",
	],
)
class UnifiedSearchTests(TestCase):

	def setUp(self):
		self.station = PoliceStation.objects.create(
			name="Search Station", code="SEARCH"
		)
		self.other_station = PoliceStation.objects.create(
			name="Other Station", code="OTHER"
		)
		self.user = User.objects.create_user(
			username="search-sho", password="password", id_number="SEARCH-SHO",
			role="SHO", police_station=self.station,
		)
		self.other_user = User.objects.create_user(
			username="other-sho", password="password", id_number="OTHER-SHO",
			role="SHO", police_station=self.other_station,
		)
		self.case = Case.objects.create(
			case_number="CASE/001", title="Financial Fraud Investigation",
			case_type="FRAUD", description="Bank transaction inquiry",
			created_by=self.user, police_station=self.station,
		)
		self.fir = self._document(
			"FIR.pdf", "FIR", "The accused was seen at the crime scene.",
		)
		self.failed = self._document(
			"Unreadable Evidence", "EVIDENCE", "", ocr_status=DocumentVersion.OCR_FAILED,
		)
		self.report = self._document(
			"Bank Transaction Report", "INVESTIGATION_REPORT",
			"Bank transaction records connect the accused to the transfer.",
		)

	def _document(self, name, document_type, text, ocr_status=None):
		document = Document.objects.create(
			case=self.case, name=name, document_type=document_type,
			uploaded_by=self.user,
		)
		version = DocumentVersion.objects.create(
			document=document, version_number=1,
			file=SimpleUploadedFile(f"{name}.txt", b"evidence"),
			extracted_text=text, uploaded_by=self.user,
		)
		if ocr_status:
			version.ocr_status = ocr_status
			version.save(update_fields=["ocr_status"])
		return document

	def test_exact_case_number_returns_all_documents_including_failed_ocr(self):
		results = unified_search("CASE/001", self.user)

		self.assertEqual(len(results), 1)
		self.assertEqual(
			{item["document"].pk for item in results[0]["documents"]},
			{self.fir.pk, self.failed.pk, self.report.pk},
		)

	def test_document_name_and_ocr_keyword_search_group_under_case(self):
		name_results = unified_search("Bank Transaction Report", self.user)
		text_results = unified_search("crime scene", self.user)

		self.assertEqual(name_results[0]["case"], self.case)
		self.assertEqual(name_results[0]["documents"][0]["document"], self.report)
		self.assertEqual(text_results[0]["documents"][0]["document"], self.fir)
		self.assertTrue(text_results[0]["documents"][0]["matches"])

	def test_semantic_fallback_search_returns_source_metadata(self):
		results = unified_search("What evidence connects the accused to the crime scene?", self.user)
		match = results[0]["documents"][0]["matches"][0]

		self.assertEqual(results[0]["case"].pk, self.case.pk)
		self.assertEqual(match["version_id"], self.fir.versions.first().pk)
		self.assertIn("crime scene", match["text"])

	def test_search_does_not_return_other_station_case(self):
		other_case = Case.objects.create(
			case_number="CASE/002", title="Private Case", case_type="THEFT",
			created_by=self.other_user, police_station=self.other_station,
		)
		Document.objects.create(
			case=other_case, name="Private Bank Report", document_type="EVIDENCE",
			uploaded_by=self.other_user,
		)

		self.assertEqual(unified_search("CASE/002", self.user), [])
		self.assertEqual(unified_search("Private", self.user), [])

	def test_empty_and_unknown_search_return_no_results(self):
		self.assertEqual(unified_search("", self.user), [])
		self.assertEqual(unified_search("does not exist", self.user), [])

	def test_search_api_and_html_are_case_centric(self):
		self.client.force_login(self.user)
		response = self.client.get(reverse("search_api"), {"q": "CASE/001"})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["results"][0]["case"]["case_number"], "CASE/001")
		self.assertContains(
			self.client.get(reverse("search"), {"q": "CASE/001"}),
			"Unreadable Evidence",
		)


@override_settings(SECURE_SSL_REDIRECT=False)
class RAGTests(TestCase):

	def setUp(self):
		self.station = PoliceStation.objects.create(name="RAG Station", code="RAG")
		self.other_station = PoliceStation.objects.create(name="Other Station", code="OTH")
		self.user = User.objects.create_user(
			username="rag-user", password="password", id_number="RAG-USER",
			role="SHO", police_station=self.station,
		)
		self.other_user = User.objects.create_user(
			username="other-user", password="password", id_number="OTHER-USER",
			role="SHO", police_station=self.other_station,
		)
		self.case = Case.objects.create(
			case_number="CASE-RAG-001", title="Evidence Review",
			case_type="THEFT", created_by=self.user, police_station=self.station,
		)
		self.other_case = Case.objects.create(
			case_number="CASE-RAG-002", title="Private Review",
			case_type="THEFT", created_by=self.other_user, police_station=self.other_station,
		)
		self.document = Document.objects.create(
			case=self.case, name="Witness Statement", document_type="WITNESS_STATEMENT",
			uploaded_by=self.user,
		)
		self.other_document = Document.objects.create(
			case=self.other_case, name="Confidential Statement", document_type="WITNESS_STATEMENT",
			uploaded_by=self.other_user,
		)
		self.version = DocumentVersion.objects.create(
			document=self.document, version_number=1,
			file=SimpleUploadedFile("witness.txt", b"witness statement"),
			extracted_text="The witness saw the accused near the warehouse at 11:00 PM.",
			uploaded_by=self.user,
		)
		self.other_version = DocumentVersion.objects.create(
			document=self.other_document, version_number=1,
			file=SimpleUploadedFile("private.txt", b"private statement"),
			extracted_text="The accused was not present in the warehouse. This is unrelated evidence.",
			uploaded_by=self.other_user,
		)

	def test_authorized_user_can_ask_questions_about_an_accessible_case(self):
		with patch("cases.rag.generate_rag_answer", return_value={
			"answer": "The witness statement says the accused was near the warehouse.",
			"sources": [{"document_name": "Witness Statement", "document_id": self.document.pk, "document_version_id": self.version.pk}],
			"provider": "mock",
			"model": "mock-model",
			"grounded": True,
		}):
			result = ask_case(self.user, self.case.pk, "Where was the accused seen?")
		self.assertTrue(result["success"])
		self.assertEqual(result["case"]["case_id"], self.case.pk)
		self.assertEqual(result["sources"][0]["document_name"], "Witness Statement")

	def test_unauthorized_user_cannot_retrieve_case_information(self):
		result = ask_case(self.other_user, self.case.pk, "Where was the accused seen?")
		self.assertFalse(result["success"])
		self.assertIn("not authorized", str(result["error"]).lower())

	def test_semantic_search_is_restricted_to_authorized_data(self):
		with patch("cases.rag.unified_search", return_value=[{
			"case": self.case,
			"documents": [{
				"document": self.document,
				"score": 0.9,
				"matches": [{"text": "The witness saw the accused near the warehouse.", "score": 0.9, "version_id": self.version.pk}],
				"version": self.version,
			}, {
				"document": self.other_document,
				"score": 0.95,
				"matches": [{"text": "The accused was not present in the warehouse.", "score": 0.95, "version_id": self.other_version.pk}],
				"version": self.other_version,
			}],
		}]):
			with patch("cases.rag.generate_rag_answer", return_value={
				"answer": "The witness saw the accused nearby.",
				"sources": [],
				"provider": "mock",
				"model": "mock-model",
				"grounded": True,
			}):
				result = ask_case(self.user, self.case.pk, "Where was the accused seen?")
		self.assertEqual(len(result["retrieved_chunks"]), 1)
		self.assertEqual(result["retrieved_chunks"][0]["document_id"], self.document.pk)
		self.assertNotIn(self.other_document.pk, {chunk["document_id"] for chunk in result["retrieved_chunks"]})

	def test_no_result_search_is_handled_correctly(self):
		with patch("cases.rag.unified_search", return_value=[]):
			result = ask_case(self.user, self.case.pk, "completely unrelated legal phrase that should not match")
		self.assertFalse(result["success"])
		self.assertIn("available documents do not contain enough information", result["error"].lower())

	def test_insufficient_context_is_handled_correctly(self):
		self.version.extracted_text = ""
		self.version.save(update_fields=["extracted_text"])
		with patch("cases.rag.unified_search", return_value=[{
			"case": self.case,
			"documents": [{"document": self.document, "score": 0.7, "matches": [], "version": None}],
		}]):
			result = ask_case(self.user, self.case.pk, "What happened?")
		self.assertFalse(result["success"])
		self.assertIn("insufficient", result["error"].lower())

	def test_source_references_correspond_to_actual_retrieved_documents(self):
		with patch("cases.rag.unified_search", return_value=[{
			"case": self.case,
			"documents": [{
				"document": self.document,
				"score": 0.85,
				"matches": [{"text": "The witness saw the accused near the warehouse.", "score": 0.85, "version_id": self.version.pk, "chunk_index": 3}],
				"version": self.version,
			}],
		}]):
			with patch("cases.rag.generate_rag_answer", return_value={
				"answer": "The witness saw the accused near the warehouse.",
				"sources": [{"document_id": self.document.pk, "document_name": "Witness Statement", "document_version_id": self.version.pk, "chunk_id": 3}],
				"provider": "mock",
				"model": "mock-model",
				"grounded": True,
			}):
				result = ask_case(self.user, self.case.pk, "Who was near the warehouse?")
		self.assertEqual(result["sources"][0]["document_id"], self.document.pk)
		self.assertEqual(result["sources"][0]["chunk_id"], 3)

	def test_llm_failures_are_handled_safely(self):
		with patch("cases.rag.unified_search", return_value=[{
			"case": self.case,
			"documents": [{"document": self.document, "score": 0.8, "matches": [{"text": "The witness saw the accused near the warehouse.", "score": 0.8, "version_id": self.version.pk}], "version": self.version}],
		}]):
			with patch("cases.rag.generate_rag_answer", side_effect=RuntimeError("openai unavailable")):
				result = ask_case(self.user, self.case.pk, "Where was the accused seen?")
		self.assertFalse(result["success"])
		self.assertIn("llm", str(result["error"]).lower())

	def test_another_case_data_never_appears_in_context(self):
		with patch("cases.rag.unified_search", return_value=[{
			"case": self.case,
			"documents": [{"document": self.document, "score": 0.9, "matches": [{"text": "The witness saw the accused near the warehouse.", "score": 0.9, "version_id": self.version.pk}], "version": self.version}],
		}, {
			"case": self.other_case,
			"documents": [{"document": self.other_document, "score": 0.9, "matches": [{"text": "The accused was not present in the warehouse.", "score": 0.9, "version_id": self.other_version.pk}], "version": self.other_version}],
		}]):
			with patch("cases.rag.generate_rag_answer", return_value={
				"answer": "Available documents support the warehouse sighting.",
				"sources": [{"document_id": self.document.pk, "document_name": "Witness Statement", "document_version_id": self.version.pk}],
				"provider": "mock",
				"model": "mock-model",
				"grounded": True,
			}):
				result = ask_case(self.user, self.case.pk, "Where was the accused seen?")
		for chunk in result["retrieved_chunks"]:
			self.assertNotEqual(chunk["document_id"], self.other_document.pk)
		self.assertEqual(result["case"]["case_id"], self.case.pk)

	def test_mcp_rag_tool_enforces_authorization(self):
		from mcp_gateway.main import ask_case_question
		self.client.force_login(self.user)
		result = self.client.post("/cases/" + str(self.case.pk) + "/ask/", {"question": "Where was the accused seen?"}, follow=True)
		self.assertEqual(result.status_code, 200)
		self.assertTrue(result.json()["success"])
		self.assertEqual(ask_case_question.__name__, "ask_case_question")
		self.client.force_login(self.other_user)
		forbidden = self.client.post("/cases/" + str(self.case.pk) + "/ask/", {"question": "Where was the accused seen?"}, follow=True)
		self.assertEqual(forbidden.status_code, 403)
