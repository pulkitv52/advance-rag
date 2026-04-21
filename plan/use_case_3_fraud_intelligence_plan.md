# Use Case 3: Fraud Intelligence & USR Enhancement Plan

## Gap Analysis: What We Have vs. What the Use Case Demands

| Use Case Requirement | Current State | Gap |
|---|---|---|
| Dynamic eligibility in near real-time | Static batch scoring | ❌ Not triggered on data change |
| ML-based beneficiary segmentation | 3-rule heuristic (age/gender/scheme) | ⚠️ Shallow — no clustering |
| Geo-spatial intelligence for last-mile | Bar chart by district name | ❌ No real map, no LGD code matching |
| Federated database management | Single PostgreSQL + Neo4j | ❌ No federation layer yet |
| AI/NLP interoperability | Schema mapped once | ⚠️ Not live |
| Anomaly detection in scheme utilization | Same-GP + same-DOB check | ❌ Very high false positives |
| Feedback loop / grievance intelligence | Not built | ❌ Not started |

---

## Design Philosophy

> Every fraud rule has a **Confidence Score (0–100)** and a minimum threshold before flagging.
> A case is only surfaced for human review if `confidence >= 70 AND at least 2 independent rules agree`.
> This "AND 2 rules" barrier eliminates false positives in production.

---

## Part 1: Fraud Detection — 4 Rule Sets

### Rule Set A: Ghost Beneficiary Detection

**A1 — Biologically Impossible Age** | Confidence: 95 | FP Risk: Near zero
```cypher
MATCH (c:Citizen)
WHERE duration.between(date(c.dob), date()).years > 105
RETURN c.name, c.dob, c.uid
```

**A2 — Wrong Age for Scheme** | Confidence: 85 | FP Risk: Low
```cypher
MATCH (c:Citizen)-[:ENROLLED_IN]->(s:Scheme)
WHERE s.name CONTAINS 'Old Age'
  AND duration.between(date(c.dob), date()).years < 58
RETURN c.name, c.dob, s.name AS scheme
```

**A3 — Child in Adult Scheme** | Confidence: 90 | FP Risk: Very low
```cypher
MATCH (c:Citizen)-[:ENROLLED_IN]->(s:Scheme)
WHERE duration.between(date(c.dob), date()).years < 18
  AND s.name IN ['Employment Scheme', 'Widow Pension', 'Old Age Pension']
RETURN c.name, c.dob, s.name
```

---

### Rule Set B: Duplicate Identity Detection

**B1 — Exact Duplicate (Different UID)** | Confidence: 92 | FP Risk: Low
```cypher
MATCH (c1:Citizen), (c2:Citizen)
WHERE id(c1) < id(c2)
  AND c1.name = c2.name AND c1.dob = c2.dob
  AND c1.gender = c2.gender AND c1.uid <> c2.uid
RETURN c1.name, c1.uid, c2.uid, c1.dob
```

**B2 — Fuzzy Name Match + Same DOB + Same GP** | Confidence: 75–100 | FP Risk: Very low  
*(Catches `RAHIMA BIBI` vs `RAHIMA BIWI`, `GAYATRI CHOUDHURI` vs `GAYATRI CHOWDHURY`)*
```cypher
MATCH (c1:Citizen)-[:RESIDES_IN]->(g:GP)<-[:RESIDES_IN]-(c2:Citizen)
WHERE id(c1) < id(c2)
  AND c1.dob = c2.dob AND c1.gender = c2.gender AND c1.uid <> c2.uid
  AND apoc.text.sorensenDiceSimilarity(c1.name, c2.name) > 0.75
RETURN c1.name, c2.name,
       apoc.text.sorensenDiceSimilarity(c1.name, c2.name) AS name_similarity,
       g.name AS shared_gp, c1.dob
ORDER BY name_similarity DESC
LIMIT 50
```
Confidence formula: `60 + (name_similarity * 40)` → max 100

**B3 — Cross-Scheme Double Dipping** | Confidence: 88 | FP Risk: Low
```cypher
MATCH (c1:Citizen)-[:ENROLLED_IN]->(s1:Scheme)
MATCH (c2:Citizen)-[:ENROLLED_IN]->(s2:Scheme)
WHERE c1.dob = c2.dob AND c1.gender = c2.gender
  AND id(c1) < id(c2) AND c1.uid <> c2.uid
  AND apoc.text.sorensenDiceSimilarity(c1.name, c2.name) > 0.80
RETURN c1.name, c2.name, s1.name AS scheme1, s2.name AS scheme2, c1.uid, c2.uid
```

---

### Rule Set C: Scheme Anomaly Detection

**C1 — GP Benefit Concentration Spike** | Confidence: 75 | FP Risk: Medium
```cypher
MATCH (g:GP)<-[:RESIDES_IN]-(c:Citizen)-[:PART_OF]->(b:Block)
WITH g, b, count(c) AS total,
     count(CASE WHEN c.vulnerability_score >= 60 THEN 1 END) AS max_risk_count
WITH b, g, total, max_risk_count,
     toFloat(max_risk_count) / total AS concentration_ratio
WHERE concentration_ratio > 0.5
RETURN g.name, b.name, total, max_risk_count, concentration_ratio
ORDER BY concentration_ratio DESC
```

**C2 — Mutually Exclusive Scheme Membership** | Confidence: 90 | FP Risk: Low

Contradiction pairs:
| Scheme A | Scheme B | Reason |
|---|---|---|
| Widow Pension | Vivah Protsahan | Widow ≠ married |
| Old Age Pension (60+) | MGNREGS (working age) | Age conflict |
| BPL scheme | APL scheme | Economic category conflict |
| Child scholarship | Adult employment | Age conflict |

```cypher
MATCH (c:Citizen)-[:ENROLLED_IN]->(s1:Scheme)
MATCH (c)-[:ENROLLED_IN]->(s2:Scheme)
WHERE s1.name CONTAINS 'Widow'
  AND (s2.name CONTAINS 'Married' OR s2.name CONTAINS 'Vivah')
RETURN c.name, c.uid, s1.name, s2.name
```

**C3 — Enrollment Date Spike** | Confidence: 80 | FP Risk: Low *(requires date on edge)*
```cypher
MATCH (c:Citizen)-[r:ENROLLED_IN]->(s:Scheme)
MATCH (c)-[:RESIDES_IN]->(g:GP)
WHERE r.enrollment_date IS NOT NULL
WITH g, s, r.enrollment_date AS enroll_date, count(c) AS daily_count
WHERE daily_count > 50
RETURN g.name, s.name, enroll_date, daily_count
ORDER BY daily_count DESC
```

---

### Rule Set D: Data Quality Pre-Checks (Run Before Fraud Rules)

```cypher
// D1: NULL or placeholder DOB
MATCH (c:Citizen) WHERE c.dob IS NULL OR c.dob = '1900-01-01' RETURN count(c)

// D2: Future DOB (data entry error)
MATCH (c:Citizen) WHERE date(c.dob) > date() RETURN c.name, c.dob

// D3: Suspiciously short or numeric names
MATCH (c:Citizen) WHERE size(c.name) < 3 OR c.name =~ '.*\\d.*' RETURN c.name, c.uid
```

---

## Part 2: Enhanced Vulnerability Scoring (0–100 Scale)

| Factor | Condition | Points |
|---|---|---|
| Age | > 80 years | 30 |
| Age | 60–80 years | 20 |
| Age | < 5 years (infant) | 15 |
| Gender | Female | 10 |
| Scheme Coverage | 0 schemes | 25 |
| Scheme Coverage | 1 scheme | 15 |
| Economy | BPL | 15 |
| Widow | Widow scheme enrolled | 10 |
| Disability | Disability scheme | 15 |
| Location | Tribal/LGD remote area | 10 |

**Risk Tiers:**
- 0–20: 🟢 Low Risk
- 21–40: 🟡 Moderate Risk
- 41–60: 🟠 High Risk
- 61–100: 🔴 Critical — Immediate intervention

### Enhanced Cypher (for ai_analytics.py)
```cypher
MATCH (c:Citizen)
OPTIONAL MATCH (c)-[:ENROLLED_IN]->(s:Scheme)
WITH c, collect(s.name) as scheme_names, count(s) as scheme_count
SET c.vulnerability_score = (
    CASE
        WHEN duration.between(date(c.dob), date()).years > 80 THEN 30
        WHEN duration.between(date(c.dob), date()).years > 60 THEN 20
        WHEN duration.between(date(c.dob), date()).years < 5  THEN 15
        ELSE 0 END +
    CASE WHEN c.gender = 'FEMALE' THEN 10 ELSE 0 END +
    CASE
        WHEN scheme_count = 0 THEN 25
        WHEN scheme_count = 1 THEN 15
        ELSE 0 END +
    CASE WHEN any(s IN scheme_names WHERE toLower(s) CONTAINS 'widow') THEN 10 ELSE 0 END +
    CASE WHEN any(s IN scheme_names WHERE toLower(s) CONTAINS 'disab') THEN 15 ELSE 0 END +
    CASE WHEN any(s IN scheme_names WHERE toLower(s) CONTAINS 'bpl')   THEN 15 ELSE 0 END
),
c.risk_tier = CASE
    WHEN c.vulnerability_score >= 61 THEN 'CRITICAL'
    WHEN c.vulnerability_score >= 41 THEN 'HIGH'
    WHEN c.vulnerability_score >= 21 THEN 'MODERATE'
    ELSE 'LOW'
END
RETURN count(c) AS scored_citizens
```

---

## Part 3: Confidence Summary

| Rule | Confidence | FP Risk | Priority |
|---|---|---|---|
| A1 — Age > 105 | 95 | Near zero | ⭐ Immediate |
| A2 — Wrong age for scheme | 85 | Low | ⭐ Immediate |
| A3 — Child in adult scheme | 90 | Very low | ⭐ Immediate |
| B1 — Exact duplicate | 92 | Low | ⭐ Immediate |
| **B2 — Fuzzy name + same GP** | **75–100** | **Very low** | **🔥 Top Priority** |
| B3 — Cross-scheme double-dip | 88 | Low | High |
| C2 — Scheme contradiction | 90 | Low | High |
| C1 — GP concentration spike | 75 | Medium | Medium |
| C3 — Enrollment date spike | 80 | Low | Low (needs date field) |

---

## Part 4: Build Sequence

| Week | Task |
|---|---|
| 1 | Implement B2 fuzzy dedup in `ai_analytics.py` (replaces broken exact-match) |
| 1 | Implement A1, A2, A3 ghost detection |
| 2 | Full dataset import — all ~1L citizens from PostgreSQL into Neo4j |
| 2 | Run enhanced 0–100 scoring on full graph |
| 3 | C2 scheme contradiction rules + scheme taxonomy |
| 4 | LGD code → tribal area mapping for geo-risk |
| Future | C3 enrollment date spike detection |
| Future | Grievance node + sentiment feedback loop |
