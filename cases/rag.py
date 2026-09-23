import json
import logging
import os
import time
from typing import Any

from django.core.exceptions import ValidationError

from .models import Case, Document, DocumentVersion
from .permissions import can_access_case, can_access_document_version
from .rag_prompts import get_rag_system_prompt
from .search import unified_search

logger = logging.getLogger(__name__)


def _normalize_question(question: Any) -> str:
    if not isinstance(question, str):
        raise ValidationError("Question must be a string.")
    cleaned = question.strip()
    if not cleaned:
        raise ValidationError("Question cannot be empty.")
    if len(cleaned) > 2000:
        raise ValidationError("Question is too long.")
    return cleaned


def _case_metadata(case: Case) -> dict[str, Any]:
    police_station = getattr(case, "police_station", None)
    return {
        "case_id": case.pk,
        "case_number": getattr(case, "case_number", None),
        "title": getattr(case, "title", None),
        "case_type": getattr(case, "case_type", None),
        "status": getattr(case, "status", None),
        "police_station": getattr(police_station, "name", None),
    }


def _document_summary(document: Document) -> dict[str, Any]:
    return {
        "document_id": document.pk,
        "document_name": getattr(document, "name", None),
        "document_type": getattr(document, "document_type", None),
    }


def _authorized_document_versions(user, case: Case):
    documents = Document.objects.filter(case_id=case.pk).select_related("case")
    result = []
    for document in documents:
        versions = document.versions.all().select_related("document")
        for version in versions:
            if can_access_document_version(user, version):
                result.append(version)
    return result


def _source_from_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    source = {
        "document_id": chunk.get("document_id"),
        "document_name": chunk.get("document_name"),
        "document_version_id": chunk.get("document_version_id"),
        "chunk_id": chunk.get("chunk_id"),
        "similarity": chunk.get("similarity"),
    }
    return {key: value for key, value in source.items() if value is not None}


def _collect_retrieved_chunks(user, case_id: int, search_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    retrieved_chunks: list[dict[str, Any]] = []
    seen = set()

    for result in search_results:
        case = result.get("case")
        if case is None or case.pk != case_id:
            continue

        for item in result.get("documents", []):
            document = item.get("document")
            if document is None or document.case_id != case_id:
                continue

            version = item.get("version")
            for match in item.get("matches", []):
                version_id = match.get("version_id")
                if version_id is None:
                    continue

                candidate = DocumentVersion.objects.filter(pk=version_id).select_related("document").first()
                if candidate is None or candidate.document.case_id != case_id:
                    continue
                if not can_access_document_version(user, candidate):
                    continue

                chunk_id = match.get("chunk_index")
                if chunk_id is None:
                    chunk_id = match.get("chunk_id")
                key = (candidate.document_id, candidate.pk, chunk_id)
                if key in seen:
                    continue
                seen.add(key)

                retrieved_chunks.append({
                    "chunk_id": chunk_id,
                    "document_id": candidate.document_id,
                    "document_version_id": candidate.pk,
                    "document_name": candidate.document.name,
                    "document_type": candidate.document.document_type,
                    "content": match.get("text") or "",
                    "similarity": match.get("score"),
                })

    return retrieved_chunks


def _build_context(user, case: Case, retrieved_chunks: list[dict[str, Any]]) -> dict[str, Any]:
    documents = []
    seen_documents = set()
    for chunk in retrieved_chunks:
        doc_id = chunk["document_id"]
        if doc_id in seen_documents:
            continue
        seen_documents.add(doc_id)
        document = Document.objects.filter(pk=doc_id).select_related("case").first()
        if document is None:
            continue
        documents.append({
            "document_id": document.pk,
            "document_name": document.name,
            "document_type": document.document_type,
            "version_id": chunk.get("document_version_id"),
        })

    return {
        "case": _case_metadata(case),
        "documents": documents,
        "retrieved_chunks": retrieved_chunks,
    }


def _source_references_from_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs = []
    seen = set()
    for chunk in chunks:
        source = _source_from_chunk(chunk)
        key = (
            source.get("document_id"),
            source.get("document_version_id"),
            source.get("chunk_id"),
        )
        if key in seen:
            continue
        seen.add(key)
        refs.append(source)
    return refs


def _mock_provider_call(question: str, context: dict[str, Any]) -> dict[str, Any]:
    chunks = context.get("retrieved_chunks", [])
    if not chunks:
        return {
            "answer": "The available documents do not contain enough information to answer that question.",
            "sources": [],
            "provider": "mock",
            "model": "mock-default",
            "grounded": False,
            "confidence": 0.0,
        }

    evidence = "\n".join(
        f"- {chunk['document_name']} (version {chunk['document_version_id']}): {chunk['content']}"
        for chunk in chunks[:5]
    )
    answer = (
        "Based on the retrieved evidence: "
        f"{evidence}"
    )
    return {
        "answer": answer,
        "sources": _source_references_from_chunks(chunks),
        "provider": "mock",
        "model": "mock-default",
        "grounded": True,
        "confidence": min(0.93, 0.65 + (len(chunks) * 0.08)),
    }


def _openai_provider_call(question: str, context: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    payload = {
        "system": get_rag_system_prompt(),
        "user": json.dumps({
            "question": question,
            "context": context,
        }, ensure_ascii=False),
    }

    response = client.responses.create(
        model=model_name,
        input=[
            {"role": "system", "content": payload["system"]},
            {"role": "user", "content": payload["user"]},
        ],
    )

    content = ""
    if hasattr(response, "output_text") and response.output_text:
        content = response.output_text
    else:
        items = getattr(response, "output", []) or []
        for item in items:
            if getattr(item, "type", None) == "message":
                text_parts = getattr(item, "content", []) or []
                for part in text_parts:
                    if getattr(part, "type", None) == "output_text":
                        content += getattr(part, "text", "")
                    elif isinstance(part, dict) and part.get("type") == "output_text":
                        content += str(part.get("text", ""))

    if not content:
        raise RuntimeError("Empty model response.")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Malformed LLM response.") from exc

    answer = parsed.get("answer") or "The available documents do not contain enough information to answer that question."
    sources = parsed.get("sources") or _source_references_from_chunks(context.get("retrieved_chunks", []))
    return {
        "answer": answer,
        "sources": sources,
        "provider": "openai",
        "model": model_name,
        "grounded": bool(parsed.get("grounded", bool(context.get("retrieved_chunks")))),
        "confidence": parsed.get("confidence", 0.7),
    }


def generate_rag_answer(question: str, context: dict[str, Any]) -> dict[str, Any]:
    """Return a grounded answer and citations using the configured LLM provider."""
    provider_name = (os.getenv("NYAYAVAULT_LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "mock").lower()
    question = question.strip()
    chunks = context.get("retrieved_chunks", [])

    if not chunks:
        return {
            "answer": "The available documents do not contain enough information to answer that question.",
            "sources": [],
            "provider": provider_name,
            "model": os.getenv("OPENAI_MODEL", "n/a"),
            "grounded": False,
            "confidence": 0.0,
        }

    if provider_name == "openai":
        try:
            return _openai_provider_call(question, context)
        except Exception as exc:
            logger.exception("OpenAI LLM failure for RAG request")
            raise RuntimeError("LLM provider unavailable.") from exc

    return _mock_provider_call(question, context)


def ask_case(user, case_id: int, question: str, top_k: int = 5):
    """Answer a question using from the authorized case scope only."""
    start = time.perf_counter()
    logger.info("RAG request started | case_id=%s user_id=%s", case_id, getattr(user, "pk", None))

    if user is None or not getattr(user, "is_authenticated", False):
        return {
            "success": False,
            "error": "Authentication required.",
        }

    try:
        question = _normalize_question(question)
    except ValidationError as exc:
        return {
            "success": False,
            "error": str(exc),
        }

    case = Case.objects.filter(pk=case_id).select_related("police_station", "created_by", "assigned_to").first()
    if case is None:
        return {
            "success": False,
            "error": "Case not found.",
        }

    if not can_access_case(user, case):
        return {
            "success": False,
            "error": "You are not authorized to access this case.",
        }

    search_results = unified_search(question, user, top_k=top_k)
    authorized_results = []
    for result in search_results:
        result_case = result.get("case")
        if result_case is None or result_case.pk != case.pk:
            continue
        documents = []
        for item in result.get("documents", []):
            document = item.get("document")
            if document is None or document.case_id != case.pk:
                continue
            version = item.get("version")
            if version and not can_access_document_version(user, version):
                continue
            documents.append(item)
        if documents:
            authorized_results.append({"case": result_case, "documents": documents})

    if not authorized_results:
        duration = time.perf_counter() - start
        logger.info("RAG no results | case_id=%s user_id=%s duration=%.3fs", case_id, getattr(user, "pk", None), duration)
        return {
            "success": False,
            "error": "The available documents do not contain enough information to answer that question.",
            "case": _case_metadata(case),
            "sources": [],
            "retrieved_chunks": [],
        }

    retrieved_chunks = _collect_retrieved_chunks(user, case.pk, authorized_results)
    if not retrieved_chunks:
        duration = time.perf_counter() - start
        logger.info("RAG insufficient context | case_id=%s user_id=%s duration=%.3fs", case_id, getattr(user, "pk", None), duration)
        return {
            "success": False,
            "error": "Insufficient context: the available documents do not contain enough information to answer that question.",
            "case": _case_metadata(case),
            "sources": [],
            "retrieved_chunks": [],
        }

    context = _build_context(user, case, retrieved_chunks)
    context["retrieved_chunks"] = retrieved_chunks

    try:
        llm_start = time.perf_counter()
        llm_result = generate_rag_answer(question, context)
        llm_duration = time.perf_counter() - llm_start
    except Exception as exc:
        duration = time.perf_counter() - start
        logger.exception("RAG LLM failure | case_id=%s user_id=%s duration=%.3fs", case_id, getattr(user, "pk", None), duration)
        return {
            "success": False,
            "error": "The LLM provider is unavailable. Please try again later.",
            "case": _case_metadata(case),
            "sources": [],
            "retrieved_chunks": retrieved_chunks,
        }

    allowed_sources = _source_references_from_chunks(retrieved_chunks)
    answer_sources = llm_result.get("sources") or allowed_sources
    filtered_sources = []
    allowed_ids = {chunk["document_id"] for chunk in retrieved_chunks}
    for source in answer_sources:
        if source.get("document_id") in allowed_ids:
            filtered_sources.append(source)
    if not filtered_sources:
        filtered_sources = allowed_sources

    duration = time.perf_counter() - start
    logger.info(
        "RAG request completed | case_id=%s user_id=%s chunks=%s retrieval_time=%.3fs llm_time=%.3fs total=%.3fs provider=%s model=%s",
        case_id,
        getattr(user, "pk", None),
        len(retrieved_chunks),
        max(0.0, llm_start - start),
        llm_duration,
        duration,
        llm_result.get("provider", "n/a"),
        llm_result.get("model", "n/a"),
    )

    return {
        "success": True,
        "answer": llm_result.get("answer") or "The available documents do not contain enough information to answer that question.",
        "sources": filtered_sources,
        "retrieved_chunks": retrieved_chunks,
        "case": _case_metadata(case),
        "documents": context.get("documents", []),
        "confidence": llm_result.get("confidence", 0.0),
        "grounded": bool(llm_result.get("grounded", bool(retrieved_chunks))),
        "provider": llm_result.get("provider", "n/a"),
        "model": llm_result.get("model", "n/a"),
    }
