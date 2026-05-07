"""
Graph Sync Service — Full Dataset Import
=========================================
Pulls ALL citizens from PostgreSQL into Neo4j in batches.
Handles ~1 lakh records efficiently using UNWIND + MERGE.
Tracks progress and supports resumable imports via OFFSET pagination.
"""

import asyncio
import os
from typing import Any, Dict, List, Optional

import asyncpg

from src.core.config import get_settings
from src.core.logger import logger
from src.services.graph_db import get_driver

settings = get_settings()

DB_CONFIG = {
    "user": "postgres",
    "password": "postgres",
    "database": "srsdb",
    "host": "127.0.0.1",
    "port": 5434,
}

BATCH_SIZE = 2000  # Safe batch size for Neo4j UNWIND
CHECKPOINT_FILE = "/home/pulkitv52/Advance-rag/logs/backend/sync_checkpoint.txt"


async def get_db_connection():
    return await asyncpg.connect(**DB_CONFIG)


# ─────────────────────────────────────────────────────────────────────────────
# Core Cypher: MERGE Citizens + Geographic Hierarchy + Scheme Enrollment
# ─────────────────────────────────────────────────────────────────────────────

CITIZEN_SYNC_CYPHER = """
UNWIND $data AS row

// ── Citizen node ──────────────────────────────────────────────────────────
MERGE (c:Citizen {uid: row.uid})
ON CREATE SET
    c.name           = row.fullname,
    c.beneficiary_id = row.scheme_beneficiary_id,
    c.gender         = row.gender,
    c.dob            = row.member_dob,
    c.mobile         = row.mobile,
    c.age            = CASE WHEN row.member_dob IS NOT NULL AND row.member_dob <> '' AND row.member_dob <> 'None' THEN duration.between(date(row.member_dob), date()).years ELSE null END,
    c.lgd_block_code = row.lgd_block_code,
    c.type           = 'Citizen',
    c.is_ghost_flag  = false,
    c.is_dup_flag    = false,
    c.is_anomaly_flag= false,
    c.created_at     = datetime()
ON MATCH SET
    c.name           = COALESCE(row.fullname, c.name),
    c.gender         = COALESCE(row.gender, c.gender),
    c.dob            = COALESCE(row.member_dob, c.dob),
    c.mobile         = COALESCE(row.mobile, c.mobile),
    c.age            = CASE WHEN row.member_dob IS NOT NULL AND row.member_dob <> '' AND row.member_dob <> 'None' THEN duration.between(date(row.member_dob), date()).years ELSE c.age END,
    c.lgd_block_code = COALESCE(row.lgd_block_code, c.lgd_block_code),
    c.tran_count_1   = COALESCE(row.tran_count_1, c.tran_count_1),
    c.tran_count_2   = COALESCE(row.tran_count_2, c.tran_count_2),
    c.entry_time     = COALESCE(row.entry_ts, c.entry_time),
    c.updated_at     = datetime()

// ── Geographic hierarchy ───────────────────────────────────────────────────
MERGE (d:District {code: row.lgd_district_code})
ON CREATE SET d.name = row.lgd_district_name, d.type = 'Location'

MERGE (b:Block {code: row.lgd_block_code})
ON CREATE SET b.name = row.lgd_block_name, b.type = 'Location'

MERGE (g:GP {code: row.lgd_gp_code})
ON CREATE SET g.name = row.lgd_gp_name, g.type = 'Location', g.total_citizens = 0, g.high_risk_count = 0, g.high_risk_pct = 0.0

MERGE (g)-[:PART_OF]->(b)
MERGE (b)-[:PART_OF]->(d)
MERGE (c)-[:RESIDES_IN]->(g)

// ── Scheme enrollment ──────────────────────────────────────────────────────
MERGE (s:Scheme {id: row.scheme_id})
ON CREATE SET
    s.name = COALESCE(row.scheme_name, 'Swasthya Sathi'),
    s.type = 'Scheme',
    s.beneficiary_count = 0
MERGE (c)-[:ENROLLED_IN {status: 'Active'}]->(s)

// ── Identity Hubs (Permutations) ──────────────────────────────────────────
// Ration Card Hub
FOREACH (ignoreMe IN CASE WHEN row.ration_card_number IS NOT NULL AND row.ration_card_number <> "" THEN [1] ELSE [] END |
    MERGE (rc:RationCard {number: row.ration_card_number})
    ON CREATE SET rc.type = 'IdentityHub'
    MERGE (c)-[rel:MEMBER_OF]->(rc)
    SET rel.member_id = row.ration_card_memberid,
        rel.updated_at = datetime()
)

// Mobile Hub
FOREACH (ignoreMe IN CASE WHEN row.mobile IS NOT NULL AND row.mobile <> "" THEN [1] ELSE [] END |
    MERGE (m:Mobile {number: row.mobile})
    ON CREATE SET m.type = 'IdentityHub'
    MERGE (c)-[:HAS_MOBILE]->(m)
)

// Operator Hub (Entry Desk)
FOREACH (ignoreMe IN CASE WHEN row.entry_by IS NOT NULL AND row.entry_by <> "" THEN [1] ELSE [] END |
    MERGE (o:Operator {id: row.entry_by})
    ON CREATE SET o.type = 'AuditHub'
    MERGE (c)-[:REGISTERED_BY]->(o)
)

// Address Factory Hub
FOREACH (ignoreMe IN CASE WHEN row.address_sanitized IS NOT NULL AND row.address_sanitized <> "" THEN [1] ELSE [] END |
    MERGE (a:Address {text: row.address_sanitized})
    ON CREATE SET a.type = 'LocationHub'
    MERGE (c)-[:LIVES_AT]->(a)
)
"""


def _format_rows(rows) -> List[Dict]:
    """Normalise asyncpg Records into plain dicts safe for Neo4j."""
    out = []
    for r in rows:
        # Simple address sanitization (exact match factory)
        raw_addr = r.get("address") or ""
        sanitized_addr = raw_addr.strip().upper() if raw_addr else ""

        out.append(
            {
                "uid": r["uid"] or "",
                "scheme_beneficiary_id": r.get("scheme_beneficiary_id") or "",
                "fullname": (r.get("fullname") or "UNKNOWN").strip().upper(),
                "gender": (r.get("gender") or "").strip().upper(),
                "member_dob": str(r["member_dob"]) if r.get("member_dob") else None,
                "mobile": (r.get("mobile") or "").strip(),
                "ration_card_number": (r.get("ration_card_number") or "").strip(),
                "address_sanitized": sanitized_addr,
                "entry_by": (r.get("entry_by") or "").strip(),
                "lgd_district_code": str(r.get("lgd_district_code") or ""),
                "lgd_district_name": (r.get("lgd_district_name") or "Unknown District").strip(),
                "lgd_block_code": str(r.get("lgd_block_code") or ""),
                "lgd_block_name": (r.get("lgd_block_name") or "Unknown Block").strip(),
                "lgd_gp_code": str(r.get("lgd_gp_code") or ""),
                "lgd_gp_name": (r.get("lgd_gp_name") or "Unknown GP").strip(),
                "scheme_id": str(r.get("scheme_id") or "SS_001"),
                "scheme_name": r.get("scheme_name") or "Swasthya Sathi",
                "ration_card_memberid": (r.get("ration_card_memberid") or "").strip(),
                "tran_count_1": r.get("tran_count_1") or 0,
                "tran_count_2": r.get("tran_count_2") or 0,
                "entry_ts": str(r.get("entry_ts")) if r.get("entry_ts") else None,
            }
        )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Full Dataset Import — Paginated Batches
# ─────────────────────────────────────────────────────────────────────────────


async def sync_citizens_to_graph(limit: Optional[int] = None, batch_size: int = BATCH_SIZE) -> int:
    """
    Pulls ALL citizens from PostgreSQL and upserts them into Neo4j.

    Args:
        limit:      If set, imports at most this many records (useful for testing).
                    If None, imports the entire dataset.
        batch_size: Number of records per Neo4j transaction (default 2000).

    Returns:
        Total number of records imported.
    """
    conn = await get_db_connection()
    driver = await get_driver()
    total_imported = 0

    try:
        # ── 1. Count total records ─────────────────────────────────────────
        count_query = "SELECT count(*) FROM srsadmin.swasthya_sathi_beneficiary WHERE uid IS NOT NULL"
        total_in_db = await conn.fetchval(count_query)
        cap = min(limit, total_in_db) if limit else total_in_db
        logger.info(
            f"Knowledge Graph Sync — {cap:,} records to process (DB total: {total_in_db:,})"
        )

        # ── 2. Paginate through all records ───────────────────────────────
        fetch_query = """
        SELECT
            uid, scheme_beneficiary_id, fullname, gender, member_dob,
            mobile, ration_card_number, address, entry_by,
            lgd_district_code, lgd_district_name,
            lgd_block_code,   lgd_block_name,
            lgd_gp_code,      lgd_gp_name,
            scheme_id,        ration_card_memberid,
            tran_count_1,     tran_count_2,
            entry_ts
        FROM srsadmin.swasthya_sathi_beneficiary
        WHERE uid IS NOT NULL
        ORDER BY uid
        LIMIT $1 OFFSET $2
        """

        offset = 0
        if os.path.exists(CHECKPOINT_FILE):
            try:
                with open(CHECKPOINT_FILE, "r") as f:
                    offset = int(f.read().strip())
                logger.info(f"Resuming sync from checkpoint: Offset {offset:,}")
                if limit:
                    cap = min(limit + offset, total_in_db)
            except Exception as e:
                logger.warning(f"Could not read checkpoint file: {e}. Starting from 0.")

        async with driver.session() as session:
            while offset < cap:
                current_batch_size = min(batch_size, cap - offset)
                rows = await conn.fetch(fetch_query, current_batch_size, offset)
                if not rows:
                    break

                data = _format_rows(rows)
                await session.run(CITIZEN_SYNC_CYPHER, data=data)

                total_imported += len(rows)
                offset += len(rows)

                # Save checkpoint
                try:
                    with open(CHECKPOINT_FILE, "w") as f:
                        f.write(str(offset))
                except Exception as e:
                    logger.warning(f"Failed to save checkpoint: {e}")

                pct = (offset / total_in_db) * 100
                logger.info(f"  Progress: {offset:,}/{total_in_db:,} ({pct:.1f}%)")

        # Clean up checkpoint on full completion
        if offset >= total_in_db and os.path.exists(CHECKPOINT_FILE):
            os.remove(CHECKPOINT_FILE)
            logger.info("Sync complete. Checkpoint file removed.")

        logger.info(
            f"Graph Sync session complete — {total_imported:,} citizens processed in this run."
        )
        return total_imported

    except Exception as e:
        logger.error(f"Graph Sync failed at offset {offset}: {e}")
        raise
    finally:
        await conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Create Neo4j Indexes (run once for performance)
# ─────────────────────────────────────────────────────────────────────────────


async def ensure_graph_indexes():
    """
    Creates indexes and constraints for high-performance graph queries.
    Safe to run multiple times (uses IF NOT EXISTS).
    """
    driver = await get_driver()
    index_statements = [
        "CREATE CONSTRAINT citizen_uid IF NOT EXISTS FOR (c:Citizen) REQUIRE c.uid IS UNIQUE",
        "CREATE CONSTRAINT district_code IF NOT EXISTS FOR (d:District) REQUIRE d.code IS UNIQUE",
        "CREATE CONSTRAINT block_code IF NOT EXISTS FOR (b:Block) REQUIRE b.code IS UNIQUE",
        "CREATE CONSTRAINT gp_code IF NOT EXISTS FOR (g:GP) REQUIRE g.code IS UNIQUE",
        "CREATE CONSTRAINT scheme_id IF NOT EXISTS FOR (s:Scheme) REQUIRE s.id IS UNIQUE",
        "CREATE INDEX citizen_name IF NOT EXISTS FOR (c:Citizen) ON (c.name)",
        "CREATE INDEX citizen_dob  IF NOT EXISTS FOR (c:Citizen) ON (c.dob)",
        "CREATE INDEX citizen_score IF NOT EXISTS FOR (c:Citizen) ON (c.vulnerability_score)",
        "CREATE INDEX citizen_tier  IF NOT EXISTS FOR (c:Citizen) ON (c.risk_tier)",
    ]
    async with driver.session() as session:
        for stmt in index_statements:
            try:
                await session.run(stmt)
            except Exception as e:
                logger.warning(f"Index/constraint already exists or failed: {e}")
    logger.info("Neo4j indexes and constraints verified.")


# ─────────────────────────────────────────────────────────────────────────────
# Fraud Detection: Edges & Graph Patterns
# ─────────────────────────────────────────────────────────────────────────────


async def create_fraud_edges() -> dict:
    """
    Creates fraud-specific graph relationships (POTENTIAL_DUPLICATE, SAME_DOB_AT_GP, FLAGGED_AS, HIGH_RISK_CLUSTER).
    Returns stats for created objects.
    """
    driver = await get_driver()
    stats = {}
    async with driver.session() as session:
        # B1: Exact duplicate
        res = await session.run("""
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
        """)
        stats["B1_exact_duplicates"] = (await res.single())["cnt"]

        # B3: DOB Cluster (Ghost factory)
        res = await session.run("""
        CALL apoc.periodic.iterate(
            "MATCH (c1:Citizen)-[:RESIDES_IN]->(g:GP)
             WITH g, c1.dob AS dob, count(c1) AS cluster_size, collect(c1) as citizens
             WHERE cluster_size >= 5 AND dob IS NOT NULL
             RETURN citizens, dob, g.code AS gcode, cluster_size",
            "UNWIND citizens as c
             UNWIND citizens as other
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
        """)
        stats["B3_dob_cluster_edges"] = (await res.single())["cnt"]

        # A1: Ghost Age > 110
        res = await session.run("""
        CALL apoc.periodic.iterate(
            "MATCH (c:Citizen) WHERE c.age > 110 RETURN c",
            "MERGE (f:FraudFlag {rule: 'A1'})
             ON CREATE SET f.type = 'GHOST', f.description = 'Age > 110'
             MERGE (c)-[r:FLAGGED_AS]->(f)
             SET r.confidence = 85, r.detected_at = datetime(), c.is_ghost_flag = true",
            {batchSize: 5000, parallel: false}
        ) YIELD total RETURN total AS cnt
        """)
        stats["A1_ghost_age"] = (await res.single())["cnt"]

        # A2: Ghost Future DOB
        res = await session.run("""
        MATCH (c:Citizen)
        WHERE c.age < 0
        MERGE (f:FraudFlag {rule: 'A2'})
        ON CREATE SET f.type = 'GHOST', f.description = 'DOB in future'
        MERGE (c)-[r:FLAGGED_AS]->(f)
        SET r.confidence = 90, r.detected_at = datetime(), c.is_ghost_flag = true
        RETURN count(r) as cnt
        """)
        stats["A2_future_dob"] = (await res.single())["cnt"]

        # D1: Missing DOB
        res = await session.run("""
        MATCH (c:Citizen)
        WHERE c.dob IS NULL OR c.dob = '' OR c.dob = 'None'
        MERGE (f:FraudFlag {rule: 'D1'})
        ON CREATE SET f.type = 'DATA_QUALITY', f.description = 'Missing DOB'
        MERGE (c)-[r:FLAGGED_AS]->(f)
        SET r.confidence = 60, r.detected_at = datetime()
        RETURN count(r) as cnt
        """)
        stats["D1_missing_dob"] = (await res.single())["cnt"]

        # Update GP/Scheme stats (total citizens, beneficiaries)
        await session.run("""
        MATCH (g:GP)<-[:RESIDES_IN]-(c:Citizen)
        WITH g, count(c) as total
        SET g.total_citizens = total
        """)

        await session.run("""
        MATCH (s:Scheme)<-[:ENROLLED_IN]-(c:Citizen)
        WITH s, count(c) as total
        SET s.beneficiary_count = total
        """)

        # C1: Scheme Concentration Anomaly
        res = await session.run("""
        MATCH (g:GP)<-[:RESIDES_IN]-(c:Citizen)-[:ENROLLED_IN]->(s:Scheme)
        WITH g, s, count(c) as gp_scheme_count
        WHERE gp_scheme_count >= 50 AND s.beneficiary_count > 0
        WITH g, s, gp_scheme_count, toFloat(gp_scheme_count) / s.beneficiary_count as ratio
        WHERE ratio > 0.15
        MERGE (g)-[r:HIGH_RISK_CLUSTER]->(s)
        SET r.concentration_ratio = ratio,
            r.gp_beneficiary_count = gp_scheme_count,
            r.total_scheme_count = s.beneficiary_count,
            r.rule = 'C1'
        RETURN count(r) as cnt
        """)
        stats["C1_scheme_concentration"] = (await res.single())["cnt"]

        # E1: Household Overload (Shared Ration Card Ring)
        res = await session.run("""
        MATCH (rc:RationCard)<-[:MEMBER_OF]-(c:Citizen)
        WITH rc, count(c) as members
        WHERE members > 10
        MERGE (f:FraudFlag {rule: 'E1'})
        ON CREATE SET f.type = 'HOUSEHOLD_RING', f.description = 'Ration Card Shared by >10 UIDs'
        MERGE (rc)-[r:FLAGGED_AS]->(f)
        SET r.confidence = 95, r.detected_at = datetime()
        RETURN count(r) as cnt
        """)
        stats["E1_household_rings"] = (await res.single())["cnt"]

        # F1: Operator Corruption/Anomaly
        res = await session.run("""
        MATCH (o:Operator)<-[:REGISTERED_BY]-(c:Citizen)
        WITH o, count(c) as total,
             count(CASE WHEN c.is_ghost_flag = true OR c.is_dup_flag = true THEN 1 END) as fraud_count
        WHERE total > 20 AND (toFloat(fraud_count)/total) > 0.15
        MERGE (f:FraudFlag {rule: 'F1'})
        ON CREATE SET f.type = 'INTERNAL_ANOMALY', f.description = 'High Fraud registration rate (>15%)'
        MERGE (o)-[r:FLAGGED_AS]->(f)
        SET r.confidence = 90, r.detected_at = datetime(), r.error_rate = toFloat(fraud_count)/total
        RETURN count(r) as cnt
        """)
        stats["F1_operator_anomalies"] = (await res.single())["cnt"]

        # H1: Ghost Monetization Persistence
        res = await session.run("""
        MATCH (c:Citizen)
        WHERE (c.is_ghost_flag = true OR c.is_dup_flag = true)
          AND (c.tran_count_1 > 0 OR c.tran_count_2 > 0)
        MERGE (f:FraudFlag {rule: 'H1'})
        ON CREATE SET f.type = 'EXPLOITATION', f.description = 'Monetized Ghost (Active transactions on ghost/dup account)'
        MERGE (c)-[r:FLAGGED_AS]->(f)
        SET r.confidence = 98, r.detected_at = datetime()
        RETURN count(r) as cnt
        """)
        stats["H1_ghost_monetization"] = (await res.single())["cnt"]

        # I1: Member ID Conflict Persistence
        res = await session.run("""
        MATCH (rc:RationCard)<-[r1:MEMBER_OF]-(c1:Citizen)
        MATCH (rc)<-[r2:MEMBER_OF]-(c2:Citizen)
        WHERE elementId(c1) < elementId(c2)
          AND r1.member_id = r2.member_id 
          AND r1.member_id IS NOT NULL AND r1.member_id <> ""
        MERGE (f:FraudFlag {rule: 'I1'})
        ON CREATE SET f.type = 'IDENTITY_CLONE', f.description = 'Shared Member ID on same Ration Card'
        MERGE (c1)-[fl1:FLAGGED_AS]->(f)
        MERGE (c2)-[fl2:FLAGGED_AS]->(f)
        SET fl1.confidence = 100, fl1.detected_at = datetime(),
            fl2.confidence = 100, fl2.detected_at = datetime()
        RETURN count(DISTINCT c1) + count(DISTINCT c2) as cnt
        """)
        stats["I1_member_id_conflicts"] = (await res.single())["cnt"]

        # Update GP high risk scores
        await session.run("""
        MATCH (g:GP)<-[:RESIDES_IN]-(c:Citizen)
        WHERE c.risk_tier IN ['HIGH', 'CRITICAL'] OR c.risk_score >= 60 OR c.is_ghost_flag = true OR c.is_dup_flag = true
        WITH g, count(c) as high_risk
        SET g.high_risk_count = high_risk,
            g.high_risk_pct = CASE WHEN COALESCE(g.total_citizens, 0) > 0 THEN toFloat(high_risk) / g.total_citizens ELSE 0.0 END
        """)

    logger.info(f"Graph Fraud Edges created: {stats}")
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Full Sync Runner (indexes → import → score → fraud edges)
# ─────────────────────────────────────────────────────────────────────────────


async def run_full_sync(limit: Optional[int] = None):
    """
    Master runner:
      1. Ensure indexes
      2. Import all citizens from PostgreSQL
      3. Trigger vulnerability scoring on the full graph
    """
    from src.services.ai_analytics import calculate_vulnerability_scores

    logger.info("=" * 60)
    logger.info("Full Graph Sync Starting")
    logger.info("=" * 60)

    await ensure_graph_indexes()
    imported = await sync_citizens_to_graph(limit=limit)

    logger.info(f"Import done ({imported:,} records). Running vulnerability scoring...")
    scored = await calculate_vulnerability_scores()

    logger.info("Creating graph fraud edges...")
    fraud_stats = await create_fraud_edges()

    logger.info(f"Full Sync complete — {imported:,} imported, {scored:,} scored.")
    return {"imported": imported, "scored": scored, "fraud_stats": fraud_stats}


if __name__ == "__main__":
    import sys

    # Usage: python graph_sync.py [limit]
    # Example: python graph_sync.py 10000   → imports first 10k for testing
    #          python graph_sync.py          → imports everything
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(run_full_sync(limit=lim))
