from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


StatementKind = Literal["ddl", "dml", "view", "validation"]


@dataclass(frozen=True)
class RegistryStatement:
    key: str
    kind: StatementKind
    statement: str


def _prepare_statement(statement: str):
    try:
        from sqlalchemy import text as sqlalchemy_text

        return sqlalchemy_text(statement)
    except ModuleNotFoundError:
        return statement


PERSON_DETAIL_DDL = """
CREATE TABLE IF NOT EXISTS srsadmin.person_detail (
    ration_card_memberid VARCHAR NOT NULL PRIMARY KEY,
    ration_card_number VARCHAR,
    ration_card_type_code VARCHAR,
    uid VARCHAR,
    uid_verified_status INTEGER,
    fullname VARCHAR,
    member_dob VARCHAR,
    gender VARCHAR,
    caste VARCHAR,
    disability_type VARCHAR,
    mobile VARCHAR,
    is_hof INTEGER,
    hof_member_id VARCHAR,
    relationship_hof VARCHAR,
    father_name VARCHAR,
    mother_name VARCHAR,
    spouse_name VARCHAR,
    rc_member_status VARCHAR,
    rc_approval_date TIMESTAMP,
    rc_closure_date TIMESTAMP,
    lgd_district_code INTEGER,
    lgd_district_name VARCHAR,
    lgd_block_code INTEGER,
    lgd_block_name VARCHAR,
    lgd_gp_code INTEGER,
    lgd_gp_name VARCHAR,
    address VARCHAR,
    last_refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
""".strip()

PERSON_SCHEME_ENROLLMENT_DDL = """
CREATE TABLE IF NOT EXISTS srsadmin.person_scheme_enrollment (
    ration_card_memberid VARCHAR NOT NULL,
    scheme_id VARCHAR NOT NULL,
    scheme_type VARCHAR,
    scheme_beneficiary_id VARCHAR,
    enrollment_status VARCHAR,
    enrollment_grade SMALLINT,
    approved_date TIMESTAMP,
    closing_date TIMESTAMP,
    total_amount_received NUMERIC NOT NULL DEFAULT 0,
    installment_count INTEGER NOT NULL DEFAULT 0,
    first_payment_date TIMESTAMP,
    last_payment_date TIMESTAMP,
    lgd_district_code INTEGER,
    last_refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ration_card_memberid, scheme_id)
)
""".strip()

ELIGIBILITY_STATUS_DDL = """
CREATE TABLE IF NOT EXISTS srsadmin.eligibility_status (
    ration_card_memberid VARCHAR NOT NULL,
    scheme_id VARCHAR NOT NULL,
    is_eligible BOOLEAN,
    is_enrolled BOOLEAN,
    eligibility_state VARCHAR,
    failed_rules TEXT[],
    evaluated_at TIMESTAMPTZ,
    PRIMARY KEY (ration_card_memberid, scheme_id)
)
""".strip()

PERSON_DETAIL_FAMILY_INDEX = """
CREATE INDEX IF NOT EXISTS idx_person_detail_ration_card_number
    ON srsadmin.person_detail (ration_card_number)
""".strip()

PSE_MEMBER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_pse_ration_card_memberid
    ON srsadmin.person_scheme_enrollment (ration_card_memberid)
""".strip()

PERSON_DETAIL_UID_INDEX = """
CREATE INDEX IF NOT EXISTS idx_person_detail_uid
    ON srsadmin.person_detail (uid)
""".strip()

PSE_SCHEME_INDEX = """
CREATE INDEX IF NOT EXISTS idx_pse_scheme_id
    ON srsadmin.person_scheme_enrollment (scheme_id)
""".strip()

PSE_DISTRICT_INDEX = """
CREATE INDEX IF NOT EXISTS idx_pse_district
    ON srsadmin.person_scheme_enrollment (lgd_district_code)
""".strip()

ENROLLMENT_ELIGIBILITY_VIEW = """
CREATE OR REPLACE VIEW srsadmin.enrollment_eligibility AS
SELECT
    pd.ration_card_memberid,
    pd.ration_card_number,
    pd.fullname,
    pd.member_dob,
    pd.gender,
    pd.caste,
    pd.disability_type,
    pd.is_hof,
    pd.hof_member_id,
    pd.relationship_hof,
    pd.ration_card_type_code,
    pd.rc_member_status,
    pd.lgd_district_code,
    pd.lgd_district_name,
    pd.lgd_block_code,
    pd.lgd_block_name,
    pd.lgd_gp_code,
    pd.lgd_gp_name,
    pse.scheme_id,
    pse.scheme_type,
    pse.enrollment_status,
    pse.enrollment_grade,
    pse.approved_date,
    pse.closing_date,
    pse.total_amount_received,
    pse.installment_count,
    pse.first_payment_date,
    pse.last_payment_date,
    es.is_eligible,
    es.is_enrolled,
    es.eligibility_state,
    es.failed_rules,
    es.evaluated_at
FROM srsadmin.person_detail pd
JOIN srsadmin.person_scheme_enrollment pse
    USING (ration_card_memberid)
LEFT JOIN srsadmin.eligibility_status es
    USING (ration_card_memberid, scheme_id)
""".strip()


def _district_filter(alias: str, district_code: Optional[int]) -> str:
    if district_code is None:
        return ""
    return f"WHERE {alias}.lgd_district_code = :district_code"


def build_person_detail_upsert_sql(district_code: Optional[int] = None) -> str:
    district_filter = _district_filter("rc", district_code)
    return f"""
INSERT INTO srsadmin.person_detail (
    ration_card_memberid,
    ration_card_number,
    ration_card_type_code,
    uid,
    uid_verified_status,
    fullname,
    member_dob,
    gender,
    caste,
    disability_type,
    mobile,
    is_hof,
    hof_member_id,
    relationship_hof,
    father_name,
    mother_name,
    spouse_name,
    rc_member_status,
    rc_approval_date,
    rc_closure_date,
    lgd_district_code,
    lgd_district_name,
    lgd_block_code,
    lgd_block_name,
    lgd_gp_code,
    lgd_gp_name,
    address,
    last_refreshed_at
)
SELECT DISTINCT ON (rc.ration_card_memberid)
    rc.ration_card_memberid,
    rc.ration_card_number,
    rc.ration_card_type_code,
    rc.uid,
    rc.uid_verified_status,
    rc.fullname,
    rc.member_dob,
    rc.gender,
    COALESCE(NULLIF(rc.caste_as_caste_data, ''), rc.caste) AS caste,
    rc.reserve_field1 AS disability_type,
    rc.mobile,
    rc.is_hof,
    rc.hof_member_id,
    rc.relationship_hof,
    rc.father_name,
    rc.mother_name,
    rc.spouse_name,
    rc.member_status AS rc_member_status,
    rc.approval_date AS rc_approval_date,
    rc.closure_date AS rc_closure_date,
    rc.lgd_district_code,
    rc.lgd_district_name,
    rc.lgd_block_code,
    rc.lgd_block_name,
    rc.lgd_gp_code,
    rc.lgd_gp_name,
    rc.address,
    NOW() AS last_refreshed_at
FROM srsadmin.rc_beneficiary rc
{district_filter}
ORDER BY rc.ration_card_memberid, rc.entry_ts DESC NULLS LAST
ON CONFLICT (ration_card_memberid) DO UPDATE
SET
    ration_card_number = EXCLUDED.ration_card_number,
    ration_card_type_code = EXCLUDED.ration_card_type_code,
    uid = EXCLUDED.uid,
    uid_verified_status = EXCLUDED.uid_verified_status,
    fullname = EXCLUDED.fullname,
    member_dob = EXCLUDED.member_dob,
    gender = EXCLUDED.gender,
    caste = EXCLUDED.caste,
    disability_type = EXCLUDED.disability_type,
    mobile = EXCLUDED.mobile,
    is_hof = EXCLUDED.is_hof,
    hof_member_id = EXCLUDED.hof_member_id,
    relationship_hof = EXCLUDED.relationship_hof,
    father_name = EXCLUDED.father_name,
    mother_name = EXCLUDED.mother_name,
    spouse_name = EXCLUDED.spouse_name,
    rc_member_status = EXCLUDED.rc_member_status,
    rc_approval_date = EXCLUDED.rc_approval_date,
    rc_closure_date = EXCLUDED.rc_closure_date,
    lgd_district_code = EXCLUDED.lgd_district_code,
    lgd_district_name = EXCLUDED.lgd_district_name,
    lgd_block_code = EXCLUDED.lgd_block_code,
    lgd_block_name = EXCLUDED.lgd_block_name,
    lgd_gp_code = EXCLUDED.lgd_gp_code,
    lgd_gp_name = EXCLUDED.lgd_gp_name,
    address = EXCLUDED.address,
    last_refreshed_at = EXCLUDED.last_refreshed_at
""".strip()


def build_person_scheme_enrollment_upsert_sql(district_code: Optional[int] = None) -> str:
    rc_filter = _district_filter("rc", district_code)
    sc_filter = _district_filter("sc", district_code)
    ss_filter = _district_filter("ss", district_code)
    return f"""
INSERT INTO srsadmin.person_scheme_enrollment (
    ration_card_memberid,
    scheme_id,
    scheme_type,
    scheme_beneficiary_id,
    enrollment_status,
    enrollment_grade,
    approved_date,
    closing_date,
    total_amount_received,
    installment_count,
    first_payment_date,
    last_payment_date,
    lgd_district_code,
    last_refreshed_at
)
WITH cash_txn AS (
    SELECT
        scheme_beneficiary_id,
        scheme_id,
        SUM(amount) AS total_amount,
        COUNT(*) AS installment_count,
        MIN(transaction_timestamp) AS first_payment_date,
        MAX(transaction_timestamp) AS last_payment_date
    FROM srsadmin.scheme_transaction_cash_2526
    GROUP BY scheme_beneficiary_id, scheme_id
),
cash_rows AS (
    SELECT DISTINCT ON (rc.ration_card_memberid, sc.scheme_id)
        rc.ration_card_memberid,
        sc.scheme_id,
        'CASH' AS scheme_type,
        sc.scheme_beneficiary_id,
        CASE
            WHEN sc.closing_date IS NULL THEN 'ACTIVE'
            ELSE 'CLOSED'
        END AS enrollment_status,
        sc.grade AS enrollment_grade,
        sc.approved_date,
        sc.closing_date,
        COALESCE(txn.total_amount, 0) AS total_amount_received,
        COALESCE(txn.installment_count, 0) AS installment_count,
        txn.first_payment_date,
        txn.last_payment_date,
        sc.lgd_district_code,
        NOW() AS last_refreshed_at
    FROM srsadmin.rc_beneficiary rc
    JOIN srsadmin.scheme_beneficiary_cash sc
        ON (
            rc.uid IS NOT NULL
            AND sc.uid IS NOT NULL
            AND rc.uid = sc.uid
        )
        OR (
            (rc.uid IS NULL OR sc.uid IS NULL)
            AND rc.ration_card_memberid IS NOT NULL
            AND rc.ration_card_memberid = sc.ration_card_memberid
        )
    LEFT JOIN cash_txn txn
        ON sc.scheme_beneficiary_id = txn.scheme_beneficiary_id
        AND sc.scheme_id = txn.scheme_id
    {sc_filter if district_code is not None else rc_filter}
    ORDER BY rc.ration_card_memberid, sc.scheme_id, sc.approved_date DESC NULLS LAST
),
ss_txn AS (
    SELECT
        scheme_beneficiary_id,
        SUM(amount) AS total_amount,
        COUNT(*) AS claim_count,
        MIN(transaction_timestamp) AS first_claim_date,
        MAX(transaction_timestamp) AS last_claim_date
    FROM srsadmin.swasthya_sathi_transaction_2526
    GROUP BY scheme_beneficiary_id
),
ss_rows AS (
    SELECT DISTINCT ON (rc.ration_card_memberid, ss.scheme_id)
        rc.ration_card_memberid,
        ss.scheme_id,
        'SWASTHYA_SATHI' AS scheme_type,
        ss.scheme_beneficiary_id,
        CASE
            WHEN ss.closing_date IS NULL THEN 'ACTIVE'
            ELSE 'CLOSED'
        END AS enrollment_status,
        ss.grade AS enrollment_grade,
        ss.approved_date,
        ss.closing_date,
        COALESCE(txn.total_amount, 0) AS total_amount_received,
        COALESCE(txn.claim_count, 0) AS installment_count,
        txn.first_claim_date AS first_payment_date,
        txn.last_claim_date AS last_payment_date,
        ss.lgd_district_code,
        NOW() AS last_refreshed_at
    FROM srsadmin.rc_beneficiary rc
    JOIN srsadmin.swasthya_sathi_beneficiary ss
        ON (
            rc.uid IS NOT NULL
            AND ss.uid IS NOT NULL
            AND rc.uid = ss.uid
        )
        OR (
            (rc.uid IS NULL OR ss.uid IS NULL)
            AND rc.ration_card_memberid IS NOT NULL
            AND rc.ration_card_memberid = ss.ration_card_memberid
        )
    LEFT JOIN ss_txn txn
        ON ss.scheme_beneficiary_id = txn.scheme_beneficiary_id
    {ss_filter if district_code is not None else rc_filter}
    ORDER BY rc.ration_card_memberid, ss.scheme_id, ss.approved_date DESC NULLS LAST
)
SELECT *
FROM cash_rows
UNION ALL
SELECT *
FROM ss_rows
ON CONFLICT (ration_card_memberid, scheme_id) DO UPDATE
SET
    scheme_type = EXCLUDED.scheme_type,
    scheme_beneficiary_id = EXCLUDED.scheme_beneficiary_id,
    enrollment_status = EXCLUDED.enrollment_status,
    enrollment_grade = EXCLUDED.enrollment_grade,
    approved_date = EXCLUDED.approved_date,
    closing_date = EXCLUDED.closing_date,
    total_amount_received = EXCLUDED.total_amount_received,
    installment_count = EXCLUDED.installment_count,
    first_payment_date = EXCLUDED.first_payment_date,
    last_payment_date = EXCLUDED.last_payment_date,
    lgd_district_code = EXCLUDED.lgd_district_code,
    last_refreshed_at = EXCLUDED.last_refreshed_at
""".strip()


def build_validation_queries(district_code: Optional[int] = None) -> List[RegistryStatement]:
    district_where = (
        "WHERE lgd_district_code = :district_code" if district_code is not None else ""
    )
    return [
        RegistryStatement(
            key="person_detail_row_count",
            kind="validation",
            statement=f"""
SELECT COUNT(*) AS person_detail_count
FROM srsadmin.person_detail
{district_where}
""".strip(),
        ),
        RegistryStatement(
            key="person_detail_duplicate_member_ids",
            kind="validation",
            statement=f"""
SELECT ration_card_memberid, COUNT(*) AS duplicate_count
FROM srsadmin.person_detail
{district_where}
GROUP BY ration_card_memberid
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, ration_card_memberid
LIMIT 100
""".strip(),
        ),
        RegistryStatement(
            key="person_scheme_duplicate_keys",
            kind="validation",
            statement=f"""
SELECT ration_card_memberid, scheme_id, COUNT(*) AS duplicate_count
FROM srsadmin.person_scheme_enrollment
{district_where}
GROUP BY ration_card_memberid, scheme_id
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, ration_card_memberid, scheme_id
LIMIT 100
""".strip(),
        ),
        RegistryStatement(
            key="unmatched_cash_scheme_rows",
            kind="validation",
            statement=f"""
SELECT COUNT(*) AS unmatched_cash_rows
FROM srsadmin.scheme_beneficiary_cash sc
LEFT JOIN srsadmin.person_detail pd
    ON (
        pd.uid IS NOT NULL
        AND sc.uid IS NOT NULL
        AND pd.uid = sc.uid
    )
    OR (
        (pd.uid IS NULL OR sc.uid IS NULL)
        AND pd.ration_card_memberid IS NOT NULL
        AND pd.ration_card_memberid = sc.ration_card_memberid
    )
{"WHERE sc.lgd_district_code = :district_code AND pd.ration_card_memberid IS NULL" if district_code is not None else "WHERE pd.ration_card_memberid IS NULL"}
""".strip(),
        ),
        RegistryStatement(
            key="family_sample",
            kind="validation",
            statement="""
SELECT ration_card_number, COUNT(*) AS family_size
FROM srsadmin.person_detail
GROUP BY ration_card_number
ORDER BY family_size DESC, ration_card_number
LIMIT 20
""".strip(),
        ),
    ]


def build_registry_statements(
    district_code: Optional[int] = None,
    *,
    include_schema: bool = True,
    include_person_detail: bool = True,
    include_person_scheme_enrollment: bool = True,
    include_validation_queries: bool = False,
) -> List[RegistryStatement]:
    statements: List[RegistryStatement] = []
    if include_schema:
        statements.extend(
            [
                RegistryStatement("create_person_detail", "ddl", PERSON_DETAIL_DDL),
                RegistryStatement(
                    "create_person_scheme_enrollment",
                    "ddl",
                    PERSON_SCHEME_ENROLLMENT_DDL,
                ),
                RegistryStatement("create_eligibility_status", "ddl", ELIGIBILITY_STATUS_DDL),
                RegistryStatement(
                    "create_person_detail_family_index",
                    "ddl",
                    PERSON_DETAIL_FAMILY_INDEX,
                ),
                RegistryStatement("create_person_detail_uid_index", "ddl", PERSON_DETAIL_UID_INDEX),
                RegistryStatement("create_pse_member_index", "ddl", PSE_MEMBER_INDEX),
                RegistryStatement("create_pse_scheme_index", "ddl", PSE_SCHEME_INDEX),
                RegistryStatement("create_pse_district_index", "ddl", PSE_DISTRICT_INDEX),
                RegistryStatement(
                    "create_enrollment_eligibility_view",
                    "view",
                    ENROLLMENT_ELIGIBILITY_VIEW,
                ),
            ]
        )
    if include_person_detail:
        statements.append(
            RegistryStatement(
                "load_person_detail",
                "dml",
                build_person_detail_upsert_sql(district_code),
            )
        )
    if include_person_scheme_enrollment:
        statements.append(
            RegistryStatement(
                "load_person_scheme_enrollment",
                "dml",
                build_person_scheme_enrollment_upsert_sql(district_code),
            )
        )
    if include_validation_queries:
        statements.extend(build_validation_queries(district_code))
    return statements


async def execute_registry_build(
    session: AsyncSession,
    district_code: Optional[int] = None,
    *,
    include_schema: bool = True,
    include_person_detail: bool = True,
    include_person_scheme_enrollment: bool = True,
) -> List[Dict[str, Any]]:
    statements = build_registry_statements(
        district_code=district_code,
        include_schema=include_schema,
        include_person_detail=include_person_detail,
        include_person_scheme_enrollment=include_person_scheme_enrollment,
        include_validation_queries=False,
    )
    params: Dict[str, Any] = {}
    if district_code is not None:
        params["district_code"] = district_code

    results: List[Dict[str, Any]] = []
    for registry_statement in statements:
        result = await session.execute(_prepare_statement(registry_statement.statement), params)
        results.append(
            {
                "key": registry_statement.key,
                "kind": registry_statement.kind,
                "success": True,
                "rowcount": getattr(result, "rowcount", None),
            }
        )
    await session.commit()
    return results


async def execute_validation_queries(
    session: AsyncSession,
    district_code: Optional[int] = None,
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    if district_code is not None:
        params["district_code"] = district_code

    results: List[Dict[str, Any]] = []
    for registry_statement in build_validation_queries(district_code):
        result = await session.execute(_prepare_statement(registry_statement.statement), params)
        rows = result.mappings().all()
        serialized_rows = [dict(row) for row in rows]
        results.append(
            {
                "key": registry_statement.key,
                "kind": registry_statement.kind,
                "row_count": len(serialized_rows),
                "rows": serialized_rows,
            }
        )
    return results


async def fetch_pilot_summary(
    session: AsyncSession,
    district_code: int,
) -> Dict[str, Any]:
    params = {"district_code": district_code}
    summary_queries = {
        "person_count": """
            SELECT COUNT(*) AS value
            FROM srsadmin.person_detail
            WHERE lgd_district_code = :district_code
        """,
        "enrollment_count": """
            SELECT COUNT(*) AS value
            FROM srsadmin.person_scheme_enrollment
            WHERE lgd_district_code = :district_code
        """,
        "eligibility_count": """
            SELECT COUNT(*) AS value
            FROM srsadmin.eligibility_status
        """,
        "person_duplicates": """
            SELECT COUNT(*) AS value
            FROM (
                SELECT ration_card_memberid
                FROM srsadmin.person_detail
                GROUP BY ration_card_memberid
                HAVING COUNT(*) > 1
            ) duplicate_members
        """,
        "enrollment_duplicates": """
            SELECT COUNT(*) AS value
            FROM (
                SELECT ration_card_memberid, scheme_id
                FROM srsadmin.person_scheme_enrollment
                GROUP BY ration_card_memberid, scheme_id
                HAVING COUNT(*) > 1
            ) duplicate_enrollments
        """,
        "max_family_size": """
            SELECT COALESCE(MAX(family_size), 0) AS value
            FROM (
                SELECT COUNT(*) AS family_size
                FROM srsadmin.person_detail
                WHERE lgd_district_code = :district_code
                GROUP BY ration_card_number
            ) family_sizes
        """,
    }

    summary: Dict[str, Any] = {"district_code": district_code}
    for key, query in summary_queries.items():
        result = await session.execute(_prepare_statement(query), params)
        row = result.mappings().first()
        summary[key] = row.get("value") if row else None
    return summary


async def fetch_pilot_quality_report(
    session: AsyncSession,
    district_code: int,
    *,
    include_join_loss: bool = True,
) -> Dict[str, Any]:
    params = {"district_code": district_code}
    report = await fetch_pilot_summary(session, district_code)

    scalar_queries = {
        "source_person_count": """
            SELECT COUNT(DISTINCT rc.ration_card_memberid) AS value
            FROM srsadmin.rc_beneficiary rc
            WHERE rc.lgd_district_code = :district_code
        """,
        "source_family_count": """
            SELECT COUNT(DISTINCT rc.ration_card_number) AS value
            FROM srsadmin.rc_beneficiary rc
            WHERE rc.lgd_district_code = :district_code
        """,
        "output_family_count": """
            SELECT COUNT(DISTINCT pd.ration_card_number) AS value
            FROM srsadmin.person_detail pd
            WHERE pd.lgd_district_code = :district_code
        """,
        "person_without_scheme_count": """
            SELECT COUNT(*) AS value
            FROM srsadmin.person_detail pd
            WHERE pd.lgd_district_code = :district_code
              AND NOT EXISTS (
                  SELECT 1
                  FROM srsadmin.person_scheme_enrollment pse
                  WHERE pse.ration_card_memberid = pd.ration_card_memberid
              )
        """,
        "families_with_partial_s767_coverage": """
            SELECT COUNT(*) AS value
            FROM (
                SELECT pd.ration_card_number
                FROM srsadmin.person_detail pd
                LEFT JOIN srsadmin.person_scheme_enrollment pse
                    ON pd.ration_card_memberid = pse.ration_card_memberid
                    AND pse.scheme_id = 'S767'
                WHERE pd.lgd_district_code = :district_code
                GROUP BY pd.ration_card_number
                HAVING COUNT(*) FILTER (WHERE pse.scheme_id = 'S767') > 0
                   AND COUNT(*) FILTER (WHERE pse.scheme_id IS NULL) > 0
            ) partial_families
        """,
    }

    for key, query in scalar_queries.items():
        result = await session.execute(_prepare_statement(query), params)
        row = result.mappings().first()
        report[key] = row.get("value") if row else None

    if include_join_loss:
        join_loss_queries = {
            "unmatched_cash_scheme_rows": """
                SELECT COUNT(*) AS value
                FROM srsadmin.scheme_beneficiary_cash sc
                WHERE sc.lgd_district_code = :district_code
                  AND NOT EXISTS (
                      SELECT 1
                      FROM srsadmin.person_detail pd
                      WHERE (
                          pd.uid IS NOT NULL
                          AND sc.uid IS NOT NULL
                          AND pd.uid = sc.uid
                      )
                      OR (
                          (pd.uid IS NULL OR sc.uid IS NULL)
                          AND pd.ration_card_memberid IS NOT NULL
                          AND pd.ration_card_memberid = sc.ration_card_memberid
                      )
                  )
            """,
            "unmatched_swasthya_sathi_rows": """
                SELECT COUNT(*) AS value
                FROM srsadmin.swasthya_sathi_beneficiary ss
                WHERE ss.lgd_district_code = :district_code
                  AND NOT EXISTS (
                      SELECT 1
                      FROM srsadmin.person_detail pd
                      WHERE (
                          pd.uid IS NOT NULL
                          AND ss.uid IS NOT NULL
                          AND pd.uid = ss.uid
                      )
                      OR (
                          (pd.uid IS NULL OR ss.uid IS NULL)
                          AND pd.ration_card_memberid IS NOT NULL
                          AND pd.ration_card_memberid = ss.ration_card_memberid
                      )
                  )
            """,
        }
        for key, query in join_loss_queries.items():
            result = await session.execute(_prepare_statement(query), params)
            row = result.mappings().first()
            report[key] = row.get("value") if row else None
    else:
        report["unmatched_cash_scheme_rows"] = None
        report["unmatched_swasthya_sathi_rows"] = None

    family_sample_query = """
        SELECT
            base.ration_card_number,
            base.family_size,
            base.hof_count,
            COALESCE(ss.members_in_s767, 0) AS members_in_s767,
            COALESCE(schemes.distinct_schemes, 0) AS distinct_schemes
        FROM (
            SELECT
                pd.ration_card_number,
                COUNT(*) AS family_size,
                COUNT(*) FILTER (WHERE pd.is_hof = 1) AS hof_count
            FROM srsadmin.person_detail pd
            WHERE pd.lgd_district_code = :district_code
            GROUP BY pd.ration_card_number
        ) base
        LEFT JOIN (
            SELECT
                pd.ration_card_number,
                COUNT(DISTINCT pd.ration_card_memberid) AS members_in_s767
            FROM srsadmin.person_detail pd
            JOIN srsadmin.person_scheme_enrollment pse
                ON pd.ration_card_memberid = pse.ration_card_memberid
            WHERE pd.lgd_district_code = :district_code
              AND pse.scheme_id = 'S767'
            GROUP BY pd.ration_card_number
        ) ss
            ON base.ration_card_number = ss.ration_card_number
        LEFT JOIN (
            SELECT
                pd.ration_card_number,
                COUNT(DISTINCT pse.scheme_id) AS distinct_schemes
            FROM srsadmin.person_detail pd
            LEFT JOIN srsadmin.person_scheme_enrollment pse
                ON pd.ration_card_memberid = pse.ration_card_memberid
            WHERE pd.lgd_district_code = :district_code
            GROUP BY pd.ration_card_number
        ) schemes
            ON base.ration_card_number = schemes.ration_card_number
        ORDER BY base.family_size DESC, base.ration_card_number
        LIMIT 5
    """
    scheme_mix_query = """
        SELECT
            pse.scheme_id,
            pse.scheme_type,
            COUNT(*) AS member_count
        FROM srsadmin.person_scheme_enrollment pse
        WHERE pse.lgd_district_code = :district_code
        GROUP BY pse.scheme_id, pse.scheme_type
        ORDER BY member_count DESC, pse.scheme_id
        LIMIT 10
    """

    family_sample_result = await session.execute(_prepare_statement(family_sample_query), params)
    scheme_mix_result = await session.execute(_prepare_statement(scheme_mix_query), params)

    report["largest_family_samples"] = [
        dict(row) for row in family_sample_result.mappings().all()
    ]
    report["top_scheme_mix"] = [dict(row) for row in scheme_mix_result.mappings().all()]
    report["checks"] = {
        "person_count_matches_source": report["person_count"] == report["source_person_count"],
        "family_count_matches_source": report["output_family_count"] == report["source_family_count"],
        "person_duplicates_zero": report["person_duplicates"] == 0,
        "enrollment_duplicates_zero": report["enrollment_duplicates"] == 0,
        "eligibility_pending": report["eligibility_count"] == 0,
    }
    return report


async def fetch_join_loss_report(
    session: AsyncSession,
    district_code: int,
) -> Dict[str, Any]:
    params = {"district_code": district_code}
    queries = {
        "unmatched_cash_scheme_rows": """
            WITH pd_uid AS (
                SELECT DISTINCT uid
                FROM srsadmin.person_detail
                WHERE lgd_district_code = :district_code
                  AND uid IS NOT NULL
            ),
            pd_member AS (
                SELECT DISTINCT ration_card_memberid
                FROM srsadmin.person_detail
                WHERE lgd_district_code = :district_code
                  AND ration_card_memberid IS NOT NULL
            )
            SELECT COUNT(*) AS value
            FROM srsadmin.scheme_beneficiary_cash sc
            LEFT JOIN pd_uid
                ON sc.uid IS NOT NULL
               AND pd_uid.uid = sc.uid
            LEFT JOIN pd_member
                ON pd_uid.uid IS NULL
               AND sc.ration_card_memberid IS NOT NULL
               AND pd_member.ration_card_memberid = sc.ration_card_memberid
            WHERE sc.lgd_district_code = :district_code
              AND pd_uid.uid IS NULL
              AND pd_member.ration_card_memberid IS NULL
        """,
        "unmatched_swasthya_sathi_rows": """
            WITH pd_uid AS (
                SELECT DISTINCT uid
                FROM srsadmin.person_detail
                WHERE lgd_district_code = :district_code
                  AND uid IS NOT NULL
            ),
            pd_member AS (
                SELECT DISTINCT ration_card_memberid
                FROM srsadmin.person_detail
                WHERE lgd_district_code = :district_code
                  AND ration_card_memberid IS NOT NULL
            )
            SELECT COUNT(*) AS value
            FROM srsadmin.swasthya_sathi_beneficiary ss
            LEFT JOIN pd_uid
                ON ss.uid IS NOT NULL
               AND pd_uid.uid = ss.uid
            LEFT JOIN pd_member
                ON pd_uid.uid IS NULL
               AND ss.ration_card_memberid IS NOT NULL
               AND pd_member.ration_card_memberid = ss.ration_card_memberid
            WHERE ss.lgd_district_code = :district_code
              AND pd_uid.uid IS NULL
              AND pd_member.ration_card_memberid IS NULL
        """,
    }

    report: Dict[str, Any] = {"district_code": district_code}
    for key, query in queries.items():
        result = await session.execute(_prepare_statement(query), params)
        row = result.mappings().first()
        report[key] = row.get("value") if row else None

    cash_total_result = await session.execute(
        _prepare_statement(
            """
            SELECT COUNT(*) AS value
            FROM srsadmin.scheme_beneficiary_cash
            WHERE lgd_district_code = :district_code
            """
        ),
        params,
    )
    ss_total_result = await session.execute(
        _prepare_statement(
            """
            SELECT COUNT(*) AS value
            FROM srsadmin.swasthya_sathi_beneficiary
            WHERE lgd_district_code = :district_code
            """
        ),
        params,
    )

    cash_total = (cash_total_result.mappings().first() or {}).get("value")
    ss_total = (ss_total_result.mappings().first() or {}).get("value")
    report["cash_source_rows"] = cash_total
    report["swasthya_sathi_source_rows"] = ss_total
    report["cash_match_rate_pct"] = (
        round((1 - (report["unmatched_cash_scheme_rows"] / cash_total)) * 100, 2)
        if cash_total
        else None
    )
    report["swasthya_sathi_match_rate_pct"] = (
        round((1 - (report["unmatched_swasthya_sathi_rows"] / ss_total)) * 100, 2)
        if ss_total
        else None
    )
    return report


async def fetch_rollout_summary(session: AsyncSession) -> Dict[str, Any]:
    queries = {
        "person_count": """
            SELECT COUNT(*) AS value
            FROM srsadmin.person_detail
        """,
        "enrollment_count": """
            SELECT COUNT(*) AS value
            FROM srsadmin.person_scheme_enrollment
        """,
        "eligibility_count": """
            SELECT COUNT(*) AS value
            FROM srsadmin.eligibility_status
        """,
        "family_count": """
            SELECT COUNT(DISTINCT ration_card_number) AS value
            FROM srsadmin.person_detail
        """,
        "person_district_count": """
            SELECT COUNT(DISTINCT lgd_district_code) AS value
            FROM srsadmin.person_detail
            WHERE lgd_district_code IS NOT NULL
        """,
        "enrollment_district_count": """
            SELECT COUNT(DISTINCT lgd_district_code) AS value
            FROM srsadmin.person_scheme_enrollment
            WHERE lgd_district_code IS NOT NULL
        """,
        "non_303_person_count": """
            SELECT COUNT(*) AS value
            FROM srsadmin.person_detail
            WHERE lgd_district_code <> 303
        """,
        "non_303_enrollment_count": """
            SELECT COUNT(*) AS value
            FROM srsadmin.person_scheme_enrollment
            WHERE lgd_district_code <> 303
        """,
    }

    summary: Dict[str, Any] = {}
    for key, query in queries.items():
        result = await session.execute(_prepare_statement(query), {})
        row = result.mappings().first()
        summary[key] = row.get("value") if row else None

    top_districts_query = """
        SELECT
            lgd_district_code,
            COUNT(*) AS person_count
        FROM srsadmin.person_detail
        GROUP BY lgd_district_code
        ORDER BY person_count DESC, lgd_district_code
        LIMIT 10
    """
    district_result = await session.execute(_prepare_statement(top_districts_query), {})
    summary["top_person_districts"] = [dict(row) for row in district_result.mappings().all()]
    summary["full_rollout_detected"] = bool(summary.get("non_303_person_count"))
    return summary
