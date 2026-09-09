from django.contrib import admin

from .models import DocumentShare, PoliceStation, UserSigningKey


@admin.register(PoliceStation)
class PoliceStationAdmin(admin.ModelAdmin):
	list_display = ("name", "code", "is_active", "created_at")
	list_filter = ("is_active",)
	search_fields = ("name", "code")


@admin.register(DocumentShare)
class DocumentShareAdmin(admin.ModelAdmin):
	list_display = ("document_version", "target_type", "permission", "is_active", "created_at")
	list_filter = ("target_type", "permission", "is_active")
	search_fields = ("document_version__document__name", "shared_by__username")


@admin.register(UserSigningKey)
class UserSigningKeyAdmin(admin.ModelAdmin):
	list_display = ("user", "created_at")
	readonly_fields = ("private_key", "public_key")

# Register your models here.
