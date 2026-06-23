"""
AI Analytics Engine — Use Case 3: Unified Social Registry
==========================================================
Implements:
  - Enhanced vulnerability scoring (0-100, 10 factors)
  - Rule Set A: Ghost Beneficiary Detection
  - Rule Set B: Duplicate Identity Detection (with fuzzy name matching via APOC)
  - Rule Set C: Scheme Anomaly Detection
  - Rule Set D: Data Quality Audit
  - AI-powered eligibility assessment (NVIDIA NIM)
  - Rule Set E: Household Identity Rings (Shared Ration Card)
  - Rule Set F: Internal Trail / Operator Anomaly Detection
"""

import asyncio
from typing import Any, Dict, List

from src.core.config import get_settings
from src.core.logger import logger
from src.services import nvidia
from src.services.graph_db import get_driver

settings = get_settings()

# ─────────────────────────────────────────────────────────────────────────────
# PART 1: Vulnerability Scoring (0–100 scale, 10 factors)
# ─────────────────────────────────────────────────────────────────────────────


async def calculate_vulnerability_scores() -> int:
    """
    Calculates and writes c.vulnerability_score and c.risk_tier onto every Citizen node.

    Scoring factors (max 100):
      Age >80                → 30 pts
      Age 60-80              → 20 pts
      Age <5  (infant)       → 15 pts
      Female gender          → 10 pts
    # We use apoc.periodic.iterate to process 2.2M+ records in batches of 10,000
    # to avoid MemoryPoolOutOfMemoryError (Neo.TransientError.General.MemoryPoolOutOfMemoryError)
    """
    driver = await get_driver()
    logger.info("Calculating enhanced vulnerability scores (0-100) for all citizens...")

    # We use apoc.periodic.iterate to process 2.2M+ records in batches of 10,000
    # to avoid MemoryPoolOutOfMemoryError (Neo.TransientError.General.MemoryPoolOutOfMemoryError)
    cypher = """
    CALL apoc.periodic.iterate(
        "MATCH (c:Citizen) RETURN c",
        "OPTIONAL MATCH (c)-[:ENROLLED_IN]->(s:Scheme)
         WITH c, collect(toLower(s.name)) AS scheme_names, count(s) AS scheme_count
         SET c.vulnerability_score = (
            CASE
                WHEN c.dob IS NOT NULL AND
                     duration.between(date(c.dob), date()).years > 80 THEN 30
                WHEN c.dob IS NOT NULL AND
                     duration.between(date(c.dob), date()).years > 60 THEN 20
                WHEN c.dob IS NOT NULL AND
                     duration.between(date(c.dob), date()).years < 5  THEN 15
                ELSE 0
            END +
            CASE WHEN c.gender = 'FEMALE' THEN 10 ELSE 0 END +
            CASE
                WHEN scheme_count = 0 THEN 25
                WHEN scheme_count = 1 THEN 15
                ELSE 0
            END +
            CASE WHEN any(s IN scheme_names WHERE s CONTAINS 'widow') THEN 10 ELSE 0 END +
            CASE WHEN any(s IN scheme_names WHERE s CONTAINS 'disab') THEN 15 ELSE 0 END +
            CASE WHEN any(s IN scheme_names WHERE s CONTAINS 'bpl')   THEN 15 ELSE 0 END
         ),
         c.risk_tier = CASE
            WHEN c.vulnerability_score >= 61 THEN 'CRITICAL'
            WHEN c.vulnerability_score >= 41 THEN 'HIGH'
            WHEN c.vulnerability_score >= 21 THEN 'MODERATE'
            ELSE 'LOW'
         END",
        {batchSize: 10000, parallel: false}
    ) YIELD batches, total, errorMessages
    RETURN total AS processed_count
    """

    async with driver.session() as session:
        result = await session.run(cypher)
        record = await result.single()
        count = record["processed_count"]
        logger.info(f"Scored {count} citizens with batched vulnerability model.")
        return count


async def calculate_dashboard_aggregates() -> Dict:
    """
    Computes global and regional aggregates and persists them to the graph.
    This enables the dashboard to load instantly by reading single nodes
    instead of scanning 2.2M citizens live.
    """
    driver = await get_driver()
    logger.info("Caching dashboard aggregates for high-speed retrieval...")

    # 1. Global Stats Node
    global_cypher = """
    MATCH (c:Citizen)
    WITH 
        count(c) AS total,
        avg(c.vulnerability_score) AS avg_vuln,
        count(CASE WHEN c.vulnerability_score >= 61 THEN 1 END) AS crit,
        count(CASE WHEN c.vulnerability_score >= 41 AND c.vulnerability_score < 61 THEN 1 END) AS high,
        count(CASE WHEN c.gender = 'FEMALE' THEN 1 END) AS female
    MERGE (s:GlobalStats {id: 'USR_HUB'})
    SET s.total_citizens = total,
        s.avg_vulnerability = round(coalesce(avg_vuln, 0) * 10) / 10,
        s.critical_count = crit,
        s.high_risk_count = high,
        s.female_count = female,
        s.critical_tier_count = crit,
        s.last_updated = datetime()
    RETURN s
    """

    # 2. District Heatmap Aggregates
    # We store these directly on the District nodes
    district_cypher = """
    MATCH (c:Citizen)-[:RESIDES_IN]->(:GP)-[:PART_OF]->(:Block)-[:PART_OF]->(d:District)
    WITH d, 
         count(c) AS count, 
         avg(c.vulnerability_score) AS avg_score,
         count(CASE WHEN c.risk_tier = 'CRITICAL' THEN 1 END) AS crit_count,
         count(CASE WHEN c.risk_tier = 'HIGH' THEN 1 END) AS high_count
    SET d.citizen_count = count,
        d.avg_risk_score = round(avg_score * 10) / 10,
        d.critical_count = crit_count,
        d.high_count = high_count,
        d.last_updated = datetime()
    """

    async with driver.session() as session:
        await session.run(global_cypher)
        await session.run(district_cypher)
        logger.info("Dashboard aggregates updated successfully.")
        return {"status": "success"}


# ─────────────────────────────────────────────────────────────────────────────
# PART 2: Rule Set A — Ghost Beneficiary Detection
# ─────────────────────────────────────────────────────────────────────────────


async def detect_ghost_beneficiaries() -> Dict[str, List[Dict]]:
    """
    Rule Set A: Detects impossible or ineligible benefit recipients.
    Returns counts and records for A1, A2, A3.
    """
    driver = await get_driver()
    logger.info("Running Ghost Beneficiary detection (Rule Set A)...")

    results = {}

    # A1: Biologically impossible age (>105) — Confidence 95
    a1_query = """
    MATCH (c:Citizen)
    WHERE c.dob IS NOT NULL
      AND duration.between(date(c.dob), date()).years > 105
    RETURN c.name AS name, c.uid AS uid, c.dob AS dob,
           duration.between(date(c.dob), date()).years AS age,
           95 AS confidence,
           'A1_IMPOSSIBLE_AGE' AS rule
    ORDER BY age DESC
    LIMIT 500
    """

    # A2: Enrolled in Old Age scheme but under 58 — Confidence 85
    a2_query = """
    MATCH (c:Citizen)-[:ENROLLED_IN]->(s:Scheme)
    WHERE c.dob IS NOT NULL
      AND (toLower(s.name) CONTAINS 'old age' OR toLower(s.name) CONTAINS 'pension')
      AND duration.between(date(c.dob), date()).years < 58
    RETURN c.name AS name, c.uid AS uid, c.dob AS dob,
           duration.between(date(c.dob), date()).years AS age,
           s.name AS scheme,
           85 AS confidence,
           'A2_WRONG_AGE_FOR_SCHEME' AS rule
    LIMIT 500
    """

    # A3: Child (<18) in adult scheme — Confidence 90
    a3_query = """
    MATCH (c:Citizen)-[:ENROLLED_IN]->(s:Scheme)
    WHERE c.dob IS NOT NULL
      AND duration.between(date(c.dob), date()).years < 18
      AND any(kw IN ['widow', 'pension', 'employment', 'mgnregs']
              WHERE toLower(s.name) CONTAINS kw)
    RETURN c.name AS name, c.uid AS uid, c.dob AS dob,
           duration.between(date(c.dob), date()).years AS age,
           s.name AS scheme,
           90 AS confidence,
           'A3_CHILD_IN_ADULT_SCHEME' AS rule
    LIMIT 500
    """

    async with driver.session() as session:
        for rule, query in [("A1", a1_query), ("A2", a2_query), ("A3", a3_query)]:
            result = await session.run(query)
            data = await result.data()
            results[rule] = data
            logger.info(f"  {rule}: {len(data)} potential ghost beneficiaries found.")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# PART 3: Rule Set B — Duplicate Identity Detection
# ─────────────────────────────────────────────────────────────────────────────


async def find_identity_clusters() -> Dict[str, List[Dict]]:
    """
    Rule Set B: Detects duplicate/fraudulent identities.
    B1 — Exact name + DOB duplicate (different UIDs)
    B2 — Fuzzy name match (>75% similarity) + same DOB + same GP (APOC required)
    """
    driver = await get_driver()
    logger.info("Running Duplicate Identity detection (Rule Set B)...")

    results = {}

    # B1: Exact duplicate — Confidence 92
    # Optimized for 2M+: Bucket by Name + DOB to avoid Cartesian Product
    b1_query = """
    MATCH (c:Citizen)
    WHERE c.name IS NOT NULL AND c.dob IS NOT NULL
    WITH c.name AS name, c.dob AS dob, collect(c) AS cluster
    WHERE size(cluster) > 1
    UNWIND cluster AS c1
    UNWIND cluster AS c2
    WITH c1, c2
    WHERE elementId(c1) < elementId(c2)
      AND c1.uid <> c2.uid
      AND c1.gender = c2.gender
    OPTIONAL MATCH (c1)-[:RESIDES_IN]->(g:GP)
    RETURN c1.name AS name1, c2.name AS name2, c1.uid AS uid1, c2.uid AS uid2,
           c1.dob AS dob, c1.gender AS gender, g.name AS shared_gp,
           1.0 AS name_similarity,
           92 AS confidence,
           'B1_EXACT_DUPLICATE' AS rule
    LIMIT 500
    """

    # B2: Fuzzy match via APOC Sorensen-Dice — Confidence formula: 60 + similarity*40
    # Optimized: Limit search to same GP + DOB to avoid explosive comparisons
    b2_query = """
    MATCH (c:Citizen)-[:RESIDES_IN]->(g:GP)
    WHERE c.dob IS NOT NULL AND c.gender IS NOT NULL AND c.name IS NOT NULL
    WITH g, c.dob AS dob, c.gender AS gender, collect(c) AS cluster
    WHERE size(cluster) > 1
    UNWIND cluster AS c1
    UNWIND cluster AS c2
    WITH c1, c2, g,
         apoc.text.sorensenDiceSimilarity(c1.name, c2.name) AS similarity
    WHERE elementId(c1) < elementId(c2)
      AND c1.uid <> c2.uid
      AND similarity > 0.82
    RETURN c1.name AS name1, c2.name AS name2,
           c1.uid AS uid1, c2.uid AS uid2,
           c1.dob AS dob, g.name AS shared_gp,
           round(similarity * 100) / 100 AS name_similarity,
           toInteger(60 + similarity * 40) AS confidence,
           'B2_FUZZY_NAME_DUPLICATE' AS rule
    ORDER BY similarity DESC
    LIMIT 500
    """

    async with driver.session() as session:
        # B1
        r1 = await session.run(b1_query)
        results["B1"] = await r1.data()
        logger.info(f"  B1 (exact duplicate): {len(results['B1'])} pairs found.")

        # B2 — requires APOC
        try:
            r2 = await session.run(b2_query)
            results["B2"] = await r2.data()
            logger.info(f"  B2 (fuzzy name duplicate): {len(results['B2'])} pairs found.")
        except Exception as e:
            logger.warning(f"  B2 skipped — APOC may not be loaded: {e}")
            results["B2"] = []

    return results


# ─────────────────────────────────────────────────────────────────────────────
# PART 4: Rule Set C — Scheme Anomaly Detection
# ─────────────────────────────────────────────────────────────────────────────


async def detect_scheme_anomalies() -> Dict[str, List[Dict]]:
    """
    Rule Set C: Detects irregular patterns in scheme utilization.
    C1 — GP benefit concentration spike (>50% at max risk score)
    C2 — Mutually exclusive scheme membership
    """
    driver = await get_driver()
    logger.info("Running Scheme Anomaly detection (Rule Set C)...")

    results = {}

    # C1: GP Concentration Anomaly — Confidence 75
    c1_query = """
    MATCH (g:GP)<-[:RESIDES_IN]-(c:Citizen)
    OPTIONAL MATCH (g)-[:PART_OF]->(b:Block)
    WITH g, b,
         count(c) AS total_citizens,
         count(CASE WHEN c.vulnerability_score >= 60 THEN 1 END) AS max_risk_count
    WHERE total_citizens > 5
    WITH g, b, total_citizens, max_risk_count,
         round(100.0 * max_risk_count / total_citizens) / 100 AS concentration_ratio
    WHERE concentration_ratio > 0.5
    RETURN g.name AS gp_name,
           COALESCE(b.name, 'Unknown') AS block,
           total_citizens,
           max_risk_count,
           concentration_ratio,
           75 AS confidence,
           'C1_GP_CONCENTRATION_SPIKE' AS rule
    ORDER BY concentration_ratio DESC
    LIMIT 30
    """

    # C2: Mutually exclusive scheme membership — Confidence 90
    c2_query = """
    MATCH (c:Citizen)-[:ENROLLED_IN]->(s1:Scheme)
    MATCH (c)-[:ENROLLED_IN]->(s2:Scheme)
    WHERE elementId(s1) < elementId(s2)
      AND (
        (toLower(s1.name) CONTAINS 'widow' AND
          (toLower(s2.name) CONTAINS 'married' OR toLower(s2.name) CONTAINS 'vivah'))
        OR
        (toLower(s1.name) CONTAINS 'bpl' AND toLower(s2.name) CONTAINS 'apl')
      )
    RETURN c.name AS name, c.uid AS uid,
           s1.name AS scheme_a, s2.name AS scheme_b,
           90 AS confidence,
           'C2_SCHEME_CONTRADICTION' AS rule
    LIMIT 50
    """

    async with driver.session() as session:
        for rule, query in [("C1", c1_query), ("C2", c2_query)]:
            result = await session.run(query)
            results[rule] = await result.data()
            logger.info(f"  {rule}: {len(results[rule])} anomalies found.")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# PART 5: Rule Set E — Household Identity Rings (Shared Ration Card)
# ─────────────────────────────────────────────────────────────────────────────


async def detect_household_rings() -> Dict[str, List[Dict]]:
    """
    Rule Set E: Detects "Synthetic Households" where one Ration Card links to
    an abnormally large number of UIDs.
    """
    driver = await get_driver()
    logger.info("Running Household Ring detection (Rule Set E)...")

    # E1: Ration Card with >10 members — Confidence 95
    e1_query = """
    MATCH (rc:RationCard)<-[:MEMBER_OF]-(c:Citizen)
    WITH rc, count(c) AS member_count, collect(c.name) AS members
    WHERE member_count > 10
    RETURN rc.number AS ration_card, 
           member_count, 
           members,
           95 AS confidence,
           'E1_HOUSEHOLD_OVERLOAD' AS rule
    ORDER BY member_count DESC
    LIMIT 50
    """

    async with driver.session() as session:
        result = await session.run(e1_query)
        data = await result.data()
        logger.info(f"  E1: {len(data)} suspicious households found.")
        return {"E1": data}


# ─────────────────────────────────────────────────────────────────────────────
# PART 6: Rule Set H/I — Advanced Utilization Patterns
# ─────────────────────────────────────────────────────────────────────────────


async def detect_advanced_utilization_fraud() -> Dict[str, List[Dict]]:
    """
    Advanced pattern detection using hardened identity hubs and transaction counts.
    H1 — Ghost Monetization (Flagged as ghost but has active transactions)
    I1 — Member ID Conflict (Two different UIDs sharing the same Member ID)
    """
    driver = await get_driver()
    logger.info("Running Advanced Utilization fraud detection (Rule Set H/I)...")

    results = {}

    # H1: Ghost Monetization — Confidence 98
    h1_query = """
    MATCH (c:Citizen)
    WHERE (c.is_ghost_flag = true OR c.is_dup_flag = true)
      AND (
        coalesce(c.transaction_rows, 0) > 0
        OR coalesce(c.tran_count_1, 0) > 0
        OR coalesce(c.tran_count_2, 0) > 0
      )
    RETURN c.name AS name, c.uid AS uid,
           coalesce(c.transaction_rows, c.tran_count_1, 0) AS trans,
           98 AS confidence,
           'H1_GHOST_MONETIZATION' AS rule
    LIMIT 100
    """

    # I1: Member ID Conflict — Confidence 100
    i1_query = """
    MATCH (rc:RationCard)<-[r1:MEMBER_OF]-(c1:Citizen)
    MATCH (rc)<-[r2:MEMBER_OF]-(c2:Citizen)
    WHERE elementId(c1) < elementId(c2)
      AND r1.member_id = r2.member_id 
      AND r1.member_id IS NOT NULL AND r1.member_id <> ""
    RETURN c1.name AS name1, c2.name AS name2, 
           c1.uid AS uid1, c2.uid AS uid2, 
           r1.member_id AS shared_member_id,
           100 AS confidence,
           'I1_MEMBER_ID_CONFLICT' AS rule
    LIMIT 100
    """

    async with driver.session() as session:
        # H1
        res_h = await session.run(h1_query)
        results["H1"] = await res_h.data()
        logger.info(f"  H1 (ghost monetization): {len(results['H1'])} alerts found.")

        # I1
        res_i = await session.run(i1_query)
        results["I1"] = await res_i.data()
        logger.info(f"  I1 (member id conflict): {len(results['I1'])} alerts found.")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# PART 6: Rule Set F — Internal Trail / Operator Anomaly Detection
# ─────────────────────────────────────────────────────────────────────────────


async def detect_operator_anomalies() -> Dict[str, List[Dict]]:
    """
    Rule Set F: Detects corruption or incompetence in the registration process.
    Flags operators with abnormally high fraud/ghost rates.
    """
    driver = await get_driver()
    logger.info("Running Operator Anomaly detection (Rule Set F)...")

    # F1: Operator with >15% fraud rate — Confidence 90
    f1_query = """
    MATCH (o:Operator)<-[:REGISTERED_BY]-(c:Citizen)
    WITH o, count(c) AS total_registrations,
         count(CASE WHEN c.is_ghost_flag = true OR c.is_dup_flag = true THEN 1 END) AS fraud_count
    WHERE total_registrations > 20
    WITH o, total_registrations, fraud_count, 
         toFloat(fraud_count) / total_registrations AS fraud_rate
    WHERE fraud_rate > 0.15
    RETURN o.id AS operator_id, 
           total_registrations, 
           fraud_count, 
           round(fraud_rate * 100) / 100 AS fraud_rate,
           90 AS confidence,
           'F1_OPERATOR_CORRUPTION' AS rule
    ORDER BY fraud_rate DESC
    LIMIT 30
    """

    async with driver.session() as session:
        result = await session.run(f1_query)
        data = await result.data()
        logger.info(f"  F1: {len(data)} suspicious operators found.")
        return {"F1": data}


# ─────────────────────────────────────────────────────────────────────────────
# PART 7: Rule Set D — Data Quality Audit
# ─────────────────────────────────────────────────────────────────────────────


async def run_data_quality_audit() -> Dict[str, Any]:
    """
    Rule Set D: Pre-fraud data quality checks.
    Must run before fraud rules to avoid false positives from dirty data.
    """
    driver = await get_driver()
    logger.info("Running Data Quality Audit (Rule Set D)...")

    results = {}

    queries = {
        "D1_NULL_DOB": "MATCH (c:Citizen) WHERE c.dob IS NULL RETURN count(c) AS count",
        "D2_PLACEHOLDER_DOB": "MATCH (c:Citizen) WHERE c.dob IN ['1900-01-01', '0000-00-00', ''] RETURN count(c) AS count",
        "D3_FUTURE_DOB": "MATCH (c:Citizen) WHERE c.dob IS NOT NULL AND date(c.dob) > date() RETURN count(c) AS count",
        "D4_SHORT_NAME": "MATCH (c:Citizen) WHERE size(c.name) < 3 RETURN count(c) AS count",
        "D5_NULL_UID": "MATCH (c:Citizen) WHERE c.uid IS NULL RETURN count(c) AS count",
        "D6_NULL_GENDER": "MATCH (c:Citizen) WHERE c.gender IS NULL RETURN count(c) AS count",
    }

    async with driver.session() as session:
        for key, query in queries.items():
            result = await session.run(query)
            record = await result.single()
            results[key] = record["count"] if record else 0

    total_issues = sum(results.values())
    logger.info(f"Data Quality Audit complete. Total issues: {total_issues}")
    for k, v in results.items():
        if v > 0:
            logger.warning(f"  {k}: {v} records affected")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# PART 6: AI-Powered Eligibility Assessment (NVIDIA NIM)
# ─────────────────────────────────────────────────────────────────────────────


async def assess_eligibility_with_ai(citizen_uid: str) -> str:
    """
    Uses the NVIDIA NIM LLM to reason about a citizen's eligibility and fraud risk
    using their 2-hop Knowledge Graph neighborhood.
    """
    driver = await get_driver()

    context_query = """
    MATCH (c:Citizen {uid: $uid})
    OPTIONAL MATCH (c)-[:RESIDES_IN]->(g:GP)-[:PART_OF]->(b:Block)-[:PART_OF]->(d:District)
    OPTIONAL MATCH (c)-[:ENROLLED_IN]->(scheme:Scheme)
    
    // Fraud connections
    OPTIONAL MATCH (c)-[dup:POTENTIAL_DUPLICATE]-(c2:Citizen)
    OPTIONAL MATCH (c)-[flag:FLAGGED_AS]->(f:FraudFlag)
    OPTIONAL MATCH (c)-[dob:SAME_DOB_AT_GP]-(c3:Citizen)
    OPTIONAL MATCH (g)-[risk:HIGH_RISK_CLUSTER]->(s_anom:Scheme)
    
    // Hub connections (Permutations)
    OPTIONAL MATCH (c)-[:HAS_MOBILE]->(m:Mobile)
    OPTIONAL MATCH (c)-[:MEMBER_OF]->(rc:RationCard)
    OPTIONAL MATCH (c)-[:REGISTERED_BY]->(o:Operator)
    OPTIONAL MATCH (c)-[:LIVES_AT]->(addr:Address)

    // Cluster stats for hubs
    OPTIONAL MATCH (m)<-[:HAS_MOBILE]-(other_m:Citizen)
    OPTIONAL MATCH (rc)<-[:MEMBER_OF]-(other_rc:Citizen)
    OPTIONAL MATCH (o)<-[:REGISTERED_BY]-(other_o:Citizen)
    
    RETURN c AS citizen,
           g.name AS gp, b.name AS block, d.name AS district,
           g.high_risk_pct AS gp_risk,
           rc.number AS ration_card,
           m.number AS mobile,
           o.id AS operator,
           addr.text AS address,
           collect(DISTINCT scheme.name) AS schemes,
           count(DISTINCT dup) AS duplicate_edges,
           count(DISTINCT dob) AS dob_cluster_edges,
           count(DISTINCT other_m) AS mobile_share_count,
           count(DISTINCT other_rc) AS household_size,
           count(DISTINCT other_o) AS operator_volume,
           collect(DISTINCT {rule: flag.rule, type: f.type, conf: flag.confidence}) AS fraud_flags,
           count(DISTINCT risk) AS gp_anomalies
    """

    async with driver.session() as session:
        result = await session.run(context_query, uid=citizen_uid)
        record = await result.single()
        if not record:
            return '{"assessment": "Citizen not found in the Knowledge Graph.", "confidence_percentage": 0, "recommendation": "CLEAR", "triggered_rules": [], "eligible_schemes": []}'

        c = dict(record["citizen"])
        schemes = record["schemes"]
        location = f"{record['gp']}, {record['block']}, {record['district']}"

    prompt = f"""You are the Lead Fraud Investigator for the West Bengal Unified Social Registry.
Analyze this citizen's graph topology and determine if they are a fraudulent entry or a genuine beneficiary.

[CITIZEN PROFILE]
Name: {c.get('name')}
DOB: {c.get('dob')} (Age: {c.get('age')})
Vulnerability Score: {c.get('vulnerability_score')} ({c.get('risk_tier')})
Location: {location}
Enrolled Schemes: {', '.join(schemes) if schemes else 'None'}

[GRAPH CONTEXT (FRAUD SIGNALS)]
- Shared Mobile Hub: {record['mobile']} (Shared with {record['mobile_share_count']} UIDs)
- Household Hub: RC #{record['ration_card']} (Size: {record['household_size']})
- Registration Trail: Operator {record['operator']} (Volume: {record['operator_volume']})
- Geographic Hub: {record['address']}
- Duplicate Identity Edges: {record['duplicate_edges']}
- Same-DOB Cluster Edges: {record['dob_cluster_edges']}
- Area GP Risk Level: {round((record['gp_risk'] or 0)*100, 1)}%
- Active Fraud Flags: {record['fraud_flags']}

[DECISION MATRIX]
- If Duplicate Edges > 0 -> SUSPEND (Rule B1/B2)
- If DOB Cluster > 0 -> INVESTIGATE (Rule B3)
- If Age > 110 or Future DOB -> SUSPEND (Rule A1/A2)
- If missing DOB -> MONITOR for data quality
- Otherwise -> CLEAR

Return a pure JSON dictionary. DO NOT wrap the output in any markdown formatting (no ```json). Output exactly this JSON structure:
{{
  "assessment": "Brief 2-sentence explanation of finding based on graph context",
  "confidence_percentage": 85,
  "recommendation": "CLEAR | MONITOR | INVESTIGATE | SUSPEND",
  "triggered_rules": ["B1", "A2"],
  "eligible_schemes": ["Swasthya Sathi"]
}}"""

    answer = await nvidia.generate_rag_answer(
        query=f"Conduct graph-based fraud assessment for UID: {citizen_uid}",
        context_chunks=[],
        system_prompt=prompt,
    )
    return answer


RULE_METADATA = {
    "A1": {
        "label": "Ghost (Age Anomaly)",
        "desc": "Identity with impossible age (>105). High probability of synthetic record.",
    },
    "A2": {
        "label": "Ghost (Pension Anomaly)",
        "desc": "Individual receiving Old Age Pension but is under 58 years old.",
    },
    "A3": {
        "label": "Ghost (Child in Adult Scheme)",
        "desc": "Minor under 18 enrolled in adult-only schemes (MGNREGS/Widow).",
    },
    "B1": {
        "label": "Identity Duplicate (Exact)",
        "desc": "Exact Name/DOB match across different IDs. High risk of double-dipping.",
    },
    "B2": {
        "label": "Identity Duplicate (Fuzzy)",
        "desc": "Name/DOB show high similarity (>82%). Check for name variations.",
    },
    "E1": {
        "label": "Synthetic Household",
        "desc": "Ration Card linked to >10 members. Verify household composition.",
    },
    "F1": {
        "label": "Operator Corruption Suspect",
        "desc": "Registration point with >15% anomaly rate. Investigate operator trail.",
    },
    "H1": {
        "label": "Ghost Monetization",
        "desc": "Flagged phantom identity has active financial transactions.",
    },
    "I1": {
        "label": "Systemic Data Conflict",
        "desc": "Multiple IDs sharing one Member ID. Severe data entry breach.",
    },
}


async def persist_fraud_results(results_map: Dict[str, List[Dict]]):
    """
    Writes detected fraud flags and relationships back to the Knowledge Graph.
    Includes human-readable labels and actionable layman descriptions.
    """
    driver = await get_driver()
    logger.info("Persisting Intelligence Edges with Field Instructions...")

    all_flags = []
    for rule, cases in results_map.items():
        meta = RULE_METADATA.get(
            rule, {"label": f"Rule {rule}", "desc": "Intelligence flag requiring field audit."}
        )
        for case in cases:
            uid = case.get("uid") or case.get("uid1")
            if not uid:
                continue

            all_flags.append(
                {
                    "uid": uid,
                    "rule": rule,
                    "label": meta["label"],
                    "type": (
                        "GHOST"
                        if rule.startswith("A")
                        else "DUPLICATE" if rule.startswith("B") else "ANOMALY"
                    ),
                    "confidence": case.get("confidence", 70),
                    "description": meta["desc"],
                }
            )

    if not all_flags:
        logger.info("No flags to persist.")
        return

    cypher = """
    UNWIND $batch AS row
    MATCH (c:Citizen {uid: row.uid})
    MERGE (f:FraudFlag {rule: row.rule})
    SET f.type = row.type, 
        f.description = row.description
    MERGE (c)-[rel:FLAGGED_AS]->(f)
    SET rel.confidence = row.confidence,
        rel.detected_at = datetime()
    SET c.is_ghost_flag = (CASE WHEN row.type = 'GHOST' THEN true ELSE coalesce(c.is_ghost_flag, false) END),
        c.is_dup_flag = (CASE WHEN row.type = 'DUPLICATE' THEN true ELSE coalesce(c.is_dup_flag, false) END)
    """

    async with driver.session() as session:
        batch_size = 5000
        for i in range(0, len(all_flags), batch_size):
            batch = all_flags[i : i + batch_size]
            await session.run(cypher, {"batch": batch})

    logger.info(f"Persisted {len(all_flags)} fraud relationships.")


async def persist_operator_anomalies(operators_map: Dict[str, List[Dict]]):
    """Registers suspicious operators as high-risk corruption nodes."""
    driver = await get_driver()
    cases = operators_map.get("F1", [])
    if not cases:
        return

    cypher = """
    UNWIND $batch AS row
    MATCH (o:Operator {id: row.operator_id})
    SET o.fraud_rate = row.fraud_rate,
        o.is_suspicious = true,
        o.last_audit = datetime()
    """
    async with driver.session() as session:
        await session.run(cypher, {"batch": cases})
    logger.info(f"Persisted {len(cases)} operator corruption flags.")


# ─────────────────────────────────────────────────────────────────────────────
# PART 7: Full Batch Runner
# ─────────────────────────────────────────────────────────────────────────────


async def run_full_intelligence_batch() -> Dict[str, Any]:
    """
    Master runner: executes all rule sets in the correct order.
    Order: Data Quality → Scoring → Ghost Detection → Duplicate Detection → Anomaly Detection
    """
    logger.info("=" * 60)
    logger.info("USR Intelligence Batch — Full Run Starting")
    logger.info("=" * 60)

    # Step 1: Data quality audit (must be first)
    quality = await run_data_quality_audit()

    # Step 2: Enhanced vulnerability scoring
    scored = await calculate_vulnerability_scores()

    # Step 3: Ghost beneficiary detection
    ghosts = await detect_ghost_beneficiaries()

    # Step 4: Duplicate identity detection
    duplicates = await find_identity_clusters()

    # Step 5: Scheme anomaly detection
    anomalies = await detect_scheme_anomalies()

    # Step 6: Household Ring detection (Rule E)
    households = await detect_household_rings()

    # 6. Cache Dashboard Aggregates (NEW: Big Data Optimization)
    await calculate_dashboard_aggregates()

    logger.info("=" * 60)
    # Step 7: Operator Anomaly detection (Rule F)
    operators = await detect_operator_anomalies()

    # Step 8: Advanced Utilization fraud (Rule H/I)
    advanced = await detect_advanced_utilization_fraud()

    # Summary
    ghost_total = sum(len(v) for v in ghosts.values())
    dup_total = sum(len(v) for v in duplicates.values())
    anomaly_total = sum(len(v) for v in anomalies.values())
    h_ring_total = sum(len(v) for v in households.values())
    op_total = sum(len(v) for v in operators.values())
    adv_total = sum(len(v) for v in advanced.values())

    # Step 9: Persist Intelligence Edges (NEW: Dashboard Population)
    await persist_fraud_results({**ghosts, **duplicates, **anomalies, **advanced})
    await persist_operator_anomalies(operators)

    summary = {
        "data_quality": quality,
        "citizens_scored": scored,
        "ghost_flags": {rule: len(cases) for rule, cases in ghosts.items()},
        "duplicate_flags": {rule: len(cases) for rule, cases in duplicates.items()},
        "anomaly_flags": {rule: len(cases) for rule, cases in anomalies.items()},
        "household_rings": {rule: len(cases) for rule, cases in households.items()},
        "operator_anomalies": {rule: len(cases) for rule, cases in operators.items()},
        "advanced_fraud": {rule: len(cases) for rule, cases in advanced.items()},
        "total_fraud_alerts": ghost_total
        + dup_total
        + anomaly_total
        + h_ring_total
        + op_total
        + adv_total,
    }

    logger.info("=" * 60)
    logger.info(f"Batch complete. Total fraud alerts: {summary['total_fraud_alerts']}")
    logger.info(f"  Ghost beneficiaries: {ghost_total}")
    logger.info(f"  Duplicate identities: {dup_total}")
    logger.info(f"  Scheme anomalies: {anomaly_total}")
    logger.info(f"  Advanced Pattern Fraud: {adv_total}")
    logger.info("=" * 60)

    return summary


if __name__ == "__main__":
    asyncio.run(run_full_intelligence_batch())
