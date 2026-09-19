import hashlib
import re
from collections import defaultdict
from functools import lru_cache

from django.db.models import Q

from .models import Case, Document, DocumentVersion
from .permissions import can_access_case, can_access_document_version


_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*(?:[/-])[A-Za-z0-9_-]+$")
_CHUNK_SIZE = 1200
_CHUNK_OVERLAP = 200
_STOPWORDS = {
    "a", "about", "after", "again", "against", "all", "also", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "can", "cannot", "could", "did", "do", "does",
    "doing", "down", "during", "each", "few", "for", "from", "further", "had", "has",
    "have", "having", "he", "her", "here", "hers", "herself", "him", "himself", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me", "more",
    "most", "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she", "should",
    "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves",
    "then", "there", "these", "they", "this", "those", "through", "to", "too", "under",
    "until", "up", "very", "was", "we", "were", "what", "when", "where", "which", "while",
    "who", "whom", "why", "will", "with", "you", "your", "yours", "yourself", "yourselves"
}


def _significant_query_terms(query):
    return [
        term for term in re.findall(r"\w+", (query or "").lower())
        if len(term) > 1 and term not in _STOPWORDS
    ]


@lru_cache(maxsize=1)
def _semantic_model():
    """Load the optional model once so searches do not reload it."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None
    try:
        return SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        return None


_EMBEDDING_CACHE = {}


def _chunks(text):
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= _CHUNK_SIZE:
        return [text]
    return [
        text[start:start + _CHUNK_SIZE]
        for start in range(0, len(text), _CHUNK_SIZE - _CHUNK_OVERLAP)
    ]


def _semantic_matches(query, version):
    terms = _significant_query_terms(query)
    if len(terms) < 2:
        return []

    chunks = _chunks(version.extracted_text)
    if not chunks:
        return []

    model = _semantic_model()
    if model is not None:
        try:
            query_vector = model.encode([query], normalize_embeddings=True)[0]
            cache_key = (version.pk, hashlib.sha256(version.extracted_text.encode()).hexdigest())
            vectors = _EMBEDDING_CACHE.get(cache_key)
            if vectors is None:
                vectors = model.encode(chunks, normalize_embeddings=True)
                _EMBEDDING_CACHE[cache_key] = vectors
            scores = [float(vector @ query_vector) for vector in vectors]
        except Exception:
            scores = []
    else:
        query_terms = set(terms)
        scores = []
        for chunk in chunks:
            chunk_terms = set(re.findall(r"\w+", chunk.lower()))
            shared = query_terms & {term for term in chunk_terms if term not in _STOPWORDS}
            scores.append(
                len(shared) / max(len(query_terms), 1)
            )

    matches = []
    for index, score in enumerate(scores):
        if score > 0:
            matches.append({
                "text": chunks[index],
                "score": round(score, 4),
                "version_id": version.pk,
                "version_number": version.version_number,
                "chunk_index": index,
            })
    return sorted(matches, key=lambda match: match["score"], reverse=True)[:3]


def _keyword_matches(query, version):
    terms = _significant_query_terms(query)
    text = (version.extracted_text or "").strip()
    lowered = text.lower()
    if not text or not terms or not any(term in lowered for term in terms):
        return []

    first_position = min(
        (lowered.find(term) for term in terms if lowered.find(term) >= 0),
        default=0,
    )
    start = max(first_position - 90, 0)
    end = min(start + 240, len(text))
    score = sum(lowered.count(term) for term in terms) / len(terms)
    return [{
        "text": text[start:end],
        "score": round(min(score / 5, 1), 4),
        "version_id": version.pk,
        "version_number": version.version_number,
        "chunk_index": 0,
    }]


def _metadata_score(query, document):
    terms = _significant_query_terms(query)
    if not terms:
        return 0
    haystack = " ".join([
        document.name or "",
        document.document_type or "",
        document.description or "",
    ]).lower()
    return sum(term in haystack for term in terms) / max(len(terms), 1)


def _visible_versions(user, document):
    versions = document.versions.all()
    if can_access_case(user, document.case):
        return list(versions)
    return [version for version in versions if can_access_document_version(user, version)]


def _latest_text_version(versions):
    return next(
        (version for version in sorted(versions, key=lambda item: item.version_number, reverse=True)
         if (version.extracted_text or "").strip()),
        None,
    )


def _case_result(case, documents):
    return {
        "case": case,
        "documents": sorted(
            documents,
            key=lambda item: item["score"],
            reverse=True,
        ),
    }


def unified_search(query, user=None, top_k=10):
    """Return authorized, case-grouped search results for the UI or API."""
    query = (query or "").strip()
    if not query or user is None or not user.is_authenticated:
        return []

    significant_terms = _significant_query_terms(query)
    if not significant_terms and not _IDENTIFIER_RE.match(query):
        return []

    exact_cases = Case.objects.filter(case_number__iexact=query)
    if _IDENTIFIER_RE.match(query) or exact_cases.exists():
        grouped = []
        for case in exact_cases:
            visible_documents = []
            if can_access_case(user, case):
                for document in case.documents.all():
                    visible_documents.append({
                        "document": document,
                        "score": 1.0,
                        "matches": [],
                        "version": document.versions.order_by("-version_number").first(),
                    })
            else:
                for document in case.documents.all():
                    versions = _visible_versions(user, document)
                    if versions:
                        visible_documents.append({
                            "document": document,
                            "score": 1.0,
                            "matches": [],
                            "version": max(versions, key=lambda item: item.version_number),
                        })
            if visible_documents:
                grouped.append(_case_result(case, visible_documents))
        return grouped

    grouped = defaultdict(list)
    cases = Case.objects.all().prefetch_related("documents__versions")
    for case in cases:
        case_metadata_match = any(
            query.lower() in (value or "").lower()
            for value in [case.title, case.description, case.case_type, case.case_number]
        )
        for document in case.documents.all():
            if not can_access_case(user, case):
                visible_versions = _visible_versions(user, document)
                if not visible_versions:
                    continue
            else:
                visible_versions = list(document.versions.all())

            version = _latest_text_version(visible_versions)
            matches = []
            if version is not None:
                matches = _keyword_matches(query, version)
                semantic_matches = _semantic_matches(query, version)
                if semantic_matches:
                    unique_matches = {
                        (match["version_id"], match["chunk_index"], match["text"]): match
                        for match in matches + semantic_matches
                    }
                    matches = sorted(
                        unique_matches.values(),
                        key=lambda match: match["score"],
                        reverse=True,
                    )[:3]

            metadata_score = _metadata_score(query, document)
            score = max(metadata_score, max((match["score"] for match in matches), default=0))
            if case_metadata_match:
                score = max(score, 0.5)
            if score <= 0:
                continue
            grouped[case.pk].append({
                "document": document,
                "score": round(score, 4),
                "matches": matches,
                "version": version,
            })

    case_map = Case.objects.in_bulk(grouped.keys())
    results = [
        _case_result(case_map[case_id], documents[:top_k])
        for case_id, documents in grouped.items()
    ]
    return sorted(results, key=lambda result: max(
        (document["score"] for document in result["documents"]),
        default=0,
    ), reverse=True)


def serialize_search_results(results):
    return [
        {
            "case": {
                "id": result["case"].pk,
                "case_number": result["case"].case_number,
                "title": result["case"].title,
            },
            "documents": [
                {
                    "id": item["document"].pk,
                    "name": item["document"].name,
                    "document_type": item["document"].document_type,
                    "score": item["score"],
                    "version_id": item["version"].pk if item["version"] else None,
                    "version_number": item["version"].version_number if item["version"] else None,
                    "matches": item["matches"],
                }
                for item in result["documents"]
            ],
        }
        for result in results
    ]
