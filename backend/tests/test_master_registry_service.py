import asyncio

from src.services import master_registry


def test_person_detail_upsert_sql_adds_pilot_district_filter():
    sql = master_registry.build_person_detail_upsert_sql(district_code=303)

    assert "FROM srsadmin.rc_beneficiary rc" in sql
    assert "WHERE rc.lgd_district_code = :district_code" in sql
    assert "ON CONFLICT (ration_card_memberid) DO UPDATE" in sql


def test_person_detail_upsert_sql_omits_filter_for_full_rollout():
    sql = master_registry.build_person_detail_upsert_sql()

    assert "WHERE rc.lgd_district_code = :district_code" not in sql
    assert ":district_code" not in sql


def test_person_scheme_enrollment_sql_is_idempotent_and_has_fallback_join():
    sql = master_registry.build_person_scheme_enrollment_upsert_sql(district_code=303)

    assert "INSERT INTO srsadmin.person_scheme_enrollment" in sql
    assert "ON CONFLICT (ration_card_memberid, scheme_id) DO UPDATE" in sql
    assert "rc.ration_card_memberid = sc.ration_card_memberid" in sql
    assert "rc.ration_card_memberid = ss.ration_card_memberid" in sql
    assert "WHERE sc.lgd_district_code = :district_code" in sql
    assert "WHERE ss.lgd_district_code = :district_code" in sql


def test_registry_statements_include_schema_loads_and_validation_queries():
    statements = master_registry.build_registry_statements(
        district_code=303,
        include_schema=True,
        include_person_detail=True,
        include_person_scheme_enrollment=True,
        include_validation_queries=True,
    )

    keys = [statement.key for statement in statements]

    assert "create_person_detail" in keys
    assert "create_enrollment_eligibility_view" in keys
    assert "create_person_detail_uid_index" in keys
    assert "load_person_detail" in keys
    assert "load_person_scheme_enrollment" in keys
    assert "person_detail_row_count" in keys
    assert len(statements) == 16


def test_validation_queries_use_district_filter_when_requested():
    queries = master_registry.build_validation_queries(district_code=303)

    assert len(queries) == 5
    assert all(query.kind == "validation" for query in queries)
    assert "WHERE lgd_district_code = :district_code" in queries[0].statement
    assert "WHERE sc.lgd_district_code = :district_code" in queries[3].statement


class _FakeResult:
    def __init__(self, rowcount: int):
        self.rowcount = rowcount


class _FakeSession:
    def __init__(self):
        self.calls = []
        self.committed = False

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return _FakeResult(rowcount=1)

    async def commit(self):
        self.committed = True


class _FakeMappingsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeValidationResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return _FakeMappingsResult(self._rows)


class _FakeValidationSession:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return _FakeValidationResult([{"value": 1}])


def test_execute_registry_build_runs_selected_statements_with_params():
    session = _FakeSession()

    results = asyncio.run(
        master_registry.execute_registry_build(
            session=session,
            district_code=303,
            include_schema=False,
            include_person_detail=True,
            include_person_scheme_enrollment=False,
        )
    )

    assert session.committed is True
    assert len(session.calls) == 1
    assert session.calls[0][1] == {"district_code": 303}
    assert len(results) == 1
    assert results[0]["key"] == "load_person_detail"
    assert results[0]["success"] is True


def test_execute_validation_queries_returns_serialized_rows():
    session = _FakeValidationSession()

    results = asyncio.run(master_registry.execute_validation_queries(session, district_code=303))

    assert len(results) == 5
    assert all(result["kind"] == "validation" for result in results)
    assert results[0]["rows"] == [{"value": 1}]
    assert session.calls[0][1] == {"district_code": 303}


def test_fetch_pilot_summary_returns_expected_keys():
    session = _FakeValidationSession()

    summary = asyncio.run(master_registry.fetch_pilot_summary(session, 303))

    assert summary["district_code"] == 303
    assert summary["person_count"] == 1
    assert summary["enrollment_count"] == 1
    assert summary["eligibility_count"] == 1
    assert summary["person_duplicates"] == 1
    assert summary["enrollment_duplicates"] == 1
    assert summary["max_family_size"] == 1


class _FakeQualityValidationSession:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params):
        sql = str(statement)
        self.calls.append((sql, params))
        if "LIMIT 5" in sql:
            return _FakeValidationResult(
                [
                    {
                        "ration_card_number": "RC1",
                        "family_size": 5,
                        "hof_count": 1,
                        "members_in_s767": 2,
                        "distinct_schemes": 3,
                    }
                ]
            )
        if "LIMIT 10" in sql:
            return _FakeValidationResult(
                [
                    {
                        "scheme_id": "S767",
                        "scheme_type": "SWASTHYA_SATHI",
                        "member_count": 10,
                    }
                ]
            )
        return _FakeValidationResult([{"value": 1}])


def test_fetch_pilot_quality_report_returns_checks_and_samples():
    session = _FakeQualityValidationSession()

    report = asyncio.run(
        master_registry.fetch_pilot_quality_report(session, 303, include_join_loss=False)
    )

    assert report["district_code"] == 303
    assert report["source_person_count"] == 1
    assert report["source_family_count"] == 1
    assert report["output_family_count"] == 1
    assert report["unmatched_cash_scheme_rows"] is None
    assert report["unmatched_swasthya_sathi_rows"] is None
    assert report["largest_family_samples"][0]["ration_card_number"] == "RC1"
    assert report["top_scheme_mix"][0]["scheme_id"] == "S767"
    assert report["checks"]["person_count_matches_source"] is True
    assert report["checks"]["family_count_matches_source"] is True


def test_fetch_join_loss_report_returns_rates():
    session = _FakeValidationSession()

    report = asyncio.run(master_registry.fetch_join_loss_report(session, 303))

    assert report["district_code"] == 303
    assert report["unmatched_cash_scheme_rows"] == 1
    assert report["unmatched_swasthya_sathi_rows"] == 1
    assert report["cash_source_rows"] == 1
    assert report["swasthya_sathi_source_rows"] == 1
    assert report["cash_match_rate_pct"] == 0.0
    assert report["swasthya_sathi_match_rate_pct"] == 0.0


class _FakeRolloutSession:
    def __init__(self):
        self.calls = []
        self.counter = 0

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))
        self.counter += 1
        if "LIMIT 10" in str(statement):
            return _FakeValidationResult([{"lgd_district_code": 303, "person_count": 10}])
        values = [100, 200, 0, 50, 2, 2, 90, 180]
        return _FakeValidationResult([{"value": values[self.counter - 1]}])


def test_fetch_rollout_summary_returns_totals_and_detection_flag():
    session = _FakeRolloutSession()

    summary = asyncio.run(master_registry.fetch_rollout_summary(session))

    assert summary["person_count"] == 100
    assert summary["enrollment_count"] == 200
    assert summary["non_303_person_count"] == 90
    assert summary["non_303_enrollment_count"] == 180
    assert summary["full_rollout_detected"] is True
    assert summary["top_person_districts"][0]["lgd_district_code"] == 303
