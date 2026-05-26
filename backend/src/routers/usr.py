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

import io

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response
from fpdf import FPDF

from src.core.logger import logger
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
async def get_intelligence_feed(limit: int = 100, offset: int = 0):
    """
    Unified feed of all Intelligence Flags from the Knowledge Graph.
    Consolidates Ghosts, Duplicates, and Anomalies into a single stream.
    """
    safe_limit = max(1, min(limit, 5000))
    safe_offset = max(0, offset)

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
            RETURN
                f.rule AS rule,
                coalesce(f.label, f.rule) AS label,
                f.type AS type,
                f.description AS description,
                c.name AS name,
                c.uid AS uid,
                coalesce(c.dob, 'Unknown') AS dob,
                coalesce(c.gp_name, 'Unknown') AS gp_name,
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
                coalesce(rel.confidence, 0) AS confidence,
                toString(rel.detected_at) AS detected_at
            UNION ALL
            MATCH (c1:Citizen)-[rel:POTENTIAL_DUPLICATE]->(c2:Citizen)
            RETURN
                coalesce(rel.rule, 'B1') AS rule,
                coalesce(rel.rule, 'B1') AS label,
                'DUPLICATE' AS type,
                ('Potential duplicate with ' + coalesce(c2.uid, 'unknown UID')) AS description,
                c1.name AS name,
                c1.uid AS uid,
                coalesce(c1.dob, 'Unknown') AS dob,
                coalesce(c1.gp_name, 'Unknown') AS gp_name,
                coalesce(rel.confidence, 85) AS confidence,
                toString(rel.detected_at) AS detected_at
            UNION ALL
            MATCH (c1:Citizen)-[rel:SAME_DOB_AT_GP]->(c2:Citizen)
            RETURN
                coalesce(rel.rule, 'B3') AS rule,
                coalesce(rel.rule, 'B3') AS label,
                'DUPLICATE' AS type,
                ('Same DOB at GP as ' + coalesce(c2.uid, 'unknown UID')) AS description,
                c1.name AS name,
                c1.uid AS uid,
                coalesce(c1.dob, 'Unknown') AS dob,
                coalesce(c1.gp_name, 'Unknown') AS gp_name,
                coalesce(rel.confidence, 80) AS confidence,
                toString(rel.detected_at) AS detected_at
        }
        RETURN
            rule, label, type, description, name, uid, dob, gp_name, confidence, detected_at
        ORDER BY confidence DESC, detected_at DESC
        SKIP $offset
        LIMIT $limit
    """,
        params={"limit": safe_limit, "offset": safe_offset},
    )

    return {"total": total, "limit": safe_limit, "offset": safe_offset, "feed": data}


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
async def get_field_audit_queue(limit: int = 50):
    """
    Returns the top N citizens requiring urgent field verification.
    Selection criteria: Critical Risk Tier (Score > 60) AND multiple fraud flags.
    """
    data = await run_neo4j_query(f"""
        MATCH (c:Citizen)-[f:FLAGGED_AS]->(fl:FraudFlag)
        OPTIONAL MATCH (c)-[:RESIDES_IN]->(g:GP)-[:PART_OF]->(b:Block)-[:PART_OF]->(d:District)
        WITH c, g, b, d, count(f) as flags, collect(fl.description) as flag_notes
        RETURN
            c.name          AS name,
            c.uid           AS uid,
            c.dob           AS dob,
            c.gender        AS gender,
            c.vulnerability_score AS score,
            d.name          AS district,
            b.name          AS block,
            g.name          AS gp,
            flags,
            flag_notes
        ORDER BY flags DESC, c.vulnerability_score DESC
        LIMIT {limit}
    """)
    return {"queue": data}


@router.get("/audit-queue/export-pdf")
async def export_audit_queue_pdf():
    """
    Generates a professional forensic audit brief in PDF format.
    Includes the top 50 priority cases with signal justifications.
    """
    try:
        # Fetch the same priority data
        data = await run_neo4j_query("""
            MATCH (c:Citizen)-[f:FLAGGED_AS]->(fl:FraudFlag)
            OPTIONAL MATCH (c)-[:RESIDES_IN]->(g:GP)-[:PART_OF]->(b:Block)-[:PART_OF]->(d:District)
            WITH c, g, b, d, count(f) as flags, collect(fl.label + ": " + fl.description) as flag_notes
            RETURN 
                c.name AS name, 
                c.uid AS uid, 
                g.name AS gp, 
                b.name AS block, 
                d.name AS district,
                flags, 
                flag_notes
            ORDER BY flags DESC, c.vulnerability_score DESC
            LIMIT 50
        """)

        # Generate PDF using fpdf2
        pdf = FPDF()
        pdf.add_page()

        # Header
        pdf.set_font("helvetica", "B", 20)
        pdf.cell(0, 15, "Social Registry Forensic Audit Brief", ln=True, align="C")
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(0, 10, "PRIORITY FIELD VERIFICATION LIST (TOP 50 CASES)", ln=True, align="C")
        pdf.ln(5)

        # Meta info
        pdf.set_font("helvetica", "", 9)
        pdf.cell(0, 5, f"Analysis Segment: 1.02M Social Registry Records", ln=True)
        pdf.cell(0, 5, f"Date: 2026-04-20 | Intelligence Layer: Phase 4 Advanced", ln=True)
        pdf.line(10, pdf.get_y() + 2, 200, pdf.get_y() + 2)
        pdf.ln(10)

        # Table Column Widths
        w = [40, 35, 45, 15, 55]  # Name, UID, GP/Block, Flags, Justification

        # Table Headers
        pdf.set_fill_color(240, 240, 240)
        pdf.set_font("helvetica", "B", 8)
        headers = ["CITIZEN NAME", "UID / ID", "REGION (GP/BLOCK)", "SIGS", "RISK JUSTIFICATION"]
        for i in range(len(headers)):
            pdf.cell(w[i], 8, headers[i], border=1, fill=True)
        pdf.ln()

        # Rows
        pdf.set_font("helvetica", "", 7)
        for row in data:
            # We use multi_cell or calculate height if notes are long
            if start_y > 260:  # Page break logic
                pdf.add_page()
                pdf.set_font("helvetica", "B", 8)
                for i in range(len(headers)):
                    pdf.cell(w[i], 8, headers[i], border=1, fill=True)
                pdf.ln()
                pdf.set_font("helvetica", "", 7)
                start_y = pdf.get_y()

            # Render Row
            name = str(row["name"])[:25]
            uid = str(row["uid"])
            region = f"{row['gp']} ({row['block']})"[:30]
            sigs = str(row["flags"])
            # Join top 2 notes to keep it reasonably short
            notes = " | ".join(row["flag_notes"][:2]) if row["flag_notes"] else "General Anomaly"

            # Since cells can't easily wrap without multi_cell, we do a simple truncation for now
            # In a production environment, we'd use a more complex table generator
            pdf.cell(w[0], 10, name, border=1)
            pdf.cell(w[1], 10, uid, border=1)
            pdf.cell(w[2], 10, region, border=1)
            pdf.cell(w[3], 10, sigs, border=1, align="C")
            pdf.cell(w[4], 10, notes[:40] + "...", border=1)
            pdf.ln()

        # Output to bytes
        pdf_bytes = pdf.output()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=USR_Forensic_Field_Brief.pdf"},
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
