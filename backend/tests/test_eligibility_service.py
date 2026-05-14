from src.models.eligibility import EligibilityRule
from src.services.eligibility import (
    _build_priority_criteria_context,
    detect_scheme_id_from_filename,
    evaluate_citizen_against_rule,
    extract_eligibility_metadata,
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
