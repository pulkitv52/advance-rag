"""Query / RAG inference router."""

import io
import re
import time
from difflib import get_close_matches
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.database import get_session
from src.core.logger import logger
from src.models.analysis import Analysis
from src.models.document import QueryLog
from src.services import agent_router, extractor, graph_db, nvidia, report_store, reporting, vector_db
from src.services.confidence import compute_confidence


router = APIRouter(prefix="/query", tags=["Query"])


class QueryRequest(BaseModel):
    query: str
    top_k: int = 10
    document_ids: Optional[list[str]] = None
    stream: bool = False
    history: Optional[list[dict[str, str]]] = None


class QueryResponse(BaseModel):
    query: str
    answer: str
    sources: list[dict[str, Any]]
    latency_ms: float
    confidence_score: float | None = None
    citation_coverage: float | None = None
    graph_enrichment_used: bool = False
    weak_claims: list[str] = Field(default_factory=list)


USR_FRAUD_KEYWORDS = (
    "fraud",
    "duplicate",
    "ghost",
    "anomaly",
    "flag",
    "corruption",
    "suspicious",
)

INTENT_VOCAB = {
    "scheme",
    "schemes",
    "citizen",
    "citizens",
    "beneficiary",
    "beneficiaries",
    "eligibility",
    "eligible",
    "fraud",
    "duplicate",
    "anomaly",
    "policy",
    "manual",
    "document",
    "documents",
    "count",
    "list",
    "total",
    "average",
    "explain",
    "details",
}


def normalize_query_text(query: str) -> str:
    """
    Fuzzy-normalize likely misspelled intent tokens (e.g., 'schems' -> 'schemes')
    without changing numbers/IDs or heavily rewriting user text.
    """
    if not query:
        return query
    parts = re.findall(r"[A-Za-z]+|\d+|[^A-Za-z\d\s]+|\s+", query)
    normalized: list[str] = []
    for token in parts:
        if not token.isalpha():
            normalized.append(token)
            continue
        low = token.lower()
        if len(low) < 4 or low in INTENT_VOCAB:
            normalized.append(token)
            continue
        match = get_close_matches(low, INTENT_VOCAB, n=1, cutoff=0.84)
        if match:
            fixed = match[0]
            if token.isupper():
                normalized.append(fixed.upper())
            elif token[0].isupper():
                normalized.append(fixed.capitalize())
            else:
                normalized.append(fixed)
        else:
            normalized.append(token)
    return "".join(normalized)


def _is_usr_fraud_question(query: str) -> bool:
    q = query.lower()
    return any(k in q for k in USR_FRAUD_KEYWORDS)


def _is_exhaustive_scheme_query(query: str) -> bool:
    q = query.lower()
    has_scheme_term = any(k in q for k in ("scheme", "schemes", "cheme", "schme", "shceme"))
    has_exhaustive_term = any(
        k in q for k in ("all", "list all", "all schemes", "all scheme", "every scheme", "complete list")
    )
    return has_scheme_term and has_exhaustive_term


def _extract_possible_person_name(query: str) -> str | None:
    """
    Best-effort name extraction for direct citizen checks.
    Handles prompts like:
      - Does Pramila Das come under fraud?
      - Is "Pramila Das" flagged?
      - Give details about Pramila Das
      - pumy mraol citizen details          ← lowercase, name-first pattern
      - pumy mraol details
      - give me info on rahul mondal
      - i want to know each detail aboy PUMY MRAOL  ← ALL CAPS lookup with typo
    """
    q = query.strip()

    # 1. Quoted name — highest priority
    quoted = re.search(r'["\']([^"\']{2,80})["\']', q)
    if quoted:
        candidate = quoted.group(1).strip()
        return candidate if candidate else None

    # Common noise and stop words that are NOT part of a person's name
    COMMON_WORDS = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "dare", "ought",
        "get", "give", "show", "find", "fetch", "tell", "me", "my", "your",
        "his", "her", "its", "our", "their", "this", "that", "these", "those",
        "what", "who", "whom", "which", "where", "when", "why", "how",
        "about", "from", "with", "for", "on", "in", "at", "by", "of", "to",
        "and", "or", "but", "not", "no", "yes", "please", "want", "know", "each",
        "every", "all", "any", "some", "many", "few", "more", "most",
        "citizen", "beneficiary", "details", "detail", "info", "information",
        "record", "records", "profile", "data", "check", "fraud", "scheme",
        "query", "search", "lookup", "find", "get", "show", "tell", "want", "know"
    }

    trailing_noise = {
        "having", "have", "has", "fraud", "flagged", "suspicious",
        "case", "details", "info", "information", "record", "records",
        "citizen", "beneficiary", "data", "profile", "check", "scheme", "schemes"
    }
    stop_words = {"her", "him", "them", "it", "this", "that", "these", "those"}

    def _clean_candidate(raw: str) -> str:
        candidate = re.sub(r"\s+", " ", raw).strip(" ?.,")
        parts = candidate.split()
        # Strip trailing noise words
        while parts and parts[-1].lower() in trailing_noise:
            parts.pop()
        # Strip leading noise words
        while parts and parts[0].lower() in trailing_noise:
            parts.pop(0)
        return " ".join(parts).strip()

    def _is_valid_name(name: str) -> bool:
        if not name:
            return False
        parts = [p.lower() for p in name.split()]
        if not parts:
            return False
        # Reject if all words are common noise words
        if all(p in COMMON_WORDS for p in parts):
            return False
        # Reject if it starts with a query verb/action word
        query_verbs = {"get", "give", "show", "find", "fetch", "tell", "list", "want", "know", "explain", "about", "detail", "details", "i", "explain", "describe"}
        if parts[0] in query_verbs:
            return False
        return True

    # 2. Capitalized or ALL CAPS sequences (e.g. "Pramila Das" or "PUMY MRAOL")
    # Matches sequences of 2 or 3 capitalized or ALL CAPS words.
    caps_pattern = re.search(r"\b([A-Z][a-zA-Z]{2,30}(?:\s+[A-Z][a-zA-Z]{1,30}){1,2})\b", q)
    if caps_pattern:
        candidate = _clean_candidate(caps_pattern.group(1))
        if _is_valid_name(candidate):
            return candidate

    # 3. Explicit phrasing patterns (any case)
    patterns = [
        r"does\s+([a-zA-Z.\- ]{2,80}?)\s+comes?\s+under",
        r"is\s+([a-zA-Z.\- ]{2,80}?)\s+(?:a|an)?\s*(?:fraud|flagged|suspicious)",
        r"details\s+about\s+([a-zA-Z.\- ]{2,80})",
        r"about\s+([a-zA-Z.\- ]{2,80})",
        r"(?:info|information|profile|record)\s+(?:on|for|of)\s+([a-zA-Z.\- ]{2,80})",
        r"(?:get|give|show|fetch)\s+(?:me\s+)?(?:details?|info|data)\s+(?:on|for|of)\s+([a-zA-Z.\- ]{2,80})",
        # "pumy mraol citizen details" — name BEFORE the noise word
        r"^([a-zA-Z.\- ]{4,80}?)\s+(?:citizen|beneficiary|details?|info|record|profile)\b",
    ]

    for p in patterns:
        m = re.search(p, q, flags=re.IGNORECASE)
        if m:
            candidate = _clean_candidate(m.group(1))
            if _is_valid_name(candidate) and candidate.lower() not in stop_words and len(candidate) >= 4:
                return candidate

    # 4. Lowercase multi-word fallback: two consecutive lowercase words that are NOT common English/query words.
    words = re.findall(r"[a-zA-Z]+", q)
    name_tokens = [w for w in words if w.lower() not in COMMON_WORDS and len(w) >= 3]
    if len(name_tokens) >= 2:
        candidate = " ".join(name_tokens[:2])
        if _is_valid_name(candidate) and len(candidate) >= 4:
            return candidate

    return None

    return None


def _extract_scheme_id(query: str) -> str | None:
    """
    Extract scheme ID like S767, S123, M999 from query text, or resolve from friendly names.
    """
    m = re.search(r"\b([A-Z]\d{3,5})\b", query.upper())
    if m:
        return m.group(1)
    
    # Try friendly name mapping
    q_clean = re.sub(r"[^a-z0-9\s]", "", query.lower())
    if any(k in q_clean for k in ("swasthya", "sathi", "swastha", "swasth")):
        return "S767"
    if any(k in q_clean for k in ("lokkhir", "lokhir", "lakhinar", "lakshmir", "bhandar", "lakhir")):
        return "S051"
    if any(k in q_clean for k in ("banglar", "bari")):
        return "S769"
    if any(k in q_clean for k in ("chaa", "cha", "sundari")):
        return "S760"
    if any(k in q_clean for k in ("mission", "vatsalya", "vatsala")):
        return "C529"
    if any(k in q_clean for k in ("amar", "fasal", "gola")):
        return "S589"
    if any(k in q_clean for k in ("post", "matric", "scholarship")):
        return "C501"
    return None


def _extract_age_threshold(query: str) -> int | None:
    """
    Extract age threshold from phrases like:
    - above 100 years
    - over 60
    - >= 75 years
    """
    q = query.lower()
    patterns = [
        r"(?:above|over)\s+age\s+(\d{1,3})",
        r"(?:above|over)\s+(\d{1,3})\s*(?:years?|yrs?)?",
        r"(?:older\s+than)\s+(\d{1,3})\s*(?:years?|yrs?)?",
        r"age\s*>=\s*(\d{1,3})",
        r">=\s*(\d{1,3})\s*(?:years?|yrs?)?",
        r"at\s+least\s+(\d{1,3})\s*(?:years?|yrs?)?",
    ]
    for p in patterns:
        m = re.search(p, q)
        if m:
            return int(m.group(1))
    return None


def _is_age_query(query: str) -> bool:
    q = query.lower()
    return any(k in q for k in ("age", "years", "year old", "yrs"))


def _build_usr_citizen_answer(name: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return (
            f"I could not find a USR citizen record matching '{name}' in the Knowledge Graph. "
            "Please verify spelling, or provide UID for an exact lookup."
        )

    lines: list[str] = []
    lines.append(
        f"I found {len(rows)} matching USR citizen record(s) for '{name}' in the Knowledge Graph."
    )
    for i, row in enumerate(rows, start=1):
        flags = row.get("flags", [])
        schemes = row.get("schemes", [])
        is_flagged = len(flags) > 0
        lines.append(f"")
        lines.append(f"{i}. {row.get('name', 'Unknown')} (UID: {row.get('uid', 'N/A')})")
        lines.append(
            f"   Location: {row.get('gp') or 'N/A'}, {row.get('block') or 'N/A'}, {row.get('district') or 'N/A'}"
        )
        lines.append(
            f"   Risk: {row.get('risk_tier') or 'N/A'} | Vulnerability Score: {row.get('vulnerability_score') if row.get('vulnerability_score') is not None else 'N/A'}"
        )
        lines.append(
            f"   Fraud Status: {'FLAGGED' if is_flagged else 'No active fraud flag found'}"
        )
        if schemes:
            lines.append("   Enrolled Schemes:")
            for s in schemes:
                lines.append(f"   - [{s.get('id', 'N/A')}] {s.get('name', 'Unknown Scheme')}")
        else:
            lines.append("   Enrolled Schemes: None found in graph")
        if flags:
            lines.append("   Flags:")
            for f in flags[:5]:
                lines.append(
                    f"   - {f.get('rule')}: {f.get('type')} (confidence: {f.get('confidence', 'N/A')}), {f.get('description', '')}"
                )
    return "\n".join(lines)


def _extract_possible_uid(query: str) -> str | None:
    """
    Extract UID-like numeric token (commonly 12 digits) from query text.
    """
    m = re.search(r"\b(\d{10,16})\b", query)
    if not m:
        return None
    return m.group(1)


def _build_usr_uid_answer(uid: str, row: dict[str, Any]) -> str:
    flags = row.get("flags", [])
    dupes = row.get("duplicate_links", [])
    schemes = row.get("schemes", [])
    lines = [
        f"USR record found for UID {uid}:",
        f"Name: {row.get('name', 'Unknown')}",
        f"Location: {row.get('gp') or 'N/A'}, {row.get('block') or 'N/A'}, {row.get('district') or 'N/A'}",
        f"Risk: {row.get('risk_tier') or 'N/A'} | Vulnerability Score: {row.get('vulnerability_score') if row.get('vulnerability_score') is not None else 'N/A'}",
        f"Fraud Status: {'FLAGGED' if flags else 'No active fraud flag found'}",
    ]
    if schemes:
        lines.append("Enrolled Schemes:")
        for s in schemes:
            lines.append(f"- [{s.get('id', 'N/A')}] {s.get('name', 'Unknown Scheme')}")
    else:
        lines.append("Enrolled Schemes: None found in graph")
    if flags:
        lines.append("Flags:")
        for f in flags[:6]:
            lines.append(
                f"- {f.get('rule')}: {f.get('type')} (confidence: {f.get('confidence', 'N/A')}), {f.get('description', '')}"
            )
    if dupes:
        lines.append("Potential duplicate links:")
        for d in dupes[:8]:
            lines.append(
                f"- {d.get('name', 'Unknown')} (UID: {d.get('uid', 'N/A')}) via {d.get('rule', 'B-rule')} (confidence: {d.get('confidence', 'N/A')})"
            )
    return "\n".join(lines)


def _is_simple_greeting(query: str) -> bool:
    q = query.strip().lower().strip("?.!,")
    greetings = {
        "hello", "hi", "hey", "hola", "greetings", "howdy", "hi there", "hello there", "hey there",
        "good morning", "good afternoon", "good evening", "namaste", "namaskar"
    }
    return q in greetings


@router.post("/", response_model=QueryResponse, summary="Ask a question across your documents")
async def query_documents(
    request: QueryRequest,
    session: AsyncSession = Depends(get_session),
):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    start_total = time.perf_counter()
    if _is_simple_greeting(request.query):
        answer = (
            "Hello! I am your Govt. of West Bengal Finance Department Intelligence Assistant.\n\n"
            "I can assist you with:\n"
            "1. **Researching Policy Circulars & Treasury Directives**: Ask about audit guidelines, treasury rules, or financial notifications.\n"
            "2. **Verifying Citizen Benefit Schemes**: Check eligibility criteria and rules for schemes like *Swasthya Sathi*, *Lakshmir Bhandar*, *Amar Fasal Amar Gola*, and more.\n"
            "3. **Inspecting Social Registry Analytics**: Ask about flagged cases, potential duplicate identity detections, or anomalies in the registry.\n\n"
            "How can I assist you with your research or queries today?"
        )
        total_latency_ms = round((time.perf_counter() - start_total) * 1000, 2)
        log = QueryLog(
            query=request.query,
            answer=answer,
            chunks_used=0,
            document_id=request.document_ids[0] if request.document_ids else None,
            latency_ms=total_latency_ms,
        )
        session.add(log)
        await session.commit()
        logger.info("[ROUTER AGENT] Conversational greeting matched. Returning preset help answer.")
        return QueryResponse(
            query=request.query,
            answer=answer,
            sources=[
                {
                    "filename": "System Assistant (Greeting)",
                    "page": None,
                    "score": 1.0,
                    "snippet": "Friendly system greeting assistant responder.",
                }
            ],
            latency_ms=total_latency_ms,
            confidence_score=1.0,
            citation_coverage=1.0,
            graph_enrichment_used=False,
            weak_claims=[],
        )

    normalized_query = normalize_query_text(request.query)
    logger.info(f"--- [QUERY START] --- Query: '{request.query[:100]}...'")
    if normalized_query != request.query:
        logger.info(f"[QUERY NORMALIZER] Normalized query to: '{normalized_query[:100]}...'")

    # Deterministic exhaustive scheme-list mode for broad "all schemes" questions.
    if _is_exhaustive_scheme_query(normalized_query):
        schemes = await graph_db.get_usr_schemes()
        if schemes:
            header = [
                "| Scheme ID | Name | Citizens | Enrollments |",
                "| --- | --- | ---: | ---: |",
            ]
            rows = [
                f"| {s.get('id', 'N/A')} | {s.get('name', 'N/A')} | {s.get('citizen_count', 0)} | {s.get('enrollment_count', 0)} |"
                for s in schemes
            ]
            answer = (
                f"Found {len(schemes)} schemes in the live registry.\n\n"
                + "\n".join(header + rows)
            )
        else:
            answer = "No schemes were found in the live registry."

        total_latency_ms = round((time.perf_counter() - start_total) * 1000, 2)
        log = QueryLog(
            query=request.query,
            answer=answer,
            chunks_used=0,
            document_id=request.document_ids[0] if request.document_ids else None,
            latency_ms=total_latency_ms,
        )
        session.add(log)
        await session.commit()
        logger.info("[ROUTER AGENT] Deterministic exhaustive scheme mode executed.")
        return QueryResponse(
            query=request.query,
            answer=answer,
            sources=[
                {
                    "filename": "USR Knowledge Graph (Scheme Catalog)",
                    "page": None,
                    "score": 1.0,
                    "snippet": "Deterministic live scheme catalog listing from Neo4j.",
                }
            ],
            latency_ms=total_latency_ms,
            confidence_score=1.0,
            citation_coverage=1.0,
            graph_enrichment_used=True,
            weak_claims=[],
        )

    # ─────────────────────────────────────────────────────────────────────────
    # DETERMINISTIC FAST-PASS PRE-ROUTER
    # Bypasses LLM routing for direct name/UID snap lookups, EXCEPT if document-intent keywords are present.
    # ─────────────────────────────────────────────────────────────────────────
    candidate_uid = _extract_possible_uid(normalized_query)
    candidate_name = _extract_possible_person_name(normalized_query)
    
    # Document-intent or Database-action keywords that require LLM agentic Hybrid/RAG routing
    agent_keywords = [
        "eligible", "eligibility", "criteria", "rule", "rules", "policy", "manual", "explain", "why", "how", "document", "pdf",
        "list", "show", "find", "count", "how many", "who are", "who is", "search", "lookup", "total", "sum", "average", "avg",
        "scheme", "schemes", "cheme", "schme", "shceme", "chemes", "schmes", "shcemes"
    ]
    has_agent_intent = any(k in normalized_query.lower() for k in agent_keywords)
    
    if (candidate_uid or candidate_name) and not has_agent_intent:
        logger.info("[ROUTER AGENT] Detected direct citizen lookup without document/db intent. Running deterministic fast-pass.")

        
        # 1. Direct UID fast-pass
        if candidate_uid:
            try:
                row = await graph_db.get_usr_citizen_fraud_snapshot_by_uid(candidate_uid)
                if row:
                    answer = _build_usr_uid_answer(candidate_uid, row)
                    total_latency_ms = round((time.perf_counter() - start_total) * 1000, 2)
                    log = QueryLog(
                        query=request.query,
                        answer=answer,
                        chunks_used=0,
                        document_id=request.document_ids[0] if request.document_ids else None,
                        latency_ms=total_latency_ms,
                    )
                    session.add(log)
                    await session.commit()
                    logger.info(f"[USR-DIRECT] UID-first deterministic hit for '{candidate_uid}'")
                    return QueryResponse(
                        query=request.query,
                        answer=answer,
                        sources=[
                            {
                                "filename": "USR Knowledge Graph",
                                "page": None,
                                "score": 1.0,
                                "snippet": f"Direct citizen lookup for UID: {candidate_uid}",
                            }
                        ],
                        latency_ms=total_latency_ms,
                        confidence_score=1.0,
                        citation_coverage=1.0,
                        graph_enrichment_used=True,
                        weak_claims=[],
                    )
            except Exception as e:
                logger.warning(f"USR UID-first resolution failed: {e}")

        # 2. Direct Name fast-pass
        if candidate_name:
            try:
                matches = await graph_db.get_usr_citizen_fraud_snapshot(candidate_name, limit=5)
                if matches:
                    answer = _build_usr_citizen_answer(candidate_name, matches)
                    total_latency_ms = round((time.perf_counter() - start_total) * 1000, 2)
                    trust_metadata = compute_confidence(answer, [], graph_enrichment_used=True)
                    log = QueryLog(
                        query=request.query,
                        answer=answer,
                        chunks_used=0,
                        document_id=request.document_ids[0] if request.document_ids else None,
                        latency_ms=total_latency_ms,
                    )
                    session.add(log)
                    await session.commit()
                    logger.info(
                        f"[USR-DIRECT] Citizen lookup hit for '{candidate_name}' (query not fraud-gated)"
                    )
                    return QueryResponse(
                        query=request.query,
                        answer=answer,
                        sources=[
                            {
                                "filename": "USR Knowledge Graph",
                                "page": None,
                                "score": 1.0,
                                "snippet": f"Direct citizen lookup for name: {candidate_name}",
                            }
                        ],
                        latency_ms=total_latency_ms,
                        confidence_score=trust_metadata["confidence_score"],
                        citation_coverage=1.0,
                        graph_enrichment_used=True,
                        weak_claims=[],
                    )

                # Name detected but no match -> return suggestions if available in DB
                suggestions = await graph_db.get_usr_citizen_name_suggestions(candidate_name, limit=8)
                if suggestions:
                    answer_lines = [
                        f"No exact USR citizen match found for '{candidate_name}' in the Knowledge Graph.",
                        "Closest name matches found:"
                    ]
                    for i, row in enumerate(suggestions, start=1):
                        answer_lines.append(
                            f"{i}. {row.get('name', 'Unknown')} (UID: {row.get('uid', 'N/A')}) "
                            f"- {row.get('gp') or 'N/A'}, {row.get('block') or 'N/A'}, {row.get('district') or 'N/A'}"
                        )
                    answer_lines.append(
                        "Please confirm the correct UID/name variant to run a precise lookup."
                    )
                    answer = "\n".join(answer_lines)
                    total_latency_ms = round((time.perf_counter() - start_total) * 1000, 2)
                    log = QueryLog(
                        query=request.query,
                        answer=answer,
                        chunks_used=0,
                        document_id=request.document_ids[0] if request.document_ids else None,
                        latency_ms=total_latency_ms,
                    )
                    session.add(log)
                    await session.commit()
                    logger.info(
                        f"[USR-DIRECT] No exact match for '{candidate_name}' — returned closest suggestions."
                    )
                    return QueryResponse(
                        query=request.query,
                        answer=answer,
                        sources=[
                            {
                                "filename": "USR Knowledge Graph",
                                "page": None,
                                "score": 1.0,
                                "snippet": f"Direct citizen lookup miss for name: {candidate_name}",
                            }
                        ],
                        latency_ms=total_latency_ms,
                        confidence_score=1.0,
                        citation_coverage=1.0,
                        graph_enrichment_used=True,
                        weak_claims=[],
                    )
                else:
                    # Suggestions is empty -> this is not a citizen search. Fall through to standard LLM router!
                    logger.info(
                        f"[USR-DIRECT] No citizen matches or suggestions found for '{candidate_name}'. Falling back to Agentic Router."
                    )
            except Exception as e:
                logger.warning(f"USR citizen name resolution failed: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # DYNAMIC ROUTING AGENT FLOW
    # Used for aggregate queries, text-to-cypher analytics, policy RAG, and hybrid requests.
    # ─────────────────────────────────────────────────────────────────────────
    logger.info("[ROUTER AGENT] Invoking LLM Routing Agent...")
    route_info = await agent_router.route_query(normalized_query, history=request.history)
    route = route_info.get("route", "DOCUMENT_RAG")
    explanation = route_info.get("explanation", "")
    extracted_params = route_info.get("extracted_params", {})
    
    logger.info(f"[ROUTER AGENT] Route Selected: {route} | Explanation: {explanation}")
    
    sources = []
    confidence_score = 0.8
    citation_coverage = 0.8
    graph_enrichment_used = False
    weak_claims = []
    
    # --- ROUTE A: DYNAMIC_CYPHER ---
    run_rag_fallback = False
    if route == "DYNAMIC_CYPHER":
        explicit_scheme_id = extracted_params.get("scheme_id") or _extract_scheme_id(normalized_query)
        age_threshold = _extract_age_threshold(request.query) if _is_age_query(request.query) else None
        if explicit_scheme_id and age_threshold is not None:
            # Deterministic guard for age+scheme queries to avoid fragile LLM Cypher syntax errors.
            cypher_query = (
                f"MATCH (c:Citizen)-[:ENROLLED_IN]->(s:Scheme {{id: '{explicit_scheme_id.upper()}'}})\n"
                "WHERE c.dob IS NOT NULL\n"
                "  AND trim(toString(c.dob)) <> ''\n"
                f"  AND duration.between(date(c.dob), date()).years > {age_threshold}\n"
                "RETURN c.name AS name, c.uid AS uid, c.dob AS dob, "
                "duration.between(date(c.dob), date()).years AS age\n"
                "ORDER BY age DESC\n"
                "LIMIT 100"
            )
            logger.info(
                f"[DYNAMIC_CYPHER] Deterministic age-query guard activated for scheme "
                f"{explicit_scheme_id.upper()} and threshold > {age_threshold}."
            )
        else:
            cypher_query = await agent_router.generate_cypher(normalized_query, extracted_params=extracted_params)
        if cypher_query:
            if agent_router.is_cypher_safe(cypher_query):
                try:
                    rows = await graph_db.execute_read_only_cypher(cypher_query)
                    graph_enrichment_used = True
                    if rows:
                        # Format rows into a clean markdown table
                        headers = list(rows[0].keys())
                        table_lines = [
                            "| " + " | ".join(headers) + " |",
                            "| " + " | ".join(["---"] * len(headers)) + " |"
                        ]
                        for row in rows[:50]:
                            row_vals = []
                            for h in headers:
                                val = row[h]
                                if isinstance(val, list):
                                    row_vals.append(", ".join(map(str, val)))
                                else:
                                    row_vals.append(str(val))
                            table_lines.append("| " + " | ".join(row_vals) + " |")
                        markdown_table = "\n".join(table_lines)
                        
                        # Generate structured, professional response
                        synthesis_prompt = (
                            f"You are a helpful administrative data analyst. Synthesize the raw database query results below "
                            f"into a professional, detailed, and highly clear explanation answering the user's question: '{normalized_query}'\n\n"
                            f"### Raw Database Results:\n{markdown_table}\n\n"
                            f"Present the results clearly, explain any key insights or totals, and output a complete Markdown table representing the data."
                        )
                        answer = await nvidia.generate_rag_answer(
                            query=normalized_query,
                            context_chunks=[{"text": synthesis_prompt, "filename": "USR Knowledge Graph"}],
                            history=request.history,
                        )
                        sources = [{
                            "filename": "USR Knowledge Graph (Dynamic Cypher)",
                            "page": None,
                            "score": 1.0,
                            "snippet": f"Executed read-only Cypher query:\n\n```cypher\n{cypher_query}\n```",
                        }]
                    else:
                        logger.info("[DYNAMIC_CYPHER] Cypher query returned 0 rows. Returning direct DB-backed empty-result answer.")
                        answer = (
                            "No matching records were found in the live knowledge graph for this query."
                        )
                        sources = [{
                            "filename": "USR Knowledge Graph (Dynamic Cypher)",
                            "page": None,
                            "score": 1.0,
                            "snippet": f"Executed read-only Cypher query with 0 rows:\n\n```cypher\n{cypher_query}\n```",
                        }]
                except Exception as e:
                    logger.error(f"Dynamic Cypher execution failed: {e}. Attempting automatic query repair.")
                    repaired_query = await agent_router.repair_cypher(
                        normalized_query,
                        failed_cypher=cypher_query,
                        execution_error=str(e),
                        extracted_params=extracted_params,
                    )
                    if repaired_query and agent_router.is_cypher_safe(repaired_query):
                        try:
                            rows = await graph_db.execute_read_only_cypher(repaired_query)
                            graph_enrichment_used = True
                            if rows:
                                headers = list(rows[0].keys())
                                table_lines = [
                                    "| " + " | ".join(headers) + " |",
                                    "| " + " | ".join(["---"] * len(headers)) + " |"
                                ]
                                for row in rows[:50]:
                                    row_vals = []
                                    for h in headers:
                                        val = row[h]
                                        if isinstance(val, list):
                                            row_vals.append(", ".join(map(str, val)))
                                        else:
                                            row_vals.append(str(val))
                                    table_lines.append("| " + " | ".join(row_vals) + " |")
                                markdown_table = "\n".join(table_lines)

                                synthesis_prompt = (
                                    f"You are a helpful administrative data analyst. Synthesize the raw database query results below "
                                    f"into a professional, detailed, and highly clear explanation answering the user's question: '{normalized_query}'\n\n"
                                    f"### Raw Database Results:\n{markdown_table}\n\n"
                                    f"Present the results clearly, explain any key insights or totals, and output a complete Markdown table representing the data."
                                )
                                answer = await nvidia.generate_rag_answer(
                                    query=normalized_query,
                                    context_chunks=[{"text": synthesis_prompt, "filename": "USR Knowledge Graph"}],
                                    history=request.history,
                                )
                                sources = [{
                                    "filename": "USR Knowledge Graph (Dynamic Cypher - Auto Repaired)",
                                    "page": None,
                                    "score": 1.0,
                                    "snippet": f"Executed repaired read-only Cypher query:\n\n```cypher\n{repaired_query}\n```",
                                }]
                                logger.info("[DYNAMIC_CYPHER] Auto-repaired Cypher executed successfully.")
                            else:
                                logger.info("[DYNAMIC_CYPHER] Repaired Cypher returned 0 rows. Returning direct DB-backed empty-result answer.")
                                answer = (
                                    "No matching records were found in the live knowledge graph for this query."
                                )
                                sources = [{
                                    "filename": "USR Knowledge Graph (Dynamic Cypher - Auto Repaired)",
                                    "page": None,
                                    "score": 1.0,
                                    "snippet": f"Executed repaired read-only Cypher query with 0 rows:\n\n```cypher\n{repaired_query}\n```",
                                }]
                        except Exception as repair_exec_error:
                            logger.error(
                                f"Dynamic Cypher repaired query execution failed: {repair_exec_error}. "
                                "Triggering RAG/HYBRID fallback."
                            )
                            run_rag_fallback = True
                    else:
                        logger.error("Dynamic Cypher repair unavailable or unsafe. Triggering RAG/HYBRID fallback.")
                        run_rag_fallback = True
            else:
                logger.warning("[DYNAMIC_CYPHER] Generated Cypher blocked by security sandbox. Triggering RAG/HYBRID fallback.")
                run_rag_fallback = True
        else:
            logger.warning("[DYNAMIC_CYPHER] Cypher generation returned None. Triggering RAG/HYBRID fallback.")
            run_rag_fallback = True
            
    # --- ROUTE B: HYBRID or DOCUMENT_RAG or DYNAMIC_CYPHER Fallback ---
    if route != "DYNAMIC_CYPHER" or run_rag_fallback:
        if run_rag_fallback:
            logger.info(f"[ROUTER FALLBACK] Running fallback RAG pipeline for query: '{request.query[:100]}'")
            route = "HYBRID"
        # 1. Fetch vector search results from Qdrant
        t0 = time.perf_counter()
        query_embedding = await nvidia.get_query_embedding(normalized_query)
        embed_time = time.perf_counter() - t0
        logger.info(f"[1/3] [NIM-EMBED] Generated query vector in {embed_time:.2f}s")

        t0 = time.perf_counter()
        candidate_top_k = request.top_k * 3
        explicit_scheme_id = _extract_scheme_id(normalized_query)
        initial_chunks = await vector_db.search_chunks(
            query_embedding=query_embedding,
            top_k=candidate_top_k,
            document_ids=request.document_ids,
            scheme_id=explicit_scheme_id,
        )
        if explicit_scheme_id:
            if not initial_chunks:
                logger.warning(
                    f"[QDRANT] No metadata-scoped chunks for {explicit_scheme_id.upper()}. "
                    "Falling back to generic retrieval + filename scope (backward compatibility)."
                )
                fallback_chunks = await vector_db.search_chunks(
                    query_embedding=query_embedding,
                    top_k=candidate_top_k,
                    document_ids=request.document_ids,
                )
                scheme_token = explicit_scheme_id.upper()
                scoped = [
                    c for c in fallback_chunks
                    if scheme_token in str(c.get("filename", "")).upper()
                ]
                initial_chunks = scoped if scoped else fallback_chunks
            logger.info(
                f"[QDRANT] Scheme-scoped retrieval enforced via metadata filter for {explicit_scheme_id.upper()}: "
                f"{len(initial_chunks)} candidates"
            )
        retrieve_time = time.perf_counter() - t0
        logger.info(f"[2/3] [QDRANT] Retrieved {len(initial_chunks)} candidates in {retrieve_time:.2f}s")

        t0 = time.perf_counter()
        chunks = await nvidia.rerank_chunks(
            query=normalized_query,
            chunks=initial_chunks,
            top_n=request.top_k,
        )
        rerank_time = time.perf_counter() - t0
        logger.info(f"[2.1/3] [NIM-RERANK] Refined to {len(chunks)} chunks in {rerank_time:.2f}s")

        graph_context = ""
        
        # 2. If HYBRID, fetch matching relational DB snapshots to merge context
        if route == "HYBRID":
            name = extracted_params.get("name") or candidate_name
            uid = extracted_params.get("uid") or candidate_uid
            scheme_id = extracted_params.get("scheme_id") or _extract_scheme_id(normalized_query)
            
            graph_insights = []
            if uid:
                usr_record = await graph_db.get_usr_citizen_fraud_snapshot_by_uid(uid)
                if usr_record:
                    graph_insights.append(f"### Direct Citizen Record for UID {uid}:\n{_build_usr_uid_answer(uid, usr_record)}")
            elif name:
                usr_records = await graph_db.get_usr_citizen_fraud_snapshot(name, limit=5)
                if usr_records:
                    graph_insights.append(f"### Direct Citizen Records for Name '{name}':\n{_build_usr_citizen_answer(name, usr_records)}")
            
            if scheme_id:
                scheme_citizens = await graph_db.get_usr_citizens_by_scheme(scheme_id, limit=25)
                if scheme_citizens:
                    lines = [f"### Live Database Records (Enrolled Citizens in Scheme {scheme_id}):"]
                    for i, c in enumerate(scheme_citizens, start=1):
                        loc = f"{c.get('gp') or 'N/A'}, {c.get('block') or 'N/A'}, {c.get('district') or 'N/A'}"
                        lines.append(
                            f"{i}. Name: {c.get('name')}, UID: {c.get('uid')}, DOB: {c.get('dob') or 'N/A'}, "
                            f"Location: {loc}"
                        )
                    graph_insights.append("\n".join(lines))
                    
            if graph_insights:
                graph_context = "\n\n".join(graph_insights)
                graph_enrichment_used = True
                logger.info(f"[HYBRID RAG] Injected relational snapshot data into query context.")
                
        # Also try default multi-hop enrichment if entities are present as secondary help
        if not graph_context:
            try:
                entities = await extractor.extract_entities_from_query(normalized_query)
                if entities:
                    facts = await graph_db.search_multi_hop_context(entities, request.document_ids)
                    if facts:
                        graph_context = "\n### Relational Intelligence (Deep Graph Analysis):\n" + "\n".join(facts)
                        graph_enrichment_used = True
            except Exception as e:
                logger.warning(f"Secondary Graph enrichment failed: {e}")

        # Ensure we have chunks or content
        if not chunks:
            logger.warning("[2/3] [QDRANT] No relevant context found for query")
            return QueryResponse(
                query=request.query,
                answer="No relevant documents or records could be found. Please verify your query or upload appropriate policy documents.",
                sources=[],
                latency_ms=round((time.perf_counter() - start_total) * 1000, 2),
                confidence_score=0.0,
                citation_coverage=0.0,
                graph_enrichment_used=False,
                weak_claims=["No relevant evidence was found for this query."],
            )

        t0 = time.perf_counter()
        enriched_query = f"{normalized_query}\n\n{graph_context}" if graph_context else normalized_query
        answer = await nvidia.generate_rag_answer(
            query=enriched_query,
            context_chunks=chunks,
            stream=False,
            history=request.history,
        )
        generate_time = time.perf_counter() - t0
        logger.info(f"[3/3] [NIM-LLM] Generated grounded answer in {generate_time:.2f}s")
        
        # Build standard sources
        sources = [
            {
                "filename": c["filename"],
                "page": c.get("page"),
                "score": round(c["score"], 4),
                "snippet": c["text"][:300],
            }
            for c in chunks
        ]
        if graph_context:
            sources.append({
                "filename": "USR Knowledge Graph (Snapshot Context)",
                "page": None,
                "score": 1.0,
                "snippet": graph_context[:1000],
            })
            
        trust_metadata = compute_confidence(answer, chunks, graph_enrichment_used)
        confidence_score = trust_metadata["confidence_score"]
        citation_coverage = trust_metadata["citation_coverage"]
        weak_claims = trust_metadata["weak_claims"]

    # ─────────────────────────────────────────────────────────────────────────
    # AUDIT LOGGING & RESPONSE COMPILATION
    # ─────────────────────────────────────────────────────────────────────────
    total_latency_ms = round((time.perf_counter() - start_total) * 1000, 2)
    log = QueryLog(
        query=request.query,
        answer=answer,
        chunks_used=len(sources),
        document_id=request.document_ids[0] if request.document_ids else None,
        latency_ms=total_latency_ms,
    )
    session.add(log)
    await session.commit()

    logger.info(f"--- [QUERY FINISH] --- Total Latency: {total_latency_ms}ms")

    return QueryResponse(
        query=request.query,
        answer=answer,
        sources=sources,
        latency_ms=total_latency_ms,
        confidence_score=confidence_score,
        citation_coverage=citation_coverage,
        graph_enrichment_used=graph_enrichment_used,
        weak_claims=weak_claims,
    )



@router.post("/stream", summary="Stream a RAG answer via SSE")
async def stream_query(
    request: QueryRequest,
    session: AsyncSession = Depends(get_session),
):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    normalized_query = normalize_query_text(request.query)
    query_embedding = await nvidia.get_query_embedding(normalized_query)
    explicit_scheme_id = _extract_scheme_id(normalized_query)
    initial_chunks = await vector_db.search_chunks(
        query_embedding=query_embedding,
        top_k=request.top_k * 3,
        document_ids=request.document_ids,
        scheme_id=explicit_scheme_id,
    )
    if explicit_scheme_id and not initial_chunks:
        fallback_chunks = await vector_db.search_chunks(
            query_embedding=query_embedding,
            top_k=request.top_k * 3,
            document_ids=request.document_ids,
        )
        scheme_token = explicit_scheme_id.upper()
        scoped = [
            c for c in fallback_chunks
            if scheme_token in str(c.get("filename", "")).upper()
        ]
        initial_chunks = scoped if scoped else fallback_chunks
    chunks = await nvidia.rerank_chunks(
        query=normalized_query,
        chunks=initial_chunks,
        top_n=request.top_k,
    )

    if not chunks:

        async def no_context():
            yield "data: No relevant documents found.\n\n"

        return StreamingResponse(no_context(), media_type="text/event-stream")

    token_stream = await nvidia.generate_rag_answer(
        query=normalized_query,
        context_chunks=chunks,
        stream=True,
        history=request.history,
    )

    async def event_generator():
        async for token in token_stream:
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class ExportRequest(BaseModel):
    analysis_id: str | None = None
    query: str
    answer: str
    sources: list[dict[str, Any]]
    visuals: Optional[list[str]] = None


@router.post("/export", summary="Export research results to a professional PDF")
async def export_query_report(request: ExportRequest, session: AsyncSession = Depends(get_session)):
    try:
        if request.analysis_id:
            analysis = await session.get(Analysis, request.analysis_id)
            if not analysis:
                raise HTTPException(status_code=404, detail="Analysis not found for report export.")

        pdf_bytes = reporting.generate_executive_report(
            query=request.query,
            answer=request.answer,
            sources=request.sources,
            visuals=request.visuals,
        )

        filename = f"Research_Report_{int(time.time())}.pdf"
        if request.analysis_id:
            await report_store.persist_report(
                session,
                analysis_id=request.analysis_id,
                pdf_bytes=pdf_bytes,
                filename=filename,
            )
            await session.commit()

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Access-Control-Expose-Headers": "Content-Disposition, Content-Type, Content-Length",
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")
