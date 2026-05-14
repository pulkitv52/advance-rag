from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.database import get_session
from src.models.document import Document
from src.models.eligibility import (
    EligibilityDecision,
    EligibilityManualInput,
    EligibilityRule,
    EligibilitySchemaSignal,
)
from src.services import eligibility

router = APIRouter(prefix="/api/eligibility", tags=["Eligibility Audit"])

DECISION_BUCKET_MAP = {
    "VALID_ENROLLMENT": "ELIGIBLE_ENROLLED",
    "INCLUSION_ERROR": "NOT_ELIGIBLE_ENROLLED",
    "EXCLUSION_ERROR": "ELIGIBLE_NOT_ENROLLED",
    "NOT_APPLICABLE": "NOT_ELIGIBLE_NOT_ENROLLED",
    "REVIEW_REQUIRED": "REVIEW_REQUIRED",
}

UNMAPPED_TO_MANUAL_FIELD_MAP = {
    "medical_allowance_opt_in": ["medical_allowance_opt_in"],
    "eligible_caste": ["caste"],
    "caste_eligibility": ["caste"],
    "gender_restriction": ["gender"],
    "gender_restriction_boys": ["gender", "male_sibling_scholarship_count"],
    "income_limit": ["annual_income"],
    "nationality": ["nationality"],
    "eligible_nationality": ["nationality"],
    "course_level": ["course_level"],
    "course_eligibility": ["course_level"],
    "institution_eligibility": ["institution_type"],
    "institution_code": ["institution_type"],
    "institution_standard": ["institution_type"],
    "single_scholarship_rule": ["no_other_scholarship"],
    "no_other_scholarship": ["no_other_scholarship"],
    "other_scholarship_exclusion": ["no_other_scholarship"],
    "single_other_scholarship_exclusion": ["no_other_scholarship"],
    "beneficiary_category": ["caste"],
    "institution_criteria": ["institution_type"],
    "online_course_eligibility": ["study_mode"],
}


RULE_KEY_TO_INPUT_FIELD_MAP = {
    "age_min": ["member_dob"],
    "age_max": ["member_dob"],
    "gender_in": ["gender"],
    "marital_status_in": ["marital_status"],
    "income_max": ["annual_income"],
    "requires_disability": ["disability_status"],
    "employment_status_in": ["employment_status"],
    "employment_status_not_in": ["employment_status"],
    "min_service_months": ["service_duration_months"],
    "ida_covered_required": ["ida_covered"],
    "exclude_if_receives_pension": ["receives_pension"],
    "exclude_if_retired_or_terminated": ["retired_or_terminated"],
    "exclude_if_reemployed_same_factory": ["reemployed_same_factory"],
}


def _is_empty_value(v: object) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def _suggest_manual_fields(evidence: dict) -> list[str]:
    suggested: list[str] = []
    source_values = evidence.get("source_values") or {}
    include_conditions = evidence.get("include_conditions") or {}
    exclude_conditions = evidence.get("exclude_conditions") or {}

    # 1) Essential fields required by mapped executable rule keys.
    required_inputs: list[str] = []
    for k in include_conditions.keys():
        required_inputs.extend(RULE_KEY_TO_INPUT_FIELD_MAP.get(str(k), []))
    for k in exclude_conditions.keys():
        required_inputs.extend(RULE_KEY_TO_INPUT_FIELD_MAP.get(str(k), []))
    required_inputs = list(dict.fromkeys(required_inputs))

    # Suggest only if missing/null in DB source values.
    for field_name in required_inputs:
        if _is_empty_value(source_values.get(field_name)):
            suggested.append(field_name)

    # 2) Missing fields already detected by evaluator.
    for f in (evidence.get("missing_required_fields") or []):
        if isinstance(f, str) and f.strip():
            suggested.append(f.strip())

    # 3) Unmapped criteria -> mapped manual fields (best-effort guidance).
    for key in (evidence.get("blocking_unmapped_criteria") or []):
        raw_key = str(key)
        # Normalize keys like "exclude_conditions.conflict_scheme_ids".
        normalized_key = raw_key.split(".")[-1]
        mapped = UNMAPPED_TO_MANUAL_FIELD_MAP.get(raw_key, []) or UNMAPPED_TO_MANUAL_FIELD_MAP.get(
            normalized_key, []
        )
        for field_name in mapped:
            if _is_empty_value(source_values.get(field_name)):
                suggested.append(field_name)

    # Keep stable order and uniqueness.
    return list(dict.fromkeys([x for x in suggested if x]))


class ExtractRuleRequest(BaseModel):
    scheme_id: Optional[str] = None
    rule_name: Optional[str] = None


class DecisionManualInputRequest(BaseModel):
    manual_inputs: dict
    scheme_only: bool = True


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
    scheme_only: bool = Query(default=True),
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
            scheme_only=scheme_only,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {exc}") from exc

    return summary


@router.post("/evaluate-all")
async def evaluate_all_rules(
    limit: int = Query(default=500, ge=1, le=50000),
    offset: int = Query(default=0, ge=0),
    scheme_only: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
):
    rules_result = await session.exec(
        select(EligibilityRule).where(EligibilityRule.status == "ACTIVE").order_by(desc(EligibilityRule.created_at))
    )
    rules = rules_result.all()
    if not rules:
        return {"total_rules": 0, "summaries": []}

    summaries = []
    for rule in rules:
        try:
            summary = await eligibility.run_rule_evaluation(
                session=session,
                rule=rule,
                limit=limit,
                offset=offset,
                scheme_only=scheme_only,
            )
            summaries.append(summary)
        except Exception as exc:
            summaries.append(
                {
                    "rule_id": rule.id,
                    "scheme_id": rule.scheme_id,
                    "error": str(exc),
                }
            )

    return {"total_rules": len(rules), "summaries": summaries}


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
                "decision_bucket": DECISION_BUCKET_MAP.get(row.decision, row.decision),
                "reason": row.reason,
                "decision_confidence": row.decision_confidence,
                "identity_match_confidence": row.identity_match_confidence,
                "evidence_json": row.evidence_json,
                "suggested_manual_fields": _suggest_manual_fields(evidence),
                "created_at": row.created_at,
            }
        )

    return {"total": len(serialized), "decisions": serialized}


@router.post("/decisions/{decision_id}/manual-inputs")
async def apply_manual_inputs_and_rejudge(
    decision_id: str,
    request: DecisionManualInputRequest,
    session: AsyncSession = Depends(get_session),
):
    decision_row = await session.get(EligibilityDecision, decision_id)
    if not decision_row:
        raise HTTPException(status_code=404, detail="Decision row not found")

    rule = await session.get(EligibilityRule, decision_row.rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found for this decision")

    citizen = await eligibility.fetch_single_citizen_evaluation_base(
        session=session,
        target_scheme_id=str(rule.scheme_id),
        citizen_uid=str(decision_row.citizen_uid),
        scheme_only=request.scheme_only,
    )
    if not citizen:
        citizen = {}

    prior_inputs: dict = {}
    merged_manual_inputs: dict = {}

    existing_manual = await session.exec(
        select(EligibilityManualInput).where(
            EligibilityManualInput.rule_id == rule.id,
            EligibilityManualInput.citizen_uid == str(decision_row.citizen_uid),
        )
    )
    manual_row = existing_manual.first()
    if manual_row is not None:
        prior_inputs = dict(manual_row.values_json or {})
    merged_manual_inputs = {**prior_inputs, **(request.manual_inputs or {})}

    merged = {**citizen, **merged_manual_inputs}
    outcome = eligibility.evaluate_citizen_against_rule(merged, rule)

    if manual_row is None:
        manual_row = EligibilityManualInput(
            rule_id=rule.id,
            citizen_uid=str(decision_row.citizen_uid),
            values_json=eligibility._to_json_safe(merged_manual_inputs),
        )
        session.add(manual_row)
    else:
        manual_row.values_json = eligibility._to_json_safe(merged_manual_inputs)

    evidence = decision_row.evidence_json or {}
    evidence["manual_inputs"] = eligibility._to_json_safe(merged_manual_inputs)
    evidence["checks"] = outcome.get("checks") or []
    evidence["checked_fields"] = outcome.get("checked_fields") or []
    evidence["missing_required_fields"] = outcome.get("missing_required_fields") or []
    evidence["blocking_unmapped_criteria"] = outcome.get("blocking_unmapped_criteria") or []
    evidence["source_values"] = eligibility._build_source_value_snapshot(merged)

    decision_row.decision = str(outcome.get("decision"))
    decision_row.reason = str(outcome.get("reason"))
    decision_row.decision_confidence = float(outcome.get("decision_confidence") or 0.0)
    decision_row.evidence_json = eligibility._to_json_safe(evidence)

    session.add(decision_row)
    await session.commit()
    await session.refresh(decision_row)

    return {
        "id": decision_row.id,
        "rule_id": decision_row.rule_id,
        "citizen_uid": decision_row.citizen_uid,
        "citizen_scheme_id": decision_row.citizen_scheme_id,
        "decision": decision_row.decision,
        "decision_bucket": DECISION_BUCKET_MAP.get(decision_row.decision, decision_row.decision),
        "reason": decision_row.reason,
        "decision_confidence": decision_row.decision_confidence,
        "identity_match_confidence": decision_row.identity_match_confidence,
        "evidence_json": decision_row.evidence_json,
        "created_at": decision_row.created_at,
    }


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
