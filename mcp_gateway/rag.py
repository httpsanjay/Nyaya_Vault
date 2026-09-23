# cases/rag.py

from __future__ import annotations

from typing import Any
from django.forms.models import model_to_dict

from cases.models import Case, Document, DocumentVersion


# ============================================================
# Helpers
# ============================================================

def _serialize_value(value: Any):
    """
    Convert Django/Python values into JSON-safe values.
    """

    if value is None:
        return None

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    if hasattr(value, "url"):
        try:
            return value.url
        except Exception:
            pass

    if hasattr(value, "pk"):
        return value.pk

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def _serialize_model(instance, exclude=None):
    """
    Serialize all concrete Django model fields into JSON-safe data.
    """

    exclude = set(exclude or [])

    data = {}

    for field in instance._meta.concrete_fields:

        if field.name in exclude:
            continue

        try:
            value = getattr(instance, field.name)
            data[field.name] = _serialize_value(value)
        except Exception:
            data[field.name] = None

    return data


# ============================================================
# CASE METADATA
# ============================================================

def get_case_rag_data(case_id: int) -> dict:
    """
    Return structured metadata for one case.

    Includes:
        - case information
        - creator
        - police station
        - case type
        - status
        - creation/update dates
        - documents
        - document types
        - upload timeline
        - document versions
        - signing/review information
    """

    try:
        case = Case.objects.get(pk=case_id)

    except Case.DoesNotExist:
        return {
            "success": False,
            "error": "Case not found",
            "case_id": case_id,
        }

    result = {
        "success": True,
        "case": {},
        "documents": [],
        "timeline": [],
    }

    # --------------------------------------------------------
    # Case information
    # --------------------------------------------------------

    result["case"] = _serialize_model(
        case,
        exclude={
            # Do not accidentally serialize sensitive/internal fields.
            "password",
        },
    )

    # --------------------------------------------------------
    # Creator
    # --------------------------------------------------------

    creator = getattr(case, "created_by", None)

    if creator:
        result["case"]["created_by"] = {
            "id": creator.pk,
            "username": getattr(creator, "username", None),
            "name": (
                getattr(creator, "get_full_name", lambda: "")()
                or getattr(creator, "username", None)
            ),
            "role": getattr(creator, "role", None),
        }

    # --------------------------------------------------------
    # Police station
    # --------------------------------------------------------

    station = getattr(case, "police_station", None)

    if station:

        result["case"]["police_station"] = {
            "id": station.pk,
            "name": getattr(station, "name", str(station)),
        }

        # Include useful station fields if available
        for field_name in [
            "code",
            "address",
            "district",
            "city",
        ]:
            if hasattr(station, field_name):
                result["case"]["police_station"][field_name] = (
                    _serialize_value(
                        getattr(station, field_name)
                    )
                )

    # --------------------------------------------------------
    # Documents
    # --------------------------------------------------------

    documents = Document.objects.filter(
        case=case
    ).order_by("created_at", "id")

    for document in documents:

        document_data = _serialize_model(
            document,
            exclude={
                "file",
            },
        )

        document_data["document_id"] = document.pk

        # ----------------------------------------------------
        # Document creator
        # ----------------------------------------------------

        uploaded_by = (
            getattr(document, "uploaded_by", None)
            or getattr(document, "created_by", None)
        )

        if uploaded_by:

            document_data["uploaded_by"] = {
                "id": uploaded_by.pk,
                "username": getattr(
                    uploaded_by,
                    "username",
                    None
                ),
                "name": (
                    getattr(
                        uploaded_by,
                        "get_full_name",
                        lambda: ""
                    )()
                    or getattr(
                        uploaded_by,
                        "username",
                        None
                    )
                ),
                "role": getattr(
                    uploaded_by,
                    "role",
                    None
                ),
            }

        # ----------------------------------------------------
        # Document versions
        # ----------------------------------------------------

        versions = DocumentVersion.objects.filter(
            document=document
        ).order_by("created_at", "id")

        document_data["versions"] = []

        for version in versions:

            version_data = _serialize_model(
                version,
                exclude={
                    "file",
                    "extracted_text",
                    "digital_signature",
                },
            )

            version_data["version_id"] = version.pk

            # OCR status
            version_data["ocr_status"] = getattr(
                version,
                "ocr_status",
                None
            )

            # Signing information
            signed_by = getattr(
                version,
                "signed_by",
                None
            )

            if signed_by:
                version_data["signed_by"] = {
                    "id": signed_by.pk,
                    "username": getattr(
                        signed_by,
                        "username",
                        None
                    ),
                    "name": (
                        getattr(
                            signed_by,
                            "get_full_name",
                            lambda: ""
                        )()
                        or getattr(
                            signed_by,
                            "username",
                            None
                        )
                    ),
                    "role": getattr(
                        signed_by,
                        "role",
                        None
                    ),
                }

            document_data["versions"].append(
                version_data
            )

        result["documents"].append(
            document_data
        )

        # ----------------------------------------------------
        # Timeline
        # ----------------------------------------------------

        result["timeline"].append({
            "event": "DOCUMENT_UPLOADED",
            "document_id": document.pk,
            "document_name": getattr(
                document,
                "name",
                None
            ),
            "document_type": getattr(
                document,
                "document_type",
                None
            ),
            "created_at": _serialize_value(
                getattr(document, "created_at", None)
            ),
            "uploaded_by": (
                getattr(
                    uploaded_by,
                    "username",
                    None
                )
                if uploaded_by
                else None
            ),
        })

        for version in versions:

            result["timeline"].append({
                "event": "DOCUMENT_VERSION_CREATED",
                "document_id": document.pk,
                "document_name": getattr(
                    document,
                    "name",
                    None
                ),
                "version_id": version.pk,
                "created_at": _serialize_value(
                    getattr(version, "created_at", None)
                ),
                "status": getattr(
                    version,
                    "status",
                    None
                ),
                "ocr_status": getattr(
                    version,
                    "ocr_status",
                    None
                ),
            })

    # --------------------------------------------------------
    # Sort timeline
    # --------------------------------------------------------

    result["timeline"].sort(
        key=lambda item: item.get("created_at") or ""
    )

    return result


# ============================================================
# OCR TEXT FOR A CASE
# ============================================================

def get_case_ocr_text(case_id: int) -> dict:
    """
    Return OCR extracted text from all documents belonging
    to a particular case.

    Only DocumentVersions with extracted OCR text are returned.
    """

    try:
        case = Case.objects.get(pk=case_id)

    except Case.DoesNotExist:
        return {
            "success": False,
            "error": "Case not found",
            "case_id": case_id,
        }

    documents = Document.objects.filter(
        case=case
    ).order_by("created_at", "id")

    result = {
        "success": True,
        "case_id": case.pk,
        "case_number": getattr(
            case,
            "case_number",
            None
        ),
        "documents": [],
    }

    for document in documents:

        versions = DocumentVersion.objects.filter(
            document=document
        ).order_by("created_at", "id")

        for version in versions:

            extracted_text = getattr(
                version,
                "extracted_text",
                None
            )

            if not extracted_text:
                continue

            result["documents"].append({
                "document_id": document.pk,
                "document_name": getattr(
                    document,
                    "name",
                    None
                ),
                "document_type": getattr(
                    document,
                    "document_type",
                    None
                ),
                "version_id": version.pk,
                "version_status": getattr(
                    version,
                    "status",
                    None
                ),
                "ocr_status": getattr(
                    version,
                    "ocr_status",
                    None
                ),
                "created_at": _serialize_value(
                    getattr(
                        version,
                        "created_at",
                        None
                    )
                ),
                "extracted_text": extracted_text,
            })

    return result


# ============================================================
# COMBINED RAG CONTEXT
# ============================================================

def get_case_rag_context(case_id: int) -> dict:
    """
    Return the complete RAG context for one case.

    Combines:
        1. Structured case metadata
        2. Document timeline
        3. OCR extracted text
    """

    case_data = get_case_rag_data(case_id)

    if not case_data.get("success"):
        return case_data

    ocr_data = get_case_ocr_text(case_id)

    return {
        "success": True,

        "case_information": case_data.get(
            "case",
            {}
        ),

        "documents": case_data.get(
            "documents",
            []
        ),

        "timeline": case_data.get(
            "timeline",
            []
        ),

        "ocr_documents": ocr_data.get(
            "documents",
            []
        ),
    }