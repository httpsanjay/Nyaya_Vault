import hashlib
import io
import logging
import mimetypes
import os
import zipfile

from .forms import CaseForm, DocumentForm, DocumentVersionForm, CaseAssignmentForm, User
from cryptography.hazmat.primitives import serialization
from accounts.models import User

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .filters import CaseFilter
from audit.utils import create_audit_log

from .forms import (
    CaseForm,
    DocumentForm,
    DocumentVersionForm,
)
from .models import (
    Case,
    Document,
    DocumentVersion,
    UserSigningKey,
)
from .tasks import extract_document_text
from .utils import (
    build_signature_payload,
    calculate_file_hash,
    create_signature,
    generate_user_keys,
    verify_signature,
)
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)


def queue_document_ocr(document_version_id):

    try:
        extract_document_text.delay(document_version_id)
    except Exception:
        logger.exception(
            "Unable to queue OCR for DocumentVersion %s",
            document_version_id,
        )
        DocumentVersion.objects.filter(pk=document_version_id).update(
            ocr_status=DocumentVersion.OCR_FAILED,
        )

# =========================================================
# CASES
# =========================================================


@login_required
def case_list(request):

    user = request.user

    # =========================================================
    # BASE QUERY
    # =========================================================

    if user.role == "IO":

        # IO can see ONLY:
        # - cases created by himself
        # - cases assigned to himself
        cases = Case.objects.filter(
            Q(created_by=user) |
            Q(assigned_to=user) |
            Q(assigned_officers=user)
        ).distinct()

    else:

        # Other roles
        # Keep your existing authorization here if you already
        # have more specific role restrictions.
        cases = Case.objects.all()

    # =========================================================
    # SEARCH
    # =========================================================

    q = request.GET.get("q", "").strip()

    if q:

        cases = cases.filter(
            Q(case_number__icontains=q) |
            Q(title__icontains=q) |
            Q(created_by__username__icontains=q) |
            Q(created_by__first_name__icontains=q) |
            Q(created_by__last_name__icontains=q) |
            Q(assigned_to__username__icontains=q) |
            Q(assigned_to__first_name__icontains=q) |
            Q(assigned_to__last_name__icontains=q)
        )

    # =========================================================
    # STATUS FILTER
    # =========================================================

    status = request.GET.get("status", "").strip()

    if status:
        cases = cases.filter(status=status)

    # =========================================================
    # CASE TYPE FILTER
    # =========================================================

    case_type = request.GET.get("case_type", "").strip()

    if case_type:
        cases = cases.filter(case_type=case_type)

    # =========================================================
    # ASSIGNED OFFICER FILTER
    # =========================================================

    assigned_officer = request.GET.get(
        "assigned_officer",
        ""
    ).strip()

    if assigned_officer:

        cases = cases.filter(
            Q(assigned_to__username__icontains=assigned_officer) |
            Q(assigned_to__first_name__icontains=assigned_officer) |
            Q(assigned_to__last_name__icontains=assigned_officer)
        )

    # =========================================================
    # ORDERING
    # =========================================================

    cases = cases.select_related(
        "created_by",
        "assigned_to"
    ).order_by("-created_at")

    # =========================================================
    # CASE TYPE CHOICES
    # =========================================================

    case_type_choices = Case._meta.get_field(
        "case_type"
    ).choices

    context = {
        "cases": cases,
        "case_type_choices": case_type_choices,
    }

    return render(
        request,
        "cases/case_list.html",
        context
    )


@login_required
def case_create(request):

    if request.method == "POST":

        form = CaseForm(request.POST)

        if form.is_valid():

            case = form.save(commit=False)

            case.created_by = request.user

            case.save()

            create_audit_log(
                request=request,
                action="CASE_CREATED",
                description=(
                    f"Case {case.case_number} was created."
                ),
                case=case,
            )

            return redirect(
                "case_detail",
                pk=case.pk
            )

    else:

        form = CaseForm()

    return render(
        request,
        "cases/case_create.html",
        {
            "form": form,
        }
    )



@login_required
def case_detail(request, pk):

    user = request.user

    # =========================================================
    # CASE ACCESS CONTROL
    # =========================================================

    if user.role == "IO":

        # IO can access only:
        # 1. Cases created by the IO
        # 2. Cases assigned to the IO

        case = get_object_or_404(
            Case.objects.filter(
                Q(created_by=user) |
                Q(assigned_to=user) |
                Q(assigned_officers=user)
            ).distinct(),
            pk=pk
        )

    else:

        # Other authorized roles
        case = get_object_or_404(
            Case,
            pk=pk
        )

    # =========================================================
    # POST ACTION
    # =========================================================

    if request.method == "POST":

        selected_ids = request.POST.getlist(
            "document_ids"
        )

        action = request.POST.get(
            "action",
            ""
        ).strip()

        # -----------------------------------------------------
        # GET SELECTED DOCUMENTS
        # -----------------------------------------------------

        documents = case.documents.filter(
            pk__in=selected_ids
        )

        # -----------------------------------------------------
        # GET APPROVED / SIGNED VERSIONS
        # -----------------------------------------------------

        versions = []

        for document in documents:

            valid_version = (
                document.versions
                .filter(
                    status__in=[
                        "APPROVED",
                        "SIGNED"
                    ]
                )
                .first()
            )

            if valid_version and valid_version.file:

                versions.append(
                    valid_version
                )

        # -----------------------------------------------------
        # NO VALID DOCUMENTS
        # -----------------------------------------------------

        if not versions:

            messages.error(
                request,
                "Only approved or digitally signed documents "
                "can be downloaded or shared."
            )

            return redirect(
                "case_detail",
                pk=case.pk
            )

        # =====================================================
        # CREATE ZIP ARCHIVE
        # =====================================================

        archive = io.BytesIO()

        with zipfile.ZipFile(
            archive,
            "w",
            zipfile.ZIP_DEFLATED
        ) as zip_file:

            used_names = set()

            for version in versions:

                # ---------------------------------------------
                # ORIGINAL FILE NAME
                # ---------------------------------------------

                filename = os.path.basename(
                    version.file.name
                )

                base, extension = os.path.splitext(
                    filename
                )

                candidate = filename

                suffix = 2

                # ---------------------------------------------
                # AVOID DUPLICATE FILE NAMES
                # ---------------------------------------------

                while candidate in used_names:

                    candidate = (
                        f"{base}_{suffix}"
                        f"{extension}"
                    )

                    suffix += 1

                used_names.add(candidate)

                # ---------------------------------------------
                # READ FILE
                # ---------------------------------------------

                version.file.open("rb")

                try:

                    zip_file.writestr(
                        candidate,
                        version.file.read()
                    )

                finally:

                    version.file.close()

        archive_bytes = archive.getvalue()

        # =====================================================
        # DOWNLOAD
        # =====================================================

        if action == "download":

            response = HttpResponse(
                archive_bytes,
                content_type="application/zip"
            )

            response["Content-Disposition"] = (
                f'attachment; '
                f'filename="{case.case_number}-documents.zip"'
            )

            return response

        # =====================================================
        # EMAIL
        # =====================================================

        if action == "email":

            recipient = request.POST.get(
                "recipient",
                ""
            ).strip()

            # ---------------------------------------------
            # VALIDATE EMAIL
            # ---------------------------------------------

            try:

                validate_email(recipient)

            except ValidationError:

                messages.error(
                    request,
                    "Enter a valid recipient email address."
                )

                return redirect(
                    "case_detail",
                    pk=case.pk
                )

            # ---------------------------------------------
            # SENDER NAME
            # ---------------------------------------------

            sender_name = (
                request.user.get_full_name()
                or request.user.username
            )

            # ---------------------------------------------
            # EMAIL
            # ---------------------------------------------

            email = EmailMessage(

                subject=(
                    f"Documents for case "
                    f"{case.case_number}"
                ),

                body=(
                    f"{sender_name} has shared "
                    f"approved documents from "
                    f"case {case.case_number}."
                ),

                from_email=getattr(
                    settings,
                    "DEFAULT_FROM_EMAIL",
                    "webmaster@localhost"
                ),

                to=[recipient]
            )

            # ---------------------------------------------
            # ATTACH ZIP
            # ---------------------------------------------

            email.attach(

                f"{case.case_number}-documents.zip",

                archive_bytes,

                "application/zip"
            )

            # ---------------------------------------------
            # SEND
            # ---------------------------------------------

            email.send()

            messages.success(
                request,
                f"Documents shared with {recipient}."
            )

            return redirect(
                "case_detail",
                pk=case.pk
            )

        # =====================================================
        # INVALID ACTION
        # =====================================================

        messages.error(
            request,
            "Choose a valid document action."
        )

        return redirect(
            "case_detail",
            pk=case.pk
        )

    # =========================================================
    # GET REQUEST
    # =========================================================

    return render(
        request,
        "cases/case_detail.html",
        {
            "case": case,
        }
    )



# =========================================================
# DOCUMENTS
# =========================================================

@login_required
def document_create(request, pk):

    case = get_object_or_404(
        Case,
        pk=pk
    )

    if request.method == "POST":

        form = DocumentForm(request.POST)

        if form.is_valid():

            document = form.save(commit=False)

            document.case = case
            document.uploaded_by = request.user

            document.save()

            create_audit_log(
                request=request,
                action="DOCUMENT_CREATED",
                description=(
                    f"Document '{document.name}' was created "
                    f"for case {case.case_number}."
                ),
                case=case,
                document=document,
            )

            return redirect(
                "document_upload_version",
                pk=document.pk
            )

    else:

        form = DocumentForm()

    return render(
        request,
        "cases/document_create.html",
        {
            "case": case,
            "form": form,
        }
    )

@login_required
def document_delete(request, pk):

    document = get_object_or_404(
        Document,
        pk=pk
    )

    case = document.case

    if request.method == "POST":

        # Save required information BEFORE deletion
        document_name = document.name
        case_number = case.case_number

        # Create audit log BEFORE deleting the document
        create_audit_log(
            request=request,
            action="DOCUMENT_DELETED",
            description=(
                f"Document '{document_name}' was deleted "
                f"from case {case_number}."
            ),
            case=case,
            document=document,
        )

        # Now delete the document
        document.delete()

        messages.success(
            request,
            "Document deleted successfully."
        )

        return redirect(
            "case_detail",
            pk=case.pk
        )

    return render(
        request,
        "cases/document_confirm_delete.html",
        {
            "document": document,
            "case": case,
        }
    )

@login_required
def document_version_delete(request, pk):

    version = get_object_or_404(
        DocumentVersion,
        pk=pk
    )

    document = version.document
    case = document.case

    if request.method != "POST":
        return redirect(
            "document_detail",
            pk=document.pk
        )

    # Don't allow deletion of approved/signed versions
    if version.status in ["APPROVED", "SIGNED"]:
        messages.error(
            request,
            "Approved or digitally signed versions cannot be deleted."
        )

        return redirect(
            "document_detail",
            pk=document.pk
        )

    version_number = version.version_number
    document_name = document.name
    case_number = case.case_number

    # Audit before deletion
    create_audit_log(
        request=request,
        action="DOCUMENT_VERSION_DELETED",
        description=(
            f"Version v{version_number} of document "
            f"'{document_name}' was deleted "
            f"from case {case_number}."
        ),
        case=case,
        document=document,
    )

    # Delete ONLY this version
    version.delete()

    messages.success(
        request,
        f"Version v{version_number} deleted successfully."
    )

    return redirect(
        "document_detail",
        pk=document.pk
    )

@login_required
def document_upload_version(request, pk):

    document = get_object_or_404(
        Document,
        pk=pk
    )

    if request.method == "POST":

        form = DocumentVersionForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            version = form.save(commit=False)

            version.document = document
            version.uploaded_by = request.user

            last_version = (
                document.versions
                .order_by("-version_number")
                .first()
            )

            if last_version:

                version.version_number = (
                    last_version.version_number + 1
                )

            else:

                version.version_number = 1

            # Calculate SHA-256 hash
            sha256 = hashlib.sha256()

            for chunk in version.file.chunks():

                sha256.update(chunk)

            version.file_hash = sha256.hexdigest()

            version.save()

            transaction.on_commit(
                lambda version_id=version.pk: queue_document_ocr(
                    version_id
                )
            )

            create_audit_log(
                request=request,
                action="DOCUMENT_VERSION_UPLOADED",
                description=(
                    f"Version {version.version_number} of "
                    f"'{document.name}' was uploaded."
                ),
                case=document.case,
                document=document,
                document_version=version,
            )

            return redirect(
                "document_detail",
                pk=document.pk
            )

    else:

        form = DocumentVersionForm()

    return render(
        request,
        "cases/document_upload_version.html",
        {
            "document": document,
            "form": form,
        }
    )


@login_required
def document_detail(request, pk):

    document = get_object_or_404(
        Document,
        pk=pk
    )

    versions = document.versions.all()
    latest_version = versions.first()
    signing_key_enabled = (
        request.user.role == "SHO"
        and UserSigningKey.objects.filter(user=request.user).exists()
    )

    return render(
        request,
        "cases/document_detail.html",
        {
            "document": document,
            "versions": versions,
            "latest_version": latest_version,
            "ocr_polling": latest_version is not None and latest_version.ocr_status in [
                DocumentVersion.OCR_PENDING,
                DocumentVersion.OCR_PROCESSING,
            ],
            "signing_key_enabled": signing_key_enabled,
        }
    )


@login_required
def document_version_view(request, pk):

    versions = DocumentVersion.objects.select_related(
        "document",
        "document__case",
        "uploaded_by",
        "reviewed_by",
        "signed_by",
    )

    if request.user.role == "IO":
        versions = versions.filter(
            Q(document__case__created_by=request.user) |
            Q(document__case__assigned_to=request.user) |
            Q(document__case__assigned_officers=request.user)
        ).distinct()

    version = get_object_or_404(
        versions,
        pk=pk,
    )
    document = version.document

    integrity_valid = None
    current_hash = ""

    if (
        request.method == "POST"
        and request.POST.get("action") == "verify_integrity"
    ):
        try:
            version.file.open("rb")
            current_hash = calculate_file_hash(version.file)
            integrity_valid = bool(
                version.file_hash
                and current_hash == version.file_hash
            )
        except (OSError, ValueError):
            logger.exception(
                "Unable to verify file integrity for DocumentVersion %s",
                version.pk,
            )
            integrity_valid = False
        finally:
            version.file.close()

    signature_valid = False

    if (
        version.status == "SIGNED"
        and version.digital_signature
        and version.file_hash
        and version.signed_by
    ):
        try:
            payload = build_signature_payload(
                document.pk,
                version.version_number,
                version.file_hash,
                version.signed_by.pk,
            )
            signature_valid = verify_signature(
                payload,
                version.digital_signature,
                version.signed_by.signing_key.public_key,
            )
        except (
            UserSigningKey.DoesNotExist,
            ValueError,
            TypeError,
            OSError,
        ):
            logger.exception(
                "Digital signature verification failed for DocumentVersion %s",
                version.pk,
            )

    audit_events = list(
        version.audit_logs.select_related("user").all()
    )

    timeline = [{
        "timestamp": version.created_at,
        "label": "Version Created",
        "user": version.uploaded_by,
    }]

    for audit_event in audit_events:
        timeline.append({
            "timestamp": audit_event.timestamp,
            "label": audit_event.get_action_display(),
            "user": audit_event.user,
            "description": audit_event.description,
        })

    if version.reviewed_by and not any(
        event.action in [
            "DOCUMENT_APPROVED",
            "DOCUMENT_REJECTED",
        ]
        for event in audit_events
    ):
        timeline.append({
            "timestamp": version.reviewed_at,
            "label": "Document Reviewed",
            "user": version.reviewed_by,
        })

    if version.signed_by and not any(
        event.action == "DOCUMENT_SIGNED"
        for event in audit_events
    ):
        timeline.append({
            "timestamp": version.signed_at,
            "label": "Document Digitally Signed",
            "user": version.signed_by,
        })

    timeline.sort(
        key=lambda event: event["timestamp"],
        reverse=True,
    )

    content_type = (
        mimetypes.guess_type(version.file.name)[0]
        if version.file
        else ""
    )

    if content_type == "application/pdf":
        preview_type = "pdf"
    elif content_type and content_type.startswith("image/"):
        preview_type = "image"
    else:
        preview_type = "unsupported"

    filename = os.path.basename(version.file.name) if version.file else ""

    return render(
        request,
        "cases/document_version_view.html",
        {
            "document": document,
            "version": version,
            "filename": filename,
            "content_type": content_type,
            "preview_type": preview_type,
            "integrity_valid": integrity_valid,
            "current_hash": current_hash,
            "signature_valid": signature_valid,
            "timeline": timeline,
        },
    )


@login_required
def document_ocr_status(request, pk):

    document = get_object_or_404(Document, pk=pk)
    version = document.versions.first()

    if version is None:
        return JsonResponse({"status": "EMPTY"})

    return JsonResponse({
        "status": version.ocr_status,
        "version_id": version.pk,
        "has_text": bool(version.extracted_text.strip()),
        "extracted_text": version.extracted_text,
        "version_number": version.version_number,
        "error": version.ocr_error,
    })


# =========================================================
# DIGITAL SIGNING SETUP
# =========================================================

@login_required
def enable_digital_signing(request):

    if request.method != "POST":
        return redirect("case_list")

    document_pk = request.POST.get("document_pk")

    def return_destination():
        if document_pk:
            return redirect("document_detail", pk=document_pk)
        return redirect("case_list")

    # -----------------------------------------
    # ONLY SHO CAN ENABLE DIGITAL SIGNING
    # -----------------------------------------

    if request.user.role != "SHO":

        messages.error(
            request,
            "Only the SHO can enable digital signing."
        )

        return return_destination()

    # -----------------------------------------
    # CHECK EXISTING KEY
    # -----------------------------------------

    if UserSigningKey.objects.filter(user=request.user).exists():

        messages.info(
            request,
            "Digital signing is already enabled."
        )

        return return_destination()

    # -----------------------------------------
    # GENERATE KEY PAIR
    # -----------------------------------------

    private_key, public_key = generate_user_keys()

    # -----------------------------------------
    # STORE KEY PAIR
    # -----------------------------------------

    try:
        with transaction.atomic():
            UserSigningKey.objects.create(
                user=request.user,
                private_key=private_key,
                public_key=public_key
            )
    except IntegrityError:
        messages.info(
            request,
            "Digital signing is already enabled."
        )
        return return_destination()

    messages.success(
        request,
        "Digital signing has been enabled."
    )

    return return_destination()

# =========================================================
# DIGITAL SIGNING
# =========================================================

@login_required
def sign_document_version(request, pk):

    version = get_object_or_404(DocumentVersion, pk=pk)
    document = version.document

    if request.method != "POST":
        return redirect("document_detail", pk=document.pk)

    if request.user.role != "SHO":
        messages.error(
            request,
            "Only the SHO can digitally sign documents."
        )

        return redirect("document_detail", pk=document.pk)

    if version.status != "APPROVED":
        messages.error(
            request,
            f"Only approved documents can be digitally signed. "
            f"Current status: {version.status}"
        )

        return redirect("document_detail", pk=document.pk)

    try:
        signing_key = request.user.signing_key

    except UserSigningKey.DoesNotExist:
        messages.error(
            request,
            "Digital signing is not enabled for your account."
        )

        return redirect("document_detail", pk=document.pk)

    try:
        version.file.open("rb")
        file_hash = calculate_file_hash(version.file)
    except (OSError, ValueError):
        logger.exception(
            "Unable to read file for document version %s",
            version.pk,
        )
        messages.error(
            request,
            "The document file could not be read for signing."
        )
        return redirect("document_detail", pk=document.pk)
    finally:
        version.file.close()

    payload = build_signature_payload(
        document.pk,
        version.version_number,
        file_hash,
        request.user.pk,
    )

    try:
        digital_signature = create_signature(
            payload,
            signing_key.private_key,
        )
    except (ValueError, TypeError, OSError):
        logger.exception(
            "Digital signature creation failed for document version %s",
            version.pk,
        )
        messages.error(
            request,
            "Digital signature creation failed. Please contact an administrator."
        )
        return redirect("document_detail", pk=document.pk)

    version.file_hash = file_hash
    version.digital_signature = digital_signature
    version.signed_by = request.user
    version.signed_at = timezone.now()
    version.status = "SIGNED"

    version.save(update_fields=[
        "file_hash",
        "digital_signature",
        "signed_by",
        "signed_at",
        "status",
    ])

    create_audit_log(
        request=request,
        action="DOCUMENT_SIGNED",
        description=(
            f"Document '{document.name}' "
            f"version {version.version_number} "
            f"was digitally signed by SHO "
            f"{request.user.username}."
        ),
        case=document.case,
        document=document,
        document_version=version,
    )

    messages.success(
        request,
        "Document digitally signed successfully."
    )

    return redirect(
        "document_detail",
        pk=document.pk
    )


# =========================================================
# DOCUMENT VERIFICATION
# =========================================================

@login_required
def verify_document_version(request, pk):

    version = get_object_or_404(
        DocumentVersion,
        pk=pk
    )

    # -----------------------------------------
    # Calculate SHA-256 of CURRENT FILE
    # -----------------------------------------

    sha256 = hashlib.sha256()

    version.file.open("rb")

    for chunk in iter(
        lambda: version.file.read(8192),
        b""
    ):

        sha256.update(chunk)

    version.file.close()

    current_hash = sha256.hexdigest()

    # -----------------------------------------
    # Compare with ORIGINAL STORED HASH
    # -----------------------------------------

    hash_valid = (
        version.file_hash
        and current_hash == version.file_hash
    )

    # -----------------------------------------
    # Signature status
    # -----------------------------------------

    signature_valid = False

    if (
        version.status == "SIGNED"
        and version.digital_signature
    ):

        try:
            payload = build_signature_payload(
                version.document.pk,
                version.version_number,
                version.file_hash,
                version.signed_by.pk,
            )
            signing_key = version.signed_by.signing_key
            signature_valid = verify_signature(
                payload,
                version.digital_signature,
                signing_key.public_key,
            )
        except (UserSigningKey.DoesNotExist, ValueError, TypeError, OSError):
            logger.exception(
                "Digital signature verification failed for document version %s",
                version.pk,
            )
            signature_valid = False

    # -----------------------------------------
    # FINAL VERIFICATION
    # -----------------------------------------

    is_valid = (
        hash_valid
        and signature_valid
    )

    context = {
        "version": version,
        "current_hash": current_hash,
        "stored_hash": version.file_hash,
        "hash_valid": hash_valid,
        "signature_valid": signature_valid,
        "is_valid": is_valid,
    }

    return render(
        request,
        "cases/verify_document_version.html",
        context
    )


# =========================================================
# DOCUMENT REVIEW
# =========================================================

@login_required
def submit_document_for_review(request, pk):

    version = get_object_or_404(
        DocumentVersion,
        pk=pk
    )

    if request.method != "POST":
        return redirect(
            "document_detail",
            pk=version.document.pk
        )

    # Only IO can submit documents
    if request.user.role != "IO":

        messages.error(
            request,
            "Only an Investigating Officer can submit documents."
        )

        return redirect(
            "document_detail",
            pk=version.document.pk
        )

    # Only the uploader can submit
    if version.uploaded_by != request.user:

        messages.error(
            request,
            "You can only submit documents that you uploaded."
        )

        return redirect(
            "document_detail",
            pk=version.document.pk
        )

    # Must be draft
    if version.status != "DRAFT":

        messages.error(
            request,
            "This document is already submitted."
        )

        return redirect(
            "document_detail",
            pk=version.document.pk
        )

    version.status = "PENDING_REVIEW"

    version.save(
        update_fields=["status"]
    )

    # Audit log
    create_audit_log(
        request=request,
        action="DOCUMENT_SUBMITTED_FOR_REVIEW",
        description=(
            f"Version {version.version_number} of "
            f"'{version.document.name}' was submitted for SHO review."
        ),
        case=version.document.case,
        document=version.document,
        document_version=version,
    )

    messages.success(
        request,
        "Document submitted to SHO for review."
    )

    return redirect(
        "document_detail",
        pk=version.document.pk
    )


@login_required
def approve_document(request, pk):

    version = get_object_or_404(
        DocumentVersion,
        pk=pk
    )

    if request.method != "POST":

        return redirect(
            "document_detail",
            pk=version.document.pk
        )

    # ONLY SHO
    if request.user.role != "SHO":

        messages.error(
            request,
            "Only the SHO can approve documents."
        )

        return redirect(
            "document_detail",
            pk=version.document.pk
        )

    if version.status != "PENDING_REVIEW":

        messages.error(
            request,
            "This document is not awaiting review."
        )

        return redirect(
            "document_detail",
            pk=version.document.pk
        )

    version.reviewed_by = request.user

    version.reviewed_at = timezone.now()

    version.status = "APPROVED"

    version.save(
        update_fields=[
            "reviewed_by",
            "reviewed_at",
            "status",
        ]
    )

    messages.success(
        request,
        "Document approved. It is now ready for digital signing."
    )

    return redirect(
        "document_detail",
        pk=version.document.pk
    )


@login_required
def reject_document(request, pk):

    version = get_object_or_404(
        DocumentVersion,
        pk=pk
    )

    if request.method != "POST":

        return redirect(
            "document_detail",
            pk=version.document.pk
        )

    if request.user.role != "SHO":

        messages.error(
            request,
            "Only the SHO can reject documents."
        )

        return redirect(
            "document_detail",
            pk=version.document.pk
        )

    if version.status != "PENDING_REVIEW":

        messages.error(
            request,
            "This document is not awaiting review."
        )

        return redirect(
            "document_detail",
            pk=version.document.pk
        )

    reason = request.POST.get(
        "rejection_reason",
        ""
    ).strip()

    version.status = "REJECTED"

    version.rejection_reason = reason

    version.reviewed_by = request.user

    version.reviewed_at = timezone.now()

    version.save(
        update_fields=[
            "status",
            "rejection_reason",
            "reviewed_by",
            "reviewed_at",
        ]
    )

    messages.success(
        request,
        "Document rejected."
    )

    return redirect(
        "document_detail",
        pk=version.document.pk
    )


@login_required
def assign_case(request, pk):

    case = get_object_or_404(
        Case,
        pk=pk
    )

    # Only SHO can access case assignment
    if request.user.role != "SHO":

        messages.error(
            request,
            "Only the SHO can assign cases."
        )

        return redirect(
            "case_detail",
            pk=case.pk
        )

    # -----------------------------------------
    # GET → SHOW ASSIGNMENT PAGE
    # -----------------------------------------

    if request.method == "GET":

        form = CaseAssignmentForm(instance=case)

        return render(
            request,
            "cases/case_assign.html",
            {
                "case": case,
                "form": form,
            }
        )

    # -----------------------------------------
    # POST → ASSIGN IO
    # -----------------------------------------

    if request.method == "POST":

        form = CaseAssignmentForm(request.POST, instance=case)

        if not form.is_valid():
            return render(
                request,
                "cases/case_assign.html",
                {"case": case, "form": form},
                status=400,
            )

        assigned_officers = list(form.cleaned_data["assigned_officers"])
        case.assigned_officers.set(assigned_officers)
        case.assigned_to = assigned_officers[0] if assigned_officers else None
        case.save(update_fields=["assigned_to"])

        create_audit_log(
            request=request,
            action="CASE_ASSIGNED",
            description=(
                f"Case {case.case_number} was assigned "
                f"to {', '.join(
                    officer.get_full_name() or officer.username
                    for officer in assigned_officers
                ) or 'no officers'} ."
            ),
            case=case,
        )

        messages.success(
            request,
            f"Case assignments updated for {len(assigned_officers)} officer(s)."
        )

        return redirect(
            "case_detail",
            pk=case.pk
        )



