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
from src.services.eligibility_schema import (
    manual_input_type_for_field,
    normalize_policy_concept,
)

router = APIRouter(prefix="/api/eligibility", tags=["Eligibility Audit"])

DECISION_BUCKET_MAP = {
    "VALID_ENROLLMENT": "ELIGIBLE_ENROLLED",
    "INCLUSION_ERROR": "NOT_ELIGIBLE_ENROLLED",
    "EXCLUSION_ERROR": "ELIGIBLE_NOT_ENROLLED",
    "NOT_APPLICABLE": "NOT_ELIGIBLE_NOT_ENROLLED",
    "REVIEW_REQUIRED": "REVIEW_REQUIRED",
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
    canonical_rule = evidence.get("canonical_rule") or {}

    # 1) Essential fields required by mapped executable rule keys.
    required_inputs: list[str] = []
    if isinstance(canonical_rule, dict):
        for condition in canonical_rule.get("include_conditions", []) or []:
            field_name = str(condition.get("field") or "").strip()
            if field_name:
                required_inputs.append(field_name)
        for condition in canonical_rule.get("exclude_conditions", []) or []:
            field_name = str(condition.get("field") or "").strip()
            if field_name:
                required_inputs.append(field_name)
    else:
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
    for f in evidence.get("missing_required_fields") or []:
        if isinstance(f, str) and f.strip():
            suggested.append(f.strip())

    # 3) Unmapped criteria -> mapped manual fields (best-effort guidance).
    for condition in (
        canonical_rule.get("unmapped_conditions", []) if isinstance(canonical_rule, dict) else []
    ):
        field_name = str(condition.get("suggested_input_field") or "").strip()
        if field_name and _is_empty_value(source_values.get(field_name)):
            suggested.append(field_name)

    for key in evidence.get("blocking_unmapped_criteria") or []:
        raw_key = str(key)
        # Normalize keys like "exclude_conditions.conflict_scheme_ids".
        normalized_key = raw_key.split(".")[-1]
        normalized = normalize_policy_concept(normalized_key)
        if normalized.get("mapped") == "true":
            field_name = str(normalized.get("field") or "").strip()
            if field_name and _is_empty_value(source_values.get(field_name)):
                suggested.append(field_name)

    # Keep stable order and uniqueness.
    return list(dict.fromkeys([x for x in suggested if x]))


def _manual_input_requirements(evidence: dict) -> list[dict]:
    requirements_by_field: dict[str, dict] = {}
    canonical_rule = evidence.get("canonical_rule") or {}
    source_values = evidence.get("source_values") or {}
    missing_required_fields = {
        str(field).strip()
        for field in (evidence.get("missing_required_fields") or [])
        if str(field).strip()
    }

    for condition in (
        canonical_rule.get("unmapped_conditions", []) if isinstance(canonical_rule, dict) else []
    ):
        field_name = str(condition.get("suggested_input_field") or "").strip()
        if not field_name:
            continue
        raw_requirement = str(condition.get("requirement") or "").strip()
        normalized = normalize_policy_concept(raw_requirement or field_name)
        mapped = normalized.get("mapped") == "true"
        requirements_by_field[field_name] = {
            "field": field_name,
            "input_type": str(condition.get("input_type") or "text"),
            "reason": (
                f"Normalized from policy concept '{raw_requirement}' and requires manual input because it is not executable from the current dataset."
                if mapped and raw_requirement and field_name != raw_requirement
                else str(condition.get("reason_unmapped") or condition.get("requirement") or "")
            ),
            "requirement": condition.get("requirement"),
            "mapped_from_policy_concept": mapped,
        }

    for field_name in _suggest_manual_fields(evidence):
        if not _is_empty_value(source_values.get(field_name)):
            continue
        if field_name in missing_required_fields or _is_empty_value(source_values.get(field_name)):
            reason = (
                "Missing in the current citizen dataset row and required for executable evaluation."
            )
        else:
            reason = "Required to evaluate mapped eligibility criteria."
        if field_name in requirements_by_field:
            if "Missing in the current citizen dataset row" in reason:
                requirements_by_field[field_name]["reason"] = reason
            continue
        requirements_by_field[field_name] = {
            "field": field_name,
            "input_type": manual_input_type_for_field(field_name),
            "reason": reason,
        }

    return list(requirements_by_field.values())


def _merge_latest_rule_into_evidence(evidence: dict, rule: EligibilityRule | None) -> dict:
    merged = dict(evidence or {})
    if rule is not None:
        merged["canonical_rule"] = (rule.extracted_metadata or {}).get("canonical_rule")
        merged["include_conditions"] = rule.include_conditions
        merged["exclude_conditions"] = rule.exclude_conditions
    return merged


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
        "canonical_rule": (rule.extracted_metadata or {}).get("canonical_rule"),
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


@router.get("/rules/{rule_id}/manifest")
async def get_rule_manifest(
    rule_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Return a field-mapping manifest for a given eligibility rule."""
    from src.services.eligibility_schema import FIELD_TYPES, MANUAL_ONLY_FIELD_TYPES, manual_input_type_for_field

    rule = await session.get(EligibilityRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    canonical_rule = (rule.extracted_metadata or {}).get("canonical_rule") or {}

    # Derive DB column name: same as field name (direct mapping from srsadmin table).
    def _field_db_status(field_name: str) -> str:
        if field_name in FIELD_TYPES:
            return "MAPPED"
        if field_name in MANUAL_ONLY_FIELD_TYPES:
            return "MISSING"
        # Derived fields like "age" computed from member_dob
        if field_name == "age":
            return "MAPPED_DERIVED"
        return "MISSING"

    def _field_db_column(field_name: str) -> Optional[str]:
        derived = {"age": "member_dob (computed)"}
        if field_name in derived:
            return derived[field_name]
        if field_name in FIELD_TYPES:
            return field_name
        return None

    seen_fields: dict[str, dict] = {}

    # Collect from mapped include/exclude conditions
    for condition in (canonical_rule.get("include_conditions") or []):
        field_name = str(condition.get("field") or "").strip()
        if field_name and field_name not in seen_fields:
            seen_fields[field_name] = {
                "schemaField": field_name,
                "db_column": _field_db_column(field_name),
                "db_status": _field_db_status(field_name),
                "value_type": FIELD_TYPES.get(field_name) or MANUAL_ONLY_FIELD_TYPES.get(field_name, "text"),
                "note": f"Include condition: {condition.get('operator')} {condition.get('value')}",
            }

    for condition in (canonical_rule.get("exclude_conditions") or []):
        field_name = str(condition.get("field") or "").strip()
        if field_name and field_name not in seen_fields:
            seen_fields[field_name] = {
                "schemaField": field_name,
                "db_column": _field_db_column(field_name),
                "db_status": _field_db_status(field_name),
                "value_type": FIELD_TYPES.get(field_name) or MANUAL_ONLY_FIELD_TYPES.get(field_name, "text"),
                "note": f"Exclude condition: {condition.get('operator')} {condition.get('value')}",
            }

    # Collect from unmapped conditions
    for condition in (canonical_rule.get("unmapped_conditions") or []):
        field_name = str(condition.get("suggested_input_field") or "").strip()
        if field_name and field_name not in seen_fields:
            seen_fields[field_name] = {
                "schemaField": field_name,
                "db_column": _field_db_column(field_name),
                "db_status": _field_db_status(field_name),
                "value_type": condition.get("input_type") or manual_input_type_for_field(field_name),
                "note": condition.get("reason_unmapped") or "Unmapped policy criterion requiring manual input.",
            }

    # Build manual input requirements from unmapped conditions only (rule-level, no citizen context).
    manual_reqs = []
    for condition in (canonical_rule.get("unmapped_conditions") or []):
        field_name = str(condition.get("suggested_input_field") or "").strip()
        if not field_name:
            continue
        manual_reqs.append({
            "field": field_name,
            "input_type": condition.get("input_type") or manual_input_type_for_field(field_name),
            "required": True,
            "reason": condition.get("reason_unmapped") or "Required to evaluate unmapped policy criterion.",
        })

    return {
        "manifest_version": "1.0",
        "rule_id": rule.id,
        "scheme_id": rule.scheme_id,
        "rule_name": rule.rule_name,
        "rule_version": rule.rule_version,
        "source_document_id": rule.document_id,
        "source_filename": rule.source_filename,
        "field_mapping": list(seen_fields.values()),
        "manual_input_requirements": manual_reqs,
    }


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
        select(EligibilityRule)
        .where(EligibilityRule.status == "ACTIVE")
        .order_by(desc(EligibilityRule.created_at))
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

    # Batch-fetch rules (at most a handful of unique rule IDs).
    rule_ids = sorted({str(r.rule_id) for r in rows if getattr(r, "rule_id", None)})
    rule_by_id: dict[str, EligibilityRule] = {}
    for rid in rule_ids:
        rule = await session.get(EligibilityRule, rid)
        if rule is not None:
            rule_by_id[rid] = rule

    # Batch-fetch citizen names with a single IN query instead of per-UID queries.
    uids = list({str(r.citizen_uid) for r in rows if getattr(r, "citizen_uid", None)})
    uid_to_name: dict[str, str] = {}
    if uids:
        try:
            col_stmt = text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'srsadmin'
                  AND table_name = 'swasthya_sathi_beneficiary'
                """)
            cols_result = await session.execute(col_stmt)
            available_cols = {str(r[0]).lower() for r in cols_result.fetchall()}

            name_col = next(
                (c for c in ["fullname", "full_name", "name", "citizen_name"] if c in available_cols),
                None,
            )
            if name_col:
                # Single batch query using ANY for all UIDs at once.
                batch_stmt = text(f"""
                    SELECT DISTINCT ON (uid) uid, {name_col} AS citizen_name
                    FROM srsadmin.swasthya_sathi_beneficiary
                    WHERE uid = ANY(:uids)
                    ORDER BY uid
                    """)
                batch_result = await session.execute(batch_stmt, {"uids": uids})
                for name_row in batch_result.mappings().all():
                    if name_row.get("citizen_name"):
                        uid_to_name[str(name_row["uid"])] = str(name_row["citizen_name"])
        except Exception as exc:
            uid_to_name = {}
            from src.core.logger import logger
            logger.warning(f"Eligibility decisions name enrichment failed: {exc}")

    serialized = []
    for row in rows:
        evidence = _merge_latest_rule_into_evidence(
            row.evidence_json or {}, rule_by_id.get(str(row.rule_id))
        )
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
                "evidence_json": evidence,
                "suggested_manual_fields": _suggest_manual_fields(evidence),
                "manual_input_requirements": _manual_input_requirements(evidence),
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
    latest_evidence = _merge_latest_rule_into_evidence(decision_row.evidence_json or {}, rule)
    requirements = _manual_input_requirements(latest_evidence)
    requirement_by_field = {
        str(item.get("field")): item for item in requirements if item.get("field")
    }
    for field_name, value in (request.manual_inputs or {}).items():
        req = requirement_by_field.get(str(field_name))
        if not req:
            continue
        input_type = str(req.get("input_type") or "text")
        if input_type == "boolean" and not isinstance(value, bool):
            raise HTTPException(
                status_code=400, detail=f"Manual input {field_name} must be boolean."
            )
        if input_type == "number" and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            raise HTTPException(
                status_code=400, detail=f"Manual input {field_name} must be numeric."
            )
        if input_type in {"text", "select"} and not isinstance(value, str):
            raise HTTPException(status_code=400, detail=f"Manual input {field_name} must be text.")

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

    evidence = latest_evidence
    evidence["manual_inputs"] = eligibility._to_json_safe(merged_manual_inputs)
    evidence["checks"] = outcome.get("checks") or []
    evidence["checked_fields"] = outcome.get("checked_fields") or []
    evidence["missing_required_fields"] = outcome.get("missing_required_fields") or []
    evidence["blocking_unmapped_criteria"] = outcome.get("blocking_unmapped_criteria") or []
    evidence["source_values"] = eligibility._build_source_value_snapshot(merged)
    evidence["canonical_rule"] = (rule.extracted_metadata or {}).get("canonical_rule")

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
        "suggested_manual_fields": _suggest_manual_fields(
            _merge_latest_rule_into_evidence(decision_row.evidence_json or {}, rule)
        ),
        "manual_input_requirements": _manual_input_requirements(
            _merge_latest_rule_into_evidence(decision_row.evidence_json or {}, rule)
        ),
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
