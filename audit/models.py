from django.conf import settings
from django.db import models


class AuditLog(models.Model):

    ACTION_CHOICES = [

        ("LOGIN", "User Login"),
        ("LOGOUT", "User Logout"),

        ("CASE_CREATED", "Case Created"),

        ("DOCUMENT_CREATED", "Document Created"),
        ("DOCUMENT_UPLOADED", "Document Uploaded"),
        ("DOCUMENT_VERSION_UPLOADED", "Document Version Uploaded"),

        ("DOCUMENT_SUBMITTED", "Document Submitted for Review"),

        ("DOCUMENT_APPROVED", "Document Approved"),
        ("DOCUMENT_REJECTED", "Document Rejected"),

        ("DOCUMENT_SIGNED", "Document Digitally Signed"),
        ("DOCUMENT_VERIFIED", "Document Verified"),

        ("OTHER", "Other"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs"
    )

    action = models.CharField(
        max_length=50,
        choices=ACTION_CHOICES
    )

    description = models.TextField()

    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs"
    )

    document = models.ForeignKey(
        "cases.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs"
    )

    document_version = models.ForeignKey(
        "cases.DocumentVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs"
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True
    )

    timestamp = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        ordering = ["-timestamp"]

        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self):

        return (
            f"{self.user} - "
            f"{self.get_action_display()} - "
            f"{self.timestamp}"
        )