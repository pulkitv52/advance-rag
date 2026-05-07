from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.database import get_session
from src.models.document import Document
from src.models.eligibility import EligibilityDecision, EligibilityRule, EligibilitySchemaSignal
from src.services import eligibility

router = APIRouter(prefix="/api/eligibility", tags=["Eligibility Audit"])


class ExtractRuleRequest(BaseModel):
    scheme_id: Optional[str] = None
    rule_name: Optional[str] = None


@router.post("/rules/extract/{document_id}")
async def extract_rule_from_uploaded_document(
    document_id: str,
    request: ExtractRuleRequest,
    session: AsyncSession = Depends(get_session),
):
    doc = await session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status != "success":
        raise HTTPException(
            status_code=400,
            detail="Document ingestion is not complete. Wait until status=success.",
        )

    try:
        rule = await eligibility.create_rule_from_document(
            session=session,
            document=doc,
            scheme_id=request.scheme_id,
            rule_name=request.rule_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Rule extraction failed: {exc}") from exc

    return {
        "rule_id": rule.id,
        "scheme_id": rule.scheme_id,
        "rule_name": rule.rule_name,
        "rule_version": rule.rule_version,
        "include_conditions": rule.include_conditions,
        "exclude_conditions": rule.exclude_conditions,
        "source_filename": rule.source_filename,
        "source_excerpt": rule.source_excerpt,
        "scheme_detection": (rule.extracted_metadata or {}).get("scheme_detection"),
    }


@router.get("/rules")
async def list_rules(
    scheme_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    query = select(EligibilityRule)
    if scheme_id:
        query = query.where(EligibilityRule.scheme_id == scheme_id)
    query = query.order_by(desc(EligibilityRule.created_at)).limit(limit)

    result = await session.exec(query)
    rows = result.all()
    return {"total": len(rows), "rules": rows}


@router.post("/evaluate/{rule_id}")
async def evaluate_rule(
    rule_id: str,
    limit: int = Query(default=500, ge=1, le=50000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    rule = await session.get(EligibilityRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    try:
        summary = await eligibility.run_rule_evaluation(
            session=session,
            rule=rule,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {exc}") from exc

    return summary


@router.get("/decisions")
async def list_decisions(
    rule_id: Optional[str] = None,
    decision: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    query = select(EligibilityDecision).order_by(desc(EligibilityDecision.created_at))
    if rule_id:
        query = query.where(EligibilityDecision.rule_id == rule_id)
    if decision:
        query = query.where(EligibilityDecision.decision == decision)

    query = query.limit(limit)
    result = await session.exec(query)
    rows = result.all()

    # Enrich with citizen_name (prefer saved evidence, fallback to srsadmin lookup).
    uids = [str(r.citizen_uid) for r in rows if getattr(r, "citizen_uid", None)]
    uid_to_name = {}
    if uids:
        try:
            # Detect name column in srsadmin table to avoid schema variance issues.
            col_stmt = text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'srsadmin'
                  AND table_name = 'swasthya_sathi_beneficiary'
                """
            )
            cols_result = await session.execute(col_stmt)
            available_cols = {str(r[0]).lower() for r in cols_result.fetchall()}

            name_col = None
            for candidate in ["fullname", "full_name", "name", "citizen_name"]:
                if candidate in available_cols:
                    name_col = candidate
                    break

            if name_col:
                # Per-UID lookup is intentionally used for portability with text() SQL binds.
                fetch_stmt = text(
                    f"""
                    SELECT uid, {name_col} AS citizen_name
                    FROM srsadmin.swasthya_sathi_beneficiary
                    WHERE uid = :uid
                    LIMIT 1
                    """
                )
                for uid in sorted(set(uids)):
                    row_result = await session.execute(fetch_stmt, {"uid": uid})
                    row = row_result.mappings().first()
                    if row and row.get("citizen_name"):
                        uid_to_name[uid] = row.get("citizen_name")
        except Exception as exc:
            # Keep API non-blocking; decisions still return even if name enrichment fails.
            # UI will show '-' for unresolved names.
            uid_to_name = {}
            from src.core.logger import logger

            logger.warning(f"Eligibility decisions name enrichment failed: {exc}")

    serialized = []
    for row in rows:
        evidence = row.evidence_json or {}
        citizen_name = evidence.get("citizen_name") or uid_to_name.get(str(row.citizen_uid))
        serialized.append(
            {
                "id": row.id,
                "rule_id": row.rule_id,
                "citizen_uid": row.citizen_uid,
                "citizen_name": citizen_name,
                "citizen_scheme_id": row.citizen_scheme_id,
                "decision": row.decision,
                "reason": row.reason,
                "decision_confidence": row.decision_confidence,
                "identity_match_confidence": row.identity_match_confidence,
                "evidence_json": row.evidence_json,
                "created_at": row.created_at,
            }
        )

    return {"total": len(serialized), "decisions": serialized}


@router.get("/schema-signals")
async def list_schema_signals(
    status: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=2000),
    session: AsyncSession = Depends(get_session),
):
    query = select(EligibilitySchemaSignal).order_by(
        desc(EligibilitySchemaSignal.occurrence_count),
        desc(EligibilitySchemaSignal.last_seen_at),
    )
    if status:
        query = query.where(EligibilitySchemaSignal.status == status.upper())
    query = query.limit(limit)

    result = await session.exec(query)
    rows = result.all()
    return {"total": len(rows), "signals": rows}
