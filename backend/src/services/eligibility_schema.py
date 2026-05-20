from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

FIELD_TYPES: Dict[str, str] = {
    "age": "number",
    "gender": "text",
    "marital_status": "text",
    "annual_income": "number",
    "is_disabled": "boolean",
    "employment_status": "text",
    "service_duration_months": "number",
    "ida_covered": "boolean",
    "scheme_id": "text",
    "receives_pension": "boolean",
    "retired_or_terminated": "boolean",
    "reemployed_same_factory": "boolean",
    "member_dob": "date",
    "caste": "text",
    "rc_ration_card_type_code": "text",
    "rc_is_hof": "boolean",
}

MANUAL_ONLY_FIELD_TYPES: Dict[str, str] = {
    "course_level": "text",
    "study_mode": "text",
    "institution_type": "text",
    "no_other_scholarship": "boolean",
    "nationality": "text",
    "medical_allowance_opt_in": "boolean",
    "male_sibling_scholarship_count": "number",
}

FIELD_DESCRIPTIONS: Dict[str, str] = {
    "age": "Citizen age in completed years, derived from member_dob.",
    "gender": "Gender of the citizen.",
    "marital_status": "Marital status of the citizen.",
    "annual_income": "Total annual family income in INR.",
    "is_disabled": "Whether the citizen is disabled.",
    "employment_status": "Employment status of the citizen.",
    "service_duration_months": "Completed service duration in months.",
    "ida_covered": "Whether the citizen is IDA covered.",
    "scheme_id": "Scheme identifier for current enrollment.",
    "receives_pension": "Whether the citizen currently receives a pension.",
    "retired_or_terminated": "Whether the citizen is retired or terminated.",
    "reemployed_same_factory": "Whether the citizen was re-employed in the same factory.",
    "member_dob": "Date of birth in YYYY-MM-DD format.",
    "caste": "Citizen caste category.",
    "rc_ration_card_type_code": "Ration card type code.",
    "rc_is_hof": "Whether the citizen is head of family.",
    "course_level": "Course level relevant to eligibility.",
    "study_mode": "Study or course mode relevant to eligibility.",
    "institution_type": "Institution type or eligibility category.",
    "no_other_scholarship": "Whether the applicant is not receiving another scholarship.",
    "nationality": "Nationality requirement for the applicant.",
    "medical_allowance_opt_in": "Whether the applicant opted into the medical allowance path.",
    "male_sibling_scholarship_count": "Count of male siblings already receiving scholarship support.",
}

POLICY_CONCEPT_FIELD_MAP: Dict[str, Dict[str, str]] = {
    "caste_category": {"field": "caste", "input_type": "text"},
    "eligible_caste": {"field": "caste", "input_type": "text"},
    "caste_eligibility": {"field": "caste", "input_type": "text"},
    "beneficiary_category": {"field": "caste", "input_type": "text"},
    "income_limit": {"field": "annual_income", "input_type": "number"},
    "gender_restriction": {"field": "gender", "input_type": "text"},
    "gender_restriction_boys": {"field": "gender", "input_type": "text"},
    "institution_eligibility": {"field": "institution_type", "input_type": "text"},
    "institution_code": {"field": "institution_type", "input_type": "text"},
    "institution_standard": {"field": "institution_type", "input_type": "text"},
    "institution_criteria": {"field": "institution_type", "input_type": "text"},
    "course_level": {"field": "course_level", "input_type": "text"},
    "course_eligibility": {"field": "course_level", "input_type": "text"},
    "course_mode": {"field": "study_mode", "input_type": "text"},
    "online_course_eligibility": {"field": "study_mode", "input_type": "text"},
    "study_mode": {"field": "study_mode", "input_type": "text"},
    "no_other_scholarship": {"field": "no_other_scholarship", "input_type": "boolean"},
    "single_scholarship_rule": {"field": "no_other_scholarship", "input_type": "boolean"},
    "other_scholarship_exclusion": {"field": "no_other_scholarship", "input_type": "boolean"},
    "single_other_scholarship_exclusion": {
        "field": "no_other_scholarship",
        "input_type": "boolean",
    },
    "nationality": {"field": "nationality", "input_type": "text"},
    "eligible_nationality": {"field": "nationality", "input_type": "text"},
    "medical_allowance_opt_in": {"field": "medical_allowance_opt_in", "input_type": "boolean"},
}


ALLOWED_OPERATORS_BY_TYPE: Dict[str, set[str]] = {
    "text": {"=", "!=", "in", "not_in", "is_null", "is_not_null"},
    "number": {"=", "!=", ">", "<", ">=", "<=", "is_null", "is_not_null"},
    "date": {"=", "!=", ">", "<", ">=", "<=", "is_null", "is_not_null"},
    "boolean": {"=", "!=", "is_null", "is_not_null"},
}


MANUAL_INPUT_TYPES = {"boolean", "number", "text", "select"}
SCHEME_CODE_PATTERN = re.compile(r"^(SS_\d{2,6}|S\d{2,6}|C\d{2,6})$", flags=re.IGNORECASE)


class EligibilityCondition(BaseModel):
    field: str
    operator: str
    value: Optional[Any] = None
    value_type: Optional[str] = None
    evidence_quote: Optional[str] = None

    @field_validator("field")
    @classmethod
    def validate_field(cls, value: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("Condition field must not be empty.")
        if normalized not in FIELD_TYPES:
            raise ValueError(f"Unsupported condition field: {normalized}")
        return normalized

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, value: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("Condition operator must not be empty.")
        return normalized

    @model_validator(mode="after")
    def validate_semantics(self) -> "EligibilityCondition":
        expected_type = FIELD_TYPES[self.field]
        if not self.value_type:
            self.value_type = expected_type

        if self.value_type != expected_type:
            raise ValueError(
                f"Condition value_type {self.value_type!r} does not match field type {expected_type!r} "
                f"for field {self.field!r}."
            )

        allowed_ops = ALLOWED_OPERATORS_BY_TYPE.get(expected_type, set())
        if self.operator not in allowed_ops:
            raise ValueError(
                f"Operator {self.operator!r} is not allowed for field {self.field!r} of type {expected_type!r}."
            )

        if self.operator in {"is_null", "is_not_null"}:
            if self.value is not None:
                raise ValueError(f"Operator {self.operator!r} must not include a value.")
            return self

        if self.operator in {"in", "not_in"}:
            if not isinstance(self.value, list) or not self.value:
                raise ValueError(f"Operator {self.operator!r} requires a non-empty list value.")
            self._validate_list_values(expected_type)
            return self

        self._validate_scalar_value(expected_type)
        return self

    def _validate_scalar_value(self, expected_type: str) -> None:
        if self.value is None:
            raise ValueError(f"Operator {self.operator!r} requires a value.")
        if expected_type == "number":
            if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
                raise ValueError("Numeric conditions require an int or float value.")
            return
        if expected_type == "boolean":
            if not isinstance(self.value, bool):
                raise ValueError("Boolean conditions require a true/false value.")
            return
        if expected_type in {"text", "date"} and not isinstance(self.value, str):
            raise ValueError(f"{expected_type.title()} conditions require a string value.")

    def _validate_list_values(self, expected_type: str) -> None:
        values = self.value or []
        if expected_type == "text":
            if not all(isinstance(v, str) for v in values):
                raise ValueError("Text list conditions require string values.")
            return
        if expected_type == "number":
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
                raise ValueError("Numeric list conditions require int or float values.")
            return
        if expected_type == "date":
            if not all(isinstance(v, str) for v in values):
                raise ValueError("Date list conditions require string values.")
            return
        raise ValueError(f"Operator {self.operator!r} is not supported for type {expected_type!r}.")


class UnmappedCondition(BaseModel):
    requirement: str
    suggested_input_field: str
    input_type: str = "text"
    reason_unmapped: str
    evidence_quote: Optional[str] = None

    @field_validator("requirement", "suggested_input_field", "reason_unmapped")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("Unmapped condition fields must not be empty.")
        return normalized

    @field_validator("input_type")
    @classmethod
    def validate_input_type(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        if normalized not in MANUAL_INPUT_TYPES:
            raise ValueError(f"Unsupported manual input type: {normalized}")
        return normalized


class CanonicalEligibilityRule(BaseModel):
    scheme_id: str
    rule_name: str
    include_conditions: List[EligibilityCondition] = Field(default_factory=list)
    exclude_conditions: List[EligibilityCondition] = Field(default_factory=list)
    unmapped_conditions: List[UnmappedCondition] = Field(default_factory=list)

    @field_validator("scheme_id", "rule_name")
    @classmethod
    def validate_top_level_text(cls, value: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("Top-level canonical rule fields must not be empty.")
        return normalized


def _condition(field: str, operator: str, value: Optional[Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"field": field, "operator": operator}
    if value is not None:
        payload["value"] = value
    return payload


def build_canonical_rule_from_legacy(
    scheme_id: str,
    rule_name: str,
    include_conditions: Optional[Dict[str, Any]],
    exclude_conditions: Optional[Dict[str, Any]],
    unmapped_criteria: Optional[List[str]] = None,
) -> Dict[str, Any]:
    include_conditions = include_conditions or {}
    exclude_conditions = exclude_conditions or {}
    canonical_include: List[Dict[str, Any]] = []
    canonical_exclude: List[Dict[str, Any]] = []

    if include_conditions.get("age_min") is not None:
        canonical_include.append(_condition("age", ">=", int(include_conditions["age_min"])))
    if include_conditions.get("age_max") is not None:
        canonical_include.append(_condition("age", "<=", int(include_conditions["age_max"])))
    if include_conditions.get("gender_in"):
        canonical_include.append(_condition("gender", "in", list(include_conditions["gender_in"])))
    if include_conditions.get("marital_status_in"):
        canonical_include.append(
            _condition("marital_status", "in", list(include_conditions["marital_status_in"]))
        )
    if include_conditions.get("income_max") is not None:
        canonical_include.append(
            _condition("annual_income", "<=", float(include_conditions["income_max"]))
        )
    if include_conditions.get("requires_disability") is True:
        canonical_include.append(_condition("is_disabled", "=", True))
    if include_conditions.get("employment_status_in"):
        canonical_include.append(
            _condition(
                "employment_status",
                "in",
                list(include_conditions["employment_status_in"]),
            )
        )
    if include_conditions.get("min_service_months") is not None:
        canonical_include.append(
            _condition(
                "service_duration_months",
                ">=",
                int(include_conditions["min_service_months"]),
            )
        )
    if include_conditions.get("ida_covered_required") is True:
        canonical_include.append(_condition("ida_covered", "=", True))

    if exclude_conditions.get("conflict_scheme_ids"):
        canonical_exclude.append(
            _condition("scheme_id", "in", list(exclude_conditions["conflict_scheme_ids"]))
        )
    if exclude_conditions.get("employment_status_not_in"):
        canonical_exclude.append(
            _condition(
                "employment_status",
                "in",
                list(exclude_conditions["employment_status_not_in"]),
            )
        )
    if exclude_conditions.get("exclude_if_receives_pension") is True:
        canonical_exclude.append(_condition("receives_pension", "=", True))
    if exclude_conditions.get("exclude_if_retired_or_terminated") is True:
        canonical_exclude.append(_condition("retired_or_terminated", "=", True))
    if exclude_conditions.get("exclude_if_reemployed_same_factory") is True:
        canonical_exclude.append(_condition("reemployed_same_factory", "=", True))

    canonical_unmapped = [
        normalize_unmapped_condition_payload({"requirement": str(item).strip()})
        for item in (unmapped_criteria or [])
        if str(item).strip()
    ]

    payload = CanonicalEligibilityRule(
        scheme_id=scheme_id,
        rule_name=rule_name,
        include_conditions=canonical_include,
        exclude_conditions=canonical_exclude,
        unmapped_conditions=canonical_unmapped,
    )
    return payload.model_dump()


def validate_canonical_rule_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    validated = CanonicalEligibilityRule.model_validate(payload)
    return validated.model_dump()


def sanitize_canonical_rule_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    validated = validate_canonical_rule_payload(payload)
    include_conditions = list(validated.get("include_conditions", []))
    exclude_conditions = list(validated.get("exclude_conditions", []))
    unmapped_conditions = list(validated.get("unmapped_conditions", []))

    cleaned_include: List[Dict[str, Any]] = []
    cleaned_exclude: List[Dict[str, Any]] = []

    for condition in include_conditions:
        downgraded = _downgrade_invalid_condition(condition, "include")
        if downgraded is not None:
            unmapped_conditions.append(downgraded)
            continue
        cleaned_include.append(condition)

    for condition in exclude_conditions:
        downgraded = _downgrade_invalid_condition(condition, "exclude")
        if downgraded is not None:
            unmapped_conditions.append(downgraded)
            continue
        cleaned_exclude.append(condition)

    final_payload = {
        **validated,
        "include_conditions": cleaned_include,
        "exclude_conditions": cleaned_exclude,
        "unmapped_conditions": dedupe_unmapped_conditions(unmapped_conditions),
    }
    return CanonicalEligibilityRule.model_validate(final_payload).model_dump()


def _downgrade_invalid_condition(
    condition: Dict[str, Any], bucket: str
) -> Optional[Dict[str, Any]]:
    field_name = str(condition.get("field") or "").strip()
    if field_name != "scheme_id":
        return None

    operator = str(condition.get("operator") or "").strip()
    if operator not in {"=", "!=", "in", "not_in"}:
        return None

    values = condition.get("value")
    if isinstance(values, list):
        value_list = [str(item).strip() for item in values if str(item).strip()]
    else:
        value_list = [str(values).strip()] if str(values or "").strip() else []

    if not value_list:
        return None

    if all(SCHEME_CODE_PATTERN.match(item) for item in value_list):
        return None

    source_phrase = str(condition.get("evidence_quote") or value_list[0]).strip()
    normalized = normalize_unmapped_condition_payload(
        {
            "requirement": (
                f"Excluded if covered under {source_phrase}"
                if bucket == "exclude"
                else source_phrase
            ),
            "evidence_quote": condition.get("evidence_quote"),
        }
    )
    normalized["reason_unmapped"] = (
        f"Condition used field 'scheme_id' with non-code value(s) {value_list}, so it was downgraded "
        "to a manual-review condition."
    )
    return normalized


def _dedupe_unmapped_condition(condition: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "requirement": str(condition.get("requirement") or "").strip(),
        "suggested_input_field": str(condition.get("suggested_input_field") or "").strip(),
        "input_type": str(condition.get("input_type") or "text").strip().lower(),
        "reason_unmapped": str(condition.get("reason_unmapped") or "").strip(),
        "evidence_quote": condition.get("evidence_quote"),
    }


def dedupe_unmapped_conditions(conditions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in conditions:
        cleaned = _dedupe_unmapped_condition(raw)
        key = (cleaned["suggested_input_field"], cleaned["requirement"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
    return deduped


def merge_canonical_rule_payloads(
    base_payload: Dict[str, Any], fallback_payload: Dict[str, Any]
) -> Dict[str, Any]:
    merged_include = dedupe_condition_list(
        list(base_payload.get("include_conditions", []))
        + list(fallback_payload.get("include_conditions", []))
    )
    merged_exclude = dedupe_condition_list(
        list(base_payload.get("exclude_conditions", []))
        + list(fallback_payload.get("exclude_conditions", []))
    )
    merged_unmapped = dedupe_unmapped_conditions(
        list(base_payload.get("unmapped_conditions", []))
        + list(fallback_payload.get("unmapped_conditions", []))
    )

    return CanonicalEligibilityRule.model_validate(
        {
            "scheme_id": base_payload.get("scheme_id") or fallback_payload.get("scheme_id"),
            "rule_name": base_payload.get("rule_name") or fallback_payload.get("rule_name"),
            "include_conditions": merged_include,
            "exclude_conditions": merged_exclude,
            "unmapped_conditions": merged_unmapped,
        }
    ).model_dump()


def dedupe_condition_list(conditions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for condition in conditions:
        field_name = str(condition.get("field") or "").strip()
        operator = str(condition.get("operator") or "").strip()
        value_repr = repr(condition.get("value"))
        key = (field_name, operator, value_repr)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(condition)
    return deduped


def build_llm_field_registry() -> Dict[str, Any]:
    fields = {}
    for field_name, field_type in FIELD_TYPES.items():
        fields[field_name] = {
            "type": field_type,
            "description": FIELD_DESCRIPTIONS.get(field_name, field_name),
            "supported_operators": sorted(ALLOWED_OPERATORS_BY_TYPE.get(field_type, set())),
        }
    return {
        "description": "Available logical fields for eligibility rules",
        "fields": fields,
    }


def manual_input_type_for_field(field_name: str) -> str:
    normalized = str(field_name).strip().lower()
    if normalized.startswith(("has_", "is_", "exclude_", "receives_", "covered_", "eligible_")):
        return "boolean"
    field_type = FIELD_TYPES.get(field_name) or MANUAL_ONLY_FIELD_TYPES.get(field_name, "text")
    if field_type == "boolean":
        return "boolean"
    if field_type == "number":
        return "number"
    return "text"


def normalize_policy_concept(concept: str) -> Dict[str, str]:
    normalized = str(concept).strip()
    if not normalized:
        return {"concept": "", "field": "", "input_type": "text", "mapped": "false"}

    lookup_key = normalized.lower()
    mapping = POLICY_CONCEPT_FIELD_MAP.get(lookup_key)
    if mapping:
        return {
            "concept": normalized,
            "field": mapping["field"],
            "input_type": mapping["input_type"],
            "mapped": "true",
        }

    heuristic = _normalize_policy_phrase(lookup_key)
    if heuristic:
        return {
            "concept": normalized,
            "field": heuristic["field"],
            "input_type": heuristic["input_type"],
            "mapped": "true",
        }

    return {
        "concept": normalized,
        "field": normalized,
        "input_type": manual_input_type_for_field(normalized),
        "mapped": "false",
    }


def _normalize_policy_phrase(text: str) -> Optional[Dict[str, str]]:
    if "west bengal" in text and ("resident" in text or "residency" in text):
        return {"field": "has_west_bengal_residency", "input_type": "boolean"}
    if "medical allowance" in text:
        return {"field": "receives_medical_allowance", "input_type": "boolean"}
    if "covered under" in text:
        tokens = [
            token
            for token in re.findall(r"[a-z0-9]+", text.lower())
            if token
            not in {
                "excluded",
                "exclude",
                "if",
                "covered",
                "under",
                "families",
                "family",
                "the",
                "of",
                "and",
                "or",
                "any",
            }
        ]
        stem = "_".join(tokens[:5]) if tokens else "other_scheme"
        return {"field": f"exclude_families_covered_under_{stem}", "input_type": "boolean"}
    if "other category" in text and "state government" in text:
        return {"field": "state_notified_category_eligibility", "input_type": "boolean"}
    if "permanent resident" in text:
        return {"field": "permanent_residency_status", "input_type": "boolean"}

    if " " not in text:
        return None

    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token
        and token
        not in {
            "the",
            "of",
            "and",
            "or",
            "to",
            "for",
            "a",
            "an",
            "as",
            "be",
            "by",
            "from",
            "with",
            "in",
            "on",
            "any",
            "may",
            "is",
            "are",
            "time",
        }
    ]
    if not tokens:
        return None

    stem = "_".join(tokens[:6])
    boolean_signals = {
        "resident",
        "residency",
        "eligible",
        "eligibility",
        "employee",
        "employed",
        "drawing",
        "receiving",
        "receives",
        "belongs",
        "belongs_to",
        "category",
        "allowance",
    }
    input_type = "boolean" if any(signal in tokens for signal in boolean_signals) else "text"
    prefix = "has_" if input_type == "boolean" else ""
    return {"field": f"{prefix}{stem}", "input_type": input_type}


def normalize_unmapped_condition_payload(condition: Dict[str, Any]) -> Dict[str, Any]:
    requirement = str(
        condition.get("requirement") or condition.get("suggested_input_field") or ""
    ).strip()
    normalized = normalize_policy_concept(requirement)
    mapped = normalized.get("mapped") == "true"
    return {
        "requirement": requirement,
        "suggested_input_field": normalized.get("field") or requirement,
        "input_type": normalized.get("input_type") or str(condition.get("input_type") or "text"),
        "reason_unmapped": (
            f"Policy concept '{requirement}' is not yet executable from the current dataset and has been normalized to manual field '{normalized.get('field')}'."
            if mapped and normalized.get("field") and normalized.get("field") != requirement
            else str(
                condition.get("reason_unmapped")
                or "Detected criterion is not yet mapped to the executable field registry."
            )
        ),
        "evidence_quote": condition.get("evidence_quote"),
    }
