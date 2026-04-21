from src.routers.query import (
    _extract_possible_person_name,
    _extract_possible_uid,
    _is_usr_fraud_question,
)


def test_extract_name_from_does_come_under_pattern():
    q = "does Pramila das comes under fraud if yes give details about her"
    name = _extract_possible_person_name(q)
    assert name is not None
    assert "pramila" in name.lower()
    assert "das" in name.lower()


def test_extract_name_from_quoted_pattern():
    q = 'Is "Pramila Das" flagged as fraud?'
    assert _extract_possible_person_name(q) == "Pramila Das"


def test_extract_name_from_about_pattern():
    q = "Give details about Pramila Das"
    name = _extract_possible_person_name(q)
    assert name == "Pramila Das"


def test_extract_name_with_trailing_having_word():
    q = "Is Pramila das having fraud?"
    name = _extract_possible_person_name(q)
    assert name is not None
    assert name.lower() == "pramila das"


def test_usr_fraud_question_detection():
    assert _is_usr_fraud_question("Is Pramila Das fraud?")
    assert _is_usr_fraud_question("show duplicate flags for this citizen")
    assert not _is_usr_fraud_question("summarize chapter 3 of this policy")


def test_extract_possible_uid():
    q = "does Pramila das having uid : 599031892622 comes under fraud"
    assert _extract_possible_uid(q) == "599031892622"
