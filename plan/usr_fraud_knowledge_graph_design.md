# USR Fraud Intelligence — Knowledge Graph Full Design

**Status:** Documented · Core implementation delivered (this doc now serves as design reference)  
**Author:** AI Architecture Review  
**Date:** 2026-04-15  
**Scope:** Unified Social Registry registry-source dataset

---

## 1. Why the Knowledge Graph Matters for Fraud Detection

Standard rule-based fraud detection (e.g. SQL queries) finds **local** anomalies — a single citizen with a bad DOB, or two citizens with the same name. But real-world welfare fraud is a **network problem**:

- A ghost beneficiary factory operates across 30 citizens in a single GP, all sharing the same DOB
- A corrupt agent registers 200 duplicates across 5 blocks, each slightly modified to evade name-matching
- A scheme concentration fraud has 23% of beneficiaries from one GP — invisible unless you see the full enrollment network

A **Knowledge Graph** makes all of this visible as a connected structure. Fraud that was invisible in rows of a database becomes obvious as anomalous cluster patterns in the graph.

---

## 2. Current State (Historical at Draft Time)

This section reflects the baseline when this design was drafted.

### Draft-time baseline:
```
(:Citizen {uid, name, dob, gender, risk_score, risk_tier})
    -[:LIVES_IN]->  (:GP {code, name})
    -[:ENROLLED_IN]-> (:Scheme {id, name})
(:GP)-[:PART_OF]->(:Block)-[:PART_OF]->(:District)
```

### Draft-time gaps (since implemented in current codebase):
- No `POTENTIAL_DUPLICATE` edges between similar citizens
- No `SAME_DOB_AT_GP` cluster edges
- No `HIGH_RISK_CLUSTER` scheme concentration edges
- No `FLAGGED_AS` links to FraudFlag alert nodes
- No `FraudFlag` nodes at all

### Historical result:
At draft time, fraud signals were disconnected from graph edges.  
Current implementation has since added fraud edges/flags and USR APIs for graph-backed fraud intelligence.

---

## 3. Target Architecture — Full Fraud Knowledge Graph

### 3.1 Node Schema

| Label | Properties | Description |
|---|---|---|
| `Citizen` | `uid, name, dob, age, gender, risk_score (0–100), risk_tier (LOW/MODERATE/HIGH/CRITICAL), scheme_beneficiary_id, is_ghost_flag, is_dup_flag, is_anomaly_flag` | Every beneficiary from the registry source |
| `GP` | `code, name, total_citizens, high_risk_count, high_risk_pct, critical_count` | Gram Panchayat — geographic unit |
| `Block` | `code, name` | Administrative block |
| `District` | `code, name, avg_risk_score` | District |
| `Scheme` | `id, name, beneficiary_count` | Welfare scheme (Swasthya Sathi etc.) |
| `FraudFlag` | `rule, type (GHOST/DUPLICATE/ANOMALY/DATA_QUALITY), confidence, description, created_at` | Alert node — shared by all citizens matching the rule |

### 3.2 Relationship Schema (Complete)

#### Structural Edges (Always built during sync)
```cypher
(Citizen)-[:LIVES_IN {gp_code}]->(GP)
(GP)-[:PART_OF {block_code}]->(Block)
(Block)-[:PART_OF {district_code}]->(District)
(Citizen)-[:ENROLLED_IN {enrolled_at}]->(Scheme)
```

#### Fraud Signal Edges (Built by fraud batch — `run_full_intelligence_batch()`)

```cypher
-- Rule B1: Exact duplicate
(Citizen)-[:POTENTIAL_DUPLICATE {
  confidence: 92,
  rule: "B1",
  name_similarity: 1.0,
  matching_fields: ["name", "dob", "gp"]
}]->(Citizen)

-- Rule B2: Fuzzy name duplicate (same DOB, same GP, similar name)
(Citizen)-[:POTENTIAL_DUPLICATE {
  confidence: 78,
  rule: "B2",
  name_similarity: 0.82,
  matching_fields: ["dob", "gp", "name_prefix"]
}]->(Citizen)

-- Rule B3: DOB cluster at GP (5+ citizens share same DOB at same GP)
(Citizen)-[:SAME_DOB_AT_GP {
  dob: "1990-01-01",
  cluster_size: 12,
  gp_code: "3023456"
}]->(Citizen)

-- Rule A1/A2: Ghost beneficiary linked to alert node
(Citizen)-[:FLAGGED_AS {
  confidence: 85,
  detected_at: datetime()
}]->(FraudFlag {rule: "A1", type: "GHOST", description: "Age > 110"})

-- Rule C1: Scheme concentration anomaly at GP level
(GP)-[:HIGH_RISK_CLUSTER {
  scheme: "SWASTHYA_SATHI",
  gp_beneficiary_count: 450,
  total_scheme_count: 1800,
  concentration_ratio: 0.25
}]->(Scheme)

-- Rule D1: Data quality issue
(Citizen)-[:FLAGGED_AS {
  confidence: 60,
  detected_at: datetime()
}]->(FraudFlag {rule: "D1", type: "DATA_QUALITY", description: "Missing DOB"})
```

---

## 4. Fraud Detection Rules — Full Specification

### Rule Set A: Ghost Beneficiary Detection

| Rule | Trigger | Confidence | Action |
|---|---|---|---|
| A1 | `age > 110` | 85% | Create `FLAGGED_AS → FraudFlag(GHOST, "Implausible age")` |
| A2 | `age < 0` (DOB in future) | 90% | Create `FLAGGED_AS → FraudFlag(GHOST, "Future DOB")` |
| A3 | `dob IS NULL AND scheme_beneficiary_id IS NOT NULL` | 60% | Create `FLAGGED_AS → FraudFlag(DATA_QUALITY, "No DOB on file")` |

**False Positive Reduction:**
- Use age > 110, NOT 100 (super-centenarians exist and are legitimate)
- Distinguish "missing DOB" (D rule) from "implausible DOB" (A rule) — different confidence levels
- Cross-check against scheme enrollment date (if enrolled after age 80, reduce ghost confidence)

---

### Rule Set B: Duplicate Identity Detection

| Rule | Trigger | Confidence |
|---|---|---|
| B1 | Exact: `name == name AND dob == dob AND gp_code == gp_code` | 92% |
| B2 | Fuzzy: `name_similarity >= 0.80 AND dob == dob AND gp_code == gp_code` | 78% |
| B3 | DOB cluster: `5+ citizens with same dob at same GP` | 70% |
| B4 | Cross-GP: `name == name AND dob == dob AND district == district` | 65% |

**Graph edge created:** `(c1)-[:POTENTIAL_DUPLICATE {confidence, rule, name_similarity}]->(c2)`

**False Positive Reduction:**
- Require DOB + GP match for B1/B2 (name alone has too many common names in WB)
- For B3: require minimum GP size > 50 citizens before flagging (small GPs inflate ratio)
- For B4: cross-GP same name+DOB is suspicious but lower confidence — requires investigator review
- Name similarity threshold: 0.80 minimum (not 0.60) to avoid flagging AMIT vs AMITA

---

### Rule Set C: Scheme Anomaly Detection

| Rule | Trigger | Confidence |
|---|---|---|
| C1 | GP has > 15% of a scheme's total beneficiaries | 70% |
| C2 | Single citizen enrolled in logically conflicting schemes | 65% |
| C3 | Scheme enrollment date predates citizen's birth year | 80% |

**Graph edge created:** `(GP)-[:HIGH_RISK_CLUSTER {scheme, ratio}]->(Scheme)`

**False Positive Reduction:**
- C1: Apply only when GP has > 50 enrolled in the scheme (absolute minimum)
- C2: Requires scheme conflict matrix (e.g. two mutually exclusive income brackets) — define explicitly
- C3: Parse enrollment date carefully — bad data entry creates many false positives here

---

### Rule Set D: Data Quality Audit

| Rule | Trigger | Confidence |
|---|---|---|
| D1 | `dob IS NULL` | 60% |
| D2 | `fullname IS NULL OR fullname = ''` | 65% |
| D3 | Duplicate `scheme_beneficiary_id` across two different `uid` | 88% |
| D4 | `lgd_district_code` not in known list | 55% |

**Note:** D rules are data quality issues, NOT directly fraud. However D3 (duplicate scheme_beneficiary_id) is a strong fraud signal — it means two citizens were registered under the same official ID.

---

## 5. LLM Eligibility Assessment Prompt

When the user clicks "Assess Citizen" for a specific `uid`, the system should:
1. Fetch the citizen's 2-hop graph neighborhood from Neo4j
2. Count: same-DOB neighbors, duplicate edges, FraudFlag connections
3. Pass the full context to the LLM with the structured prompt below

```python
FRAUD_ASSESSMENT_PROMPT = """
You are a senior welfare fraud analyst for the West Bengal Unified Social Registry (USR).
You have been given the complete Knowledge Graph profile for one beneficiary.
Your task is to assess fraud risk and recommend action.

═══════════════════════════════════════════
BENEFICIARY PROFILE
═══════════════════════════════════════════
Name:            {name}
Date of Birth:   {dob}  (Age: {age} years)
Gender:          {gender}
Scheme ID:       {scheme_beneficiary_id}
Risk Score:      {risk_score}/100  (Tier: {risk_tier})

GEOGRAPHIC LOCATION
-------------------
GP:       {gp_name} (Code: {gp_code})
Block:    {block_name}
District: {district_name}

SCHEME ENROLLMENT
-----------------
{scheme_list}

═══════════════════════════════════════════
KNOWLEDGE GRAPH CONTEXT (2-HOP ANALYSIS)
═══════════════════════════════════════════

DUPLICATE SIGNALS
-----------------
Potential duplicate relationships:    {duplicate_count}
  {duplicate_pairs_detail}
  (Each entry: citizen name | DOB | confidence% | rule | name similarity)

SAME-DOB CLUSTER AT GP
-----------------------
Citizens sharing this DOB at {gp_name}: {same_dob_count}
  Threshold for ghost factory flag: 5+
  Status: {same_dob_status}

GEOGRAPHIC RISK CONTEXT
-----------------------
High-risk citizens in {gp_name}: {gp_high_risk_count} / {gp_total} ({gp_high_risk_pct}%)
Scheme concentration flags at this GP: {gp_scheme_flags}

ACTIVE FRAUD FLAGS
------------------
{flag_list}
  (Format: FLAG TYPE | Rule | Confidence | Description)

MULTI-HOP INSIGHTS (2-hop graph traversal)
-------------------------------------------
{multi_hop_insights}

═══════════════════════════════════════════
FRAUD RULES REFERENCE
═══════════════════════════════════════════
A1: Age > 110 years → Ghost (confidence 85%)
A2: DOB in future   → Ghost (confidence 90%)
B1: Exact match (name+DOB+GP) → Duplicate (confidence 92%)
B2: Fuzzy match (name 80%+, same DOB, same GP) → Duplicate (confidence 78%)
B3: 5+ with same DOB at GP → DOB cluster / ghost factory (confidence 70%)
B4: Cross-GP same name+DOB → Suspicious duplicate (confidence 65%)
C1: GP >15% of scheme beneficiaries → Concentration fraud (confidence 70%)
C3: Enrollment before birth year → Data falsification (confidence 80%)
D1: Missing DOB → Data quality (confidence 60%)
D3: Duplicate scheme_beneficiary_id → Identity theft (confidence 88%)

═══════════════════════════════════════════
INSTRUCTIONS
═══════════════════════════════════════════
Step 1: List which fraud rules (A1–D4) are triggered for this citizen.
Step 2: Assess whether each trigger is likely a TRUE POSITIVE or FALSE POSITIVE.
         - Consider: common surname in region, large legitimate family, data entry errors
Step 3: Calculate overall fraud confidence (0–100%) using weighted averaging.
Step 4: Recommend one of: CLEAR / MONITOR / INVESTIGATE / SUSPEND
         - CLEAR: <30% confidence. No action needed.
         - MONITOR: 30–59%. Flag for quarterly review.
         - INVESTIGATE: 60–79%. Field verification required within 30 days.
         - SUSPEND: ≥80%. Scheme disbursement halt pending verification.
Step 5: If the citizen appears legitimate, identify any ADDITIONAL SCHEMES they may
         be eligible for based on their profile.

Respond ONLY in this JSON format:
{{
  "fraud_rules_triggered": ["B1", "B3"],
  "false_positive_assessment": "Common Bengali surname. However, exact DOB match and same GP is unusual.",
  "overall_confidence": 84,
  "recommendation": "INVESTIGATE",
  "reasoning": "Two citizens with identical name and DOB registered at the same GP. Name similarity 1.0. DOB cluster of 8 at this GP further elevates suspicion. Recommend field verification.",
  "additional_schemes_eligible": ["PM-KISAN (if agricultural land holder)", "NFSA (income bracket check needed)"],
  "priority": "HIGH"
}}
"""
```

---

## 6. Knowledge Map Visualization Design

### Node Colors (risk-aware)

| Node Type | Color | Hex | Visual Style |
|---|---|---|---|
| Citizen — LOW | Green | `#10b981` | Small circle |
| Citizen — MODERATE | Amber | `#f59e0b` | Medium circle |
| Citizen — HIGH | Orange | `#f97316` | Large circle |
| Citizen — CRITICAL | Crimson | `#ef4444` | Large circle + pulsing ring |
| GP node | Blue | `#3b82f6` | Diamond shape |
| Block node | Indigo | `#6366f1` | Hexagon |
| District node | Purple | `#8b5cf6` | Large hexagon |
| Scheme node | Cyan | `#06b6d4` | Square |
| FraudFlag node | Dark Red | `#dc2626` | Warning triangle, always visible |

### Edge Colors (semantic)

| Relationship | Color | Style |
|---|---|---|
| `LIVES_IN` | Slate `#94a3b8` | Thin solid line |
| `PART_OF` | Slate `#cbd5e1` | Very thin dashed |
| `ENROLLED_IN` | Cyan `#06b6d4` | Medium solid |
| `POTENTIAL_DUPLICATE` | Amber `#f59e0b` | Thick dashed + arrowhead |
| `SAME_DOB_AT_GP` | Red `#ef4444` | Thick solid + pulsing |
| `HIGH_RISK_CLUSTER` | Dark Red `#dc2626` | Very thick solid |
| `FLAGGED_AS` | Dark Red `#7f1d1d` | Thick dotted to FraudFlag |

### Interaction Design
- Clicking a FraudFlag node → highlights all citizens connected to it
- Clicking a GP node → shows all Citizen nodes at that GP, colored by risk tier
- Clicking a Citizen node → shows their 2-hop neighborhood + opens "Assess with AI" panel
- Hover on `POTENTIAL_DUPLICATE` edge → tooltip showing confidence %, rule, name similarity

---

## 7. Implementation Plan

### Phase 1 — Enrich `graph_sync.py` with property updates
- Add `age`, `is_ghost_flag`, `is_dup_flag`, `is_anomaly_flag` to Citizen nodes
- Add `high_risk_pct`, `risk_concentration` to GP nodes
- Add `beneficiary_count` to Scheme nodes

### Phase 2 — Add `create_fraud_edges()` to `graph_sync.py`
Called after initial sync. Creates all B-rule duplicate edges and A-rule ghost flags in graph:
```python
async def create_fraud_edges(limit: int = None) -> dict:
    # B1: exact duplicate pairs → POTENTIAL_DUPLICATE edges
    # B3: DOB clusters → SAME_DOB_AT_GP edges
    # A1/A2: ghost citizens → FLAGGED_AS → FraudFlag nodes
    # C1: GP concentration → HIGH_RISK_CLUSTER edges
    return {"edges_created": n}
```

### Phase 3 — Update `graph_db.py` `get_combined_graph()`
Replace document-entity query with USR-aware query:
```cypher
MATCH (c:Citizen)-[:LIVES_IN]->(gp:GP)
OPTIONAL MATCH (c)-[dup:POTENTIAL_DUPLICATE]->(c2:Citizen)
OPTIONAL MATCH (c)-[:FLAGGED_AS]->(f:FraudFlag)
RETURN c, gp, dup, c2, f
LIMIT 500
```
Returns both structural and fraud edges to the frontend.

### Phase 4 — Update `ai_analytics.py` `assess_eligibility_with_ai()`
Pull 2-hop neighborhood for the citizen before calling NVIDIA LLM:
```python
graph_context = await get_citizen_graph_context(uid)  # new function
prompt = FRAUD_ASSESSMENT_PROMPT.format(**citizen_data, **graph_context)
response = await nvidia_client.chat.completions.create(...)
```

### Phase 5 — Add new API endpoint
```
GET /api/usr/citizen/{uid}/graph-neighborhood
```
Returns a citizen's personal 2-hop subgraph for the Knowledge Map panel.

### Phase 6 — Frontend Knowledge Map update
- Change node color mapping from document entity types → citizen risk tiers
- Render `FraudFlag` nodes as warning triangles
- Render `POTENTIAL_DUPLICATE` edges as thick amber dashed lines
- Add "Assess with AI" button in citizen hover panel

---

## 8. False Positive Reduction Summary

| Risk | Current | Mitigation |
|---|---|---|
| Common Bengali name flagged as duplicate | No mitigation | Require DOB + GP match minimum |
| Large legitimate families flagged | No mitigation | Require 3 matching fields for B1/B2 |
| Age > 100 flagged as ghost | Threshold too low | Raise threshold to age > 110 |
| Small GP inflating C1 ratio | No minimum | Require ≥50 in scheme before C1 fires |
| Missing DOB flagged as ghost | Conflated with A rules | Separate D-rules: "Missing" ≠ "Implausible" |
| Enrollment date data entry errors | No handling | Flag as D-rule, lower confidence (55%) |
| Cross-GP same name flagged too aggressively | No cross-GP | B4 fires at 65% only — field review threshold |

---

## 9. Files to Change (Implementation Checklist)

| File | Change |
|---|---|
| `backend/src/services/graph_sync.py` | Add `create_fraud_edges()`, enrich node properties |
| `backend/src/services/graph_db.py` | Rewrite `get_combined_graph()` for USR schema |
| `backend/src/services/ai_analytics.py` | Add `get_citizen_graph_context()`, update prompt |
| `backend/src/routers/usr.py` | Add `GET /citizen/{uid}/graph-neighborhood` |
| `frontend/src/App.tsx` | Update Knowledge Map node/edge color scheme |

---

*This document must be reviewed and approved before any implementation begins.*
