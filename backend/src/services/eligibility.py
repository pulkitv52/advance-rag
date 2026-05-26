import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.logger import logger
from src.models.document import Document
from src.models.eligibility import (
    EligibilityDecision,
    EligibilityManualInput,
    EligibilityRule,
    EligibilitySchemaSignal,
)
from src.services import nvidia, storage
from src.services.eligibility_schema import (
    build_canonical_rule_from_legacy,
    build_llm_field_registry,
    manual_input_type_for_field,
    merge_canonical_rule_payloads,
    normalize_policy_concept,
    normalize_unmapped_condition_payload,
    sanitize_canonical_rule_payload,
    validate_canonical_rule_payload,
)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_to_json_safe(v) for v in value]
    return value


def _parse_amount(raw: str) -> Optional[float]:
    normalized = str(raw or "").strip().lower()
    if not normalized:
        return None

    multiplier = 1.0
    if re.search(r"\bcrores?\b", normalized):
        multiplier = 10_000_000.0
    elif re.search(r"\blakhs?\b", normalized):
        multiplier = 100_000.0
    elif re.search(r"\bthousand\b", normalized):
        multiplier = 1_000.0

    cleaned = re.sub(r"[^0-9.]", "", normalized)
    if not cleaned:
        return None
    try:
        return float(cleaned) * multiplier
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


def _split_policy_sentences(raw_text: str) -> List[str]:
    pieces = re.split(r"(?<=[\.\!\?\:\;])\s+|\n+", str(raw_text or ""))
    return [_clean_text(piece) for piece in pieces if _clean_text(piece)]


def _extract_keyword_fallback_unmapped_conditions(
    raw_text: str, existing_payload: Dict[str, Any]
) -> List[Dict[str, Any]]:
    lowered = _clean_text(raw_text).lower()
    if not lowered:
        return []

    existing_fields = {
        str(item.get("field") or "").strip()
        for item in list(existing_payload.get("include_conditions", []))
        + list(existing_payload.get("exclude_conditions", []))
        if item.get("field")
    }
    existing_unmapped = {
        str(item.get("suggested_input_field") or "").strip()
        for item in existing_payload.get("unmapped_conditions", [])
        if item.get("suggested_input_field")
    }
    sentences = _split_policy_sentences(raw_text)

    fallback_specs = [
        {
            "patterns": [r"\bcaste\b", r"\bsc\b", r"\bst\b", r"\bobc\b", r"\bminority\b"],
            "requirement": "caste_category",
            "skip_fields": {"caste"},
        },
        {
            "patterns": [r"\bcourse level\b", r"\bundergraduate\b", r"\bpostgraduate\b", r"\bclass\s+(?:xi|xii|11|12)\b"],
            "requirement": "course_level",
            "skip_fields": {"course_level"},
        },
        {
            "patterns": [r"\bcourse mode\b", r"\bregular\b", r"\bregular course\b", r"\bdistance\b", r"\bcorrespondence\b", r"\bonline\b"],
            "requirement": "course_mode",
            "skip_fields": {"study_mode"},
        },
        {
            "patterns": [r"\binstitution\b", r"\brecognized institution\b", r"\bgovernment institution\b", r"\beducational institution\b"],
            "requirement": "institution_eligibility",
            "skip_fields": {"institution_type"},
        },
        {
            "patterns": [r"\bno other scholarship\b", r"\bnot(?:\s+be)?\s+receiving any other scholarship\b", r"\banother scholarship\b"],
            "requirement": "no_other_scholarship",
            "skip_fields": {"no_other_scholarship"},
        },
        {
            "patterns": [r"\bpermanent resident\b", r"\bresident of west bengal\b", r"\bwest bengal resident\b"],
            "requirement": "Permanent resident of West Bengal",
            "skip_fields": {"has_west_bengal_residency", "permanent_residency_status"},
        },
        {
            "patterns": [r"\bmedical allowance\b"],
            "requirement": "Employee of State or Central Government drawing Medical Allowance (unless forfeited)",
            "skip_fields": {"receives_medical_allowance", "medical_allowance_opt_in"},
        },
        {
            "patterns": [r"\bother category\b.*\bstate government\b", r"\bnotified by the state government\b"],
            "requirement": "Any other category as may be notified by the State Government from time to time",
            "skip_fields": {"state_notified_category_eligibility"},
        },
    ]

    fallback_conditions: List[Dict[str, Any]] = []
    for spec in fallback_specs:
        if spec["skip_fields"] & existing_fields or spec["skip_fields"] & existing_unmapped:
            continue
        matched_sentence = next(
            (
                sentence
                for sentence in sentences
                if any(re.search(pattern, sentence, flags=re.IGNORECASE) for pattern in spec["patterns"])
            ),
            None,
        )
        if not matched_sentence and not any(
            re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in spec["patterns"]
        ):
            continue
        fallback_conditions.append(
            normalize_unmapped_condition_payload(
                {
                    "requirement": spec["requirement"],
                    "evidence_quote": matched_sentence,
                }
            )
        )

    for sentence in sentences:
        if "covered under" not in sentence.lower():
            continue
        normalized = normalize_unmapped_condition_payload(
            {
                "requirement": sentence,
                "evidence_quote": sentence,
            }
        )
        suggested = str(normalized.get("suggested_input_field") or "").strip()
        if not suggested or suggested in existing_unmapped:
            continue
        fallback_conditions.append(normalized)
        existing_unmapped.add(suggested)

    return fallback_conditions


def detect_scheme_id_from_filename(filename: str) -> Dict[str, Any]:
    """Extract scheme IDs from filename patterns like `doc_GE_S767_0.pdf`."""
    upper = _clean_text(filename).upper()
    # Supports: S767, S051, SS_001, SS_1001, C501 etc.
    hits = re.findall(r"(?<![A-Z0-9])(SS_\d{2,6}|S\d{2,6}|C\d{2,6})(?![A-Z0-9])", upper)
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
    for hit in re.findall(r"\b(?:S\d{2,6}|SS_\d{2,6}|C\d{2,6})\b", upper):
        score_map[hit] = score_map.get(hit, 0) + 3

    # 2) Boost using known scheme IDs present in srsadmin dump.
    try:
        known_rows = await session.exec(text("""
                SELECT DISTINCT scheme_id
                FROM srsadmin.swasthya_sathi_beneficiary
                WHERE scheme_id IS NOT NULL AND BTRIM(scheme_id) <> ''
                LIMIT 2000
                """))
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

    age_between = _extract_between(
        r"age\s*(?:between|from)\s*(\d{1,3})\s*(?:to|-|and)\s*(\d{1,3})", text
    )
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
        r"(?:annual\s+income|income).{0,40}(?:below|less\s+than|up\s*to|upto|not\s*exceed(?:ing)?)\s*(?:rs\.?|inr)?\s*([0-9][0-9,]*(?:\.\d+)?(?:\s*(?:thousand|lakh|lakhs|crore|crores))?)",
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
    conflict_scheme_codes = re.findall(r"\b(?:S\d{2,6}|SS_\d{2,6}|C\d{2,6})\b", text.upper())
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
    mid = cleaned[mid_start : mid_start + part]
    tail = cleaned[-part:]
    return f"[HEAD]\n{head}\n\n[MIDDLE]\n{mid}\n\n[TAIL]\n{tail}"


def _build_detected_criteria(
    include_conditions: Dict[str, Any],
    exclude_conditions: Dict[str, Any],
    evidence: List[Dict[str, Any]],
    unmapped_criteria: List[str],
) -> List[Dict[str, Any]]:
    """
    Dynamic criteria layer:
    - EXECUTABLE: already mapped into include/exclude conditions.
    - NEEDS_USER_INPUT: known criterion concept but field is not in executable schema.
    - UNMAPPED_LOGIC: no known mapping yet.
    """
    criteria: List[Dict[str, Any]] = []
    seen: set[str] = set()

    # Executable include/exclude criteria.
    for k, v in (include_conditions or {}).items():
        key = f"include::{k}"
        if key in seen:
            continue
        seen.add(key)
        criteria.append(
            {
                "criterion_key": k,
                "bucket": "include",
                "value": v,
                "status": "EXECUTABLE",
                "source": "normalized_rule",
            }
        )
    for k, v in (exclude_conditions or {}).items():
        key = f"exclude::{k}"
        if key in seen:
            continue
        seen.add(key)
        criteria.append(
            {
                "criterion_key": k,
                "bucket": "exclude",
                "value": v,
                "status": "EXECUTABLE",
                "source": "normalized_rule",
            }
        )

    # Heuristic mapping from evidence field to required manual input concept.
    evidence_lookup: Dict[str, str] = {}
    for ev in evidence or []:
        f = str(ev.get("field") or "").strip()
        q = str(ev.get("quote") or "").strip()
        if f and f not in evidence_lookup:
            evidence_lookup[f] = q

    for raw_key in unmapped_criteria or []:
        normalized_key = str(raw_key).split(".")[-1]
        normalized = normalize_policy_concept(normalized_key)
        suggested_input = normalized.get("field") if normalized.get("mapped") == "true" else None
        status = "NEEDS_USER_INPUT" if suggested_input else "UNMAPPED_LOGIC"
        criteria.append(
            {
                "criterion_key": str(raw_key),
                "bucket": "unknown",
                "value": None,
                "status": status,
                "suggested_input_field": suggested_input,
                "evidence_quote": evidence_lookup.get(str(raw_key))
                or evidence_lookup.get(normalized_key),
                "source": "evidence_unmapped",
            }
        )
    return criteria


def _build_priority_criteria_context(raw_text: str, max_chars: int = 8000) -> Dict[str, Any]:
    """
    Build a focused text context around explicit eligibility/inclusion/exclusion cues.
    This helps the LLM lock onto structured rule sections before using generic semantics.
    """
    cleaned = _clean_text(raw_text)
    if not cleaned:
        return {"focused_text": "", "matches": []}

    keyword_patterns = [
        r"\beligibility\b",
        r"\beligible\b",
        r"\binclusion\b",
        r"\binclude\b",
        r"\bwho\s+can\s+apply\b",
        r"\bnot\s+eligible\b",
        r"\bexclusion\b",
        r"\bexclude\b",
        r"\bineligible\b",
    ]
    combined = re.compile("|".join(keyword_patterns), flags=re.IGNORECASE)

    spans: List[tuple[int, int]] = []
    matches: List[str] = []
    for m in combined.finditer(cleaned):
        start = max(0, m.start() - 120)
        end = min(len(cleaned), m.end() + 620)
        spans.append((start, end))
        matches.append(m.group(0).lower())

    if not spans:
        return {"focused_text": "", "matches": []}

    spans.sort(key=lambda s: s[0])
    merged: List[List[int]] = []
    for start, end in spans:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)

    chunks: List[str] = []
    consumed = 0
    for start, end in merged:
        piece = cleaned[start:end].strip()
        if not piece:
            continue
        room = max_chars - consumed
        if room <= 0:
            break
        if len(piece) > room:
            piece = piece[:room].rstrip()
        chunks.append(piece)
        consumed += len(piece) + 2

    return {
        "focused_text": "\n\n".join(chunks).strip(),
        "matches": sorted(set(matches)),
    }


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
    focused = _build_priority_criteria_context(raw_text)
    focused_text = focused.get("focused_text") or ""
    focused_matches = focused.get("matches") or []
    schema_hint = (scheme_hint or detected_scheme or "").upper() or None
    field_registry = build_llm_field_registry()

    prompt = (
        "You are an expert policy analyst. Analyze the given policy/gazette document text and extract eligibility criteria.\n"
        "Prioritize explicit sections/phrases about eligibility, inclusion, exclusion, and ineligible cases first.\n"
        "Use the full document as fallback for missing details.\n"
        "Return ONLY a valid JSON object with this schema:\n"
        "{\n"
        '  "document_intent": {"summary": "string", "document_type": "scheme_guideline|gazette|circular|unknown", "is_eligibility_document": true|false},\n'
        '  "scheme_detection": {"scheme_id": "string|null", "scheme_name": "string|null", "confidence": "HIGH|MEDIUM|LOW"},\n'
        '  "include_conditions": [{"field":"string","operator":"string","value":"any|null","value_type":"string|null","evidence_quote":"string|null"}],\n'
        '  "exclude_conditions": [{"field":"string","operator":"string","value":"any|null","value_type":"string|null","evidence_quote":"string|null"}],\n'
        '  "unmapped_conditions": [{"requirement":"string","suggested_input_field":"string","input_type":"boolean|number|text|select","reason_unmapped":"string","evidence_quote":"string|null"}],\n'
        '  "evidence": [{"field":"string","quote":"string"}],\n'
        '  "extraction_confidence": "HIGH|MEDIUM|LOW",\n'
        '  "no_criteria_reason": "string|null"\n'
        "}\n"
        "Rules:\n"
        "- Use only fields from the provided logical field registry.\n"
        "- Use only operators allowed for each field.\n"
        "- Use null/empty arrays when unknown; do not invent facts.\n"
        "- If a requirement cannot be mapped confidently, put it in unmapped_conditions.\n"
        "- If document does not contain explicit eligibility criteria, set include_conditions/exclude_conditions empty and explain no_criteria_reason.\n"
        f"- Preferred scheme hint (if any): {schema_hint}\n\n"
        "Logical field registry:\n"
        f"{json.dumps(field_registry, ensure_ascii=True)}\n\n"
        "Focused criteria context (highest priority):\n"
        f"{focused_text or '[NO_FOCUSED_CONTEXT_FOUND]'}\n\n"
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

    regex_fallback = extract_eligibility_metadata(raw_text, scheme_id=schema_hint)

    include = parsed.get("include_conditions") or []
    exclude = parsed.get("exclude_conditions") or []
    unmapped_conditions = [
        normalize_unmapped_condition_payload(item)
        for item in (parsed.get("unmapped_conditions") or [])
        if isinstance(item, dict)
    ]
    evidence = parsed.get("evidence", []) or []
    scheme_from_llm = (
        ((parsed.get("scheme_detection") or {}).get("scheme_id")) or schema_hint or None
    )

    try:
        canonical_payload = sanitize_canonical_rule_payload(
            {
                "scheme_id": str(scheme_from_llm).upper() if scheme_from_llm else "UNKNOWN",
                "rule_name": "LLM Extracted Eligibility Rule",
                "include_conditions": include,
                "exclude_conditions": exclude,
                "unmapped_conditions": unmapped_conditions,
            }
        )
    except ValueError:
        legacy_include = parsed.get("include_conditions") or {}
        legacy_exclude = parsed.get("exclude_conditions") or {}
        canonical_payload = build_canonical_rule_from_legacy(
            scheme_id=str(scheme_from_llm).upper() if scheme_from_llm else "UNKNOWN",
            rule_name="LLM Extracted Eligibility Rule",
            include_conditions=legacy_include if isinstance(legacy_include, dict) else {},
            exclude_conditions=legacy_exclude if isinstance(legacy_exclude, dict) else {},
            unmapped_criteria=[],
        )

    regex_canonical_payload = build_canonical_rule_from_legacy(
        scheme_id=str(scheme_from_llm).upper() if scheme_from_llm else (schema_hint or "UNKNOWN"),
        rule_name="Regex Fallback Eligibility Rule",
        include_conditions=regex_fallback.get("include_conditions") or {},
        exclude_conditions=regex_fallback.get("exclude_conditions") or {},
        unmapped_criteria=[],
    )
    evidence_unmapped = [
        normalize_unmapped_condition_payload(
            {
                "requirement": str(item.get("field") or "").strip(),
                "evidence_quote": item.get("quote"),
            }
        )
        for item in (parsed.get("evidence") or [])
        if str(item.get("field") or "").strip()
        and str(item.get("field") or "").strip()
        not in {
            "gender",
            "annual_income",
            "age",
            "marital_status",
            "employment_status",
            "scheme_id",
        }
    ]
    canonical_payload = merge_canonical_rule_payloads(
        canonical_payload,
        {
            "scheme_id": canonical_payload.get("scheme_id")
            or regex_canonical_payload.get("scheme_id")
            or "UNKNOWN",
            "rule_name": canonical_payload.get("rule_name") or "LLM Extracted Eligibility Rule",
            "include_conditions": regex_canonical_payload.get("include_conditions", []),
            "exclude_conditions": regex_canonical_payload.get("exclude_conditions", []),
            "unmapped_conditions": evidence_unmapped,
        },
    )
    keyword_fallback_unmapped = _extract_keyword_fallback_unmapped_conditions(
        raw_text, canonical_payload
    )
    canonical_payload = merge_canonical_rule_payloads(
        canonical_payload,
        {
            "scheme_id": canonical_payload.get("scheme_id") or "UNKNOWN",
            "rule_name": canonical_payload.get("rule_name") or "LLM Extracted Eligibility Rule",
            "include_conditions": [],
            "exclude_conditions": [],
            "unmapped_conditions": keyword_fallback_unmapped,
        },
    )

    detected_fields = [str(item.get("field", "")).strip() for item in evidence if item.get("field")]
    canonical_fields = [
        str(item.get("field", "")).strip()
        for item in canonical_payload.get("include_conditions", [])
        + canonical_payload.get("exclude_conditions", [])
        if item.get("field")
    ]
    unmapped_criteria = sorted(
        {
            str(item.get("suggested_input_field") or item.get("requirement") or "").strip()
            for item in canonical_payload.get("unmapped_conditions", [])
            if str(item.get("suggested_input_field") or item.get("requirement") or "").strip()
        }
    )

    return {
        "scheme_id": str(scheme_from_llm).upper() if scheme_from_llm else None,
        "include_conditions": canonical_payload.get("include_conditions", []),
        "exclude_conditions": canonical_payload.get("exclude_conditions", []),
        "canonical_rule": canonical_payload,
        "extracted_fields": sorted(set(canonical_fields + detected_fields)),
        "parser": "llm_v2",
        "document_intent": parsed.get("document_intent"),
        "scheme_detection_llm": parsed.get("scheme_detection"),
        "evidence": evidence,
        "unmapped_criteria": unmapped_criteria,
        "unmapped_conditions": canonical_payload.get("unmapped_conditions", []),
        "detected_criteria": _build_detected_criteria(
            include_conditions={
                "canonical_count": len(canonical_payload.get("include_conditions", []))
            },
            exclude_conditions={
                "canonical_count": len(canonical_payload.get("exclude_conditions", []))
            },
            evidence=evidence,
            unmapped_criteria=unmapped_criteria,
        ),
        "extraction_confidence": parsed.get("extraction_confidence"),
        "no_criteria_reason": parsed.get("no_criteria_reason"),
        "focused_context": {
            "applied": bool(focused_text),
            "keyword_hits": focused_matches,
            "excerpt": focused_text[:1200] if focused_text else None,
        },
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
    if value is None:
        return ""
    return str(value).strip().upper()


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


def _is_empty_manual_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _get_canonical_rule_payload(rule: EligibilityRule) -> Dict[str, Any]:
    extracted_meta = rule.extracted_metadata or {}
    canonical = extracted_meta.get("canonical_rule")
    if isinstance(canonical, dict):
        return validate_canonical_rule_payload(canonical)

    return build_canonical_rule_from_legacy(
        scheme_id=str(rule.scheme_id),
        rule_name=str(rule.rule_name),
        include_conditions=rule.include_conditions or {},
        exclude_conditions=rule.exclude_conditions or {},
        unmapped_criteria=extracted_meta.get("unmapped_criteria") or [],
    )


def _resolve_logical_field_value(citizen: Dict[str, Any], field_name: str) -> Any:
    if field_name == "age":
        return _calculate_age(_parse_dob(citizen.get("member_dob")))
    if field_name == "gender":
        return _normalize_text(citizen.get("gender"))
    if field_name == "marital_status":
        return _normalize_text(citizen.get("marital_status"))
    if field_name == "annual_income":
        income_raw = citizen.get("annual_income")
        return _parse_amount(str(income_raw)) if income_raw is not None else None
    if field_name == "is_disabled":
        return _to_boolish(citizen.get("is_disabled") or citizen.get("disability_status"))
    if field_name == "employment_status":
        return _normalize_text(citizen.get("employment_status"))
    if field_name == "service_duration_months":
        return _to_int(citizen.get("service_duration_months"))
    if field_name == "ida_covered":
        return _to_boolish(citizen.get("ida_covered"))
    if field_name == "scheme_id":
        return _normalize_text(citizen.get("scheme_id"))
    if field_name == "receives_pension":
        return _to_boolish(citizen.get("receives_pension"))
    if field_name == "retired_or_terminated":
        return _to_boolish(citizen.get("retired_or_terminated"))
    if field_name == "reemployed_same_factory":
        return _to_boolish(citizen.get("reemployed_same_factory"))
    if field_name == "member_dob":
        dob = _parse_dob(citizen.get("member_dob"))
        return dob.isoformat() if dob else None
    if field_name == "caste":
        return _normalize_text(citizen.get("caste"))
    if field_name == "rc_ration_card_type_code":
        return _normalize_text(citizen.get("rc_ration_card_type_code"))
    if field_name == "rc_is_hof":
        return _to_boolish(citizen.get("rc_is_hof"))
    return citizen.get(field_name)


def _normalize_expected_value(field_name: str, value: Any) -> Any:
    if value is None:
        return None
    if field_name in {
        "gender",
        "marital_status",
        "employment_status",
        "scheme_id",
        "caste",
        "rc_ration_card_type_code",
    }:
        if isinstance(value, list):
            return [_normalize_text(v) for v in value]
        return _normalize_text(value)
    if field_name in {"annual_income", "age", "service_duration_months"}:
        if isinstance(value, list):
            normalized = []
            for item in value:
                if isinstance(item, (int, float)) and not isinstance(item, bool):
                    normalized.append(float(item))
            return normalized
        return float(value)
    if field_name in {
        "is_disabled",
        "ida_covered",
        "rc_is_hof",
        "receives_pension",
        "retired_or_terminated",
        "reemployed_same_factory",
    }:
        if isinstance(value, list):
            return [_to_boolish(v) for v in value]
        return _to_boolish(value)
    if field_name == "member_dob":
        if isinstance(value, list):
            return [str(v).strip() for v in value]
        return str(value).strip()
    return value


def _evaluate_operator(actual: Any, operator: str, expected: Any) -> bool:
    if operator == "is_null":
        return actual is None
    if operator == "is_not_null":
        return actual is not None
    if actual is None:
        return False
    if operator == "=":
        return actual == expected
    if operator == "!=":
        return actual != expected
    if operator == ">":
        return actual > expected
    if operator == "<":
        return actual < expected
    if operator == ">=":
        return actual >= expected
    if operator == "<=":
        return actual <= expected
    if operator == "in":
        return actual in (expected or [])
    if operator == "not_in":
        return actual not in (expected or [])
    raise ValueError(f"Unsupported operator: {operator}")


def _invert_operator_for_report(operator: str) -> str:
    return {
        "=": "!=",
        "!=": "=",
        ">": "<=",
        "<": ">=",
        ">=": "<",
        "<=": ">",
        "in": "not_in",
        "not_in": "in",
        "is_null": "is_not_null",
        "is_not_null": "is_null",
    }.get(operator, f"not_{operator}")


def _evaluate_canonical_conditions(
    citizen: Dict[str, Any],
    conditions: List[Dict[str, Any]],
    bucket: str,
) -> tuple[List[Dict[str, Any]], List[str], bool]:
    checks: List[Dict[str, Any]] = []
    missing_required_fields: List[str] = []
    passed_all = True

    for condition in conditions:
        field_name = str(condition.get("field") or "").strip()
        operator = str(condition.get("operator") or "").strip()
        actual = _resolve_logical_field_value(citizen, field_name)
        expected = _normalize_expected_value(field_name, condition.get("value"))

        if _is_empty_manual_value(actual) and operator not in {"is_null", "is_not_null"}:
            missing_required_fields.append(field_name)
            continue

        matched = _evaluate_operator(actual, operator, expected)
        if bucket == "include":
            passed = matched
            reported_operator = operator
        else:
            passed = not matched
            reported_operator = _invert_operator_for_report(operator)

        checks.append(
            {
                "field": field_name,
                "operator": reported_operator,
                "expected": expected,
                "actual": actual,
                "passed": passed,
                "bucket": bucket,
            }
        )
        passed_all = passed_all and passed

    return checks, missing_required_fields, passed_all


def _evaluate_unmapped_conditions(
    citizen: Dict[str, Any], unmapped_conditions: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    non_blocking_keys = {"eligibility_scope", "exclusion_list"}
    unresolved: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()
    for condition in unmapped_conditions:
        input_field = str(condition.get("suggested_input_field") or "").strip()
        input_type = str(condition.get("input_type") or "text").strip().lower()
        requirement_key = str(condition.get("requirement") or input_field).strip()
        if requirement_key in non_blocking_keys:
            continue
        dedupe_key = input_field or requirement_key
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        if not input_field:
            unresolved.append(condition)
            continue
        manual_value = citizen.get(input_field)
        if _is_empty_manual_value(manual_value):
            unresolved.append(condition)
            continue
        if input_type == "boolean" and _to_boolish(manual_value) is None:
            unresolved.append(condition)
    return unresolved


def evaluate_citizen_against_rule(
    citizen: Dict[str, Any],
    rule: EligibilityRule,
    canonical_rule: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate one citizen. Pass canonical_rule from a bulk loop to skip re-validation."""
    if canonical_rule is None:
        canonical_rule = _get_canonical_rule_payload(rule)
    include_conditions = canonical_rule.get("include_conditions", [])
    exclude_conditions = canonical_rule.get("exclude_conditions", [])
    unmapped_conditions = canonical_rule.get("unmapped_conditions", [])

    current_scheme = _normalize_text(citizen.get("scheme_id"))
    target_scheme = _normalize_text(rule.scheme_id)
    is_enrolled_in_target = current_scheme == target_scheme

    include_checks, include_missing, include_passed = _evaluate_canonical_conditions(
        citizen, include_conditions, "include"
    )
    exclude_checks, exclude_missing, exclude_passed = _evaluate_canonical_conditions(
        citizen, exclude_conditions, "exclude"
    )
    checks = include_checks + exclude_checks
    missing_required_fields = sorted(set(include_missing + exclude_missing))
    is_eligible = include_passed and exclude_passed

    unresolved_unmapped = _evaluate_unmapped_conditions(citizen, unmapped_conditions)
    blocking_unmapped = sorted(
        {
            str(item.get("suggested_input_field") or item.get("requirement") or "").strip()
            for item in unresolved_unmapped
            if str(item.get("suggested_input_field") or item.get("requirement") or "").strip()
        }
    )

    has_criteria = bool(include_conditions) or bool(exclude_conditions) or bool(unmapped_conditions)
    if blocking_unmapped:
        return {
            "decision": "REVIEW_REQUIRED",
            "reason": (
                "Document contains unresolved eligibility criteria requiring manual inputs: "
                + ", ".join(blocking_unmapped)
                + "."
            ),
            "decision_confidence": 0.0,
            "is_eligible": False,
            "is_enrolled_in_target": is_enrolled_in_target,
            "checks": checks,
            "checked_fields": sorted({str(c.get("field")) for c in checks if c.get("field")}),
            "missing_required_fields": [],
            "blocking_unmapped_criteria": blocking_unmapped,
        }

    if not has_criteria:
        return {
            "decision": "REVIEW_REQUIRED",
            "reason": "No usable eligibility criteria were extracted from the policy document. Manual rule validation is required.",
            "decision_confidence": 0.0,
            "is_eligible": False,
            "is_enrolled_in_target": is_enrolled_in_target,
            "checks": [],
            "checked_fields": [],
            "missing_required_fields": [],
            "blocking_unmapped_criteria": [],
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
            "checked_fields": sorted({str(c.get("field")) for c in checks if c.get("field")}),
            "missing_required_fields": missing_unique,
            "blocking_unmapped_criteria": [],
        }

    passed_checks = [c for c in checks if c.get("passed")]
    failed_checks = [c for c in checks if not c.get("passed")]

    if is_eligible and not is_enrolled_in_target:
        decision = "EXCLUSION_ERROR"
        reason = (
            f"Citizen is eligible by extracted criteria but not enrolled in target scheme {target_scheme}. "
            + (
                "Passed checks: "
                + "; ".join(_format_check_for_reason(c) for c in passed_checks)
                + "."
                if passed_checks
                else "No executable checks were available."
            )
        )
    elif not is_eligible and is_enrolled_in_target:
        decision = "INCLUSION_ERROR"
        reason = (
            f"Citizen is enrolled in target scheme {target_scheme} but failed eligibility checks. "
            + (
                "Failed checks: "
                + "; ".join(_format_check_for_reason(c) for c in failed_checks)
                + "."
                if failed_checks
                else "No failing check details available."
            )
        )
    elif is_eligible and is_enrolled_in_target:
        decision = "VALID_ENROLLMENT"
        reason = f"Citizen is eligible and correctly enrolled in target scheme {target_scheme}."
    else:
        decision = "NOT_APPLICABLE"
        reason = f"Citizen is not eligible and not enrolled in target scheme {target_scheme}. " + (
            "Failed checks: " + "; ".join(_format_check_for_reason(c) for c in failed_checks) + "."
            if failed_checks
            else "No failing check details available."
        )

    matched_checks = sum(1 for c in checks if c["passed"])
    total_checks = len(checks)
    base = 0.75
    confidence = (
        base if total_checks == 0 else min(0.99, base + (matched_checks / total_checks) * 0.2)
    )

    return {
        "decision": decision,
        "reason": reason,
        "decision_confidence": round(confidence, 4),
        "is_eligible": is_eligible,
        "is_enrolled_in_target": is_enrolled_in_target,
        "checks": checks,
        "checked_fields": sorted({str(c.get("field")) for c in checks if c.get("field")}),
        "missing_required_fields": [],
        "blocking_unmapped_criteria": [],
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
    canonical_rule = llm_metadata.get("canonical_rule")
    if not isinstance(canonical_rule, dict):
        canonical_rule = build_canonical_rule_from_legacy(
            scheme_id=resolved_scheme_id,
            rule_name=rule_name or f"Eligibility Rule - {resolved_scheme_id}",
            include_conditions=regex_metadata.get("include_conditions") or {},
            exclude_conditions=regex_metadata.get("exclude_conditions") or {},
            unmapped_criteria=llm_metadata.get("unmapped_criteria") or [],
        )

    include_conditions = regex_metadata.get("include_conditions") or {}
    exclude_conditions = regex_metadata.get("exclude_conditions") or {}

    metadata = {
        **llm_metadata,
        "scheme_id": resolved_scheme_id,
        "include_conditions": include_conditions,
        "exclude_conditions": exclude_conditions,
        "extracted_fields": sorted(
            {
                str(item.get("field"))
                for item in canonical_rule.get("include_conditions", [])
                + canonical_rule.get("exclude_conditions", [])
                if item.get("field")
            }
        ),
        "regex_backup": regex_metadata,
        "decision_source": "llm_v2",
        "regex_fallback_applied": False,
    }
    metadata["scheme_detection"] = detection
    metadata["scheme_detection_filename"] = filename_detection
    metadata["scheme_id_overridden"] = bool(scheme_id)
    metadata["scheme_id_resolved"] = resolved_scheme_id
    metadata["canonical_rule"] = canonical_rule

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


# Module-level cache: avoids repeated slow information_schema queries per request.
_column_cache: Dict[str, List[str]] = {}


async def _get_beneficiary_columns(session: AsyncSession, schema: str, table: str) -> List[str]:
    cache_key = f"{schema}.{table}"
    if cache_key in _column_cache:
        return _column_cache[cache_key]
    query = text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :table
        """)
    result = await session.execute(query, {"schema": schema, "table": table})
    rows = result.mappings().all()
    columns = [str(r.get("column_name")) for r in rows if r.get("column_name")]
    if columns:
        _column_cache[cache_key] = columns
    return columns


async def fetch_beneficiaries(
    session: AsyncSession, limit: int, offset: int = 0
) -> List[Dict[str, Any]]:
    schema = "srsadmin"
    table = "master_beneficiary_dataset"
    columns = await _get_beneficiary_columns(session, schema=schema, table=table)
    if not columns:
        table = "swasthya_sathi_beneficiary"
        columns = await _get_beneficiary_columns(session, schema=schema, table=table)
    if not columns:
        raise ValueError(
            "No beneficiary source table found in srsadmin.master_beneficiary_dataset or srsadmin.swasthya_sathi_beneficiary."
        )

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
        "disability_status",
        "is_disabled",
    ]
    selected = [c for c in desired if c in columns]

    if "uid" not in selected or "scheme_id" not in selected:
        raise ValueError("Beneficiary table must contain uid and scheme_id columns.")

    query = text(f"""
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
        """)
    result = await session.execute(query, {"limit": limit, "offset": offset})
    rows = result.mappings().all()
    enriched: List[Dict[str, Any]] = []
    for row in rows:
        enriched.append(_enrich_citizen_row(dict(row)))

    return enriched


def _build_source_value_snapshot(citizen: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        "uid",
        "scheme_id",
        "scheme_beneficiary_id",
        "fullname",
        "member_dob",
        "gender",
        "caste",
        "ration_card_number",
        "approved_date",
        "closing_date",
        "closure_remarks",
        "tran_count_1",
        "tran_count_2",
        "transaction_rows",
        "transaction_total_amount",
        "latest_transaction_timestamp",
        "employment_status",
        "service_duration_months",
        "retired_or_terminated",
        "receives_pension",
        "ida_covered",
        "reemployed_same_factory",
        "annual_income",
        "disability_status",
        "is_disabled",
        "study_mode",
        "institution_type",
        "no_other_scholarship",
        "nationality",
    ]
    return _to_json_safe({k: citizen.get(k) for k in keys})


def _enrich_citizen_row(item: Dict[str, Any]) -> Dict[str, Any]:
    rc_status = _normalize_text(item.get("rc_member_status"))
    closing_date = item.get("closing_date")
    closure_remarks = _normalize_text(item.get("closure_remarks") or item.get("rc_closure_remarks"))
    tran1 = _to_int(item.get("tran_count_1")) or 0
    tran2 = _to_int(item.get("tran_count_2")) or 0

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
    item["ida_covered"] = item.get("ida_covered")
    item["receives_pension"] = item.get("receives_pension")
    item["reemployed_same_factory"] = item.get("reemployed_same_factory")
    item["marital_status"] = item.get("marital_status")
    return item


async def fetch_citizen_evaluation_base(
    session: AsyncSession,
    target_scheme_id: str,
    limit: int,
    offset: int = 0,
    scheme_only: bool = True,
) -> List[Dict[str, Any]]:
    """
    Build one evaluation row per UID from master dataset.
    Priority:
    1) Row enrolled in target scheme (if exists)
    2) Otherwise most recent row from any scheme
    """
    schema = "srsadmin"
    table = "master_beneficiary_dataset"
    columns = await _get_beneficiary_columns(session, schema=schema, table=table)
    if not columns:
        # Safe fallback to previous behavior if master table is absent.
        return await fetch_beneficiaries(session, limit=limit, offset=offset)

    if scheme_only:
        query = text(f"""
            SELECT m.*
            FROM {schema}.{table} m
            WHERE m.uid IS NOT NULL
              AND BTRIM(m.uid) <> ''
              AND UPPER(BTRIM(m.scheme_id)) = :target_scheme_id
            ORDER BY m.uid
            LIMIT :limit OFFSET :offset
            """)
    else:
        query = text(f"""
            WITH ranked AS (
                SELECT
                    m.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY m.uid
                        ORDER BY
                            CASE WHEN m.scheme_id = :target_scheme_id THEN 0 ELSE 1 END ASC,
                            m.latest_transaction_timestamp DESC NULLS LAST,
                            m.approved_date DESC NULLS LAST
                    ) AS rn
                FROM {schema}.{table} m
                WHERE m.uid IS NOT NULL AND BTRIM(m.uid) <> ''
            )
            SELECT *
            FROM ranked
            WHERE rn = 1
            ORDER BY uid
            LIMIT :limit OFFSET :offset
            """)

    result = await session.execute(
        query,
        {
            "target_scheme_id": target_scheme_id,
            "limit": limit,
            "offset": offset,
        },
    )
    rows = result.mappings().all()

    enriched: List[Dict[str, Any]] = []
    for row in rows:
        enriched.append(_enrich_citizen_row(dict(row)))

    return enriched


async def fetch_single_citizen_evaluation_base(
    session: AsyncSession,
    target_scheme_id: str,
    citizen_uid: str,
    scheme_only: bool = True,
) -> Optional[Dict[str, Any]]:
    schema = "srsadmin"
    table = "master_beneficiary_dataset"
    columns = await _get_beneficiary_columns(session, schema=schema, table=table)
    if not columns:
        return None

    if scheme_only:
        query = text(f"""
            SELECT m.*
            FROM {schema}.{table} m
            WHERE m.uid = :uid
              AND UPPER(BTRIM(m.scheme_id)) = :target_scheme_id
            ORDER BY m.latest_transaction_timestamp DESC NULLS LAST, m.approved_date DESC NULLS LAST
            LIMIT 1
            """)
    else:
        query = text(f"""
            SELECT m.*
            FROM {schema}.{table} m
            WHERE m.uid = :uid
            ORDER BY
                CASE WHEN UPPER(BTRIM(m.scheme_id)) = :target_scheme_id THEN 0 ELSE 1 END ASC,
                m.latest_transaction_timestamp DESC NULLS LAST,
                m.approved_date DESC NULLS LAST
            LIMIT 1
            """)

    result = await session.execute(
        query, {"uid": citizen_uid, "target_scheme_id": target_scheme_id}
    )
    row = result.mappings().first()
    if not row:
        return None
    return _enrich_citizen_row(dict(row))


async def run_rule_evaluation(
    session: AsyncSession,
    rule: EligibilityRule,
    limit: int = 500,
    offset: int = 0,
    scheme_only: bool = True,
) -> Dict[str, Any]:
    canonical_rule = _get_canonical_rule_payload(rule)
    target_scheme_id = _normalize_text(rule.scheme_id)
    citizens = await fetch_citizen_evaluation_base(
        session=session,
        target_scheme_id=target_scheme_id,
        limit=limit,
        offset=offset,
        scheme_only=scheme_only,
    )
    manual_rows = await session.exec(
        select(EligibilityManualInput).where(EligibilityManualInput.rule_id == rule.id)
    )
    manual_by_uid = {
        str(r.citizen_uid): (r.values_json or {})
        for r in manual_rows.all()
        if getattr(r, "citizen_uid", None)
    }
    bucket_alias = {
        "VALID_ENROLLMENT": "ELIGIBLE_ENROLLED",
        "INCLUSION_ERROR": "NOT_ELIGIBLE_ENROLLED",
        "EXCLUSION_ERROR": "ELIGIBLE_NOT_ENROLLED",
        "NOT_APPLICABLE": "NOT_ELIGIBLE_NOT_ENROLLED",
        "REVIEW_REQUIRED": "REVIEW_REQUIRED",
    }
    counts = {
        "INCLUSION_ERROR": 0,
        "EXCLUSION_ERROR": 0,
        "VALID_ENROLLMENT": 0,
        "NOT_APPLICABLE": 0,
        "REVIEW_REQUIRED": 0,
    }

    # Delete stale decisions before re-evaluating to prevent row accumulation.
    await session.execute(
        text("DELETE FROM eligibility_decisions WHERE rule_id = :rule_id"),
        {"rule_id": rule.id},
    )
    await session.flush()

    saved = 0
    preview: List[Dict[str, Any]] = []
    BATCH_SIZE = 100

    for citizen in citizens:
        try:
            uid = str(citizen.get("uid") or "")
            merged_citizen = {**citizen, **(manual_by_uid.get(uid) or {})}
            # Pass pre-computed canonical_rule to skip 500x Pydantic re-validation.
            outcome = evaluate_citizen_against_rule(merged_citizen, rule, canonical_rule)
            decision = outcome["decision"]
            counts[decision] = counts.get(decision, 0) + 1

            decision_row = EligibilityDecision(
                rule_id=rule.id,
                citizen_uid=uid,
                beneficiary_id=(
                    str(merged_citizen.get("scheme_beneficiary_id"))
                    if merged_citizen.get("scheme_beneficiary_id")
                    else None
                ),
                citizen_scheme_id=(
                    str(merged_citizen.get("scheme_id"))
                    if merged_citizen.get("scheme_id")
                    else None
                ),
                decision=decision,
                reason=outcome["reason"],
                evidence_json={
                    "rule_scheme_id": rule.scheme_id,
                    "citizen_name": merged_citizen.get("fullname"),
                    "checks": _to_json_safe(outcome["checks"]),
                    "checked_fields": _to_json_safe(outcome.get("checked_fields") or []),
                    "missing_required_fields": _to_json_safe(
                        outcome.get("missing_required_fields") or []
                    ),
                    "blocking_unmapped_criteria": _to_json_safe(
                        outcome.get("blocking_unmapped_criteria") or []
                    ),
                    "source_values": _build_source_value_snapshot(merged_citizen),
                    "manual_inputs": _to_json_safe(manual_by_uid.get(uid) or {}),
                    "include_conditions": _to_json_safe(rule.include_conditions),
                    "exclude_conditions": _to_json_safe(rule.exclude_conditions),
                    "canonical_rule": _to_json_safe(canonical_rule),
                },
                identity_match_confidence=1.0,
                decision_confidence=outcome["decision_confidence"],
            )
            session.add(decision_row)
            saved += 1

            # Flush in batches to release ORM identity-map memory.
            if saved % BATCH_SIZE == 0:
                await session.flush()

            if len(preview) < 25 and decision in {
                "INCLUSION_ERROR",
                "EXCLUSION_ERROR",
                "VALID_ENROLLMENT",
            }:
                preview.append(
                    {
                        "uid": merged_citizen.get("uid"),
                        "citizen_name": merged_citizen.get("fullname"),
                        "scheme_id": merged_citizen.get("scheme_id"),
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

    bucket_counts = {
        "ELIGIBLE_ENROLLED": counts.get("VALID_ENROLLMENT", 0),
        "NOT_ELIGIBLE_ENROLLED": counts.get("INCLUSION_ERROR", 0),
        "ELIGIBLE_NOT_ENROLLED": counts.get("EXCLUSION_ERROR", 0),
        "NOT_ELIGIBLE_NOT_ENROLLED": counts.get("NOT_APPLICABLE", 0),
        "REVIEW_REQUIRED": counts.get("REVIEW_REQUIRED", 0),
    }
    unmapped_criteria = [
        str(item.get("suggested_input_field") or item.get("requirement") or "").strip()
        for item in canonical_rule.get("unmapped_conditions", [])
        if str(item.get("suggested_input_field") or item.get("requirement") or "").strip()
    ]
    executable_include_fields = sorted(
        {
            str(item.get("field"))
            for item in canonical_rule.get("include_conditions", [])
            if item.get("field")
        }
    )
    executable_exclude_fields = sorted(
        {
            str(item.get("field"))
            for item in canonical_rule.get("exclude_conditions", [])
            if item.get("field")
        }
    )

    return {
        "rule_id": rule.id,
        "scheme_id": rule.scheme_id,
        "evaluated": len(citizens),
        "decisions_saved": saved,
        "counts": counts,
        "bucket_counts": bucket_counts,
        "bucket_mapping": bucket_alias,
        "evaluation_basis": {
            "message": (
                "Buckets are computed using only mapped, executable criteria present in the master dataset. "
                "Cases with missing critical criteria or unmapped policy conditions are marked REVIEW_REQUIRED."
            ),
            "scheme_scope": "SCHEME_ONLY" if scheme_only else "PREFERRED_SCHEME",
            "scheme_scope_description": (
                "Only citizens enrolled in the target scheme were evaluated."
                if scheme_only
                else "One row per UID was evaluated, prioritizing target scheme enrollment when available."
            ),
            "executable_include_fields": executable_include_fields,
            "executable_exclude_fields": executable_exclude_fields,
            "unmapped_criteria": unmapped_criteria,
            "no_population_found": len(citizens) == 0,
            "no_population_reason": (
                f"No citizen rows found for scheme {rule.scheme_id} in the current master dataset."
                if len(citizens) == 0
                else None
            ),
        },
        "preview": preview,
    }
