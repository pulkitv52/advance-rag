"""
Graph Sync Service — Curated Beneficiary Import
===============================================
Pulls curated beneficiary profile and transaction aggregates from PostgreSQL
into Neo4j. The sync preserves the existing Citizen-centric graph contract
while adding Enrollment and payout-month structures for richer analysis.
"""

import asyncio
import argparse
import os
from typing import Any, Dict, List, Optional

import asyncpg

from src.core.config import get_settings
from src.core.logger import logger
from src.services.graph_db import get_driver

settings = get_settings()

DB_CONFIG = {
    "user": settings.registry_postgres_user,
    "password": settings.registry_postgres_password,
    "database": settings.registry_postgres_db,
    "host": settings.registry_postgres_host,
    "port": settings.registry_postgres_port,
}

PROFILE_SOURCE = f"{settings.REGISTRY_SCHEMA}.master_beneficiary_profile"
TRANSACTION_SOURCE = f"{settings.REGISTRY_SCHEMA}.master_beneficiary_transactions"

BATCH_SIZE = 2000
PROFILE_CHECKPOINT_FILE = "/home/pulkitv52/Advance-rag/logs/backend/sync_profile_checkpoint.txt"
PAYOUT_CHECKPOINT_FILE = "/home/pulkitv52/Advance-rag/logs/backend/sync_payout_checkpoint.txt"


async def get_db_connection():
    return await asyncpg.connect(**DB_CONFIG)


CITIZEN_SYNC_CYPHER = """
UNWIND $data AS row

MERGE (c:Citizen {uid: row.uid})
ON CREATE SET
    c.name = row.fullname,
    c.gender = row.gender,
    c.dob = row.member_dob,
    c.mobile = row.mobile,
    c.age = CASE
        WHEN row.member_dob IS NOT NULL AND row.member_dob <> '' AND row.member_dob <> 'None'
        THEN duration.between(date(row.member_dob), date()).years
        ELSE null
    END,
    c.type = 'Citizen',
    c.is_ghost_flag = false,
    c.is_dup_flag = false,
    c.is_anomaly_flag = false,
    c.created_at = datetime()
ON MATCH SET
    c.name = COALESCE(c.name, row.fullname),
    c.gender = COALESCE(c.gender, row.gender),
    c.dob = COALESCE(c.dob, row.member_dob),
    c.mobile = COALESCE(c.mobile, row.mobile),
    c.age = CASE
        WHEN row.member_dob IS NOT NULL AND row.member_dob <> '' AND row.member_dob <> 'None'
        THEN duration.between(date(row.member_dob), date()).years
        ELSE c.age
    END,
    c.updated_at = datetime()

MERGE (d:District {code: row.lgd_district_code})
ON CREATE SET d.name = row.lgd_district_name, d.type = 'Location'
ON MATCH SET d.name = COALESCE(d.name, row.lgd_district_name)

MERGE (b:Block {code: row.lgd_block_code})
ON CREATE SET b.name = row.lgd_block_name, b.type = 'Location'
ON MATCH SET b.name = COALESCE(b.name, row.lgd_block_name)

MERGE (g:GP {code: row.lgd_gp_code})
ON CREATE SET
    g.name = row.lgd_gp_name,
    g.type = 'Location',
    g.total_citizens = 0,
    g.high_risk_count = 0,
    g.high_risk_pct = 0.0
ON MATCH SET g.name = COALESCE(g.name, row.lgd_gp_name)

MERGE (g)-[:PART_OF]->(b)
MERGE (b)-[:PART_OF]->(d)
MERGE (c)-[:RESIDES_IN]->(g)

MERGE (s:Scheme {id: row.scheme_id})
ON CREATE SET
    s.name = row.scheme_name,
    s.type = 'Scheme',
    s.beneficiary_count = 0
ON MATCH SET s.name = COALESCE(s.name, row.scheme_name)

MERGE (e:Enrollment {key: row.enrollment_key})
ON CREATE SET
    e.uid = row.uid,
    e.scheme_id = row.scheme_id,
    e.scheme_beneficiary_id = row.scheme_beneficiary_id,
    e.source_family = row.source_family,
    e.source_table = row.source_table,
    e.status = row.enrollment_status,
    e.approved_date = row.approved_date,
    e.closing_date = row.closing_date,
    e.closure_remarks = row.closure_remarks,
    e.grade = row.grade,
    e.rc_match_type = row.rc_match_type,
    e.rc_member_status = row.rc_member_status,
    e.tran_count_1 = row.tran_count_1,
    e.tran_count_2 = row.tran_count_2,
    e.transaction_rows = row.transaction_rows,
    e.transaction_total_amount = row.transaction_total_amount,
    e.latest_transaction_timestamp = row.latest_transaction_timestamp,
    e.latest_transaction_ref_no = row.latest_transaction_ref_no,
    e.first_transaction_timestamp = row.first_transaction_timestamp,
    e.installment_count = row.installment_count,
    e.financial_years = row.financial_years,
    e.duplicate_group_size = row.duplicate_group_size,
    e.completeness_score = row.completeness_score,
    e.created_at = datetime()
ON MATCH SET
    e.status = row.enrollment_status,
    e.approved_date = COALESCE(row.approved_date, e.approved_date),
    e.closing_date = COALESCE(row.closing_date, e.closing_date),
    e.closure_remarks = COALESCE(row.closure_remarks, e.closure_remarks),
    e.grade = COALESCE(row.grade, e.grade),
    e.rc_match_type = COALESCE(row.rc_match_type, e.rc_match_type),
    e.rc_member_status = COALESCE(row.rc_member_status, e.rc_member_status),
    e.tran_count_1 = COALESCE(row.tran_count_1, e.tran_count_1, 0),
    e.tran_count_2 = COALESCE(row.tran_count_2, e.tran_count_2, 0),
    e.transaction_rows = COALESCE(row.transaction_rows, e.transaction_rows, 0),
    e.transaction_total_amount = COALESCE(row.transaction_total_amount, e.transaction_total_amount, 0),
    e.latest_transaction_timestamp = COALESCE(row.latest_transaction_timestamp, e.latest_transaction_timestamp),
    e.latest_transaction_ref_no = COALESCE(row.latest_transaction_ref_no, e.latest_transaction_ref_no),
    e.first_transaction_timestamp = COALESCE(row.first_transaction_timestamp, e.first_transaction_timestamp),
    e.installment_count = COALESCE(row.installment_count, e.installment_count, 0),
    e.financial_years = COALESCE(row.financial_years, e.financial_years),
    e.duplicate_group_size = COALESCE(row.duplicate_group_size, e.duplicate_group_size, 1),
    e.completeness_score = COALESCE(row.completeness_score, e.completeness_score, 0),
    e.updated_at = datetime()

MERGE (c)-[:HAS_ENROLLMENT]->(e)
MERGE (e)-[:ENROLLED_IN {status: row.enrollment_status}]->(s)
MERGE (c)-[:ENROLLED_IN {status: row.enrollment_status}]->(s)

FOREACH (ignoreMe IN CASE WHEN row.ration_card_number IS NOT NULL AND row.ration_card_number <> '' THEN [1] ELSE [] END |
    MERGE (rc:RationCard {number: row.ration_card_number})
    ON CREATE SET rc.type = 'IdentityHub'
    MERGE (c)-[rel:MEMBER_OF]->(rc)
    SET rel.member_id = row.ration_card_memberid,
        rel.updated_at = datetime()
)

FOREACH (ignoreMe IN CASE WHEN row.mobile IS NOT NULL AND row.mobile <> '' THEN [1] ELSE [] END |
    MERGE (m:Mobile {number: row.mobile})
    ON CREATE SET m.type = 'IdentityHub'
    MERGE (c)-[:HAS_MOBILE]->(m)
)

FOREACH (ignoreMe IN CASE WHEN row.address_sanitized IS NOT NULL AND row.address_sanitized <> '' THEN [1] ELSE [] END |
    MERGE (a:Address {text: row.address_sanitized})
    ON CREATE SET a.type = 'LocationHub'
    MERGE (c)-[:LIVES_AT]->(a)
)
"""


PAYOUT_SYNC_CYPHER = """
UNWIND $data AS row

MERGE (c:Citizen {uid: row.uid})
ON CREATE SET c.type = 'Citizen', c.created_at = datetime()

MERGE (s:Scheme {id: row.scheme_id})
ON CREATE SET s.name = row.scheme_name, s.type = 'Scheme', s.beneficiary_count = 0
ON MATCH SET s.name = COALESCE(s.name, row.scheme_name)

MERGE (e:Enrollment {key: row.enrollment_key})
ON CREATE SET
    e.uid = row.uid,
    e.scheme_id = row.scheme_id,
    e.scheme_beneficiary_id = row.scheme_beneficiary_id,
    e.created_at = datetime()
ON MATCH SET
    e.updated_at = datetime()

MERGE (c)-[:HAS_ENROLLMENT]->(e)
MERGE (e)-[:ENROLLED_IN]->(s)
MERGE (c)-[:ENROLLED_IN]->(s)

MERGE (pm:PayoutMonth {key: row.payout_month_key})
ON CREATE SET
    pm.financial_year = row.financial_year,
    pm.installment_year = row.installment_year,
    pm.installment_month_code = row.installment_month_code,
    pm.installment_month = row.installment_month,
    pm.scheme_id = row.scheme_id,
    pm.label = row.payout_month_label,
    pm.type = 'PayoutMonth',
    pm.created_at = datetime()
ON MATCH SET
    pm.label = COALESCE(pm.label, row.payout_month_label),
    pm.updated_at = datetime()

MERGE (e)-[r:RECEIVED_PAYOUT_IN]->(pm)
SET r.transaction_count = row.transaction_count,
    r.total_amount = row.total_amount,
    r.latest_transaction_timestamp = row.latest_transaction_timestamp,
    r.latest_transaction_ref_no = row.latest_transaction_ref_no,
    r.updated_at = datetime()

MERGE (s)-[sr:HAS_PAYOUT_WINDOW]->(pm)
SET sr.updated_at = datetime()
"""


def _sanitize_address(raw_addr: Optional[str]) -> str:
    return raw_addr.strip().upper() if raw_addr else ""


def _to_text_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _to_enrollment_status(closing_date: Optional[Any]) -> str:
    return "Closed" if closing_date else "Active"


def _format_profile_rows(rows: List[asyncpg.Record]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        uid = (r.get("uid") or "").strip()
        scheme_beneficiary_id = (r.get("scheme_beneficiary_id") or "").strip()
        scheme_id = str(r.get("scheme_id") or "").strip()
        enrollment_key = f"{uid}:{scheme_beneficiary_id}"
        out.append(
            {
                "uid": uid,
                "scheme_id": scheme_id,
                "scheme_name": scheme_id or "Unknown Scheme",
                "scheme_beneficiary_id": scheme_beneficiary_id,
                "enrollment_key": enrollment_key,
                "enrollment_status": _to_enrollment_status(r.get("closing_date")),
                "source_family": (r.get("source_family") or "").strip(),
                "source_table": (r.get("source_table") or "").strip(),
                "fullname": (r.get("fullname") or "UNKNOWN").strip().upper(),
                "gender": (r.get("gender") or "").strip().upper(),
                "member_dob": str(r["member_dob"]) if r.get("member_dob") else None,
                "mobile": (r.get("mobile") or "").strip(),
                "ration_card_number": (r.get("ration_card_number") or "").strip(),
                "ration_card_memberid": (r.get("ration_card_memberid") or "").strip(),
                "address_sanitized": _sanitize_address(r.get("address")),
                "lgd_district_code": str(r.get("lgd_district_code") or ""),
                "lgd_district_name": (r.get("lgd_district_name") or "Unknown District").strip(),
                "lgd_block_code": str(r.get("lgd_block_code") or ""),
                "lgd_block_name": (r.get("lgd_block_name") or "Unknown Block").strip(),
                "lgd_gp_code": str(r.get("lgd_gp_code") or ""),
                "lgd_gp_name": (r.get("lgd_gp_name") or "Unknown GP").strip(),
                "approved_date": str(r["approved_date"]) if r.get("approved_date") else None,
                "closing_date": str(r["closing_date"]) if r.get("closing_date") else None,
                "closure_remarks": (r.get("closure_remarks") or "").strip() or None,
                "grade": str(r.get("grade")).strip() if r.get("grade") is not None else None,
                "rc_match_type": (r.get("rc_match_type") or "").strip() or None,
                "rc_member_status": (r.get("rc_member_status") or "").strip() or None,
                "transaction_rows": int(r.get("transaction_rows") or 0),
                "transaction_total_amount": float(r.get("transaction_total_amount") or 0),
                "latest_transaction_timestamp": (
                    str(r["latest_transaction_timestamp"])
                    if r.get("latest_transaction_timestamp")
                    else None
                ),
                "latest_transaction_ref_no": (r.get("latest_transaction_ref_no") or "").strip()
                or None,
                "first_transaction_timestamp": (
                    str(r["first_transaction_timestamp"])
                    if r.get("first_transaction_timestamp")
                    else None
                ),
                "installment_count": int(r.get("installment_count") or 0),
                "financial_years": _to_text_list(r.get("financial_years")),
                "duplicate_group_size": int(r.get("duplicate_group_size") or 1),
                "completeness_score": int(r.get("completeness_score") or 0),
                "tran_count_1": int(r.get("tran_count_1") or 0),
                "tran_count_2": int(r.get("tran_count_2") or 0),
            }
        )
    return out


def _format_payout_rows(rows: List[asyncpg.Record]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        uid = (r.get("uid") or "").strip()
        scheme_beneficiary_id = (r.get("scheme_beneficiary_id") or "").strip()
        scheme_id = str(r.get("scheme_id") or "").strip()
        financial_year = (r.get("financial_year") or "").strip()
        installment_year = (r.get("installment_year") or "").strip()
        installment_month_code = (r.get("installment_month_code") or "").strip()
        installment_month = (r.get("installment_month") or "").strip()
        payout_month_key = ":".join(
            [
                scheme_id or "UNKNOWN",
                financial_year or "UNKNOWN",
                installment_year or "UNKNOWN",
                installment_month_code or installment_month or "UNKNOWN",
            ]
        )
        payout_month_label = " ".join(
            part for part in [installment_month or installment_month_code, installment_year] if part
        ).strip() or financial_year or "Unknown Payout Month"
        out.append(
            {
                "uid": uid,
                "scheme_id": scheme_id,
                "scheme_name": scheme_id or "Unknown Scheme",
                "scheme_beneficiary_id": scheme_beneficiary_id,
                "enrollment_key": f"{uid}:{scheme_beneficiary_id}",
                "financial_year": financial_year or None,
                "installment_year": installment_year or None,
                "installment_month_code": installment_month_code or None,
                "installment_month": installment_month or None,
                "payout_month_key": payout_month_key,
                "payout_month_label": payout_month_label,
                "transaction_count": int(r.get("transaction_count") or 0),
                "total_amount": float(r.get("total_amount") or 0),
                "latest_transaction_timestamp": (
                    str(r["latest_transaction_timestamp"])
                    if r.get("latest_transaction_timestamp")
                    else None
                ),
                "latest_transaction_ref_no": (r.get("latest_transaction_ref_no") or "").strip()
                or None,
            }
        )
    return out


def _load_checkpoint(path: str) -> int:
    if not os.path.exists(path):
        return 0
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except Exception as exc:
        logger.warning(f"Could not read checkpoint file {path}: {exc}. Starting from 0.")
        return 0


def _save_checkpoint(path: str, offset: int) -> None:
    try:
        with open(path, "w") as f:
            f.write(str(offset))
    except Exception as exc:
        logger.warning(f"Failed to save checkpoint {path}: {exc}")


def _clear_checkpoint(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)


async def sync_citizens_to_graph(limit: Optional[int] = None, batch_size: int = BATCH_SIZE) -> int:
    """
    Pull curated beneficiary profile rows from PostgreSQL and upsert them into Neo4j.

    This sync builds:
    - Citizen nodes
    - Enrollment nodes
    - direct Citizen->Scheme edges for compatibility
    - identity and geographic hubs
    """
    conn = await get_db_connection()
    driver = await get_driver()
    total_imported = 0

    try:
        count_query = f"SELECT count(*) FROM {PROFILE_SOURCE} WHERE uid IS NOT NULL"
        total_in_db = await conn.fetchval(count_query)
        cap = min(limit, total_in_db) if limit else total_in_db
        logger.info(
            f"Curated profile sync — {cap:,} records to process (DB total: {total_in_db:,})"
        )

        fetch_query = f"""
        SELECT
            uid,
            scheme_id,
            scheme_beneficiary_id,
            source_family,
            source_table,
            fullname,
            gender,
            member_dob,
            mobile,
            ration_card_number,
            ration_card_memberid,
            address,
            lgd_district_code,
            lgd_district_name,
            lgd_block_code,
            lgd_block_name,
            lgd_gp_code,
            lgd_gp_name,
            approved_date,
            closing_date,
            closure_remarks,
            grade,
            rc_match_type,
            rc_member_status,
            transaction_rows,
            transaction_total_amount,
            latest_transaction_timestamp,
            latest_transaction_ref_no,
            first_transaction_timestamp,
            installment_count,
            financial_years,
            duplicate_group_size,
            completeness_score,
            tran_count_1,
            tran_count_2
        FROM {PROFILE_SOURCE}
        WHERE uid IS NOT NULL
        ORDER BY uid, scheme_id, scheme_beneficiary_id
        LIMIT $1 OFFSET $2
        """

        offset = _load_checkpoint(PROFILE_CHECKPOINT_FILE)
        if offset:
            logger.info(f"Resuming profile sync from checkpoint: Offset {offset:,}")
            if limit:
                cap = min(limit + offset, total_in_db)

        async with driver.session() as session:
            while offset < cap:
                current_batch_size = min(batch_size, cap - offset)
                rows = await conn.fetch(fetch_query, current_batch_size, offset)
                if not rows:
                    break

                data = _format_profile_rows(rows)
                await session.run(CITIZEN_SYNC_CYPHER, data=data)

                total_imported += len(rows)
                offset += len(rows)
                _save_checkpoint(PROFILE_CHECKPOINT_FILE, offset)

                pct = (offset / total_in_db) * 100 if total_in_db else 100.0
                logger.info(f"  Profile progress: {offset:,}/{total_in_db:,} ({pct:.1f}%)")

        if offset >= total_in_db:
            _clear_checkpoint(PROFILE_CHECKPOINT_FILE)
            logger.info("Profile sync complete. Checkpoint file removed.")

        logger.info(
            f"Curated profile sync complete — {total_imported:,} profile rows processed."
        )
        return total_imported

    except Exception as exc:
        logger.error(f"Curated profile sync failed: {exc}")
        raise
    finally:
        await conn.close()


async def sync_citizens_to_graph_per_scheme(
    per_scheme_limit: int, batch_size: int = BATCH_SIZE
) -> int:
    """
    Pull a balanced sample from the curated profile source, capped per scheme_id.

    This is intended for safe graph testing so large schemes do not dominate the
    imported sample.
    """
    conn = await get_db_connection()
    driver = await get_driver()
    total_imported = 0

    try:
        count_query = f"""
        WITH ranked AS (
            SELECT
                scheme_id,
                ROW_NUMBER() OVER (
                    PARTITION BY scheme_id
                    ORDER BY uid, scheme_beneficiary_id
                ) AS rn
            FROM {PROFILE_SOURCE}
            WHERE uid IS NOT NULL
        )
        SELECT count(*)
        FROM ranked
        WHERE rn <= $1
        """
        total_in_db = await conn.fetchval(count_query, per_scheme_limit)
        logger.info(
            "Curated profile sync (per-scheme) — "
            f"{total_in_db:,} records to process with cap {per_scheme_limit:,} per scheme"
        )

        fetch_query = f"""
        WITH ranked AS (
            SELECT
                uid,
                scheme_id,
                scheme_beneficiary_id,
                source_family,
                source_table,
                fullname,
                gender,
                member_dob,
                mobile,
                ration_card_number,
                ration_card_memberid,
                address,
                lgd_district_code,
                lgd_district_name,
                lgd_block_code,
                lgd_block_name,
                lgd_gp_code,
                lgd_gp_name,
                approved_date,
                closing_date,
                closure_remarks,
                grade,
                rc_match_type,
                rc_member_status,
                transaction_rows,
                transaction_total_amount,
                latest_transaction_timestamp,
                latest_transaction_ref_no,
                first_transaction_timestamp,
                installment_count,
                financial_years,
                duplicate_group_size,
                completeness_score,
                tran_count_1,
                tran_count_2,
                ROW_NUMBER() OVER (
                    PARTITION BY scheme_id
                    ORDER BY uid, scheme_beneficiary_id
                ) AS rn
            FROM {PROFILE_SOURCE}
            WHERE uid IS NOT NULL
        )
        SELECT
            uid,
            scheme_id,
            scheme_beneficiary_id,
            source_family,
            source_table,
            fullname,
            gender,
            member_dob,
            mobile,
            ration_card_number,
            ration_card_memberid,
            address,
            lgd_district_code,
            lgd_district_name,
            lgd_block_code,
            lgd_block_name,
            lgd_gp_code,
            lgd_gp_name,
            approved_date,
            closing_date,
            closure_remarks,
            grade,
            rc_match_type,
            rc_member_status,
            transaction_rows,
            transaction_total_amount,
            latest_transaction_timestamp,
            latest_transaction_ref_no,
            first_transaction_timestamp,
            installment_count,
            financial_years,
            duplicate_group_size,
            completeness_score,
            tran_count_1,
            tran_count_2
        FROM ranked
        WHERE rn <= $1
        ORDER BY scheme_id, uid, scheme_beneficiary_id
        LIMIT $2 OFFSET $3
        """

        async with driver.session() as session:
            offset = 0
            while offset < total_in_db:
                current_batch_size = min(batch_size, total_in_db - offset)
                rows = await conn.fetch(fetch_query, per_scheme_limit, current_batch_size, offset)
                if not rows:
                    break

                data = _format_profile_rows(rows)
                await session.run(CITIZEN_SYNC_CYPHER, data=data)

                total_imported += len(rows)
                offset += len(rows)
                pct = (offset / total_in_db) * 100 if total_in_db else 100.0
                logger.info(f"  Profile sample progress: {offset:,}/{total_in_db:,} ({pct:.1f}%)")

        logger.info(
            f"Curated profile sample sync complete — {total_imported:,} profile rows processed."
        )
        return total_imported

    except Exception as exc:
        logger.error(f"Curated profile sample sync failed: {exc}")
        raise
    finally:
        await conn.close()


async def sync_payouts_to_graph(limit: Optional[int] = None, batch_size: int = BATCH_SIZE) -> int:
    """
    Build payout-month aggregates from curated transactions and sync them into Neo4j.

    This sync creates:
    - PayoutMonth nodes
    - Enrollment->PayoutMonth relationships with counts and amounts
    - Scheme->PayoutMonth relationships for scheme-level time analysis
    """
    conn = await get_db_connection()
    driver = await get_driver()
    total_imported = 0

    try:
        count_query = f"""
        SELECT count(*)
        FROM (
            SELECT 1
            FROM {TRANSACTION_SOURCE}
            GROUP BY
                uid,
                scheme_id,
                scheme_beneficiary_id,
                financial_year,
                installment_year,
                installment_month_code,
                installment_month
        ) payout_groups
        """
        total_in_db = await conn.fetchval(count_query)
        cap = min(limit, total_in_db) if limit else total_in_db
        logger.info(
            f"Payout aggregate sync — {cap:,} grouped payout windows to process (DB total: {total_in_db:,})"
        )

        fetch_query = f"""
        SELECT
            uid,
            scheme_id,
            scheme_beneficiary_id,
            financial_year,
            installment_year,
            installment_month_code,
            installment_month,
            COUNT(*)::BIGINT AS transaction_count,
            COALESCE(SUM(amount), 0)::NUMERIC AS total_amount,
            MAX(transaction_timestamp) AS latest_transaction_timestamp,
            (
                ARRAY_AGG(transaction_ref_no ORDER BY transaction_timestamp DESC NULLS LAST, source_sl_no DESC NULLS LAST)
            )[1] AS latest_transaction_ref_no
        FROM {TRANSACTION_SOURCE}
        GROUP BY
            uid,
            scheme_id,
            scheme_beneficiary_id,
            financial_year,
            installment_year,
            installment_month_code,
            installment_month
        ORDER BY
            uid,
            scheme_id,
            scheme_beneficiary_id,
            financial_year,
            installment_year,
            installment_month_code,
            installment_month
        LIMIT $1 OFFSET $2
        """

        offset = _load_checkpoint(PAYOUT_CHECKPOINT_FILE)
        if offset:
            logger.info(f"Resuming payout sync from checkpoint: Offset {offset:,}")
            if limit:
                cap = min(limit + offset, total_in_db)

        async with driver.session() as session:
            while offset < cap:
                current_batch_size = min(batch_size, cap - offset)
                rows = await conn.fetch(fetch_query, current_batch_size, offset)
                if not rows:
                    break

                data = _format_payout_rows(rows)
                await session.run(PAYOUT_SYNC_CYPHER, data=data)

                total_imported += len(rows)
                offset += len(rows)
                _save_checkpoint(PAYOUT_CHECKPOINT_FILE, offset)

                pct = (offset / total_in_db) * 100 if total_in_db else 100.0
                logger.info(f"  Payout progress: {offset:,}/{total_in_db:,} ({pct:.1f}%)")

        if offset >= total_in_db:
            _clear_checkpoint(PAYOUT_CHECKPOINT_FILE)
            logger.info("Payout sync complete. Checkpoint file removed.")

        logger.info(
            f"Payout aggregate sync complete — {total_imported:,} payout windows processed."
        )
        return total_imported

    except Exception as exc:
        logger.error(f"Payout aggregate sync failed: {exc}")
        raise
    finally:
        await conn.close()


async def sync_payouts_to_graph_per_scheme(
    per_scheme_limit: int, batch_size: int = BATCH_SIZE
) -> int:
    """
    Build payout aggregates only for the per-scheme sampled enrollments selected
    from the curated profile source.
    """
    conn = await get_db_connection()
    driver = await get_driver()
    total_imported = 0

    sample_cte = f"""
        WITH sampled_enrollments AS (
            SELECT uid, scheme_id, scheme_beneficiary_id
            FROM (
                SELECT
                    uid,
                    scheme_id,
                    scheme_beneficiary_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY scheme_id
                        ORDER BY uid, scheme_beneficiary_id
                    ) AS rn
                FROM {PROFILE_SOURCE}
                WHERE uid IS NOT NULL
            ) ranked
            WHERE rn <= $1
        )
    """

    try:
        count_query = sample_cte + f"""
        SELECT count(*)
        FROM (
            SELECT 1
            FROM {TRANSACTION_SOURCE} t
            JOIN sampled_enrollments s
              ON s.uid = t.uid
             AND s.scheme_id = t.scheme_id
             AND s.scheme_beneficiary_id = t.scheme_beneficiary_id
            GROUP BY
                t.uid,
                t.scheme_id,
                t.scheme_beneficiary_id,
                t.financial_year,
                t.installment_year,
                t.installment_month_code,
                t.installment_month
        ) payout_groups
        """
        total_in_db = await conn.fetchval(count_query, per_scheme_limit)
        logger.info(
            "Payout aggregate sync (per-scheme) — "
            f"{total_in_db:,} grouped payout windows to process with cap {per_scheme_limit:,} per scheme"
        )

        fetch_query = sample_cte + f"""
        SELECT
            t.uid,
            t.scheme_id,
            t.scheme_beneficiary_id,
            t.financial_year,
            t.installment_year,
            t.installment_month_code,
            t.installment_month,
            COUNT(*)::BIGINT AS transaction_count,
            COALESCE(SUM(t.amount), 0)::NUMERIC AS total_amount,
            MAX(t.transaction_timestamp) AS latest_transaction_timestamp,
            (
                ARRAY_AGG(
                    t.transaction_ref_no
                    ORDER BY t.transaction_timestamp DESC NULLS LAST, t.source_sl_no DESC NULLS LAST
                )
            )[1] AS latest_transaction_ref_no
        FROM {TRANSACTION_SOURCE} t
        JOIN sampled_enrollments s
          ON s.uid = t.uid
         AND s.scheme_id = t.scheme_id
         AND s.scheme_beneficiary_id = t.scheme_beneficiary_id
        GROUP BY
            t.uid,
            t.scheme_id,
            t.scheme_beneficiary_id,
            t.financial_year,
            t.installment_year,
            t.installment_month_code,
            t.installment_month
        ORDER BY
            t.scheme_id,
            t.uid,
            t.scheme_beneficiary_id,
            t.financial_year,
            t.installment_year,
            t.installment_month_code,
            t.installment_month
        LIMIT $2 OFFSET $3
        """

        async with driver.session() as session:
            offset = 0
            while offset < total_in_db:
                current_batch_size = min(batch_size, total_in_db - offset)
                rows = await conn.fetch(fetch_query, per_scheme_limit, current_batch_size, offset)
                if not rows:
                    break

                data = _format_payout_rows(rows)
                await session.run(PAYOUT_SYNC_CYPHER, data=data)

                total_imported += len(rows)
                offset += len(rows)
                pct = (offset / total_in_db) * 100 if total_in_db else 100.0
                logger.info(f"  Payout sample progress: {offset:,}/{total_in_db:,} ({pct:.1f}%)")

        logger.info(
            f"Payout sample sync complete — {total_imported:,} payout windows processed."
        )
        return total_imported

    except Exception as exc:
        logger.error(f"Payout sample sync failed: {exc}")
        raise
    finally:
        await conn.close()


async def refresh_citizen_rollups() -> None:
    """
    Recompute citizen-level aggregate properties from Enrollment nodes.

    This keeps existing Citizen-centric fraud rules working while the richer
    Enrollment layer carries scheme-specific detail.
    """
    driver = await get_driver()
    async with driver.session() as session:
        await session.run(
            """
            MATCH (c:Citizen)-[:HAS_ENROLLMENT]->(e:Enrollment)
            WITH
                c,
                count(e) AS enrollment_count,
                count(DISTINCT e.scheme_id) AS scheme_count,
                sum(coalesce(e.transaction_rows, 0)) AS total_transaction_rows,
                sum(coalesce(e.transaction_total_amount, 0)) AS total_transaction_amount,
                max(e.latest_transaction_timestamp) AS latest_transaction_timestamp,
                sum(coalesce(e.tran_count_1, 0)) AS total_tran_count_1,
                sum(coalesce(e.tran_count_2, 0)) AS total_tran_count_2
            SET c.enrollment_count = enrollment_count,
                c.scheme_count = scheme_count,
                c.transaction_rows = total_transaction_rows,
                c.transaction_total_amount = total_transaction_amount,
                c.latest_transaction_timestamp = latest_transaction_timestamp,
                c.has_transactions = total_transaction_rows > 0,
                c.tran_count_1 = total_tran_count_1,
                c.tran_count_2 = total_tran_count_2,
                c.updated_at = datetime()
            """
        )
    logger.info("Citizen rollups refreshed from Enrollment nodes.")


async def ensure_graph_indexes():
    """
    Create Neo4j indexes and constraints for both the legacy Citizen graph and
    the curated Enrollment/PayoutMonth extensions.
    """
    driver = await get_driver()
    index_statements = [
        "CREATE CONSTRAINT citizen_uid IF NOT EXISTS FOR (c:Citizen) REQUIRE c.uid IS UNIQUE",
        "CREATE CONSTRAINT enrollment_key IF NOT EXISTS FOR (e:Enrollment) REQUIRE e.key IS UNIQUE",
        "CREATE CONSTRAINT district_code IF NOT EXISTS FOR (d:District) REQUIRE d.code IS UNIQUE",
        "CREATE CONSTRAINT block_code IF NOT EXISTS FOR (b:Block) REQUIRE b.code IS UNIQUE",
        "CREATE CONSTRAINT gp_code IF NOT EXISTS FOR (g:GP) REQUIRE g.code IS UNIQUE",
        "CREATE CONSTRAINT scheme_id IF NOT EXISTS FOR (s:Scheme) REQUIRE s.id IS UNIQUE",
        "CREATE CONSTRAINT payout_month_key IF NOT EXISTS FOR (p:PayoutMonth) REQUIRE p.key IS UNIQUE",
        "CREATE INDEX citizen_name IF NOT EXISTS FOR (c:Citizen) ON (c.name)",
        "CREATE INDEX citizen_dob IF NOT EXISTS FOR (c:Citizen) ON (c.dob)",
        "CREATE INDEX citizen_score IF NOT EXISTS FOR (c:Citizen) ON (c.vulnerability_score)",
        "CREATE INDEX citizen_tier IF NOT EXISTS FOR (c:Citizen) ON (c.risk_tier)",
        "CREATE INDEX enrollment_scheme IF NOT EXISTS FOR (e:Enrollment) ON (e.scheme_id)",
        "CREATE INDEX enrollment_beneficiary IF NOT EXISTS FOR (e:Enrollment) ON (e.scheme_beneficiary_id)",
        "CREATE INDEX payout_financial_year IF NOT EXISTS FOR (p:PayoutMonth) ON (p.financial_year)",
    ]
    async with driver.session() as session:
        for stmt in index_statements:
            try:
                await session.run(stmt)
            except Exception as exc:
                logger.warning(f"Index/constraint already exists or failed: {exc}")
    logger.info("Neo4j indexes and constraints verified.")


async def create_fraud_edges() -> dict:
    """
    Create fraud-specific graph relationships on the Citizen-centric layer.
    """
    driver = await get_driver()
    stats = {}
    async with driver.session() as session:
        res = await session.run(
            """
        CALL apoc.periodic.iterate(
            "MATCH (c:Citizen)
             WITH c.name AS n, c.dob AS d, collect(c) AS cluster
             WHERE size(cluster) > 1 AND n IS NOT NULL AND n <> ''
             RETURN cluster",
            "UNWIND cluster AS c1
             UNWIND cluster AS c2
             WITH c1, c2
             WHERE elementId(c1) < elementId(c2) AND c1.gender = c2.gender
             MERGE (c1)-[r:POTENTIAL_DUPLICATE {rule: 'B1'}]->(c2)
             SET r.confidence = 92,
                 r.name_similarity = 1.0,
                 r.matching_fields = ['name', 'dob', 'gp'],
                 c1.is_dup_flag = true,
                 c2.is_dup_flag = true",
            {batchSize: 5000, parallel: false}
        ) YIELD total RETURN total AS cnt
        """
        )
        stats["B1_exact_duplicates"] = (await res.single())["cnt"]

        res = await session.run(
            """
        CALL apoc.periodic.iterate(
            "MATCH (c1:Citizen)-[:RESIDES_IN]->(g:GP)
             WITH g, c1.dob AS dob, count(c1) AS cluster_size, collect(c1) AS citizens
             WHERE cluster_size >= 5 AND dob IS NOT NULL
             RETURN citizens, dob, g.code AS gcode, cluster_size",
            "UNWIND citizens AS c
             UNWIND citizens AS other
             WITH c, other, dob, gcode, cluster_size
             WHERE elementId(c) < elementId(other)
             MERGE (c)-[r:SAME_DOB_AT_GP]->(other)
             SET r.dob = dob,
                 r.gp_code = gcode,
                 r.cluster_size = cluster_size,
                 c.is_ghost_flag = true,
                 other.is_ghost_flag = true",
            {batchSize: 2000, parallel: false}
        ) YIELD total RETURN total AS cnt
        """
        )
        stats["B3_dob_cluster_edges"] = (await res.single())["cnt"]

        res = await session.run(
            """
        CALL apoc.periodic.iterate(
            "MATCH (c:Citizen) WHERE c.age > 110 RETURN c",
            "MERGE (f:FraudFlag {rule: 'A1'})
             ON CREATE SET f.type = 'GHOST', f.description = 'Age > 110'
             MERGE (c)-[r:FLAGGED_AS]->(f)
             SET r.confidence = 85, r.detected_at = datetime(), c.is_ghost_flag = true",
            {batchSize: 5000, parallel: false}
        ) YIELD total RETURN total AS cnt
        """
        )
        stats["A1_ghost_age"] = (await res.single())["cnt"]

        res = await session.run(
            """
        MATCH (c:Citizen)
        WHERE c.age < 0
        MERGE (f:FraudFlag {rule: 'A2'})
        ON CREATE SET f.type = 'GHOST', f.description = 'DOB in future'
        MERGE (c)-[r:FLAGGED_AS]->(f)
        SET r.confidence = 90, r.detected_at = datetime(), c.is_ghost_flag = true
        RETURN count(r) AS cnt
        """
        )
        stats["A2_future_dob"] = (await res.single())["cnt"]

        res = await session.run(
            """
        MATCH (c:Citizen)
        WHERE c.dob IS NULL OR c.dob = '' OR c.dob = 'None'
        MERGE (f:FraudFlag {rule: 'D1'})
        ON CREATE SET f.type = 'DATA_QUALITY', f.description = 'Missing DOB'
        MERGE (c)-[r:FLAGGED_AS]->(f)
        SET r.confidence = 60, r.detected_at = datetime()
        RETURN count(r) AS cnt
        """
        )
        stats["D1_missing_dob"] = (await res.single())["cnt"]

        await session.run(
            """
        MATCH (g:GP)<-[:RESIDES_IN]-(c:Citizen)
        WITH g, count(DISTINCT c) AS total
        SET g.total_citizens = total
        """
        )

        await session.run(
            """
        MATCH (s:Scheme)<-[:ENROLLED_IN]-(c:Citizen)
        WITH s, count(DISTINCT c) AS total
        SET s.beneficiary_count = total
        """
        )

        res = await session.run(
            """
        MATCH (g:GP)<-[:RESIDES_IN]-(c:Citizen)-[:ENROLLED_IN]->(s:Scheme)
        WITH g, s, count(DISTINCT c) AS gp_scheme_count
        WHERE gp_scheme_count >= 50 AND s.beneficiary_count > 0
        WITH g, s, gp_scheme_count, toFloat(gp_scheme_count) / s.beneficiary_count AS ratio
        WHERE ratio > 0.15
        MERGE (g)-[r:HIGH_RISK_CLUSTER]->(s)
        SET r.concentration_ratio = ratio,
            r.gp_beneficiary_count = gp_scheme_count,
            r.total_scheme_count = s.beneficiary_count,
            r.rule = 'C1'
        RETURN count(r) AS cnt
        """
        )
        stats["C1_scheme_concentration"] = (await res.single())["cnt"]

        res = await session.run(
            """
        MATCH (rc:RationCard)<-[:MEMBER_OF]-(c:Citizen)
        WITH rc, count(DISTINCT c) AS members
        WHERE members > 10
        MERGE (f:FraudFlag {rule: 'E1'})
        ON CREATE SET f.type = 'HOUSEHOLD_RING', f.description = 'Ration Card Shared by >10 UIDs'
        MERGE (rc)-[r:FLAGGED_AS]->(f)
        SET r.confidence = 95, r.detected_at = datetime()
        RETURN count(r) AS cnt
        """
        )
        stats["E1_household_rings"] = (await res.single())["cnt"]

        res = await session.run(
            """
        MATCH (o:Operator)<-[:REGISTERED_BY]-(c:Citizen)
        WITH o, count(c) AS total,
             count(CASE WHEN c.is_ghost_flag = true OR c.is_dup_flag = true THEN 1 END) AS fraud_count
        WHERE total > 20 AND (toFloat(fraud_count)/total) > 0.15
        MERGE (f:FraudFlag {rule: 'F1'})
        ON CREATE SET f.type = 'INTERNAL_ANOMALY', f.description = 'High Fraud registration rate (>15%)'
        MERGE (o)-[r:FLAGGED_AS]->(f)
        SET r.confidence = 90, r.detected_at = datetime(), r.error_rate = toFloat(fraud_count)/total
        RETURN count(r) AS cnt
        """
        )
        stats["F1_operator_anomalies"] = (await res.single())["cnt"]

        res = await session.run(
            """
        MATCH (c:Citizen)
        WHERE (c.is_ghost_flag = true OR c.is_dup_flag = true)
          AND (
            coalesce(c.transaction_rows, 0) > 0
            OR coalesce(c.tran_count_1, 0) > 0
            OR coalesce(c.tran_count_2, 0) > 0
          )
        MERGE (f:FraudFlag {rule: 'H1'})
        ON CREATE SET f.type = 'EXPLOITATION', f.description = 'Monetized Ghost (Active transactions on ghost/dup account)'
        MERGE (c)-[r:FLAGGED_AS]->(f)
        SET r.confidence = 98, r.detected_at = datetime()
        RETURN count(r) AS cnt
        """
        )
        stats["H1_ghost_monetization"] = (await res.single())["cnt"]

        res = await session.run(
            """
        MATCH (rc:RationCard)<-[r1:MEMBER_OF]-(c1:Citizen)
        MATCH (rc)<-[r2:MEMBER_OF]-(c2:Citizen)
        WHERE elementId(c1) < elementId(c2)
          AND r1.member_id = r2.member_id
          AND r1.member_id IS NOT NULL AND r1.member_id <> ''
        MERGE (f:FraudFlag {rule: 'I1'})
        ON CREATE SET f.type = 'IDENTITY_CLONE', f.description = 'Shared Member ID on same Ration Card'
        MERGE (c1)-[fl1:FLAGGED_AS]->(f)
        MERGE (c2)-[fl2:FLAGGED_AS]->(f)
        SET fl1.confidence = 100, fl1.detected_at = datetime(),
            fl2.confidence = 100, fl2.detected_at = datetime()
        RETURN count(DISTINCT c1) + count(DISTINCT c2) AS cnt
        """
        )
        stats["I1_member_id_conflicts"] = (await res.single())["cnt"]

        await session.run(
            """
        MATCH (g:GP)<-[:RESIDES_IN]-(c:Citizen)
        WHERE c.risk_tier IN ['HIGH', 'CRITICAL']
           OR c.vulnerability_score >= 60
           OR c.is_ghost_flag = true
           OR c.is_dup_flag = true
        WITH g, count(DISTINCT c) AS high_risk
        SET g.high_risk_count = high_risk,
            g.high_risk_pct = CASE
                WHEN COALESCE(g.total_citizens, 0) > 0
                THEN toFloat(high_risk) / g.total_citizens
                ELSE 0.0
            END
        """
        )

    logger.info(f"Graph Fraud Edges created: {stats}")
    return stats


async def run_full_sync(limit: Optional[int] = None, per_scheme_limit: Optional[int] = None):
    """
    Master runner:
      1. Ensure indexes
      2. Import curated beneficiary profile into Citizen/Enrollment graph
      3. Import payout aggregates into PayoutMonth graph
      4. Refresh citizen rollups
      5. Trigger vulnerability scoring
      6. Create fraud edges
    """
    from src.services.ai_analytics import calculate_vulnerability_scores

    logger.info("=" * 60)
    logger.info("Full Graph Sync Starting")
    logger.info("=" * 60)

    await ensure_graph_indexes()
    if per_scheme_limit is not None:
        imported_profiles = await sync_citizens_to_graph_per_scheme(
            per_scheme_limit=per_scheme_limit
        )
        imported_payouts = await sync_payouts_to_graph_per_scheme(
            per_scheme_limit=per_scheme_limit
        )
    else:
        imported_profiles = await sync_citizens_to_graph(limit=limit)
        imported_payouts = await sync_payouts_to_graph(limit=limit)
    await refresh_citizen_rollups()

    logger.info(
        f"Import done ({imported_profiles:,} profiles, {imported_payouts:,} payout windows). Running vulnerability scoring..."
    )
    scored = await calculate_vulnerability_scores()

    logger.info("Creating graph fraud edges...")
    fraud_stats = await create_fraud_edges()

    logger.info(
        f"Full Sync complete — {imported_profiles:,} profiles, {imported_payouts:,} payout windows, {scored:,} scored."
    )
    return {
        "imported_profiles": imported_profiles,
        "imported_payouts": imported_payouts,
        "scored": scored,
        "fraud_stats": fraud_stats,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync curated beneficiary graph into Neo4j.")
    parser.add_argument(
        "limit",
        nargs="?",
        type=int,
        default=None,
        help="Optional global limit for the profile sync.",
    )
    parser.add_argument(
        "--per-scheme-limit",
        type=int,
        default=None,
        help="Optional cap applied independently to each scheme_id for balanced test syncs.",
    )
    args = parser.parse_args()
    asyncio.run(run_full_sync(limit=args.limit, per_scheme_limit=args.per_scheme_limit))
