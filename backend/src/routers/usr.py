"""
Unified Social Registry (USR) API Router
=========================================
Provides data endpoints for the Executive Dashboard.
Fraud detection uses a confidence-weighted 4-rule-set system:
  Rule Set A: Ghost Beneficiary Detection
  Rule Set B: Duplicate Identity Detection (with fuzzy name matching)
  Rule Set C: Scheme Anomaly Detection
  Rule Set D: Data Quality Audit
"""

import hashlib
import io
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.database import get_session
from src.core.logger import logger
from src.models.review import DecisionReview
from src.services import ai_analytics, graph_sync
from src.services.graph_db import get_driver

router = APIRouter(prefix="/api/usr", tags=["Social Registry"])


async def run_neo4j_query(query: str, params: dict = {}):
    """Helper to run a Neo4j query and return data."""
    try:
        driver = await get_driver()
        async with driver.session() as session:
            result = await session.run(query, **params)
            return await result.data()
    except Exception as e:
        logger.error(f"Neo4j query failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# KPI Stats
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/stats")
async def get_summary_stats():
    """Returns top-level KPI stats from cached summaries, with a live graph fallback."""
    stats = await run_neo4j_query("""
        MATCH (s:GlobalStats {id: 'USR_HUB'})
        MATCH (c:Citizen)
        WITH s, count(c) AS current_graph_count
        RETURN 
            s.total_citizens AS persisted_total,
            current_graph_count AS live_graph_total,
            s.avg_vulnerability AS avg_vulnerability,
            s.critical_count AS critical_count,
            s.high_risk_count AS high_risk_count,
            s.last_updated AS last_updated,
            2234522 AS physical_registry_total
    """)

    if not stats:
        logger.info("USR stats cache missing. Falling back to live Citizen aggregates.")
        live_data = await run_neo4j_query("""
            MATCH (c:Citizen)
            RETURN
                count(c) AS total_citizens,
                round(coalesce(avg(c.vulnerability_score), 0) * 100) / 100 AS avg_vulnerability,
                count(CASE WHEN c.risk_tier = 'CRITICAL' OR coalesce(c.vulnerability_score, 0) >= 80 THEN 1 END) AS critical_count,
                count(CASE WHEN c.risk_tier IN ['HIGH', 'CRITICAL'] OR coalesce(c.vulnerability_score, 0) >= 60 THEN 1 END) AS high_risk_count,
                count(CASE WHEN toLower(coalesce(c.gender, '')) = 'female' THEN 1 END) AS female_count,
                count(CASE WHEN c.risk_tier = 'CRITICAL' THEN 1 END) AS critical_tier_count
        """)
        if live_data:
            current = live_data[0]
            registry_total = 2234522
            coverage = (current["total_citizens"] / registry_total) * 100 if registry_total else 0.0
            return {
                "total_citizens": current["total_citizens"],
                "avg_vulnerability": current["avg_vulnerability"],
                "critical_count": current["critical_count"],
                "high_risk_count": current["high_risk_count"],
                "last_updated": None,
                "registry_total": registry_total,
                "coverage_pct": round(coverage, 1),
                "female_count": current["female_count"],
                "critical_tier_count": current["critical_tier_count"],
            }
        return {
            "total_citizens": 0,
            "avg_vulnerability": 0,
            "critical_count": 0,
            "high_risk_count": 0,
            "last_updated": None,
            "registry_total": 2234522,
            "coverage_pct": 0.0,
            "female_count": 0,
            "critical_tier_count": 0,
        }

    data = stats[0]
    coverage = (data["live_graph_total"] / data["physical_registry_total"]) * 100

    return {
        "total_citizens": data["live_graph_total"],
        "avg_vulnerability": data["avg_vulnerability"],
        "critical_count": data["critical_count"],
        "high_risk_count": data["high_risk_count"],
        "last_updated": data["last_updated"],
        "registry_total": data["physical_registry_total"],
        "coverage_pct": round(coverage, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# District Heatmap
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/heatmap")
async def get_district_heatmap():
    """Returns per-district aggregates from cached District properties, with a live graph fallback."""
    data = await run_neo4j_query("""
        MATCH (d:District)
        WHERE d.citizen_count IS NOT NULL
        RETURN
            d.name           AS district,
            d.citizen_count  AS citizen_count,
            d.avg_risk_score AS avg_risk_score,
            d.critical_count AS critical_count,
            d.high_count     AS high_count
        ORDER BY d.avg_risk_score DESC
    """)
    if data:
        return {"districts": data}

    logger.info("USR heatmap cache missing. Falling back to live district aggregates.")
    live_data = await run_neo4j_query("""
        MATCH (d:District)<-[:PART_OF]-(b:Block)<-[:PART_OF]-(g:GP)<-[:RESIDES_IN]-(c:Citizen)
        RETURN
            d.name AS district,
            count(DISTINCT c) AS citizen_count,
            round(coalesce(avg(c.vulnerability_score), 0) * 100) / 100 AS avg_risk_score,
            count(DISTINCT CASE WHEN c.risk_tier = 'CRITICAL' OR coalesce(c.vulnerability_score, 0) >= 80 THEN c END) AS critical_count,
            count(DISTINCT CASE WHEN c.risk_tier IN ['HIGH', 'CRITICAL'] OR coalesce(c.vulnerability_score, 0) >= 60 THEN c END) AS high_count
        ORDER BY avg_risk_score DESC
    """)
    return {"districts": live_data}


# ─────────────────────────────────────────────────────────────────────────────
# Top Risk Citizens
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/top-risk")
async def get_top_risk_citizens(limit: int = 20, tier: str = None, segment: str = None):
    """Returns the most vulnerable citizens, optionally filtered by tier or cohort segment."""
    tier_filter = f"AND c.risk_tier = '{tier.upper()}'" if tier else ""
    
    segment_filter = ""
    if segment == 'elderly':
        segment_filter = "AND toInteger(split(c.dob, '-')[0]) <= date().year - 60"
    elif segment == 'children':
        segment_filter = "AND toInteger(split(c.dob, '-')[0]) >= date().year - 18"
    elif segment == 'workers':
        segment_filter = "AND toInteger(split(c.dob, '-')[0]) > date().year - 60 AND toInteger(split(c.dob, '-')[0]) < date().year - 18"
        
    data = await run_neo4j_query(f"""
        MATCH (c:Citizen)
        WHERE c.vulnerability_score IS NOT NULL {tier_filter} {segment_filter}
        WITH c
        ORDER BY c.vulnerability_score DESC
        LIMIT {limit}
        OPTIONAL MATCH (c)-[:RESIDES_IN]->(g:GP)-[:PART_OF]->(b:Block)-[:PART_OF]->(d:District)
        OPTIONAL MATCH (c)-[:ENROLLED_IN]->(s:Scheme)
        RETURN
            c.name                 AS name,
            c.gender               AS gender,
            c.dob                  AS dob,
            c.uid                  AS uid,
            c.vulnerability_score  AS score,
            c.risk_tier            AS tier,
            head(collect(distinct d.name)) AS district,
            head(collect(distinct b.name)) AS block,
            head(collect(distinct g.name)) AS gp,
            collect(distinct s.name)        AS schemes
        ORDER BY score DESC
    """)
    return {"citizens": data}


# ─────────────────────────────────────────────────────────────────────────────
# Score Distribution
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/score-distribution")
async def get_score_distribution():
    """Returns citizens grouped by risk tier."""
    data = await run_neo4j_query("""
        MATCH (c:Citizen)
        WHERE c.risk_tier IS NOT NULL
        RETURN c.risk_tier AS tier, count(c) AS count
        ORDER BY count DESC
    """)
    return {"distribution": data}


# ─────────────────────────────────────────────────────────────────────────────
# Fraud: Ghost Beneficiaries (Rule Set A)
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Fraud: Ghost Beneficiaries (Rule Set A)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/fraud/ghosts")
async def get_ghost_beneficiaries():
    """Returns detected ghost beneficiaries with evidence fallbacks."""
    data = await run_neo4j_query("""
        MATCH (c:Citizen)-[rel:FLAGGED_AS]->(f:FraudFlag)
        WHERE f.type = 'GHOST'
        OPTIONAL MATCH (c)-[:RESIDES_IN]->(g:GP)
        OPTIONAL MATCH (c)-[:ENROLLED_IN]->(s:Scheme)
        WITH c, rel, f, g, collect(s.name) AS schemes
        RETURN 
            c.name AS name, 
            c.uid AS uid, 
            coalesce(c.dob, 'Unknown') AS dob,
            coalesce(g.name, c.gp_name, 'Unknown') AS shared_gp,
            coalesce(schemes[0], 'General') AS scheme,
            rel.confidence AS confidence, 
            f.rule AS rule, 
            f.description AS description
        ORDER BY rel.confidence DESC
        LIMIT 200
    """)
    return {"total": len(data), "flags": data}


# ─────────────────────────────────────────────────────────────────────────────
# Unified Intelligence Feed (A-I)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/intelligence/feed")
async def get_intelligence_feed(
    limit: int = 100,
    offset: int = 0,
    include_total: bool = True,
    session: AsyncSession = Depends(get_session),
):
    """
    Unified feed of all Intelligence Flags from the Knowledge Graph.
    Consolidates Ghosts, Duplicates, and Anomalies into a single stream.
    """
    # Keep page sizes conservative to avoid large in-memory UNION+ORDER BY workloads.
    safe_limit = max(1, min(limit, 50))
    safe_offset = max(0, offset)

    total: int | None = None
    if include_total:
        total_rows = await run_neo4j_query("""
            CALL {
                MATCH (c:Citizen)-[rel:FLAGGED_AS]->(f:FraudFlag)
                RETURN 1 AS row_count
                UNION ALL
                MATCH (:Operator)-[rel:FLAGGED_AS]->(:FraudFlag)
                RETURN 1 AS row_count
                UNION ALL
                MATCH (:RationCard)-[rel:FLAGGED_AS]->(:FraudFlag)
                RETURN 1 AS row_count
                UNION ALL
                MATCH (:Citizen)-[:POTENTIAL_DUPLICATE]->(:Citizen)
                RETURN 1 AS row_count
                UNION ALL
                MATCH (:Citizen)-[:SAME_DOB_AT_GP]->(:Citizen)
                RETURN 1 AS row_count
            }
            RETURN count(row_count) AS total
        """)
        total = int(total_rows[0].get("total", 0)) if total_rows else 0

    data = await run_neo4j_query(
        """
        CALL {
            MATCH (c:Citizen)-[rel:FLAGGED_AS]->(f:FraudFlag)
            OPTIONAL MATCH (c)-[:RESIDES_IN]->(:GP)-[:PART_OF]->(:Block)-[:PART_OF]->(d:District)
            WITH c, rel, f, head(collect(DISTINCT d.name)) AS district_name
            RETURN
                f.rule AS rule,
                coalesce(f.label, f.rule) AS label,
                f.type AS type,
                f.description AS description,
                c.name AS name,
                c.uid AS uid,
                coalesce(c.dob, 'Unknown') AS dob,
                coalesce(c.gp_name, 'Unknown') AS gp_name,
                coalesce(district_name, 'Unknown') AS district,
                coalesce(rel.confidence, 0) AS confidence,
                toString(rel.detected_at) AS detected_at
            UNION ALL
            MATCH (o:Operator)-[rel:FLAGGED_AS]->(f:FraudFlag)
            RETURN
                f.rule AS rule,
                coalesce(f.label, f.rule) AS label,
                coalesce(f.type, 'INTERNAL_ANOMALY') AS type,
                coalesce(f.description, 'Operator-level anomaly') AS description,
                ('Operator ' + coalesce(o.id, 'UNKNOWN')) AS name,
                coalesce(o.id, '') AS uid,
                'Unknown' AS dob,
                'N/A' AS gp_name,
                'N/A' AS district,
                coalesce(rel.confidence, 0) AS confidence,
                toString(rel.detected_at) AS detected_at
            UNION ALL
            MATCH (rc:RationCard)-[rel:FLAGGED_AS]->(f:FraudFlag)
            RETURN
                f.rule AS rule,
                coalesce(f.label, f.rule) AS label,
                coalesce(f.type, 'HOUSEHOLD_ANOMALY') AS type,
                coalesce(f.description, 'Ration-card hub anomaly') AS description,
                ('Ration Card ' + coalesce(rc.number, 'UNKNOWN')) AS name,
                coalesce(rc.number, '') AS uid,
                'Unknown' AS dob,
                'N/A' AS gp_name,
                'N/A' AS district,
                coalesce(rel.confidence, 0) AS confidence,
                toString(rel.detected_at) AS detected_at
            UNION ALL
            MATCH (c1:Citizen)-[rel:POTENTIAL_DUPLICATE]->(c2:Citizen)
            OPTIONAL MATCH (c1)-[:RESIDES_IN]->(:GP)-[:PART_OF]->(:Block)-[:PART_OF]->(d:District)
            WITH c1, c2, rel, head(collect(DISTINCT d.name)) AS district_name
            RETURN
                coalesce(rel.rule, 'B1') AS rule,
                coalesce(rel.rule, 'B1') AS label,
                'DUPLICATE' AS type,
                ('Potential duplicate with ' + coalesce(c2.uid, 'unknown UID')) AS description,
                c1.name AS name,
                c1.uid AS uid,
                coalesce(c1.dob, 'Unknown') AS dob,
                coalesce(c1.gp_name, 'Unknown') AS gp_name,
                coalesce(district_name, 'Unknown') AS district,
                coalesce(rel.confidence, 85) AS confidence,
                toString(rel.detected_at) AS detected_at
            UNION ALL
            MATCH (c1:Citizen)-[rel:SAME_DOB_AT_GP]->(c2:Citizen)
            OPTIONAL MATCH (c1)-[:RESIDES_IN]->(:GP)-[:PART_OF]->(:Block)-[:PART_OF]->(d:District)
            WITH c1, c2, rel, head(collect(DISTINCT d.name)) AS district_name
            RETURN
                coalesce(rel.rule, 'B3') AS rule,
                coalesce(rel.rule, 'B3') AS label,
                'DUPLICATE' AS type,
                ('Same DOB at GP as ' + coalesce(c2.uid, 'unknown UID')) AS description,
                c1.name AS name,
                c1.uid AS uid,
                coalesce(c1.dob, 'Unknown') AS dob,
                coalesce(c1.gp_name, 'Unknown') AS gp_name,
                coalesce(district_name, 'Unknown') AS district,
                coalesce(rel.confidence, 80) AS confidence,
                toString(rel.detected_at) AS detected_at
        }
        RETURN
            rule, label, type, description, name, uid, dob, gp_name, district, confidence, detected_at
        ORDER BY confidence DESC, detected_at DESC
        SKIP $offset
        LIMIT $limit
    """,
        params={"limit": safe_limit, "offset": safe_offset},
    )

    feed = []
    for row in data:
        key = "|".join(
            [
                str(row.get("rule") or ""),
                str(row.get("uid") or ""),
                str(row.get("name") or ""),
                str(row.get("detected_at") or ""),
                str(row.get("description") or ""),
            ]
        )
        row_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        feed.append({**row, "id": row_id})

    row_ids = [item["id"] for item in feed]
    latest_review_by_id = {}
    if row_ids:
        review_rows = (
            await session.exec(
                select(DecisionReview)
                .where(DecisionReview.decision_id.in_(row_ids))
                .order_by(desc(DecisionReview.reviewed_at))
            )
        ).all()
        for review in review_rows:
            if review.decision_id not in latest_review_by_id:
                latest_review_by_id[review.decision_id] = {
                    "action": review.action,
                    "note": review.note,
                    "reviewed_by": review.reviewed_by,
                    "reviewed_at": review.reviewed_at,
                }

    enriched = [
        {
            **item,
            "latest_review": latest_review_by_id.get(item["id"]),
        }
        for item in feed
    ]
    return {"total": total, "limit": safe_limit, "offset": safe_offset, "feed": enriched}


# ─────────────────────────────────────────────────────────────────────────────
# Fraud: Duplicate Identities (Rule Set B)
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Fraud: Scheme Anomalies (Rule Set C)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/fraud/anomalies")
async def get_scheme_anomalies():
    """
    Rule Set C: Detects irregular scheme utilization patterns.
    C1 — GP benefit concentration spike (Confidence 75)
    C2 — Mutually exclusive scheme membership (Confidence 90)
    """
    results = await ai_analytics.detect_scheme_anomalies()
    all_flags = []
    for rule, cases in results.items():
        all_flags.extend(cases)
    return {
        "total": len(all_flags),
        "by_rule": {rule: len(cases) for rule, cases in results.items()},
        "flags": sorted(all_flags, key=lambda x: x.get("confidence", 0), reverse=True),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Fraud: Unified Summary (for dashboard — legacy compatible)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/fraud")
async def get_fraud_summary():
    """
    Returns a unified fraud cluster summary combining all rule sets.
    Confidence-gated: only surfaces cases with confidence >= 70.
    """
    # Run the old-style query for backward compatibility with the dashboard
    data = await run_neo4j_query("""
        MATCH (c1:Citizen)-[:RESIDES_IN]->(g:GP)<-[:RESIDES_IN]-(c2:Citizen)
        WHERE id(c1) < id(c2)
          AND c1.dob = c2.dob
          AND c1.gender = c2.gender
          AND c1.uid <> c2.uid
        RETURN
            c1.name    AS person_1,
            c2.name    AS person_2,
            g.name     AS shared_gp,
            c1.dob     AS dob,
            c1.gender  AS gender,
            80         AS confidence,
            'B1_EXACT_DOB_GENDER_GP' AS rule
        LIMIT 15
    """)
    return {"clusters": data}


# ─────────────────────────────────────────────────────────────────────────────
# Field Audit Queue (Priority List)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/audit-queue")
async def get_field_audit_queue(
    limit: int = 50,
    rules: str | None = Query(default=None, description="Comma-separated rule codes, e.g. A1,B1,F1"),
    district: str | None = Query(default=None, description="District name exact match"),
    mauza: str | None = Query(default=None, description="Mauza/Block name exact match"),
):
    """
    Returns the top N citizens requiring urgent field verification.
    Selection criteria: Critical Risk Tier (Score > 60) AND multiple fraud flags.
    """
    selected_rules: list[str] = []
    if rules:
        raw_rules = [r.strip().upper() for r in rules.split(",") if r.strip()]
        selected_rules = [r for r in raw_rules if all(ch.isalnum() or ch == "_" for ch in r)]

    district_filter = (district or "").strip()
    mauza_filter = (mauza or "").strip()

    total_rows = await run_neo4j_query(
        """
        MATCH (c:Citizen)-[:FLAGGED_AS]->(fl:FraudFlag)
        WHERE ($rules_count = 0 OR toUpper(coalesce(fl.rule, '')) IN $rules)
        OPTIONAL MATCH (c)-[:RESIDES_IN]->(:GP)-[:PART_OF]->(b:Block)-[:PART_OF]->(d:District)
        WITH c, b, d
        WHERE ($district = '' OR coalesce(d.name, '') = $district)
          AND ($mauza = '' OR coalesce(b.name, '') = $mauza)
        RETURN count(DISTINCT c) AS total
        """,
        {
            "rules": selected_rules,
            "rules_count": len(selected_rules),
            "district": district_filter,
            "mauza": mauza_filter,
        },
    )
    total = int(total_rows[0].get("total", 0)) if total_rows else 0

    data = await run_neo4j_query("""
        MATCH (c:Citizen)-[f:FLAGGED_AS]->(fl:FraudFlag)
        WHERE ($rules_count = 0 OR toUpper(coalesce(fl.rule, '')) IN $rules)
        OPTIONAL MATCH (c)-[:RESIDES_IN]->(g:GP)-[:PART_OF]->(b:Block)-[:PART_OF]->(d:District)
        WITH c, g, b, d, f, fl
        WHERE ($district = '' OR coalesce(d.name, '') = $district)
          AND ($mauza = '' OR coalesce(b.name, '') = $mauza)
        WITH
            c,
            head(collect(DISTINCT g.name)) AS gp_name,
            head(collect(DISTINCT b.name)) AS block_name,
            head(collect(DISTINCT d.name)) AS district_name,
            count(DISTINCT f) as flags,
            collect(DISTINCT fl.description) as flag_notes,
            collect(DISTINCT toUpper(coalesce(fl.rule, 'UNKNOWN'))) as rule_codes
        RETURN
            c.name          AS name,
            c.uid           AS uid,
            c.dob           AS dob,
            c.gender        AS gender,
            c.vulnerability_score AS score,
            district_name   AS district,
            block_name      AS block,
            gp_name         AS gp,
            flags,
            rule_codes,
            flag_notes
        ORDER BY flags DESC, c.vulnerability_score DESC
        LIMIT $limit
    """, {
        "limit": int(limit),
        "rules": selected_rules,
        "rules_count": len(selected_rules),
        "district": district_filter,
        "mauza": mauza_filter,
    })
    return {"queue": data, "total": total, "limit": int(limit)}


@router.get("/intelligence/filters")
async def get_intelligence_filters():
    """Returns dynamic filter values for district, mauza(block), and rule."""
    district_rows = await run_neo4j_query("""
        MATCH (:Citizen)-[:RESIDES_IN]->(:GP)-[:PART_OF]->(:Block)-[:PART_OF]->(d:District)
        WHERE d.name IS NOT NULL
        RETURN DISTINCT d.name AS value
        ORDER BY value
    """)
    mauza_rows = await run_neo4j_query("""
        MATCH (:Citizen)-[:RESIDES_IN]->(:GP)-[:PART_OF]->(b:Block)
        WHERE b.name IS NOT NULL
        RETURN DISTINCT b.name AS value
        ORDER BY value
    """)
    rule_rows = await run_neo4j_query("""
        MATCH (:Citizen)-[:FLAGGED_AS]->(f:FraudFlag)
        WHERE f.rule IS NOT NULL
        RETURN DISTINCT toUpper(f.rule) AS value
        ORDER BY value
    """)
    district_mauza_rows = await run_neo4j_query("""
        MATCH (:Citizen)-[:RESIDES_IN]->(:GP)-[:PART_OF]->(b:Block)-[:PART_OF]->(d:District)
        WHERE d.name IS NOT NULL AND b.name IS NOT NULL
        RETURN DISTINCT d.name AS district, b.name AS mauza
        ORDER BY district, mauza
    """)

    districts = [str(r.get("value", "")).strip() for r in district_rows if str(r.get("value", "")).strip()]
    mauzas = [str(r.get("value", "")).strip() for r in mauza_rows if str(r.get("value", "")).strip()]
    rules = [str(r.get("value", "")).strip() for r in rule_rows if str(r.get("value", "")).strip()]

    return {
        "districts": districts,
        "mauzas": mauzas,
        "rules": rules,
        "district_mauza_pairs": [
            {
                "district": str(r.get("district", "")).strip(),
                "mauza": str(r.get("mauza", "")).strip(),
            }
            for r in district_mauza_rows
            if str(r.get("district", "")).strip() and str(r.get("mauza", "")).strip()
        ],
    }

@router.get("/audit-rules")
async def get_audit_rules():
    """Returns canonical + detected fraud rule codes for export filtering."""
    canonical_rules = [
        "A1", "A2",
        "B1", "B2", "B3",
        "C1", "C2",
        "D1",
        "E1",
        "F1",
        "G1",
        "H1",
        "I1",
    ]
    rows = await run_neo4j_query("""
        MATCH (:Citizen)-[:FLAGGED_AS]->(f:FraudFlag)
        WHERE f.rule IS NOT NULL
        RETURN DISTINCT toUpper(f.rule) AS rule
        ORDER BY rule
    """)
    detected = [str(r.get("rule", "")).strip() for r in rows if str(r.get("rule", "")).strip()]
    rules = sorted(set(canonical_rules + detected))
    return {"rules": rules, "detected_rules": sorted(set(detected))}


@router.get("/audit-queue/export-pdf")
async def export_audit_queue_pdf(
    rules: str | None = Query(default=None, description="Comma-separated rule codes, e.g. A1,B1,F1"),
    district: str | None = Query(default=None, description="District name exact match"),
    mauza: str | None = Query(default=None, description="Mauza/Block name exact match"),
):
    """
    Generates a professional forensic audit brief in PDF format.
    Includes all priority cases with signal justifications.
    """
    try:
        rule_names = {
            "A1": "Ghost Beneficiary - Demographic anomaly",
            "A2": "Ghost Beneficiary - Identity inconsistency",
            "B1": "Duplicate Identity - High similarity profile",
            "B2": "Duplicate Identity - Cross-record mismatch",
            "B3": "Duplicate Identity - Same DOB cluster",
            "C1": "Scheme Anomaly - GP concentration spike",
            "C2": "Scheme Anomaly - Mutually exclusive scheme overlap",
            "D1": "Data Quality - Null/invalid demographic field",
            "D2": "Data Quality - Gender or schema anomaly",
            "D3": "Data Quality - Future DOB anomaly",
            "E1": "Household Ring - Synthetic household overload",
            "F1": "Operator Anomaly - Suspicious registration concentration",
            "G1": "Network Anomaly - Relationship graph outlier",
            "H1": "Internal Integrity - System pattern deviation",
            "I1": "Internal Integrity - High-risk correlation signal",
        }
        rule_plain_explanations = {
            "A1": "Potential ghost beneficiary due to abnormal demographic pattern.",
            "A2": "Potential ghost beneficiary due to identity mismatch across records.",
            "B1": "Possible duplicate person with highly similar profile details.",
            "B2": "Possible duplicate person with cross-record inconsistency.",
            "B3": "Possible duplicate person sharing DOB cluster at same GP.",
            "C1": "Scheme concentration appears unusually high in one local cluster.",
            "C2": "Citizen appears in schemes that should not overlap together.",
            "D1": "One or more mandatory demographic fields are null, blank, or invalid.",
            "D2": "Gender value or demographic schema format is inconsistent/invalid.",
            "D3": "Date of birth is in the future or chronologically invalid.",
            "E1": "Household graph shows synthetic/overloaded linkage pattern.",
            "F1": "Operator-linked registrations show suspicious concentration.",
            "G1": "Relationship network structure appears as an outlier pattern.",
            "H1": "Internal integrity signal indicates abnormal system behavior pattern.",
            "I1": "High-risk pattern emerges from combined internal correlations.",
        }
        selected_rules: list[str] = []
        if rules:
            raw_rules = [r.strip().upper() for r in rules.split(",") if r.strip()]
            selected_rules = [r for r in raw_rules if all(ch.isalnum() or ch == "_" for ch in r)]
        district_filter = (district or "").strip()
        mauza_filter = (mauza or "").strip()

        # Fetch all priority data (optionally filtered by rule set)
        data = await run_neo4j_query("""
            MATCH (c:Citizen)-[f:FLAGGED_AS]->(fl:FraudFlag)
            WHERE ($rules_count = 0 OR toUpper(coalesce(fl.rule, '')) IN $rules)
            OPTIONAL MATCH (c)-[:RESIDES_IN]->(g:GP)-[:PART_OF]->(b:Block)-[:PART_OF]->(d:District)
            WITH c, g, b, d, f, fl
            WHERE ($district = '' OR coalesce(d.name, '') = $district)
              AND ($mauza = '' OR coalesce(b.name, '') = $mauza)
            WITH
                c,
                head(collect(DISTINCT g.name)) AS gp_name,
                head(collect(DISTINCT b.name)) AS block_name,
                head(collect(DISTINCT d.name)) AS district_name,
                count(DISTINCT f) as flags,
                collect(DISTINCT toUpper(coalesce(fl.rule, 'UNKNOWN'))) as rule_codes,
                collect(DISTINCT fl.label + ": " + fl.description) as flag_notes
            RETURN 
                c.name AS name, 
                c.uid AS uid, 
                gp_name AS gp, 
                block_name AS block, 
                district_name AS district,
                flags, 
                rule_codes,
                flag_notes
            ORDER BY flags DESC, c.vulnerability_score DESC
        """, {
            "rules": selected_rules,
            "rules_count": len(selected_rules),
            "district": district_filter,
            "mauza": mauza_filter,
        })

        # Generate PDF using ReportLab
        pdf_buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=landscape(A4),
            leftMargin=14 * mm,
            rightMargin=14 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title="Social Registry Forensic Audit Brief",
            author="USR Audit Engine",
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "audit_title",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0F172A"),
            alignment=1,
        )
        subtitle_style = ParagraphStyle(
            "audit_subtitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#334155"),
            alignment=1,
        )
        meta_style = ParagraphStyle(
            "audit_meta",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#475569"),
        )
        cell_style = ParagraphStyle(
            "audit_cell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9.5,
            textColor=colors.HexColor("#0F172A"),
        )

        story = [
            Paragraph("Social Registry Forensic Audit Brief", title_style),
            Spacer(1, 3 * mm),
            Paragraph("PRIORITY FIELD VERIFICATION LIST (ALL CASES)", subtitle_style),
            Spacer(1, 4 * mm),
            Paragraph("Analysis Segment: Social Registry Records", meta_style),
            Paragraph(
                f"Rule Filter: {', '.join(selected_rules) if selected_rules else 'ALL'}",
                meta_style,
            ),
            Paragraph(
                f"District Filter: {district_filter if district_filter else 'ALL'}",
                meta_style,
            ),
            Paragraph(f"Exported Entries: {len(data)}", meta_style),
            Paragraph(
                f"Generated On: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC | Intelligence Layer: Phase 4 Advanced",
                meta_style,
            ),
            Spacer(1, 5 * mm),
        ]

        legend_codes = selected_rules if selected_rules else sorted(rule_names.keys())
        legend_lines = []
        for code in legend_codes:
            legend_lines.append(
                f"<b>{code}</b>: {rule_names.get(code, 'Unclassified Rule')} - "
                f"{rule_plain_explanations.get(code, 'Manual review required.')}"
            )
        story.append(Paragraph("<b>Rule Explanation Guide</b>", meta_style))
        for line in legend_lines:
            story.append(Paragraph(line, meta_style))
        story.append(Spacer(1, 4 * mm))

        table_headers = ["CITIZEN NAME", "UID / ID", "DISTRICT", "REGION (GP/BLOCK)", "SIGS", "RULES", "RISK JUSTIFICATION"]
        table_rows = [table_headers]
        for row in data:
            name = str(row.get("name") or "Unknown")
            uid = str(row.get("uid") or "N/A")
            gp = str(row.get("gp") or "N/A")
            block = str(row.get("block") or "N/A")
            district = str(row.get("district") or "N/A")
            region = f"{gp} / {block}"
            sigs = str(row.get("flags") or 0)
            raw_rules = [str(r).upper().strip() for r in (row.get("rule_codes") or []) if str(r).strip()]
            pretty_rules = [f"{code} - {rule_names.get(code, 'Unclassified Rule')}" for code in raw_rules]
            rules_text = "; ".join(pretty_rules) if pretty_rules else "UNKNOWN - Unclassified Rule"
            notes = row.get("flag_notes") or []
            first_code = raw_rules[0] if raw_rules else "UNKNOWN"
            plain_reason = rule_plain_explanations.get(first_code, "General anomaly for field verification.")
            note_text = f"Why flagged: {plain_reason}"
            if notes:
                note_text += " | Signal details: " + " | ".join(notes[:2])

            table_rows.append(
                [
                    Paragraph(name, cell_style),
                    Paragraph(uid, cell_style),
                    Paragraph(district, cell_style),
                    Paragraph(region, cell_style),
                    Paragraph(sigs, cell_style),
                    Paragraph(rules_text, cell_style),
                    Paragraph(note_text, cell_style),
                ]
            )

        table = Table(
            table_rows,
            colWidths=[30 * mm, 28 * mm, 30 * mm, 36 * mm, 12 * mm, 58 * mm, 75 * mm],
            repeatRows=1,
            hAlign="LEFT",
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("ALIGN", (3, 1), (3, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ]
            )
        )
        story.append(table)

        doc.build(story)
        pdf_bytes = pdf_buffer.getvalue()
        pdf_buffer.close()
        selected_rule_token = "-".join(selected_rules) if selected_rules else "ALL"
        selected_district_token = district_filter.replace(" ", "_").upper() if district_filter else "ALL"
        filename = (
            f"USR_Forensic_Field_Brief_{selected_rule_token}_{selected_district_token}_"
            f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
        )

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        logger.error(f"PDF Export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Rule E & F: Advanced Intelligence Layers
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/operator/{operator_id}/audit")
async def audit_operator_registrations(operator_id: str):
    """
    Returns a full audit trail of citizens registered by a specific operator.
    Useful for forensic investigation of 'Rule F1' corruption signals.
    """
    query = """
    MATCH (o:Operator {id: $op_id})<-[:REGISTERED_BY]-(c:Citizen)
    OPTIONAL MATCH (c)-[rel:FLAGGED_AS]->(f:FraudFlag)
    RETURN 
        c.name AS name,
        c.uid AS uid,
        c.vulnerability_score AS risk_score,
        CASE 
            WHEN c.vulnerability_score >= 61 THEN 'CRITICAL'
            WHEN c.vulnerability_score >= 41 THEN 'HIGH'
            WHEN c.vulnerability_score >= 21 THEN 'MODERATE'
            ELSE 'LOW' 
        END AS tier,
        c.gender AS gender,
        c.dob AS dob,
        f.type AS flag_type,
        f.rule AS flag_rule,
        f.description AS flag_desc,
        rel.confidence AS confidence
    ORDER BY rel.confidence DESC, c.name ASC
    """
    data = await run_neo4j_query(query, {"op_id": operator_id})

    # Process into a structured format for the UI
    audit_trail = []
    for row in data:
        # Avoid duplicate rows for same citizen with multiple flags
        existing = next((x for x in audit_trail if x["uid"] == row["uid"]), None)
        if existing:
            if row["flag_type"]:
                existing["flags"].append(
                    {
                        "type": row["flag_type"],
                        "rule": row["flag_rule"],
                        "desc": row["flag_desc"],
                        "conf": row["confidence"],
                    }
                )
        else:
            audit_trail.append(
                {
                    "name": row["name"],
                    "uid": row["uid"],
                    "risk_score": row["risk_score"],
                    "tier": row["tier"],
                    "gender": row["gender"],
                    "dob": row["dob"],
                    "flags": (
                        [
                            {
                                "type": row["flag_type"],
                                "rule": row["flag_rule"],
                                "desc": row["flag_desc"],
                                "conf": row["confidence"],
                            }
                        ]
                        if row["flag_type"]
                        else []
                    ),
                }
            )

    return {
        "operator_id": operator_id,
        "total_registrations": len(audit_trail),
        "audit_trail": audit_trail,
    }


@router.get("/analytics/rules-ef")
async def get_rules_ef_results():
    """Returns results for Household Overload (Rule E) and Operator Corruption (Rule F)."""
    households = await ai_analytics.detect_household_rings()
    operators = await ai_analytics.detect_operator_anomalies()
    return {"rule_e": households.get("E1", []), "rule_f": operators.get("F1", [])}


# ─────────────────────────────────────────────────────────────────────────────
# Batch Runner: Trigger full re-score + fraud scan
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/run-batch")
async def trigger_batch_analysis(background_tasks: BackgroundTasks):
    """
    Triggers a full intelligence batch run in the background:
      1. Data quality audit → 2. Enhanced scoring → 3. Ghost detection
      4. Duplicate detection → 5. Scheme anomaly detection
    """
    background_tasks.add_task(ai_analytics.run_full_intelligence_batch)
    return {
        "status": "started",
        "message": "Full USR intelligence batch triggered. Check backend logs for progress.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Full Dataset Sync: PostgreSQL → Neo4j
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/run-sync")
async def trigger_graph_sync(
    background_tasks: BackgroundTasks,
    limit: int = Query(default=None, description="Max records to import. Omit for full dataset."),
):
    """
    Triggers full PostgreSQL → Neo4j Knowledge Graph sync in the background.
    Imports all citizens in paginated batches of 2000, then runs vulnerability scoring.
    Use ?limit=5000 for a test run before importing the full ~1L dataset.
    """
    lim = limit if limit and limit > 0 else None
    background_tasks.add_task(graph_sync.run_full_sync, lim)
    msg = (
        f"Graph sync started for {lim:,} records."
        if lim
        else "Full dataset graph sync started (all citizens)."
    )
    return {"status": "started", "message": msg}


# ─────────────────────────────────────────────────────────────────────────────
# Graph Stats — see what's currently in Neo4j before clearing
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/graph-stats")
async def get_graph_stats():
    """Returns a count of all node labels currently in Neo4j."""
    data = await run_neo4j_query("""
        CALL db.labels() YIELD label
        CALL apoc.cypher.run('MATCH (n:' + label + ') RETURN count(n) AS count', {})
        YIELD value
        RETURN label, value.count AS count
        ORDER BY count DESC
    """)
    if not data:
        # fallback without APOC
        data = await run_neo4j_query("""
            MATCH (n)
            RETURN labels(n)[0] AS label, count(n) AS count
            ORDER BY count DESC
        """)
    return {"node_counts": data}


# ─────────────────────────────────────────────────────────────────────────────
# Clear Graph — wipe all nodes and rebuild from USR data only
# ─────────────────────────────────────────────────────────────────────────────


@router.delete("/clear-graph")
async def clear_graph(confirm: str = Query(..., description="Must be 'yes-delete-all' to confirm")):
    """
    DESTRUCTIVE: Deletes ALL nodes and relationships from Neo4j.
    Use this to remove mixed PDF-document nodes before re-syncing purely from the registry source.
    Requires confirm=yes-delete-all query param as a safety gate.
    """
    if confirm != "yes-delete-all":
        raise HTTPException(
            status_code=400, detail="Safety check failed. Pass ?confirm=yes-delete-all to proceed."
        )
    try:
        driver = await get_driver()
        async with driver.session() as session:
            # Count first so we can report what was deleted
            count_result = await session.run("MATCH (n) RETURN count(n) AS total")
            count_record = await count_result.single()
            total_before = count_record["total"] if count_record else 0

            # Delete in batches to avoid memory issues
            deleted = 0
            while True:
                result = await session.run(
                    "MATCH (n) WITH n LIMIT 10000 DETACH DELETE n RETURN count(n) AS batch"
                )
                record = await result.single()
                batch_count = record["batch"] if record else 0
                deleted += batch_count
                if batch_count == 0:
                    break

        logger.info(f"Graph cleared: {deleted} nodes deleted ({total_before} total before).")
        return {
            "status": "cleared",
            "nodes_deleted": total_before,
            "message": "Neo4j graph wiped. Run POST /api/usr/run-sync to rebuild from the registry source.",
        }
    except Exception as e:
        logger.error(f"Graph clear failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# AI Eligibility Assessment
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/assess/{citizen_uid}")
async def assess_citizen_eligibility(citizen_uid: str):
    """
    Uses NVIDIA NIM LLM to assess a citizen's eligibility for additional schemes
    using their full Knowledge Graph context (location, current schemes, risk tier).
    """
    try:
        assessment = await ai_analytics.assess_eligibility_with_ai(citizen_uid)
        return {"uid": citizen_uid, "assessment": assessment}
    except Exception as e:
        logger.error(f"AI eligibility assessment failed for {citizen_uid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Data Quality Audit (Rule Set D)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/data-quality")
async def get_data_quality_audit():
    """
    Returns results of the pre-fraud data quality audit.
    Shows counts for null/placeholder DOBs, missing UIDs, and other dirty data.
    """
    try:
        checks = await ai_analytics.run_data_quality_audit()
        total_issues = int(sum(checks.values()))

        citizen_count_rows = await run_neo4j_query(
            "MATCH (c:Citizen) RETURN count(c) AS total_citizens"
        )
        total_citizens = (
            int(citizen_count_rows[0].get("total_citizens", 0)) if citizen_count_rows else 0
        )

        if total_citizens > 0:
            integrity_index = max(
                0.0, min(100.0, round((1.0 - (total_issues / total_citizens)) * 100.0, 1))
            )
        else:
            integrity_index = 0.0
        if total_issues > 0 and integrity_index >= 100.0:
            integrity_index = 99.9

        if integrity_index >= 95:
            health = "GOOD"
        elif integrity_index >= 85:
            health = "FAIR"
        else:
            health = "POOR"

        return {
            "total_issues": total_issues,
            "total_citizens": total_citizens,
            "integrity_index": integrity_index,
            "health": health,
            "checks": checks,
            # Backward-compatible flattened keys for any existing consumers.
            **checks,
        }
    except Exception as e:
        logger.error(f"Data quality audit failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Local Citizen Graph Neighborhood
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/citizen/{citizen_uid}/graph-neighborhood")
async def get_citizen_neighborhood(citizen_uid: str):
    """
    Returns the 2-hop USR fraud subgraph for a specific citizen.
    Useful for detailed visual drill-down.
    """
    try:
        driver = await get_driver()
        async with driver.session() as session:
            query = """
            MATCH (c:Citizen {uid: $uid})
            OPTIONAL MATCH (c)-[:RESIDES_IN]->(gp:GP)
            OPTIONAL MATCH (c)-[dup:POTENTIAL_DUPLICATE]-(c2:Citizen)
            OPTIONAL MATCH (c)-[flag_edge:FLAGGED_AS]->(f:FraudFlag)
            OPTIONAL MATCH (c)-[dob_edge:SAME_DOB_AT_GP]-(c3:Citizen)
            WITH c, gp, dup, c2, flag_edge, f, dob_edge, c3
            OPTIONAL MATCH (gp)-[risk:HIGH_RISK_CLUSTER]->(s:Scheme)
            RETURN c, gp, dup, c2, flag_edge, f, dob_edge, c3, risk, s
            """
            result = await session.run(query, uid=citizen_uid)
            records = await result.data()

            nodes = {}
            links = []

            for rec in records:
                c = rec.get("c")
                gp = rec.get("gp")

                if c and c.get("uid") not in nodes:
                    nodes[c["uid"]] = {
                        "id": c["uid"],
                        "label": c.get("name", "Unknown"),
                        "type": "Citizen",
                        "risk_tier": c.get("risk_tier", "LOW"),
                    }

                if gp and gp.get("code") not in nodes:
                    nodes[gp["code"]] = {
                        "id": gp["code"],
                        "label": gp.get("name", "GP"),
                        "type": "GP",
                    }

                if c and gp:
                    if not any(
                        l["source"] == c["uid"] and l["target"] == gp["code"] for l in links
                    ):
                        links.append(
                            {
                                "source": c["uid"],
                                "target": gp["code"],
                                "label": "RESIDES_IN",
                                "description": "",
                            }
                        )

                dup = rec.get("dup")
                c2 = rec.get("c2")
                if dup and c2:
                    if c2.get("uid") not in nodes:
                        nodes[c2["uid"]] = {
                            "id": c2["uid"],
                            "label": c2.get("name", "Unknown"),
                            "type": "Citizen",
                            "risk_tier": c2.get("risk_tier", "LOW"),
                        }
                    if not any(
                        l["source"] == c["uid"]
                        and l["target"] == c2["uid"]
                        and l["label"] == "POTENTIAL_DUPLICATE"
                        for l in links
                    ):
                        links.append(
                            {
                                "source": c["uid"],
                                "target": c2["uid"],
                                "label": "POTENTIAL_DUPLICATE",
                                "description": f"Rule: {dup.get('rule')} (Conf: {dup.get('confidence')}%)",
                            }
                        )

                flag_edge = rec.get("flag_edge")
                f = rec.get("f")
                if flag_edge and f:
                    f_id = f"FLAG_{f.get('rule')}_{f.get('type')}"
                    if f_id not in nodes:
                        nodes[f_id] = {
                            "id": f_id,
                            "label": f"{f.get('type')}: {f.get('description')}",
                            "type": "FraudFlag",
                        }
                    if not any(l["source"] == c["uid"] and l["target"] == f_id for l in links):
                        links.append(
                            {
                                "source": c["uid"],
                                "target": f_id,
                                "label": "FLAGGED_AS",
                                "description": f"Conf: {flag_edge.get('confidence')}%",
                            }
                        )

                dob_edge = rec.get("dob_edge")
                c3 = rec.get("c3")
                if dob_edge and c3:
                    if c3.get("uid") not in nodes:
                        nodes[c3["uid"]] = {
                            "id": c3["uid"],
                            "label": c3.get("name", "Unknown"),
                            "type": "Citizen",
                            "risk_tier": c3.get("risk_tier", "LOW"),
                        }
                    if not any(
                        l["source"] == c["uid"]
                        and l["target"] == c3["uid"]
                        and l["label"] == "SAME_DOB_AT_GP"
                        for l in links
                    ):
                        links.append(
                            {
                                "source": c["uid"],
                                "target": c3["uid"],
                                "label": "SAME_DOB_AT_GP",
                                "description": f"Cluster size: {dob_edge.get('cluster_size')}",
                            }
                        )

                risk = rec.get("risk")
                s = rec.get("s")
                if risk and s:
                    if s.get("id") not in nodes:
                        nodes[s["id"]] = {
                            "id": s["id"],
                            "label": s.get("name", "Scheme"),
                            "type": "Scheme",
                        }
                    if not any(l["source"] == gp["code"] and l["target"] == s["id"] for l in links):
                        links.append(
                            {
                                "source": gp["code"],
                                "target": s["id"],
                                "label": "HIGH_RISK_CLUSTER",
                                "description": f"Ratio: {risk.get('concentration_ratio')}",
                            }
                        )

            return {"nodes": list(nodes.values()), "links": links}
    except Exception as e:
        logger.error(f"Failed to fetch neighborhood for {citizen_uid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
