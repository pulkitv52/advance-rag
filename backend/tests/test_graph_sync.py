from src.services import graph_sync


def test_format_profile_rows_builds_enrollment_shape():
    rows = [
        {
            "uid": " 12345 ",
            "scheme_id": "S100",
            "scheme_beneficiary_id": "BEN-1",
            "source_family": "SCHEME_CASH",
            "source_table": "scheme_beneficiary_cash",
            "fullname": "Jane Doe",
            "gender": "female",
            "member_dob": "1990-01-02",
            "mobile": "9999999999",
            "ration_card_number": "RC1",
            "ration_card_memberid": "M1",
            "address": "  Some Lane ",
            "lgd_district_code": "101",
            "lgd_district_name": "District",
            "lgd_block_code": "202",
            "lgd_block_name": "Block",
            "lgd_gp_code": "303",
            "lgd_gp_name": "GP",
            "approved_date": "2026-01-01 00:00:00",
            "closing_date": None,
            "closure_remarks": None,
            "grade": "1",
            "rc_match_type": "UID",
            "rc_member_status": "ACTIVE",
            "transaction_rows": 3,
            "transaction_total_amount": 450.5,
            "latest_transaction_timestamp": "2026-02-01 00:00:00",
            "latest_transaction_ref_no": "REF-1",
            "first_transaction_timestamp": "2026-01-15 00:00:00",
            "installment_count": 2,
            "financial_years": ["2526"],
            "duplicate_group_size": 1,
            "completeness_score": 9,
            "tran_count_1": 1,
            "tran_count_2": 2,
        }
    ]

    formatted = graph_sync._format_profile_rows(rows)

    assert formatted[0]["uid"] == "12345"
    assert formatted[0]["enrollment_key"] == "12345:BEN-1"
    assert formatted[0]["enrollment_status"] == "Active"
    assert formatted[0]["address_sanitized"] == "SOME LANE"
    assert formatted[0]["financial_years"] == ["2526"]
    assert formatted[0]["transaction_rows"] == 3


def test_format_payout_rows_builds_payout_month_key():
    rows = [
        {
            "uid": "12345",
            "scheme_id": "S100",
            "scheme_beneficiary_id": "BEN-1",
            "financial_year": "2526",
            "installment_year": "2026",
            "installment_month_code": "JAN",
            "installment_month": "JAN",
            "transaction_count": 4,
            "total_amount": 1000,
            "latest_transaction_timestamp": "2026-01-31 00:00:00",
            "latest_transaction_ref_no": "REF-2",
        }
    ]

    formatted = graph_sync._format_payout_rows(rows)

    assert formatted[0]["enrollment_key"] == "12345:BEN-1"
    assert formatted[0]["payout_month_key"] == "S100:2526:2026:JAN"
    assert formatted[0]["payout_month_label"] == "JAN 2026"
    assert formatted[0]["transaction_count"] == 4


def test_per_scheme_parser_accepts_flag():
    parser = graph_sync.argparse.ArgumentParser()
    parser.add_argument("limit", nargs="?", type=int, default=None)
    parser.add_argument("--per-scheme-limit", type=int, default=None)

    args = parser.parse_args(["--per-scheme-limit", "1000"])

    assert args.limit is None
    assert args.per_scheme_limit == 1000
