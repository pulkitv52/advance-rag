from src.services.eligibility import (
    evaluate_manifest_subject,
    list_fixed_manifests,
    load_fixed_manifest,
)


def test_list_fixed_manifests_includes_seeded_scheme_manifests():
    manifests = list_fixed_manifests()
    scheme_ids = {item["scheme_id"] for item in manifests}

    assert "S767" in scheme_ids
    assert "C501" in scheme_ids


def test_load_fixed_manifest_returns_policy_only_payload():
    manifest = load_fixed_manifest("C501")

    assert manifest["scheme_id"] == "C501"
    assert len(manifest["include_conditions"]) == 7
    assert "mapping_status" not in manifest["include_conditions"][0]


def test_evaluate_manifest_subject_marks_unresolved_conditions_review_required():
    manifest = load_fixed_manifest("C501")
    subject = {
        "ration_card_memberid": "M1",
        "ration_card_number": "R1",
        "uid": "123456789012",
        "fullname": "Test Citizen",
        "caste": "OBC-B",
        "gender": "MALE",
        "lgd_district_code": 303,
        "person_scheme_ids": ["C501"],
        "family_scheme_ids": ["C501", "S767"],
        "family_member_count": 4,
        "male_family_member_count": 2,
        "female_family_member_count": 2,
        "is_enrolled_in_target": True,
        "target_scheme_enrollment_rows": 1,
    }

    result = evaluate_manifest_subject(subject, manifest)

    assert result["final_result"]["eligibility_state"] == "REVIEW_REQUIRED"
    assert "INC_004" in result["final_result"]["unmapped_condition_ids"]
    assert result["enrollment_result"]["is_enrolled"] is True


def test_evaluate_manifest_subject_keeps_s767_in_review_when_exclusions_are_external():
    manifest = load_fixed_manifest("S767")
    subject = {
        "ration_card_memberid": "M2",
        "ration_card_number": "R2",
        "fullname": "Resident Member",
        "gender": "FEMALE",
        "lgd_district_code": 303,
        "person_scheme_ids": ["S767"],
        "family_scheme_ids": ["S767"],
        "family_member_count": 3,
        "male_family_member_count": 1,
        "female_family_member_count": 2,
        "is_enrolled_in_target": True,
        "target_scheme_enrollment_rows": 1,
    }

    result = evaluate_manifest_subject(subject, manifest)

    assert result["final_result"]["eligibility_state"] == "REVIEW_REQUIRED"
    # Residency is derivable, but health-coverage exclusions remain unresolved in the current registry.
    assert "EXC_001" in result["final_result"]["unmapped_condition_ids"]
