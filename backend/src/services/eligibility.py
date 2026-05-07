import json
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.logger import logger
from src.models.document import Document
from src.models.eligibility import EligibilityDecision, EligibilityRule, EligibilitySchemaSignal
from src.services import nvidia, storage


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _parse_amount(raw: str) -> Optional[float]:
    cleaned = re.sub(r"[^0-9.]", "", raw)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_between(pattern: str, text: str) -> Optional[tuple[int, int]]:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1)), int(match.group(2))
    except ValueError:
        return None


def detect_scheme_id_from_filename(filename: str) -> Dict[str, Any]:
    """Extract scheme IDs from filename patterns like `doc_GE_S767_0.pdf`."""
    upper = _clean_text(filename).upper()
    # Supports: S767, S051, SS_001, SS_1001 etc.
    hits = re.findall(r"(?<![A-Z0-9])(SS_\d{2,6}|S\d{2,6})(?![A-Z0-9])", upper)
    unique = list(dict.fromkeys(hits))
    selected = unique[0] if unique else None
    return {
        "scheme_id": selected,
        "confidence": "HIGH" if selected else "LOW",
        "candidates": unique,
        "source": "filename_pattern",
    }


async def detect_scheme_id_from_text(
    session: AsyncSession,
    raw_text: str,
) -> Dict[str, Any]:
    """Best-effort scheme detection using in-document codes and known IDs from dump."""
    cleaned_text = _clean_text(raw_text)
    upper = cleaned_text.upper()

    score_map: Dict[str, int] = {}

    # 1) Direct pattern matches from document text (strong signal).
    for hit in re.findall(r"\b(?:S\d{2,6}|SS_\d{2,6})\b", upper):
        score_map[hit] = score_map.get(hit, 0) + 3

    # 2) Boost using known scheme IDs present in srsadmin dump.
    try:
        known_rows = await session.exec(
            text(
                """
                SELECT DISTINCT scheme_id
                FROM srsadmin.swasthya_sathi_beneficiary
                WHERE scheme_id IS NOT NULL AND BTRIM(scheme_id) <> ''
                LIMIT 2000
                """
            )
        )
        known_ids = [str(x).strip().upper() for x in known_rows.all() if x]
        for sid in known_ids:
            if sid and sid in upper:
                score_map[sid] = score_map.get(sid, 0) + 1
    except Exception as exc:
        logger.warning(f"Scheme detection: could not read known scheme IDs from dump: {exc}")

    ranked = sorted(score_map.items(), key=lambda x: x[1], reverse=True)
    candidates = [r[0] for r in ranked[:10]]
    selected = ranked[0][0] if ranked else None

    confidence = "LOW"
    if ranked:
        if len(ranked) == 1 or ranked[0][1] >= (ranked[1][1] + 2):
            confidence = "HIGH"
        else:
            confidence = "MEDIUM"

    return {
        "scheme_id": selected,
        "confidence": confidence,
        "candidates": candidates,
        "scores": {k: v for k, v in ranked[:10]},
    }


def extract_eligibility_metadata(raw_text: str, scheme_id: Optional[str] = None) -> Dict[str, Any]:
    """Heuristic parser to convert unstructured policy text into structured eligibility metadata."""
    text = _clean_text(raw_text)
    lower = text.lower()

    include_conditions: Dict[str, Any] = {}
    exclude_conditions: Dict[str, Any] = {}

    age_between = _extract_between(r"age\s*(?:between|from)\s*(\d{1,3})\s*(?:to|-|and)\s*(\d{1,3})", text)
    if age_between:
        include_conditions["age_min"] = age_between[0]
        include_conditions["age_max"] = age_between[1]
    else:
        min_match = re.search(
            r"(?:minimum\s+age|age\s*(?:at\s*least|>=|above|more\s+than))\s*(\d{1,3})",
            text,
            flags=re.IGNORECASE,
        )
        max_match = re.search(
            r"(?:maximum\s+age|age\s*(?:at\s*most|<=|below|less\s+than))\s*(\d{1,3})",
            text,
            flags=re.IGNORECASE,
        )
        if min_match:
            include_conditions["age_min"] = int(min_match.group(1))
        if max_match:
            include_conditions["age_max"] = int(max_match.group(1))

    gender_values: List[str] = []
    for gender in ["female", "male", "transgender"]:
        if re.search(rf"\b{gender}\b", lower):
            gender_values.append(gender.upper())
    if gender_values:
        include_conditions["gender_in"] = sorted(set(gender_values))

    marital_map = {
        "widow": "WIDOW",
        "widows": "WIDOW",
        "widowed": "WIDOW",
        "unmarried": "UNMARRIED",
        "married": "MARRIED",
        "divorced": "DIVORCED",
    }
    for token, normalized in marital_map.items():
        if re.search(rf"\b{token}\b", lower):
            include_conditions.setdefault("marital_status_in", [])
            if normalized not in include_conditions["marital_status_in"]:
                include_conditions["marital_status_in"].append(normalized)

    income_match = re.search(
        r"(?:annual\s+income|income).{0,30}(?:below|less\s+than|up\s*to|upto|not\s*exceed(?:ing)?)\s*(?:rs\.?|inr)?\s*([0-9,]+)",
        text,
        flags=re.IGNORECASE,
    )
    if income_match:
        amount = _parse_amount(income_match.group(1))
        if amount is not None:
            include_conditions["income_max"] = amount

    if re.search(r"\b(disability|disabled|pwd|person with disability)\b", lower):
        include_conditions["requires_disability"] = True

    target_scheme = (scheme_id or "").upper()
    conflict_scheme_codes = re.findall(r"\b(?:S\d{2,6}|SS_\d{2,6})\b", text.upper())
    if conflict_scheme_codes:
        # Keep target scheme out if it appears in source text.
        exclude_conditions["conflict_scheme_ids"] = [
            code for code in sorted(set(conflict_scheme_codes)) if code != target_scheme
        ]

    return {
        "scheme_id": target_scheme or None,
        "include_conditions": include_conditions,
        "exclude_conditions": exclude_conditions,
        "extracted_fields": sorted(
            set(list(include_conditions.keys()) + list(exclude_conditions.keys()))
        ),
        "parser": "regex_v1",
    }


def _extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Fallback: find first top-level JSON object.
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def _prepare_llm_text_window(raw_text: str, max_chars: int = 18000) -> str:
    cleaned = _clean_text(raw_text)
    if len(cleaned) <= max_chars:
        return cleaned
    part = max_chars // 3
    head = cleaned[:part]
    mid_start = max(0, (len(cleaned) // 2) - (part // 2))
    mid = cleaned[mid_start:mid_start + part]
    tail = cleaned[-part:]
    return f"[HEAD]\n{head}\n\n[MIDDLE]\n{mid}\n\n[TAIL]\n{tail}"


async def learn_schema_from_metadata(
    session: AsyncSession,
    metadata: Dict[str, Any],
    auto_promote_threshold: int = 3,
) -> Dict[str, Any]:
    """
    Self-learning backend loop:
    - Track unmapped criteria fields from extracted metadata.
    - Increment frequency counters.
    - Auto-promote frequent fields into ACTIVE schema vocabulary (still non-executable by default).
    """
    unmapped = [str(x).strip() for x in (metadata.get("unmapped_criteria") or []) if x]
    evidence_rows = metadata.get("evidence") or []

    if not unmapped:
        return {
            "observed_unmapped_fields": [],
            "promoted_fields": [],
            "auto_promote_threshold": auto_promote_threshold,
        }

    evidence_lookup = {}
    for item in evidence_rows:
        key = str(item.get("field") or "").strip()
        quote = str(item.get("quote") or "").strip()
        if key and quote and key not in evidence_lookup:
            evidence_lookup[key] = quote

    promoted_fields: List[str] = []
    now = datetime.utcnow()

    for field_key in sorted(set(unmapped)):
        existing = await session.exec(
            select(EligibilitySchemaSignal).where(EligibilitySchemaSignal.field_key == field_key)
        )
        row = existing.first()

        if row is None:
            row = EligibilitySchemaSignal(
                field_key=field_key,
                status="CANDIDATE",
                executable=False,
                occurrence_count=1,
                first_seen_at=now,
                last_seen_at=now,
                sample_quotes={
                    "latest_quote": evidence_lookup.get(field_key),
                    "example_source": "policy_extraction",
                },
            )
            session.add(row)
        else:
            row.occurrence_count += 1
            row.last_seen_at = now
            if evidence_lookup.get(field_key):
                row.sample_quotes = {
                    **(row.sample_quotes or {}),
                    "latest_quote": evidence_lookup[field_key],
                    "example_source": "policy_extraction",
                }

        if row.status == "CANDIDATE" and row.occurrence_count >= auto_promote_threshold:
            row.status = "ACTIVE"
            promoted_fields.append(field_key)

    await session.commit()

    return {
        "observed_unmapped_fields": sorted(set(unmapped)),
        "promoted_fields": promoted_fields,
        "auto_promote_threshold": auto_promote_threshold,
    }


async def extract_eligibility_metadata_llm(
    raw_text: str,
    scheme_hint: Optional[str],
    detected_scheme: Optional[str],
) -> Dict[str, Any]:
    """
    Stage-1 intent analysis + stage-2 structured eligibility extraction using LLM.
    Returns strict JSON-compatible dict (or empty dict if parsing fails).
    """
    text_window = _prepare_llm_text_window(raw_text)
    schema_hint = (scheme_hint or detected_scheme or "").upper() or None

    prompt = (
        "You are an expert policy analyst. Analyze the given policy/gazette document text and extract eligibility criteria.\n"
        "Return ONLY a valid JSON object with this schema:\n"
        "{\n"
        '  "document_intent": {"summary": "string", "document_type": "scheme_guideline|gazette|circular|unknown", "is_eligibility_document": true|false},\n'
        '  "scheme_detection": {"scheme_id": "string|null", "scheme_name": "string|null", "confidence": "HIGH|MEDIUM|LOW"},\n'
        '  "include_conditions": {\n'
        '    "age_min": number|null,\n'
        '    "age_max": number|null,\n'
        '    "gender_in": ["MALE|FEMALE|TRANSGENDER"],\n'
        '    "marital_status_in": ["MARRIED|UNMARRIED|WIDOW|DIVORCED"],\n'
        '    "income_max": number|null,\n'
        '    "requires_disability": true|false,\n'
        '    "employment_status_in": ["ACTIVE|EMPLOYED|UNEMPLOYED|CLOSED|TERMINATED|RETIRED"],\n'
        '    "min_service_months": number|null,\n'
        '    "ida_covered_required": true|false\n'
        "  },\n"
        '  "exclude_conditions": {\n'
        '    "conflict_scheme_ids": ["string"],\n'
        '    "employment_status_not_in": ["ACTIVE|EMPLOYED|UNEMPLOYED|CLOSED|TERMINATED|RETIRED"],\n'
        '    "exclude_if_receives_pension": true|false,\n'
        '    "exclude_if_retired_or_terminated": true|false,\n'
        '    "exclude_if_reemployed_same_factory": true|false\n'
        "  },\n"
        '  "evidence": [{"field":"string","quote":"string"}],\n'
        '  "extraction_confidence": "HIGH|MEDIUM|LOW",\n'
        '  "no_criteria_reason": "string|null"\n'
        "}\n"
        "Rules:\n"
        "- Use null/empty arrays when unknown; do not invent facts.\n"
        "- If document does not contain explicit eligibility criteria, set include_conditions/exclude_conditions empty and explain no_criteria_reason.\n"
        f"- Preferred scheme hint (if any): {schema_hint}\n\n"
        "Document text:\n"
        f"{text_window}"
    )

    response = await nvidia.generate_rag_answer(
        query="Extract policy intent and eligibility criteria JSON.",
        context_chunks=[{"text": prompt, "filename": "policy_ingest_context"}],
        system_prompt=(
            "Return only compact valid JSON. No markdown, no explanations, no prose outside JSON."
        ),
    )

    parsed = _extract_json_object(response)
    if not parsed:
        return {}

    include = parsed.get("include_conditions") or {}
    exclude = parsed.get("exclude_conditions") or {}

    # Normalize condition keys to expected structure.
    normalized_include = {}
    if include.get("age_min") is not None:
        normalized_include["age_min"] = include.get("age_min")
    if include.get("age_max") is not None:
        normalized_include["age_max"] = include.get("age_max")
    if include.get("gender_in"):
        normalized_include["gender_in"] = [str(x).upper() for x in include.get("gender_in", [])]
    if include.get("marital_status_in"):
        normalized_include["marital_status_in"] = [
            str(x).upper() for x in include.get("marital_status_in", [])
        ]
    if include.get("income_max") is not None:
        normalized_include["income_max"] = include.get("income_max")
    if include.get("requires_disability") is True:
        normalized_include["requires_disability"] = True
    if include.get("employment_status_in"):
        normalized_include["employment_status_in"] = [
            str(x).upper() for x in include.get("employment_status_in", [])
        ]
    if include.get("min_service_months") is not None:
        normalized_include["min_service_months"] = include.get("min_service_months")
    if include.get("ida_covered_required") is True:
        normalized_include["ida_covered_required"] = True

    normalized_exclude = {}
    if exclude.get("conflict_scheme_ids"):
        normalized_exclude["conflict_scheme_ids"] = [
            str(x).upper() for x in exclude.get("conflict_scheme_ids", [])
        ]
    if exclude.get("employment_status_not_in"):
        normalized_exclude["employment_status_not_in"] = [
            str(x).upper() for x in exclude.get("employment_status_not_in", [])
        ]
    if exclude.get("exclude_if_receives_pension") is True:
        normalized_exclude["exclude_if_receives_pension"] = True
    if exclude.get("exclude_if_retired_or_terminated") is True:
        normalized_exclude["exclude_if_retired_or_terminated"] = True
    if exclude.get("exclude_if_reemployed_same_factory") is True:
        normalized_exclude["exclude_if_reemployed_same_factory"] = True

    supported_fields = {
        "age_min",
        "age_max",
        "gender_in",
        "marital_status_in",
        "income_max",
        "requires_disability",
        "employment_status_in",
        "min_service_months",
        "ida_covered_required",
        "conflict_scheme_ids",
        "employment_status_not_in",
        "exclude_if_receives_pension",
        "exclude_if_retired_or_terminated",
        "exclude_if_reemployed_same_factory",
    }
    evidence = parsed.get("evidence", []) or []
    detected_fields = [str(item.get("field", "")).strip() for item in evidence if item.get("field")]
    unmapped_criteria = sorted({f for f in detected_fields if f and f not in supported_fields})

    scheme_from_llm = (
        ((parsed.get("scheme_detection") or {}).get("scheme_id"))
        or schema_hint
        or None
    )

    return {
        "scheme_id": str(scheme_from_llm).upper() if scheme_from_llm else None,
        "include_conditions": normalized_include,
        "exclude_conditions": normalized_exclude,
        "extracted_fields": sorted(
            set(list(normalized_include.keys()) + list(normalized_exclude.keys()))
        ),
        "parser": "llm_v2",
        "document_intent": parsed.get("document_intent"),
        "scheme_detection_llm": parsed.get("scheme_detection"),
        "evidence": evidence,
        "unmapped_criteria": unmapped_criteria,
        "extraction_confidence": parsed.get("extraction_confidence"),
        "no_criteria_reason": parsed.get("no_criteria_reason"),
    }


def _parse_dob(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    raw = str(value).strip()
    if not raw:
        return None

    formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _calculate_age(dob: Optional[date], as_of: Optional[date] = None) -> Optional[int]:
    if dob is None:
        return None
    today = as_of or date.today()
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return years


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().upper()


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(str(value)))
    except Exception:
        return None


def _to_boolish(value: Any) -> Optional[bool]:
    if value is None:
        return None
    normalized = _normalize_text(value)
    if normalized in {"YES", "Y", "TRUE", "1"}:
        return True
    if normalized in {"NO", "N", "FALSE", "0"}:
        return False
    return None


def _format_check_for_reason(check: Dict[str, Any]) -> str:
    field = str(check.get("field", "unknown"))
    operator = str(check.get("operator", ""))
    expected = check.get("expected")
    actual = check.get("actual")
    return f"{field} {operator} {expected} (actual={actual})"


def evaluate_citizen_against_rule(citizen: Dict[str, Any], rule: EligibilityRule) -> Dict[str, Any]:
    include = rule.include_conditions or {}
    exclude = rule.exclude_conditions or {}
    extracted_meta = rule.extracted_metadata or {}

    checks: List[Dict[str, Any]] = []

    dob = _parse_dob(citizen.get("member_dob"))
    age = _calculate_age(dob)
    gender = _normalize_text(citizen.get("gender"))
    marital_status = _normalize_text(citizen.get("marital_status"))
    current_scheme = _normalize_text(citizen.get("scheme_id"))

    income_raw = citizen.get("annual_income")
    income = _parse_amount(str(income_raw)) if income_raw is not None else None
    employment_status = _normalize_text(citizen.get("employment_status"))
    service_months = _to_int(citizen.get("service_duration_months"))
    ida_covered = _to_boolish(citizen.get("ida_covered"))
    receives_pension = _to_boolish(citizen.get("receives_pension"))
    retired_or_terminated = _to_boolish(citizen.get("retired_or_terminated"))
    reemployed_same_factory = _to_boolish(citizen.get("reemployed_same_factory"))

    is_eligible = True
    missing_required_fields: List[str] = []

    if "age_min" in include:
        passed = age is not None and age >= int(include["age_min"])
        checks.append({"field": "age", "operator": ">=", "expected": include["age_min"], "actual": age, "passed": passed})
        is_eligible = is_eligible and passed

    if "age_max" in include:
        passed = age is not None and age <= int(include["age_max"])
        checks.append({"field": "age", "operator": "<=", "expected": include["age_max"], "actual": age, "passed": passed})
        is_eligible = is_eligible and passed

    if "gender_in" in include:
        expected = [str(x).upper() for x in include["gender_in"]]
        passed = gender in expected
        checks.append({"field": "gender", "operator": "in", "expected": expected, "actual": gender, "passed": passed})
        is_eligible = is_eligible and passed

    if "marital_status_in" in include:
        expected = [str(x).upper() for x in include["marital_status_in"]]
        passed = marital_status in expected
        checks.append({"field": "marital_status", "operator": "in", "expected": expected, "actual": marital_status, "passed": passed})
        is_eligible = is_eligible and passed

    if "income_max" in include:
        passed = income is not None and income <= float(include["income_max"])
        checks.append({"field": "annual_income", "operator": "<=", "expected": include["income_max"], "actual": income, "passed": passed})
        is_eligible = is_eligible and passed

    if "employment_status_in" in include:
        expected = [str(x).upper() for x in include["employment_status_in"]]
        if not employment_status:
            missing_required_fields.append("employment_status")
        else:
            passed = employment_status in expected
            checks.append({"field": "employment_status", "operator": "in", "expected": expected, "actual": employment_status, "passed": passed})
            is_eligible = is_eligible and passed

    if "min_service_months" in include:
        expected_min = _to_int(include["min_service_months"])
        if service_months is None or expected_min is None:
            missing_required_fields.append("service_duration_months")
        else:
            passed = service_months >= expected_min
            checks.append({"field": "service_duration_months", "operator": ">=", "expected": expected_min, "actual": service_months, "passed": passed})
            is_eligible = is_eligible and passed

    if include.get("ida_covered_required"):
        if ida_covered is None:
            missing_required_fields.append("ida_covered")
        else:
            passed = ida_covered is True
            checks.append({"field": "ida_covered", "operator": "required_true", "expected": True, "actual": ida_covered, "passed": passed})
            is_eligible = is_eligible and passed

    if include.get("requires_disability"):
        disability_flag = _normalize_text(citizen.get("disability_status") or citizen.get("is_disabled"))
        passed = disability_flag in {"YES", "Y", "TRUE", "1", "DISABLED"}
        checks.append({"field": "disability_status", "operator": "required", "expected": True, "actual": disability_flag, "passed": passed})
        is_eligible = is_eligible and passed

    conflict_ids = [str(x).upper() for x in exclude.get("conflict_scheme_ids", [])]
    if conflict_ids:
        passed = current_scheme not in conflict_ids
        checks.append({"field": "scheme_id", "operator": "not_in", "expected": conflict_ids, "actual": current_scheme, "passed": passed})
        is_eligible = is_eligible and passed

    status_not_in = [str(x).upper() for x in exclude.get("employment_status_not_in", [])]
    if status_not_in:
        if not employment_status:
            missing_required_fields.append("employment_status")
        else:
            passed = employment_status not in status_not_in
            checks.append({"field": "employment_status", "operator": "not_in", "expected": status_not_in, "actual": employment_status, "passed": passed})
            is_eligible = is_eligible and passed

    if exclude.get("exclude_if_receives_pension"):
        if receives_pension is None:
            missing_required_fields.append("receives_pension")
        else:
            passed = receives_pension is False
            checks.append({"field": "receives_pension", "operator": "must_be_false", "expected": False, "actual": receives_pension, "passed": passed})
            is_eligible = is_eligible and passed

    if exclude.get("exclude_if_retired_or_terminated"):
        if retired_or_terminated is None:
            missing_required_fields.append("retired_or_terminated")
        else:
            passed = retired_or_terminated is False
            checks.append({"field": "retired_or_terminated", "operator": "must_be_false", "expected": False, "actual": retired_or_terminated, "passed": passed})
            is_eligible = is_eligible and passed

    if exclude.get("exclude_if_reemployed_same_factory"):
        if reemployed_same_factory is None:
            missing_required_fields.append("reemployed_same_factory")
        else:
            passed = reemployed_same_factory is False
            checks.append({"field": "reemployed_same_factory", "operator": "must_be_false", "expected": False, "actual": reemployed_same_factory, "passed": passed})
            is_eligible = is_eligible and passed

    target_scheme = _normalize_text(rule.scheme_id)
    is_enrolled_in_target = current_scheme == target_scheme

    unmapped_criteria = extracted_meta.get("unmapped_criteria") or []
    # Treat umbrella terms as non-blocking when we still have executable checks.
    non_blocking_unmapped = {"eligibility_scope", "exclusion_list"}
    blocking_unmapped = [u for u in unmapped_criteria if str(u) not in non_blocking_unmapped]

    if unmapped_criteria:
        if blocking_unmapped:
            return {
                "decision": "REVIEW_REQUIRED",
                "reason": (
                    "Document contains eligibility criteria not yet mapped to structured fields: "
                    + ", ".join(blocking_unmapped)
                    + ". Manual or enriched mapping required before final decision."
                ),
                "decision_confidence": 0.0,
                "is_eligible": False,
                "is_enrolled_in_target": is_enrolled_in_target,
                "checks": [],
            }

    has_criteria = bool(include) or bool(exclude)
    if not has_criteria:
        return {
            "decision": "REVIEW_REQUIRED",
            "reason": "No usable eligibility criteria were extracted from the policy document. Manual rule validation is required.",
            "decision_confidence": 0.0,
            "is_eligible": False,
            "is_enrolled_in_target": is_enrolled_in_target,
            "checks": [],
        }

    if missing_required_fields:
        missing_unique = sorted(set(missing_required_fields))
        return {
            "decision": "REVIEW_REQUIRED",
            "reason": (
                "Required citizen data is missing for executable criteria fields: "
                + ", ".join(missing_unique)
                + ". Final inclusion/exclusion decision requires these fields."
            ),
            "decision_confidence": 0.0,
            "is_eligible": False,
            "is_enrolled_in_target": is_enrolled_in_target,
            "checks": checks,
        }

    passed_checks = [c for c in checks if c.get("passed")]
    failed_checks = [c for c in checks if not c.get("passed")]

    if is_eligible and not is_enrolled_in_target:
        decision = "EXCLUSION_ERROR"
        reason = (
            f"Citizen is eligible by extracted criteria but not enrolled in target scheme {target_scheme}. "
            + (
                "Passed checks: " + "; ".join(_format_check_for_reason(c) for c in passed_checks) + "."
                if passed_checks
                else "No executable checks were available."
            )
        )
    elif not is_eligible and is_enrolled_in_target:
        decision = "INCLUSION_ERROR"
        reason = (
            f"Citizen is enrolled in target scheme {target_scheme} but failed eligibility checks. "
            + (
                "Failed checks: " + "; ".join(_format_check_for_reason(c) for c in failed_checks) + "."
                if failed_checks
                else "No failing check details available."
            )
        )
    elif is_eligible and is_enrolled_in_target:
        decision = "VALID_ENROLLMENT"
        reason = f"Citizen is eligible and correctly enrolled in target scheme {target_scheme}."
    else:
        decision = "NOT_APPLICABLE"
        reason = (
            f"Citizen is not eligible and not enrolled in target scheme {target_scheme}. "
            + (
                "Failed checks: " + "; ".join(_format_check_for_reason(c) for c in failed_checks) + "."
                if failed_checks
                else "No failing check details available."
            )
        )

    matched_checks = sum(1 for c in checks if c["passed"])
    total_checks = len(checks)
    base = 0.75
    confidence = base if total_checks == 0 else min(0.99, base + (matched_checks / total_checks) * 0.2)

    return {
        "decision": decision,
        "reason": reason,
        "decision_confidence": round(confidence, 4),
        "is_eligible": is_eligible,
        "is_enrolled_in_target": is_enrolled_in_target,
        "checks": checks,
    }


async def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    direct_text = ""
    try:
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages: List[str] = []
        for page in doc:
            pages.append(page.get_text("text"))
        doc.close()
        direct_text = _clean_text("\n".join(pages))
    except Exception as exc:
        logger.warning(f"PyMuPDF extraction failed, falling back to NIM parser: {exc}")

    # If direct text extraction is empty/too short (common for scanned PDFs), use OCR/visual parse.
    if len(direct_text) >= 120:
        return direct_text

    from src.services import nvidia

    elements = await nvidia.parse_document_bytes(pdf_bytes, "policy.pdf")
    text_parts = [str(el.get("text", "")) for el in elements if el.get("text")]
    ocr_text = _clean_text("\n".join(text_parts))
    if ocr_text:
        return ocr_text

    return direct_text


async def create_rule_from_document(
    session: AsyncSession,
    document: Document,
    scheme_id: Optional[str] = None,
    rule_name: Optional[str] = None,
) -> EligibilityRule:
    if not document.object_key:
        raise ValueError("Document is not yet ingested. object_key is empty.")

    content = storage.download_file_bytes(document.object_key)
    if document.filename.lower().endswith(".pdf"):
        raw_text = await _extract_text_from_pdf_bytes(content)
    else:
        from src.services import nvidia

        elements = await nvidia.parse_document_bytes(content, document.filename)
        raw_text = _clean_text("\n".join([str(el.get("text", "")) for el in elements]))

    if not raw_text:
        raise ValueError("Could not extract readable text from uploaded document.")

    filename_detection = detect_scheme_id_from_filename(document.filename)
    detection = await detect_scheme_id_from_text(session=session, raw_text=raw_text)
    llm_metadata = await extract_eligibility_metadata_llm(
        raw_text=raw_text,
        scheme_hint=(scheme_id or filename_detection.get("scheme_id")),
        detected_scheme=detection.get("scheme_id"),
    )
    resolved_scheme_id = (
        scheme_id
        or filename_detection.get("scheme_id")
        or llm_metadata.get("scheme_id")
        or detection.get("scheme_id")
        or ""
    ).upper()
    if not resolved_scheme_id:
        raise ValueError(
            "Could not detect scheme ID from document text. "
            "Please provide a scheme ID override for this document."
        )

    regex_metadata = extract_eligibility_metadata(raw_text, scheme_id=resolved_scheme_id)

    # LLM is the source-of-truth for executable eligibility conditions.
    # Regex output is retained only as a diagnostic backup for debugging.
    include_conditions = llm_metadata.get("include_conditions") or {}
    exclude_conditions = llm_metadata.get("exclude_conditions") or {}

    metadata = {
        **llm_metadata,
        "scheme_id": resolved_scheme_id,
        "include_conditions": include_conditions,
        "exclude_conditions": exclude_conditions,
        "extracted_fields": sorted(
            set(list(include_conditions.keys()) + list(exclude_conditions.keys()))
        ),
        "regex_backup": regex_metadata,
        "decision_source": "llm_v2",
        "regex_fallback_applied": False,
    }
    metadata["scheme_detection"] = detection
    metadata["scheme_detection_filename"] = filename_detection
    metadata["scheme_id_overridden"] = bool(scheme_id)
    metadata["scheme_id_resolved"] = resolved_scheme_id

    learning_summary = await learn_schema_from_metadata(session=session, metadata=metadata)
    metadata["schema_learning"] = learning_summary
    excerpt = raw_text[:1200]

    existing = await session.exec(
        select(EligibilityRule).where(
            EligibilityRule.document_id == document.id,
            EligibilityRule.scheme_id == resolved_scheme_id,
            EligibilityRule.status == "ACTIVE",
        )
    )
    prior = existing.first()
    next_version = (prior.rule_version + 1) if prior else 1

    rule = EligibilityRule(
        document_id=document.id,
        scheme_id=resolved_scheme_id,
        rule_name=rule_name or f"Eligibility Rule - {resolved_scheme_id}",
        rule_version=next_version,
        status="ACTIVE",
        include_conditions=metadata.get("include_conditions", {}),
        exclude_conditions=metadata.get("exclude_conditions", {}),
        extracted_metadata=metadata,
        source_filename=document.filename,
        source_excerpt=excerpt,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)

    logger.info(
        f"Eligibility rule extracted from {document.filename}: rule_id={rule.id}, scheme={resolved_scheme_id}, version={rule.rule_version}"
    )
    return rule


async def _get_beneficiary_columns(session: AsyncSession, schema: str, table: str) -> List[str]:
    query = text(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :table
        """
    )
    result = await session.execute(query, {"schema": schema, "table": table})
    rows = result.mappings().all()
    return [str(r.get("column_name")) for r in rows if r.get("column_name")]


async def fetch_beneficiaries(session: AsyncSession, limit: int, offset: int = 0) -> List[Dict[str, Any]]:
    schema = "srsadmin"
    table = "swasthya_sathi_beneficiary"
    columns = await _get_beneficiary_columns(session, schema=schema, table=table)
    if not columns:
        raise ValueError("No beneficiary source table found in srsadmin.swasthya_sathi_beneficiary.")

    desired = [
        "uid",
        "scheme_beneficiary_id",
        "fullname",
        "gender",
        "member_dob",
        "scheme_id",
        "ration_card_number",
        "mobile",
        "annual_income",
        "disability_status",
        "is_disabled",
        "approved_date",
        "closing_date",
        "closure_remarks",
        "tran_count_1",
        "tran_count_2",
    ]
    selected = [c for c in desired if c in columns]

    if "uid" not in selected or "scheme_id" not in selected:
        raise ValueError("Beneficiary table must contain uid and scheme_id columns.")

    query = text(
        f"""
        WITH base AS (
            SELECT {', '.join(selected)}
            FROM {schema}.{table}
            WHERE uid IS NOT NULL AND BTRIM(uid) <> ''
            ORDER BY uid
            LIMIT :limit OFFSET :offset
        )
        SELECT
            base.*,
            rc.member_status AS rc_member_status,
            rc.closure_remarks AS rc_closure_remarks
        FROM base
        LEFT JOIN LATERAL (
            SELECT
                r.member_status,
                r.closure_remarks
            FROM srsadmin.rc_beneficiary r
            WHERE r.uid = base.uid
            ORDER BY r.modify_ts DESC NULLS LAST, r.entry_ts DESC NULLS LAST
            LIMIT 1
        ) rc ON TRUE
        ORDER BY base.uid
        """
    )
    result = await session.execute(query, {"limit": limit, "offset": offset})
    rows = result.mappings().all()
    enriched: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        rc_status = _normalize_text(item.get("rc_member_status"))
        closing_date = item.get("closing_date")
        closure_remarks = _normalize_text(item.get("closure_remarks") or item.get("rc_closure_remarks"))
        tran1 = _to_int(item.get("tran_count_1")) or 0
        tran2 = _to_int(item.get("tran_count_2")) or 0

        employment_status = ""
        if rc_status:
            employment_status = rc_status
        elif closing_date:
            employment_status = "CLOSED"
        else:
            employment_status = "ACTIVE"

        retired_or_terminated: Optional[bool] = None
        if closure_remarks:
            if any(x in closure_remarks for x in ["RETIRED", "TERMINATED"]):
                retired_or_terminated = True
            elif any(x in closure_remarks for x in ["CLOSED", "TRANSFER", "DEATH", "INACTIVE"]):
                retired_or_terminated = False

        item["employment_status"] = employment_status
        item["service_duration_months"] = tran1 + tran2 if (tran1 or tran2) else None
        item["retired_or_terminated"] = retired_or_terminated
        item["ida_covered"] = None
        item["receives_pension"] = None
        item["reemployed_same_factory"] = None
        item["marital_status"] = item.get("marital_status")

        enriched.append(item)

    return enriched


async def run_rule_evaluation(
    session: AsyncSession,
    rule: EligibilityRule,
    limit: int = 500,
    offset: int = 0,
) -> Dict[str, Any]:
    citizens = await fetch_beneficiaries(session, limit=limit, offset=offset)
    counts = {
        "INCLUSION_ERROR": 0,
        "EXCLUSION_ERROR": 0,
        "VALID_ENROLLMENT": 0,
        "NOT_APPLICABLE": 0,
        "REVIEW_REQUIRED": 0,
    }

    saved = 0
    preview: List[Dict[str, Any]] = []

    for citizen in citizens:
        try:
            outcome = evaluate_citizen_against_rule(citizen, rule)
            decision = outcome["decision"]
            counts[decision] = counts.get(decision, 0) + 1

            decision_row = EligibilityDecision(
                rule_id=rule.id,
                citizen_uid=str(citizen.get("uid") or ""),
                beneficiary_id=(
                    str(citizen.get("scheme_beneficiary_id"))
                    if citizen.get("scheme_beneficiary_id")
                    else None
                ),
                citizen_scheme_id=(str(citizen.get("scheme_id")) if citizen.get("scheme_id") else None),
                decision=decision,
                reason=outcome["reason"],
                evidence_json={
                    "rule_scheme_id": rule.scheme_id,
                    "citizen_name": citizen.get("fullname"),
                    "checks": outcome["checks"],
                    "include_conditions": rule.include_conditions,
                    "exclude_conditions": rule.exclude_conditions,
                },
                identity_match_confidence=1.0,
                decision_confidence=outcome["decision_confidence"],
            )
            session.add(decision_row)
            saved += 1

            if len(preview) < 25 and decision in {
                "INCLUSION_ERROR",
                "EXCLUSION_ERROR",
                "VALID_ENROLLMENT",
            }:
                preview.append(
                    {
                        "uid": citizen.get("uid"),
                        "citizen_name": citizen.get("fullname"),
                        "scheme_id": citizen.get("scheme_id"),
                        "decision": decision,
                        "reason": outcome["reason"],
                        "decision_confidence": outcome["decision_confidence"],
                    }
                )
        except Exception as row_exc:
            logger.warning(
                f"Eligibility evaluation skipped row for uid={citizen.get('uid')}: {row_exc}"
            )
            continue

    await session.commit()

    return {
        "rule_id": rule.id,
        "scheme_id": rule.scheme_id,
        "evaluated": len(citizens),
        "decisions_saved": saved,
        "counts": counts,
        "preview": preview,
    }
