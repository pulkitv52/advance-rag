"""Query / RAG inference router."""

import io
import re
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.database import get_session
from src.core.logger import logger
from src.models.analysis import Analysis
from src.models.document import QueryLog
from src.services import extractor, graph_db, nvidia, report_store, reporting, vector_db
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


def _is_usr_fraud_question(query: str) -> bool:
    q = query.lower()
    return any(k in q for k in USR_FRAUD_KEYWORDS)


def _extract_possible_person_name(query: str) -> str | None:
    """
    Best-effort name extraction for direct citizen checks.
    Handles prompts like:
      - Does Pramila Das come under fraud?
      - Is "Pramila Das" flagged?
      - Give details about Pramila Das
    """
    q = query.strip()

    quoted = re.search(r'["\']([^"\']{2,80})["\']', q)
    if quoted:
        candidate = quoted.group(1).strip()
        return candidate if candidate else None

    patterns = [
        r"does\s+([a-zA-Z.\- ]{2,80}?)\s+comes?\s+under",
        r"is\s+([a-zA-Z.\- ]{2,80}?)\s+(?:a|an)?\s*(?:fraud|flagged|suspicious)",
        r"details\s+about\s+([a-zA-Z.\- ]{2,80})",
        r"about\s+([a-zA-Z.\- ]{2,80})",
    ]
    trailing_noise = {
        "having",
        "have",
        "has",
        "fraud",
        "flagged",
        "suspicious",
        "case",
        "details",
        "info",
        "information",
        "record",
        "records",
    }

    def _clean_candidate(raw: str) -> str:
        candidate = re.sub(r"\s+", " ", raw).strip(" ?.,")
        parts = candidate.split()
        while parts and parts[-1].lower() in trailing_noise:
            parts.pop()
        return " ".join(parts).strip()

    stop_words = {"her", "him", "them", "it", "this", "that", "these", "those"}
    for p in patterns:
        m = re.search(p, q, flags=re.IGNORECASE)
        if m:
            candidate = _clean_candidate(m.group(1))
            if candidate and candidate.lower() not in stop_words:
                return candidate

    # Fallback: two-or-more title-case words.
    m = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", q)
    if m:
        return m.group(1).strip()
    return None


def _extract_scheme_id(query: str) -> str | None:
    """
    Extract scheme ID like S767, S123, M999 from query text.
    """
    m = re.search(r"\b([A-Z]\d{3,5})\b", query.upper())
    if m:
        return m.group(1)
    return None


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
    lines = [
        f"USR record found for UID {uid}:",
        f"Name: {row.get('name', 'Unknown')}",
        f"Location: {row.get('gp') or 'N/A'}, {row.get('block') or 'N/A'}, {row.get('district') or 'N/A'}",
        f"Risk: {row.get('risk_tier') or 'N/A'} | Vulnerability Score: {row.get('vulnerability_score') if row.get('vulnerability_score') is not None else 'N/A'}",
        f"Fraud Status: {'FLAGGED' if flags else 'No active fraud flag found'}",
    ]
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


@router.post("/", response_model=QueryResponse, summary="Ask a question across your documents")
async def query_documents(
    request: QueryRequest,
    session: AsyncSession = Depends(get_session),
):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    start_total = time.perf_counter()
    logger.info(f"--- [QUERY START] --- Query: '{request.query[:100]}...'")

    # Deterministic USR fraud-by-citizen resolution before generic RAG.
    if _is_usr_fraud_question(request.query):
        candidate_uid = _extract_possible_uid(request.query)
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

        candidate_name = _extract_possible_person_name(request.query)
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
                        f"[USR-DIRECT] Deterministic citizen lookup hit for '{candidate_name}'"
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
                # Deterministic miss path: do NOT fall back to generic doc-RAG for this intent.
                suggestions = await graph_db.get_usr_citizen_name_suggestions(candidate_name, limit=8)
                answer_lines = [
                    f"No exact USR citizen match found for '{candidate_name}' in the Knowledge Graph."
                ]
                if suggestions:
                    answer_lines.append("Closest name matches found:")
                    for i, row in enumerate(suggestions, start=1):
                        answer_lines.append(
                            f"{i}. {row.get('name', 'Unknown')} (UID: {row.get('uid', 'N/A')}) "
                            f"- {row.get('gp') or 'N/A'}, {row.get('block') or 'N/A'}, {row.get('district') or 'N/A'}"
                        )
                    answer_lines.append(
                        "Please confirm the correct UID/name variant to run a precise fraud assessment."
                    )
                else:
                    answer_lines.append(
                        "Please verify spelling or provide UID for deterministic fraud lookup."
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
                    f"[USR-DIRECT] No exact match for '{candidate_name}', returned deterministic suggestions."
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
            except Exception as e:
                logger.warning(f"USR direct citizen resolution failed: {e}")

    t0 = time.perf_counter()
    query_embedding = await nvidia.get_query_embedding(request.query)
    embed_time = time.perf_counter() - t0
    logger.info(f"[1/3] [NIM-EMBED] Generated query vector in {embed_time:.2f}s")

    t0 = time.perf_counter()
    candidate_top_k = request.top_k * 3
    initial_chunks = await vector_db.search_chunks(
        query_embedding=query_embedding,
        top_k=candidate_top_k,
        document_ids=request.document_ids,
    )
    retrieve_time = time.perf_counter() - t0
    logger.info(
        f"[2/3] [QDRANT] Retrieved {len(initial_chunks)} candidates in {retrieve_time:.2f}s"
    )

    t0 = time.perf_counter()
    chunks = await nvidia.rerank_chunks(
        query=request.query,
        chunks=initial_chunks,
        top_n=request.top_k,
    )
    rerank_time = time.perf_counter() - t0
    logger.info(f"[2.1/3] [NIM-RERANK] Refined to {len(chunks)} chunks in {rerank_time:.2f}s")

    graph_context = ""
    graph_enrichment_used = False

    # True Hybrid RAG: Inject Knowledge Graph database results directly into the context
    scheme_id = _extract_scheme_id(request.query)
    if scheme_id:
        try:
            scheme_citizens = await graph_db.get_usr_citizens_by_scheme(scheme_id, limit=50)
            if scheme_citizens:
                lines = [f"### Live Database Records (Citizens enrolled in Scheme {scheme_id}):"]
                for i, c in enumerate(scheme_citizens, start=1):
                    loc = f"{c.get('gp') or 'N/A'}, {c.get('block') or 'N/A'}, {c.get('district') or 'N/A'}"
                    lines.append(f"{i}. Name: {c.get('name')}, UID: {c.get('uid')}, Location: {loc}")
                
                graph_context += "\n" + "\n".join(lines) + "\n"
                graph_enrichment_used = True
                logger.info(f"[HYBRID RAG] Injected {len(scheme_citizens)} DB records for scheme {scheme_id}")
        except Exception as e:
            logger.warning(f"Scheme hybrid injection failed: {e}")

    try:
        entities = await extractor.extract_entities_from_query(request.query)
        if entities:
            facts = await graph_db.search_multi_hop_context(entities, request.document_ids)
            if facts:
                graph_context += (
                    "\n### Relational Intelligence (Deep Graph Analysis):\n" + "\n".join(facts)
                )
                graph_enrichment_used = True
                logger.info(
                    f"[2.5/3] [NEO4J] Uncovered {len(facts)} relational insights from knowledge graph"
                )
    except Exception as e:
        logger.warning(f"Graph enrichment failed: {e}")

    if not chunks:
        logger.warning("[2/3] [QDRANT] No relevant context found for query")
        return QueryResponse(
            query=request.query,
            answer="No relevant documents found. Please upload documents first.",
            sources=[],
            latency_ms=round((time.perf_counter() - start_total) * 1000, 2),
            confidence_score=0.0,
            citation_coverage=0.0,
            graph_enrichment_used=False,
            weak_claims=["No relevant evidence was found for this query."],
        )

    t0 = time.perf_counter()
    enriched_query = f"{request.query}\n\n{graph_context}" if graph_context else request.query
    answer = await nvidia.generate_rag_answer(
        query=enriched_query,
        context_chunks=chunks,
        stream=False,
        history=request.history,
    )
    generate_time = time.perf_counter() - t0
    logger.info(f"[3/3] [NIM-LLM] Generated grounded answer in {generate_time:.2f}s")

    total_latency_ms = round((time.perf_counter() - start_total) * 1000, 2)
    trust_metadata = compute_confidence(answer, chunks, graph_enrichment_used)

    log = QueryLog(
        query=request.query,
        answer=answer,
        chunks_used=len(chunks),
        document_id=request.document_ids[0] if request.document_ids else None,
        latency_ms=total_latency_ms,
    )
    session.add(log)
    await session.commit()

    logger.info(f"--- [QUERY FINISH] --- Total Latency: {total_latency_ms}ms")

    return QueryResponse(
        query=request.query,
        answer=answer,
        sources=[
            {
                "filename": c["filename"],
                "page": c.get("page"),
                "score": round(c["score"], 4),
                "snippet": c["text"][:300],
            }
            for c in chunks
        ],
        latency_ms=total_latency_ms,
        confidence_score=trust_metadata["confidence_score"],
        citation_coverage=trust_metadata["citation_coverage"],
        graph_enrichment_used=trust_metadata["graph_enrichment_used"],
        weak_claims=trust_metadata["weak_claims"],
    )


@router.post("/stream", summary="Stream a RAG answer via SSE")
async def stream_query(
    request: QueryRequest,
    session: AsyncSession = Depends(get_session),
):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    query_embedding = await nvidia.get_query_embedding(request.query)
    initial_chunks = await vector_db.search_chunks(
        query_embedding=query_embedding,
        top_k=request.top_k * 3,
        document_ids=request.document_ids,
    )
    chunks = await nvidia.rerank_chunks(
        query=request.query,
        chunks=initial_chunks,
        top_n=request.top_k,
    )

    if not chunks:

        async def no_context():
            yield "data: No relevant documents found.\n\n"

        return StreamingResponse(no_context(), media_type="text/event-stream")

    token_stream = await nvidia.generate_rag_answer(
        query=request.query,
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
