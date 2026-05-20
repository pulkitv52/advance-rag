from src.models.eligibility import EligibilityRule
from src.services.eligibility import (
    _build_priority_criteria_context,
    _extract_keyword_fallback_unmapped_conditions,
    detect_scheme_id_from_filename,
    evaluate_citizen_against_rule,
    extract_eligibility_metadata,
)
from src.services.eligibility_schema import (
    build_canonical_rule_from_legacy,
    merge_canonical_rule_payloads,
    normalize_policy_concept,
    normalize_unmapped_condition_payload,
    sanitize_canonical_rule_payload,
    validate_canonical_rule_payload,
)


def test_extract_eligibility_metadata_from_policy_text():
    text = """
    Scheme S767 is applicable for female widows only.
    Minimum age 18 and maximum age 60.
    Annual income should be less than Rs 120000.
    Beneficiary must not be enrolled in SS_001.
    """

    meta = extract_eligibility_metadata(text, scheme_id="S767")

    assert meta["scheme_id"] == "S767"
    assert meta["include_conditions"]["age_min"] == 18
    assert meta["include_conditions"]["age_max"] == 60
    assert "FEMALE" in meta["include_conditions"]["gender_in"]
    assert "WIDOW" in meta["include_conditions"]["marital_status_in"]
    assert meta["include_conditions"]["income_max"] == 120000.0
    assert "SS_001" in meta["exclude_conditions"]["conflict_scheme_ids"]


def test_extract_eligibility_metadata_parses_lakh_income_amount():
    text = "Annual income should be less than Rs 2 lakh."

    meta = extract_eligibility_metadata(text, scheme_id="C501")

    assert meta["include_conditions"]["income_max"] == 200000.0


def test_extract_eligibility_metadata_parses_crore_income_amount():
    text = "Family income must not exceed INR 1.5 crore."

    meta = extract_eligibility_metadata(text, scheme_id="C501")

    assert meta["include_conditions"]["income_max"] == 15000000.0


def test_keyword_fallback_unmapped_conditions_recovers_scholarship_concepts():
    text = """
    Annual family income should not exceed Rs 2 lakh.
    Applicant must belong to SC or ST category.
    Student must be enrolled in a regular undergraduate course.
    Candidate should not be receiving any other scholarship.
    Institution must be a recognized educational institution.
    """

    fallback = _extract_keyword_fallback_unmapped_conditions(
        text,
        {
            "include_conditions": [
                {"field": "annual_income", "operator": "<=", "value": 200000},
            ],
            "exclude_conditions": [],
            "unmapped_conditions": [],
        },
    )

    fallback_fields = {item["suggested_input_field"] for item in fallback}
    assert "caste" in fallback_fields
    assert "course_level" in fallback_fields
    assert "study_mode" in fallback_fields
    assert "no_other_scholarship" in fallback_fields
    assert "institution_type" in fallback_fields


def test_evaluate_citizen_against_rule_exclusion_error():
    rule = EligibilityRule(
        scheme_id="S767",
        rule_name="Eligibility Rule - S767",
        include_conditions={"age_min": 18, "age_max": 60, "gender_in": ["FEMALE"]},
        exclude_conditions={},
    )

    citizen = {
        "uid": "123",
        "member_dob": "1990-01-01",
        "gender": "FEMALE",
        "scheme_id": "SS_001",
    }

    outcome = evaluate_citizen_against_rule(citizen, rule)
    assert outcome["decision"] == "EXCLUSION_ERROR"
    assert outcome["is_eligible"] is True
    assert outcome["is_enrolled_in_target"] is False
    assert "not enrolled in target scheme S767" in outcome["reason"]
    assert "Passed checks:" in outcome["reason"]


def test_evaluate_citizen_against_rule_inclusion_error():
    rule = EligibilityRule(
        scheme_id="S767",
        rule_name="Eligibility Rule - S767",
        include_conditions={"age_min": 18, "age_max": 60, "gender_in": ["FEMALE"]},
        exclude_conditions={},
    )

    citizen = {
        "uid": "123",
        "member_dob": "2015-01-01",
        "gender": "MALE",
        "scheme_id": "S767",
    }

    outcome = evaluate_citizen_against_rule(citizen, rule)
    assert outcome["decision"] == "INCLUSION_ERROR"
    assert outcome["is_eligible"] is False
    assert outcome["is_enrolled_in_target"] is True
    assert "enrolled in target scheme S767 but failed eligibility checks" in outcome["reason"]
    assert "Failed checks:" in outcome["reason"]


def test_detect_scheme_id_from_filename_s_prefix():
    detected = detect_scheme_id_from_filename("doc_GE_S767_0.pdf")
    assert detected["scheme_id"] == "S767"
    assert detected["confidence"] == "HIGH"


def test_detect_scheme_id_from_filename_s_with_leading_zero():
    detected = detect_scheme_id_from_filename("doc_LB_S051_1.pdf")
    assert detected["scheme_id"] == "S051"
    assert "S051" in detected["candidates"]


def test_detect_scheme_id_from_filename_c_prefix():
    detected = detect_scheme_id_from_filename("doc_QB_C501_0.pdf")
    assert detected["scheme_id"] == "C501"
    assert "C501" in detected["candidates"]


def test_non_blocking_unmapped_criteria_do_not_force_review_required():
    rule = EligibilityRule(
        scheme_id="S767",
        rule_name="Eligibility Rule - S767",
        include_conditions={"age_max": 58},
        exclude_conditions={},
        extracted_metadata={"unmapped_criteria": ["eligibility_scope", "exclusion_list"]},
    )

    citizen = {
        "uid": "123",
        "member_dob": "1940-01-01",
        "gender": "FEMALE",
        "scheme_id": "S767",
    }

    outcome = evaluate_citizen_against_rule(citizen, rule)
    assert outcome["decision"] == "INCLUSION_ERROR"
    assert "Failed checks:" in outcome["reason"]


def test_missing_required_feature_returns_review_required():
    rule = EligibilityRule(
        scheme_id="S767",
        rule_name="Eligibility Rule - S767",
        include_conditions={"employment_status_in": ["ACTIVE"]},
        exclude_conditions={},
    )

    citizen = {
        "uid": "123",
        "scheme_id": "S767",
        "employment_status": None,
    }

    outcome = evaluate_citizen_against_rule(citizen, rule)
    assert outcome["decision"] == "REVIEW_REQUIRED"
    assert "employment_status" in outcome["reason"]


def test_priority_criteria_context_extracts_relevant_windows():
    text = """
    This circular contains administrative notes.
    Eligibility: retired tea garden workers can apply.
    Inclusion criteria: age between 18 and 60, and annual income below 120000.
    Exclusion criteria: not eligible if receives pension.
    Other annexure details follow.
    """

    focused = _build_priority_criteria_context(text)

    assert focused["focused_text"]
    assert "retired tea garden workers can apply" in focused["focused_text"].lower()
    assert "not eligible if receives pension" in focused["focused_text"].lower()
    assert "eligibility" in focused["matches"]


def test_build_canonical_rule_from_legacy_maps_conditions():
    payload = build_canonical_rule_from_legacy(
        scheme_id="S767",
        rule_name="Eligibility Rule - S767",
        include_conditions={
            "age_min": 18,
            "age_max": 60,
            "gender_in": ["FEMALE"],
            "income_max": 120000,
            "requires_disability": True,
        },
        exclude_conditions={
            "conflict_scheme_ids": ["SS_001"],
            "exclude_if_receives_pension": True,
        },
        unmapped_criteria=["residency_requirement"],
    )

    assert payload["scheme_id"] == "S767"
    assert payload["rule_name"] == "Eligibility Rule - S767"
    assert {
        "field": "age",
        "operator": ">=",
        "value": 18,
        "value_type": "number",
        "evidence_quote": None,
    } in payload["include_conditions"]
    assert {
        "field": "age",
        "operator": "<=",
        "value": 60,
        "value_type": "number",
        "evidence_quote": None,
    } in payload["include_conditions"]
    assert {
        "field": "gender",
        "operator": "in",
        "value": ["FEMALE"],
        "value_type": "text",
        "evidence_quote": None,
    } in payload["include_conditions"]
    assert {
        "field": "annual_income",
        "operator": "<=",
        "value": 120000.0,
        "value_type": "number",
        "evidence_quote": None,
    } in payload["include_conditions"]
    assert {
        "field": "is_disabled",
        "operator": "=",
        "value": True,
        "value_type": "boolean",
        "evidence_quote": None,
    } in payload["include_conditions"]
    assert {
        "field": "scheme_id",
        "operator": "in",
        "value": ["SS_001"],
        "value_type": "text",
        "evidence_quote": None,
    } in payload["exclude_conditions"]
    assert {
        "field": "receives_pension",
        "operator": "=",
        "value": True,
        "value_type": "boolean",
        "evidence_quote": None,
    } in payload["exclude_conditions"]
    assert payload["unmapped_conditions"][0]["suggested_input_field"] == "residency_requirement"


def test_validate_canonical_rule_payload_rejects_invalid_boolean_operator():
    payload = {
        "scheme_id": "S767",
        "rule_name": "Eligibility Rule - S767",
        "include_conditions": [
            {"field": "is_disabled", "operator": "in", "value": [True]},
        ],
        "exclude_conditions": [],
        "unmapped_conditions": [],
    }

    try:
        validate_canonical_rule_payload(payload)
        assert False, "Expected canonical validation to fail for invalid boolean operator."
    except ValueError as exc:
        assert "not allowed" in str(exc)


def test_validate_canonical_rule_payload_accepts_valid_manual_condition_shape():
    payload = {
        "scheme_id": "S767",
        "rule_name": "Eligibility Rule - S767",
        "include_conditions": [
            {"field": "gender", "operator": "in", "value": ["FEMALE"]},
            {"field": "age", "operator": ">=", "value": 18},
        ],
        "exclude_conditions": [],
        "unmapped_conditions": [
            {
                "requirement": "Must have 10 years residency",
                "suggested_input_field": "has_10_year_residency",
                "input_type": "boolean",
                "reason_unmapped": "No residency field is available in the curated dataset.",
            }
        ],
    }

    validated = validate_canonical_rule_payload(payload)
    assert validated["include_conditions"][0]["value_type"] == "text"
    assert validated["include_conditions"][1]["value_type"] == "number"
    assert validated["unmapped_conditions"][0]["input_type"] == "boolean"


def test_normalize_policy_concept_maps_common_scheme_terms():
    assert normalize_policy_concept("caste_category")["field"] == "caste"
    assert normalize_policy_concept("gender_restriction")["field"] == "gender"
    assert normalize_policy_concept("institution_eligibility")["field"] == "institution_type"
    assert normalize_policy_concept("no_other_scholarship")["input_type"] == "boolean"
    assert normalize_policy_concept("course_mode")["field"] == "study_mode"


def test_normalize_unmapped_condition_payload_rewrites_policy_concept():
    payload = normalize_unmapped_condition_payload({"requirement": "gender_restriction"})
    assert payload["suggested_input_field"] == "gender"
    assert payload["input_type"] == "text"
    assert "normalized to manual field 'gender'" in payload["reason_unmapped"]


def test_normalize_policy_phrase_rewrites_sentence_style_requirement():
    payload = normalize_unmapped_condition_payload(
        {"requirement": "Permanent resident of West Bengal"}
    )
    assert payload["suggested_input_field"] == "has_west_bengal_residency"
    assert payload["input_type"] == "boolean"

    payload = normalize_unmapped_condition_payload(
        {
            "requirement": "Employee of State or Central Government drawing Medical Allowance (unless forfeited)"
        }
    )
    assert payload["suggested_input_field"] == "receives_medical_allowance"
    assert payload["input_type"] == "boolean"

    payload = normalize_unmapped_condition_payload(
        {"requirement": "Excluded if covered under West Bengal Health Scheme, 2008"}
    )
    assert payload["suggested_input_field"].startswith("exclude_families_covered_under_")
    assert payload["input_type"] == "boolean"


def test_sanitize_canonical_rule_payload_downgrades_non_code_scheme_exclusions():
    payload = sanitize_canonical_rule_payload(
        {
            "scheme_id": "S767",
            "rule_name": "LLM Extracted Eligibility Rule",
            "include_conditions": [],
            "exclude_conditions": [
                {
                    "field": "scheme_id",
                    "operator": "=",
                    "value": "West Bengal Health Scheme, 2008",
                    "value_type": "text",
                    "evidence_quote": "Families covered under West Bengal Health Scheme, 2008",
                }
            ],
            "unmapped_conditions": [],
        }
    )

    assert payload["exclude_conditions"] == []
    assert len(payload["unmapped_conditions"]) == 1
    assert payload["unmapped_conditions"][0]["suggested_input_field"].startswith("exclude_")
    assert "downgraded" in payload["unmapped_conditions"][0]["reason_unmapped"]


def test_sanitize_canonical_rule_payload_keeps_real_scheme_codes():
    payload = sanitize_canonical_rule_payload(
        {
            "scheme_id": "S767",
            "rule_name": "LLM Extracted Eligibility Rule",
            "include_conditions": [],
            "exclude_conditions": [
                {
                    "field": "scheme_id",
                    "operator": "=",
                    "value": "SS_001",
                    "value_type": "text",
                    "evidence_quote": "Already enrolled in SS_001",
                }
            ],
            "unmapped_conditions": [],
        }
    )

    assert len(payload["exclude_conditions"]) == 1
    assert payload["unmapped_conditions"] == []


def test_merge_canonical_rule_payloads_adds_fallback_conditions_without_duplicates():
    base = {
        "scheme_id": "S767",
        "rule_name": "LLM Extracted Eligibility Rule",
        "include_conditions": [],
        "exclude_conditions": [],
        "unmapped_conditions": [],
    }
    fallback = {
        "scheme_id": "S767",
        "rule_name": "Regex Fallback Eligibility Rule",
        "include_conditions": [
            {
                "field": "gender",
                "operator": "in",
                "value": ["FEMALE"],
                "value_type": "text",
                "evidence_quote": None,
            }
        ],
        "exclude_conditions": [],
        "unmapped_conditions": [
            {
                "requirement": "gender_restriction",
                "suggested_input_field": "gender",
                "input_type": "text",
                "reason_unmapped": "fallback",
                "evidence_quote": None,
            }
        ],
    }

    merged = merge_canonical_rule_payloads(base, fallback)
    assert len(merged["include_conditions"]) == 1
    assert merged["include_conditions"][0]["field"] == "gender"
    assert len(merged["unmapped_conditions"]) == 1


def test_evaluate_canonical_rule_valid_enrollment():
    rule = EligibilityRule(
        scheme_id="S767",
        rule_name="Eligibility Rule - S767",
        include_conditions={},
        exclude_conditions={},
        extracted_metadata={
            "canonical_rule": {
                "scheme_id": "S767",
                "rule_name": "Eligibility Rule - S767",
                "include_conditions": [
                    {"field": "age", "operator": ">=", "value": 18},
                    {"field": "gender", "operator": "in", "value": ["FEMALE"]},
                ],
                "exclude_conditions": [
                    {"field": "receives_pension", "operator": "=", "value": True},
                ],
                "unmapped_conditions": [],
            }
        },
    )

    citizen = {
        "uid": "123",
        "member_dob": "1990-01-01",
        "gender": "FEMALE",
        "scheme_id": "S767",
        "receives_pension": False,
    }

    outcome = evaluate_citizen_against_rule(citizen, rule)
    assert outcome["decision"] == "VALID_ENROLLMENT"
    assert outcome["is_eligible"] is True


def test_evaluate_canonical_rule_requires_manual_boolean_input():
    rule = EligibilityRule(
        scheme_id="S767",
        rule_name="Eligibility Rule - S767",
        include_conditions={},
        exclude_conditions={},
        extracted_metadata={
            "canonical_rule": {
                "scheme_id": "S767",
                "rule_name": "Eligibility Rule - S767",
                "include_conditions": [
                    {"field": "gender", "operator": "in", "value": ["FEMALE"]},
                ],
                "exclude_conditions": [],
                "unmapped_conditions": [
                    {
                        "requirement": "Must have 10 years residency",
                        "suggested_input_field": "has_10_year_residency",
                        "input_type": "boolean",
                        "reason_unmapped": "No residency field is available in the curated dataset.",
                    }
                ],
            }
        },
    )

    citizen = {
        "uid": "123",
        "member_dob": "1990-01-01",
        "gender": "FEMALE",
        "scheme_id": "S767",
    }

    outcome = evaluate_citizen_against_rule(citizen, rule)
    assert outcome["decision"] == "REVIEW_REQUIRED"
    assert "has_10_year_residency" in outcome["reason"]

    citizen["has_10_year_residency"] = True
    resolved = evaluate_citizen_against_rule(citizen, rule)
    assert resolved["decision"] == "VALID_ENROLLMENT"


def test_evaluate_canonical_rule_treats_boolean_manual_no_as_resolved():
    rule = EligibilityRule(
        scheme_id="S767",
        rule_name="Eligibility Rule - S767",
        include_conditions={},
        exclude_conditions={},
        extracted_metadata={
            "canonical_rule": {
                "scheme_id": "S767",
                "rule_name": "Eligibility Rule - S767",
                "include_conditions": [
                    {"field": "gender", "operator": "in", "value": ["FEMALE"]},
                ],
                "exclude_conditions": [],
                "unmapped_conditions": [
                    {
                        "requirement": "State/Central Government employee may opt in after fully foregoing medical allowance",
                        "suggested_input_field": "receives_medical_allowance",
                        "input_type": "boolean",
                        "reason_unmapped": "Manual review field.",
                    },
                    {
                        "requirement": "Any other category as may be notified by the State Government from time to time",
                        "suggested_input_field": "state_notified_category_eligibility",
                        "input_type": "boolean",
                        "reason_unmapped": "Manual review field.",
                    },
                    {
                        "requirement": "Duplicate medical allowance check",
                        "suggested_input_field": "receives_medical_allowance",
                        "input_type": "boolean",
                        "reason_unmapped": "Duplicate manual review field.",
                    },
                ],
            }
        },
    )

    citizen = {
        "uid": "123",
        "member_dob": "1990-01-01",
        "gender": "FEMALE",
        "scheme_id": "S767",
        "receives_medical_allowance": False,
        "state_notified_category_eligibility": False,
    }

    outcome = evaluate_citizen_against_rule(citizen, rule)
    assert outcome["decision"] == "VALID_ENROLLMENT"
    assert outcome["blocking_unmapped_criteria"] == []
