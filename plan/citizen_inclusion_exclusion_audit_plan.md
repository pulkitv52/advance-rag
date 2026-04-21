# Citizen Inclusion/Exclusion and Audit Plan (Scheme Eligibility from Dump + PDF)

## 1. Problem Statement
Government scheme data often has two critical errors:
1. Wrong inclusion: A citizen is enrolled in a scheme they should not receive.
2. Wrong exclusion: A citizen is eligible but is not enrolled in the scheme.

The objective is to build an explainable system that:
- Reads eligibility criteria from unstructured documents (PDF, circulars, policy notes).
- Matches criteria against citizen records from the data dump.
- Flags conflicting enrollments and missing rightful enrollments.
- Shows all flagged citizens in a dashboard and knowledge graph with clear red flags.
- Produces audit-ready reports first, then enables deeper fraud detection.

## 2. Clear Definitions (Layman Friendly)
- Inclusion Error (Red Flag): Citizen is present in a scheme but violates the scheme rule.
  - Example: Citizen enrolled in a scheme despite failing one or more active eligibility conditions.
- Exclusion Error (Amber/Orange Flag): Citizen appears eligible for a scheme but is not enrolled.
  - Example: Citizen meets active eligibility conditions but has no enrollment record.
- Identity Match Confidence: How sure we are that records from multiple tables/schemes represent the same person.

## 3. Core Business Goal
Create a trustworthy decision engine where every flag can answer:
- Why was this citizen flagged?
- Which rule was violated or missed?
- Which fields were used as evidence?
- How confident is the identity match and final decision?

## 4. End-to-End Approach

### Step A: Build Citizen 360 from the dump
- Merge citizen records across datasets/scheme tables.
- Create a unified citizen profile with key identity fields:
  - ration_card_number
  - beneficiary_id (scheme-specific)
  - name (normalized)
  - date_of_birth
  - gender
  - spouse_name / marital_status (if available)
  - mobile
  - address hierarchy (district/block/gp/village)

### Step B: Identity Resolution (Same Citizen Check)
Use deterministic + probabilistic matching.

1. Deterministic match (high trust):
- Same ration card number + same DOB.
- Same official beneficiary ID where unique.

2. Probabilistic match (scored):
- Name similarity + DOB + gender + household/address overlap + mobile overlap.
- Assign confidence tiers:
  - High (>= 0.90)
  - Medium (0.75 to 0.89)
  - Low (< 0.75, send to review)

Only high/medium confidence records are auto-evaluated for hard decisions.

### Step C: Eligibility Rule Extraction from PDF/Unstructured Docs
- Parse document text and tables.
- Extract rule clauses into a structured dynamic rule catalog:
  - scheme_name
  - rule_id
  - rule_version
  - effective_from
  - effective_to
  - include_conditions
  - exclude_conditions
  - mandatory_documents
  - conflict_schemes (mutually exclusive)
  - age/marital/gender/income/disability criteria
- Keep clause-level traceability: source document, page number, and clause snippet.
- Human validate each extracted rule version before activation (important control).

### Step D: Rule Engine for Inclusion/Exclusion
Use a generic evaluator that reads conditions from the rule catalog (no hardcoded scheme-specific logic).

For each citizen and each relevant scheme/rule version:
1. Evaluate eligibility.
2. Check actual enrollment status.
3. Assign outcome:
- `INCLUSION_ERROR`: enrolled but not eligible.
- `EXCLUSION_ERROR`: eligible but not enrolled.
- `VALID_ENROLLMENT`: eligible and enrolled.
- `NOT_APPLICABLE`: not eligible and not enrolled.
- Store evidence payload for each decision: fields checked, condition results, and confidence.

### Step E: Contradiction Matrix (Critical)
Maintain a data-driven scheme conflict matrix (configured table/catalog), for example:
- Category conflicts (income band, age band, category-exclusive schemes)
- Temporal conflicts (simultaneous enrollment not allowed during overlap period)
- Program conflicts defined by policy documents

If citizen is enrolled in conflicting schemes simultaneously, create high-priority inclusion alerts.

### Step F: Dynamic Rule Lifecycle
- Draft -> Validated -> Active -> Retired state machine for each rule version.
- Decisions are always tied to the active rule version at decision time.
- Re-run capability: when rules change, re-evaluate selected cohorts for impact analysis.

## 5. Knowledge Graph Representation (Explainable Visual)

### Nodes
- Citizen
- Scheme
- EligibilityRule
- DocumentSource
- Alert

### Edges
- `(:Citizen)-[:ENROLLED_IN]->(:Scheme)`
- `(:Scheme)-[:HAS_RULE]->(:EligibilityRule)`
- `(:EligibilityRule)-[:DERIVED_FROM]->(:DocumentSource)`
- `(:Citizen)-[:FLAGGED_AS]->(:Alert)`

### Flag Colors in Graph
- Red: Inclusion error (wrongly included / contradiction).
- Orange: Exclusion error (eligible but missing enrollment).
- Green: Valid enrollment.

Each alert tooltip must show:
- Rule name
- Evidence fields (DOB, ration card, marital status, scheme IDs)
- Reason text in plain language
- Confidence score

## 6. Audit Report Design
Generate two levels of reports.

### A. Citizen-Level Audit Report
- Citizen identifiers
- Scheme(s) enrolled
- Scheme(s) eligible-but-missing
- Inclusion/Exclusion status
- Evidence snapshot
- Rule reference (document + clause)
- Recommended next action

### B. Program-Level Audit Summary
- Total citizens evaluated
- Total red flags (inclusion errors)
- Total exclusion gaps
- Top violated rules
- Geography-wise concentration (district/block/GP)
- Pending manual review count (low identity confidence)

## 7. Dashboard Plan (Phase after Rule Engine)

### Priority widgets
- KPI cards: total flagged, inclusion errors, exclusion errors, manual review queue.
- Filter panel: district/block/GP/scheme/rule/confidence/date.
- Flagged citizens table with drill-down.
- Knowledge graph pane for selected citizen cluster.
- Case action buttons: assign, verify, close, escalate.

### Case workflow
- `OPEN` -> `UNDER_REVIEW` -> `VERIFIED` -> `CLOSED` (or `ESCALATED`)
- Every action stored with operator and timestamp for audit trail.

## 8. Fraud Detection (After Audit Foundation)
Fraud detection should be layered after inclusion/exclusion engine stabilizes.

### Fraud signals to add later
- Repeated identity reuse across schemes.
- Same mobile/ration card linked to many beneficiaries.
- Suspicious clusters in one locality.
- Operator-level anomaly trends.

This sequence prevents mixing eligibility mistakes with actual fraud signals too early.

## 9. Data Model for Alerts (Minimum)
`alert_id, citizen_uid, alert_type, severity, scheme_id, rule_id,`
`identity_match_confidence, decision_confidence, evidence_json,`
`status, assigned_to, created_at, updated_at`

## 10. Key Risks and Mitigation
1. Poor data quality (missing DOB/marital status)
- Mitigation: Pre-check pipeline + data quality score + manual review queue.

2. Wrong identity linkage (two similar names)
- Mitigation: Confidence thresholds + deterministic anchors (ration card, beneficiary ID).

3. Incorrect rule extraction from PDF text
- Mitigation: Human rule approval and versioning before production use.

4. False positives creating trust issues
- Mitigation: Explainable evidence per alert + confidence display + reversible case workflow.

5. Legal/policy change over time
- Mitigation: Rule versioning by effective date and source document.

## 11. Implementation Phases
1. Phase 1: Citizen 360 + identity resolution + confidence scoring.
2. Phase 2: PDF rule extraction + rule validation console.
3. Phase 3: Inclusion/Exclusion engine + contradiction matrix.
4. Phase 4: Knowledge graph flags + citizen drill-down explainability.
5. Phase 5: Audit dashboard + case workflow + downloadable reports.
6. Phase 6: Advanced fraud detection over confirmed alert history.

## 12. Acceptance Criteria
- System evaluates multiple schemes dynamically from rule catalog without code changes per scheme.
- System correctly detects configured cross-scheme contradictions as inclusion errors.
- System correctly detects eligible-but-not-enrolled candidates as exclusion error.
- Every alert has machine evidence + plain-language explanation.
- Graph shows red/orange/green status with drill-down reason.
- Dashboard can filter, triage, and export audit reports.

## 13. Example Decision (Illustrative Only)
Citizen X:
- Marital category: widow
- Enrolled in widow pension: yes
- Also enrolled in married-benefit scheme: yes

Engine result:
- `INCLUSION_ERROR` on married-benefit scheme enrollment.
- Red flag in knowledge graph.
- Audit note: "Citizen profile indicates widow status, but enrollment exists in married-beneficiary scheme. Identity match confidence: 0.93 using ration card + DOB + address."

This gives immediate, explainable visibility for non-technical users.
