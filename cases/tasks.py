import logging
import os
import tempfile
from pathlib import Path

from celery import shared_task

from .models import DocumentVersion
from .ocr import extract_text


logger = logging.getLogger(__name__)


@shared_task
def extract_document_text(document_version_id):
    try:
        version = DocumentVersion.objects.get(pk=document_version_id)
        version.ocr_status = DocumentVersion.OCR_PROCESSING
        version.save(update_fields=["ocr_status"])

        if not version.file:
            raise ValueError("Document version has no uploaded file")

        suffix = Path(version.file.name).suffix
        temporary_path = None

        try:
            with version.file.open("rb") as source_file:
                with tempfile.NamedTemporaryFile(
                    suffix=suffix,
                    delete=False,
                ) as temporary_file:
                    temporary_path = temporary_file.name
                    for chunk in source_file.chunks():
                        temporary_file.write(chunk)

            text = extract_text(temporary_path)
        finally:
            if temporary_path:
                os.unlink(temporary_path)

        version.extracted_text = text
        version.ocr_status = DocumentVersion.OCR_COMPLETED
        version.save(update_fields=["extracted_text", "ocr_status"])
        return text

    except Exception:
        logger.exception(
            "OCR extraction failed for DocumentVersion %s",
            document_version_id,
        )
        DocumentVersion.objects.filter(pk=document_version_id).update(
            ocr_status=DocumentVersion.OCR_FAILED,
        )
        raise
