from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):

    list_display = (
        "timestamp",
        "user",
        "action",
        "case",
        "document",
        "document_version",
        "ip_address",
    )

    list_filter = (
        "action",
        "timestamp",
    )

    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "description",
        "case__case_number",
        "document__name",
    )

    readonly_fields = (
        "user",
        "action",
        "description",
        "case",
        "document",
        "document_version",
        "ip_address",
        "timestamp",
    )