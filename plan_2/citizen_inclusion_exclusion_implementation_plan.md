# Citizen Inclusion/Exclusion Audit - Implementation Plan (Production Ready)

## 1. Objective
Build a dynamic, explainable audit platform that detects:
- `INCLUSION_ERROR`: enrolled but not eligible
- `EXCLUSION_ERROR`: eligible but not enrolled

Eligibility criteria must come from unstructured policy documents (PDF/circulars), become structured rules, and be user-manageable from frontend without code changes.

---

## 2. Scope and Principles
- Source of truth schema: `srsadmin`
- Dynamic rule engine (no scheme-specific hardcoding)
- 2-step marker checker for rule validation before activation
- Human-in-the-loop for low-confidence identity matches and uncertain extracted rules
- Full auditability: every decision tied to rule version + evidence

---

## 3. Architecture Overview

### 3.1 Data Flow
1. Ingest citizen data from `srsadmin` into canonical `citizen_360` view/table.
2. Run identity resolution to create `identity_links` with confidence score.
3. Parse policy PDFs and extract candidate rules.
4. Validate extracted rules via 2-step marker checker.
5. Publish validated rule version to `ACTIVE`.
6. Evaluate citizen-scheme eligibility and enrollment status.
7. Persist decisions, alerts, and cases.
8. Serve dashboard, graph, and reports via APIs.

### 3.2 Core Services
- `identity_resolution_service`
- `policy_ingestion_service`
- `rule_validation_service` (2-step marker)
- `eligibility_engine`
- `contradiction_engine`
- `case_workflow_service`
- `reporting_service`

---

## 4. Backend Implementation Plan

## 4.1 Database Design (Postgres)
Create these core tables:
- `citizen_profiles`
- `citizen_enrollments`
- `identity_links`
- `rule_sets`
- `rule_versions`
- `rule_conditions`
- `rule_sources`
- `scheme_conflicts`
- `eligibility_decisions`
- `audit_alerts`
- `audit_cases`
- `audit_events`

Key requirements:
- Every decision stores `rule_version_id`, `identity_match_confidence`, `decision_confidence`, `evidence_json`
- Strong indexes on `scheme_id`, `citizen_uid`, `status`, `created_at`
- Idempotency key for evaluation runs

## 4.2 Citizen 360 + Identity Resolution
- Build canonical profile mapping from `srsadmin` dump tables.
- Deterministic matching:
  - ration_card + DOB
  - unique beneficiary IDs
- Probabilistic matching:
  - name similarity, DOB, gender, address overlap, mobile overlap
- Confidence tiers:
  - High >= 0.90
  - Medium 0.75-0.89
  - Low < 0.75 (manual review queue)

Deliverables:
- Unified profile build job
- Identity link scoring job
- Manual review API for low-confidence merges

## 4.3 Policy Ingestion + Rule Structuring
- Parse PDFs/tables into extracted clauses.
- Normalize clauses into condition DSL JSON (field/operator/value).
- Persist traceability:
  - `source_document`
  - `page_number`
  - `clause_excerpt`

Rule version states:
- `DRAFT`
- `VALIDATED_STEP_1`
- `VALIDATED_STEP_2`
- `ACTIVE`
- `RETIRED`

## 4.4 2-Step Marker Checker Workflow
Step 1 checker:
- Validates syntax, field mapping, and missing references.
- Flags ambiguity and unsupported conditions.

Step 2 checker:
- Validates semantic alignment to source clauses.
- Runs dry-run against sample data for sanity.

Only Step 2 pass can activate version.

## 4.5 Eligibility + Contradiction Evaluation
For each `(citizen, scheme, active_rule_version)`:
1. Evaluate include/exclude conditions.
2. Check enrollment existence.
3. Apply contradiction matrix (`scheme_conflicts`).
4. Write outcome:
- `INCLUSION_ERROR`
- `EXCLUSION_ERROR`
- `VALID_ENROLLMENT`
- `NOT_APPLICABLE`

Persist evidence:
- condition-by-condition pass/fail
- source fields used
- confidence
- plain-language reason

## 4.6 API Plan
Rule Management:
- `POST /api/audit/rule-sets`
- `POST /api/audit/rule-sets/{id}/versions`
- `POST /api/audit/rule-versions/{id}/validate-step-1`
- `POST /api/audit/rule-versions/{id}/validate-step-2`
- `POST /api/audit/rule-versions/{id}/activate`

Evaluation:
- `POST /api/audit/sync-citizens`
- `POST /api/audit/evaluate`
- `GET /api/audit/evaluations/{run_id}`

Alerts/Cases:
- `GET /api/audit/alerts`
- `POST /api/audit/cases`
- `PATCH /api/audit/cases/{id}`
- `GET /api/audit/cases`

Reports:
- `GET /api/audit/reports/citizen/{uid}`
- `GET /api/audit/reports/program-summary`

---

## 5. Frontend Implementation Plan

## 5.1 Screens
1. Rule Studio
- Create rule set
- Add version
- Add dynamic conditions (field/operator/value)
- Link source clause snippets

2. Validation Console
- Step 1 check results
- Step 2 check results
- Approve/reject with notes

3. Activation & Run Center
- Activate version
- Trigger sync/evaluation
- View run progress and failures

4. Alert Triage Board
- Filter by scheme/rule/geography/confidence/status
- Evidence drawer with plain-language reason

5. Case Management
- Workflow: `OPEN -> UNDER_REVIEW -> VERIFIED -> CLOSED/ESCALATED`
- Assignee, comments, timeline

6. Knowledge Graph + Drilldown
- Red/Orange/Green flag nodes
- Click node -> rule + evidence + confidence

7. Reports
- Citizen-level PDF
- Program summary export (CSV/PDF)

## 5.2 UX Requirements
- Layman-readable labels (avoid internal-only jargon)
- Explicit empty states and action hints
- Full traceability shown for every flag
- No silent failures; surface backend message in UI

---

## 6. Execution Phases and Timeline

## Phase 1 (Week 1-2): Data Foundation
- citizen_360 pipeline
- identity resolution + confidence
- DB schema + migrations
- baseline tests

## Phase 2 (Week 3-4): Rule Platform
- PDF extraction pipeline
- rule DSL and storage
- 2-step marker checker
- rule version lifecycle APIs

## Phase 3 (Week 5-6): Decision Engine
- eligibility evaluator
- contradiction matrix evaluator
- decision and alert persistence
- rerun support by cohort

## Phase 4 (Week 7): UI Operations Layer
- Rule Studio
- Validation Console
- Run Center
- Alert Triage + Case workflow

## Phase 5 (Week 8): Explainability + Reports
- graph integration with colored alerts
- citizen/program reports
- audit trail screens

## Phase 6 (Week 9): Hardening
- performance tuning for large datasets
- retry/idempotency
- observability dashboards
- UAT and rollout checklist

---

## 7. Quality Gates
- Unit coverage for evaluator and identity resolution
- Contract tests for APIs
- Golden test set for rule outcomes
- Load test on large cohort runs
- Reproducibility: same input + same rule version => same outcome

---

## 8. Deployment and Operations
- Background workers for sync/evaluation
- Run metadata and checkpoints
- Alert on failures/timeouts
- Role-based access for rule activation and case closure
- Immutable audit event log for compliance

---

## 9. Risks and Controls
1. Data gaps in dump -> pre-check score + manual review queue
2. Wrong identity linkage -> confidence threshold + reviewer approval
3. Rule extraction mistakes -> mandatory 2-step validation + HITL
4. Trust issues from false positives -> evidence-rich explanation + reversible case workflow
5. Policy change over time -> effective dates + versioning

---

## 10. Definition of Done
- Dynamic rules editable from frontend
- 2-step marker checker enforced before activation
- Inclusion and exclusion detected with evidence
- Contradiction matrix evaluated and alerted
- Cases and reports operational
- Graph and dashboard explain decisions clearly
