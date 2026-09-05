import hashlib

from django.conf import settings
from django.db import models
import os

import os


def document_version_upload_path(instance, filename):

    extension = os.path.splitext(filename)[1].lower()

    # Use the Document title/name, NOT the uploaded filename
    file_title = instance.document.name.strip()

    # Make it filesystem safe
    file_title = file_title.replace(" ", "_")

    # Case unique number
    case_number = instance.document.case.case_number.strip()
    case_number = case_number.replace(" ", "_")

    return (
        f"case_documents/"
        f"v{instance.version_number}_"
        f"{file_title}_"
        f"{case_number}"
        f"{extension}"
    )

class Case(models.Model):

    STATUS_CHOICES = [
        ("OPEN", "Open"),
        ("PENDING", "Pending"),
        ("CLOSED", "Closed"),
    ]

    CASE_TYPE_CHOICES = [
        ("THEFT", "Theft"),
        ("FRAUD", "Fraud"),
        ("ASSAULT", "Assault"),
        ("CYBERCRIME", "Cyber Crime"),
        ("MISSING", "Missing Person"),
        ("OTHER", "Other"),
    ]

    case_number = models.CharField(
        max_length=50,
        unique=True
    )

    title = models.CharField(
        max_length=200
    )

    case_type = models.CharField(
        max_length=30,
        choices=CASE_TYPE_CHOICES
    )
    assigned_to = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="cases_assigned_to"
)

    assigned_officers = models.ManyToManyField(
    settings.AUTH_USER_MODEL,
    blank=True,
    related_name="cases_assigned_as_officer"
)

    other_case_type = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    description = models.TextField(
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="OPEN"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_cases"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"{self.case_number} - {self.title}"


class Document(models.Model):

    DOCUMENT_TYPE_CHOICES = [
        ("FIR", "FIR"),
        ("WITNESS_STATEMENT", "Witness Statement"),
        ("EVIDENCE", "Evidence"),
        ("INVESTIGATION_REPORT", "Investigation Report"),
        ("CHARGE_SHEET", "Charge Sheet"),
        ("FORENSIC_REPORT", "Forensic Report"),
        ("COURT_FILING", "Court Filing"),
        ("OTHER", "Other"),
    ]

    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        related_name="documents"
    )

    name = models.CharField(
        max_length=200
    )

    document_type = models.CharField(
        max_length=50,
        choices=DOCUMENT_TYPE_CHOICES
    )

    description = models.TextField(
        blank=True
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_documents"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"{self.case.case_number} - {self.name}"

class DocumentVersion(models.Model):

    OCR_PENDING = "PENDING"
    OCR_PROCESSING = "PROCESSING"
    OCR_COMPLETED = "COMPLETED"
    OCR_FAILED = "FAILED"

    OCR_STATUS_CHOICES = [
        (OCR_PENDING, "Pending"),
        (OCR_PROCESSING, "Processing"),
        (OCR_COMPLETED, "Completed"),
        (OCR_FAILED, "Failed"),
    ]

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PENDING_REVIEW", "Pending Review"),
        ("REJECTED", "Rejected"),
        ("APPROVED", "Approved"),
        ("SIGNED", "Digitally Signed"),
    ]

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="versions"
    )
    

    version_number = models.PositiveIntegerField()

    file = models.FileField(
    upload_to=document_version_upload_path
)
    extracted_text = models.TextField(blank=True)

    ocr_status = models.CharField(
        max_length=20,
        choices=OCR_STATUS_CHOICES,
        default=OCR_PENDING,
    )

    ocr_error = models.TextField(
        blank=True
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_document_versions"
    )

    file_hash = models.CharField(
        max_length=64,
        blank=True
    )

    digital_signature = models.TextField(
        blank=True
    )

    signed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="signed_document_versions"
    )

    signed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT"
    )

    rejection_reason = models.TextField(
        blank=True
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reviewed_document_versions"
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        ordering = ["-version_number"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "document",
                    "version_number"
                ],
                name="unique_document_version"
            )
        ]

    def save(self, *args, **kwargs):
        

        # Save first so the uploaded file exists on disk/storage
        super().save(*args, **kwargs)

        # =========================
        # SHA-256 FILE HASH
        # =========================

        if self.file and not self.file_hash:

            sha256 = hashlib.sha256()

            self.file.open("rb")

            try:
                for chunk in self.file.chunks():
                    sha256.update(chunk)
            finally:
                self.file.close()

            self.file_hash = sha256.hexdigest()

            super().save(
                update_fields=["file_hash"]
            )

class UserSigningKey(models.Model):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="signing_key"
    )

    public_key = models.TextField()

    private_key = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return f"Signing Key - {self.user.username}"