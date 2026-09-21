import os
import sys
from pathlib import Path
from typing import Any

import django
from dotenv import load_dotenv

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier


# ============================================================
# Configuration
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

load_dotenv()


# ============================================================
# Django initialization
# ============================================================

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "nyaya_vault.settings",
)

django.setup()


# Import Django models only after django.setup()
from cases.models import (
    Case,
    Document,
    DocumentVersion,
    DocumentShare,
)


# ============================================================
# Environment configuration
# ============================================================

MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN")

if not MCP_AUTH_TOKEN:
    raise RuntimeError(
        "MCP_AUTH_TOKEN is not configured."
    )


MCP_HOST = os.getenv(
    "MCP_HOST",
    "0.0.0.0",
)

MCP_PORT = int(
    os.getenv(
        "MCP_PORT",
        "8001",
    )
)


# ============================================================
# Authentication
# ============================================================
#
# IMPORTANT:
# StaticTokenVerifier is appropriate for controlled
# service-to-service / development deployments.
#
# For production with real users, replace this with:
# - JWT verification
# - OAuth/OIDC
# - or a custom verifier connected to your identity system.
#
# ============================================================

auth = StaticTokenVerifier(
    tokens={
        MCP_AUTH_TOKEN: {
            "client_id": "nyayavault-mcp-client",
            "scopes": [
                "cases:read",
                "documents:read",
            ],
        }
    }
)


# ============================================================
# FastMCP server
# ============================================================

mcp = FastMCP(
    name="NyayaVault MCP",
    instructions="""
    NyayaVault MCP provides controlled access to legal and
    investigation case information.

    Available capabilities include:

    - Searching cases
    - Retrieving case metadata
    - Searching documents
    - Retrieving document metadata
    - Listing documents associated with a case
    - Generating structured case-analysis prompts

    Security rules:

    - Never invent case information.
    - Never expose information not returned by a tool.
    - Treat all case and document information as confidential.
    - Do not bypass application-level authorization.
    - Do not infer missing facts.
    """,
    auth=auth,
)


# ============================================================
# Helper functions
# ============================================================

def clean_query(query: str) -> str:
    """
    Normalize and validate search input.
    """

    if not isinstance(query, str):
        raise ValueError("Query must be a string.")

    query = query.strip()

    if not query:
        raise ValueError(
            "Search query cannot be empty."
        )

    if len(query) > 200:
        raise ValueError(
            "Search query is too long."
        )

    return query


# ============================================================
# CASE TOOLS
# ============================================================

@mcp.tool(
    name="search_cases",
    title="Search Cases",
    description=(
        "Search NyayaVault cases using a case number or "
        "partial case-number query."
    ),
)
async def search_cases(
    query: str,
) -> dict[str, Any]:

    query = clean_query(query)

    cases = (
        Case.objects
        .filter(
            case_number__icontains=query
        )
        .order_by("id")[:20]
    )

    results = []

    async for case in cases:
        results.append({
            "id": case.id,
            "case_number": case.case_number,
            "status": case.status,
        })

    return {
        "query": query,
        "count": len(results),
        "results": results,
    }


@mcp.tool(
    name="get_case",
    title="Get Case",
    description=(
        "Retrieve basic metadata for a NyayaVault case "
        "using its internal case ID."
    ),
)
async def get_case(
    case_id: int,
) -> dict[str, Any]:

    if case_id <= 0:
        raise ValueError(
            "case_id must be a positive integer."
        )

    case = await (
        Case.objects
        .filter(id=case_id)
        .afirst()
    )

    if not case:
        return {
            "found": False,
            "case_id": case_id,
            "message": "Case not found.",
        }

    return {
        "found": True,
        "case": {
            "id": case.id,
            "case_number": case.case_number,
            "status": case.status,
        },
    }


@mcp.tool(
    name="get_cases_count",
    title="Get Cases Count",
    description=(
        "Return the total number of NyayaVault cases "
        "across OPEN, PENDING and CLOSED states."
    ),
)
async def get_cases_count() -> dict[str, Any]:

    statuses = [
        "OPEN",
        "PENDING",
        "CLOSED",
    ]

    total = await (
        Case.objects
        .filter(status__in=statuses)
        .acount()
    )

    return {
        "total_cases": total,
    }


# ============================================================
# DOCUMENT TOOLS
# ============================================================

@mcp.tool(
    name="search_documents",
    title="Search Documents",
    description=(
        "Search NyayaVault documents by document name."
    ),
)
async def search_documents(
    query: str,
) -> dict[str, Any]:

    query = clean_query(query)

    documents = (
        Document.objects
        .filter(
            name__icontains=query
        )
        .order_by("id")[:20]
    )

    results = []

    async for document in documents:
        results.append({
            "id": document.id,
            "name": document.name,
        })

    return {
        "query": query,
        "count": len(results),
        "results": results,
    }


@mcp.tool(
    name="get_document",
    title="Get Document",
    description=(
        "Retrieve basic metadata for a NyayaVault "
        "document."
    ),
)
async def get_document(
    document_id: int,
) -> dict[str, Any]:

    if document_id <= 0:
        raise ValueError(
            "document_id must be a positive integer."
        )

    document = await (
        Document.objects
        .filter(id=document_id)
        .afirst()
    )

    if not document:
        return {
            "found": False,
            "document_id": document_id,
            "message": "Document not found.",
        }

    return {
        "found": True,
        "document": {
            "id": document.id,
            "name": document.name,
        },
    }


@mcp.tool(
    name="get_case_documents",
    title="Get Case Documents",
    description=(
        "List documents associated with a specific "
        "NyayaVault case."
    ),
)
async def get_case_documents(
    case_id: int,
) -> dict[str, Any]:

    if case_id <= 0:
        raise ValueError(
            "case_id must be a positive integer."
        )

    case_exists = await (
        Case.objects
        .filter(id=case_id)
        .aexists()
    )

    if not case_exists:
        return {
            "found": False,
            "case_id": case_id,
            "message": "Case not found.",
        }

    documents = (
        Document.objects
        .filter(case_id=case_id)
        .order_by("id")
    )

    results = []

    async for document in documents:
        results.append({
            "id": document.id,
            "name": document.name,
        })

    return {
        "found": True,
        "case_id": case_id,
        "count": len(results),
        "documents": results,
    }


# ============================================================
# PROMPTS
# ============================================================

@mcp.prompt(
    name="summarize_case",
    title="Summarize Case",
    description=(
        "Generate a structured prompt for summarizing "
        "a NyayaVault case."
    ),
)
def summarize_case(
    case_information: str,
) -> str:

    return f"""
You are assisting with a legal/investigation case review.

Analyze ONLY the information provided below.

CASE INFORMATION:
{case_information}

Produce a structured summary containing:

1. Case identification
2. Current status
3. Key known facts
4. Important people or entities mentioned
5. Chronological events
6. Available evidence
7. Missing information
8. Important uncertainties

Rules:

- Do not invent facts.
- Do not infer facts that are not explicitly provided.
- Clearly distinguish known facts from missing information.
- Do not make a legal judgment.
- Do not fabricate evidence.
"""


@mcp.prompt(
    name="analyze_case",
    title="Analyze Case",
    description=(
        "Generate a structured analytical prompt for "
        "reviewing a case."
    ),
)
def analyze_case(
    case_information: str,
) -> str:

    return f"""
You are assisting an authorized investigator reviewing
a legal/investigation case.

CASE INFORMATION:
{case_information}

Perform a structured factual analysis.

Identify:

1. Established facts
2. Claims or allegations
3. Supporting evidence
4. Evidence gaps
5. Contradictions
6. Timeline inconsistencies
7. Missing information
8. Questions requiring further investigation

Important constraints:

- Use only the supplied information.
- Do not invent facts.
- Do not assume that an allegation is true.
- Do not provide a final legal conclusion.
- Clearly identify uncertainty.
- Separate evidence from interpretation.
"""


@mcp.prompt(
    name="review_evidence",
    title="Review Evidence",
    description=(
        "Generate a structured prompt for reviewing "
        "case evidence and identifying information gaps."
    ),
)
def review_evidence(
    evidence_information: str,
) -> str:

    return f"""
Review the following evidence information:

{evidence_information}

Analyze it using these categories:

1. Evidence identified
2. Source of each item
3. What each item establishes
4. Information that remains unverified
5. Contradictions between items
6. Missing evidence
7. Questions that should be investigated

Rules:

- Do not invent evidence.
- Do not modify the meaning of the supplied information.
- Do not assume authenticity unless explicitly established.
- Clearly identify uncertainty.
- Do not provide a final legal determination.
"""


@mcp.prompt(
    name="find_contradictions",
    title="Find Contradictions",
    description=(
        "Generate a structured prompt for identifying "
        "potential contradictions in supplied case material."
    ),
)
def find_contradictions(
    case_information: str,
) -> str:

    return f"""
Review the following case information for potential
contradictions:

{case_information}

Identify:

1. Direct contradictions
2. Timeline conflicts
3. Conflicting statements
4. Conflicting document information
5. Missing information that prevents resolution
6. Questions requiring clarification

For every potential contradiction:

- Quote or reference the relevant information.
- Explain why the information appears inconsistent.
- Do not decide which statement is true.
- Do not invent missing information.
- Mark uncertain conclusions clearly.
"""


# ============================================================
# Server
# ============================================================

if __name__ == "__main__":

    mcp.run(
        transport="streamable-http",
        host=MCP_HOST,
        port=MCP_PORT,
    )