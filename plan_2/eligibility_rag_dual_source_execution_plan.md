# Eligibility-Aware RAG (PDF + Dump) Execution Plan

## 1. Goal
Build a production-grade Research Chat that can answer:
- general policy questions from uploaded documents,
- citizen eligibility questions using both policy text and dump data,
- inclusion/exclusion outcomes with evidence and explainability.

Final answer style for citizen queries:
- `decision`: `ELIGIBLE` | `NOT_ELIGIBLE` | `REVIEW_REQUIRED`
- `reason`: deterministic explanation
- `policy_evidence`: quote/snippet references from uploaded docs
- `data_evidence`: dump fields used for decision

---

## 2. Core Principle
Use **hybrid decisioning**:
- RAG/LLM for understanding policy and extracting criteria.
- Deterministic rule engine for final eligibility outcome.

RAG is not the final judge. Rule engine is.

---

## 3. Data Sources and Responsibilities
1. MinIO
- Stores raw uploaded PDFs/docs.

2. Qdrant
- Stores chunk embeddings from uploaded docs.
- Stores optional citizen profile vectors (for semantic lookup and narrative context).

3. Neo4j
- Stores citizen relationship graph and fraud/intelligence context.
- Used for graph-based enrichment/explanations, not sole eligibility decision.

4. Postgres (`srsadmin`)
- Source of truth for structured citizen fields.
- Source of truth for extracted/approved eligibility rule versions.

---

## 4. Target Flow
1. User uploads policy document.
2. Backend extracts text (PDF parse + OCR fallback).
3. Intent + scheme detection identifies target scheme.
4. LLM extracts eligibility metadata into structured JSON.
5. Backend maps extracted metadata to executable rule schema.
6. Rule version stored as `DRAFT`, then validated, then `ACTIVE`.
7. User asks in Research Chat: “Is UID X eligible for Scheme Y?”
8. System fetches:
- policy evidence from Qdrant (doc chunks),
- citizen fields from `srsadmin`,
- optional graph context from Neo4j.
9. Rule engine computes decision.
10. Chat returns decision + evidence + confidence + review flag.

---

## 5. Decision Contract
For eligibility questions, response payload should include:
- `query_type`: `eligibility_assessment`
- `citizen_uid`
- `scheme_id`
- `decision`
- `confidence` (rule coverage confidence, not pure LLM confidence)
- `matched_include_conditions`
- `failed_include_conditions`
- `triggered_exclude_conditions`
- `unmapped_policy_conditions`
- `policy_sources` (doc IDs/chunk refs)
- `data_snapshot` (only safe fields)
- `review_required` (boolean)

If extracted criteria contain unmapped fields, force:
- `decision = REVIEW_REQUIRED`
- explicit list of unmapped criteria.

---

## 6. Backend Implementation Plan

### Phase A: Policy Extraction and Rule Normalization
1. Keep pipeline: upload -> parse/OCR -> extract metadata.
2. Introduce strict internal schema:
- include conditions (age, gender, residence, employment, marital, disability, etc.)
- exclude conditions
- derived predicates
3. Save:
- raw extracted metadata,
- normalized executable conditions,
- extraction evidence snippets,
- unmapped criteria list.

### Phase B: Deterministic Eligibility Engine
1. Build evaluator contract:
- input: citizen row + active scheme rule
- output: decision object (include/exclude/missing/unmapped)
2. Implement condition registry:
- each field has typed comparator functions
- null/missing data strategy defined per field
3. Add batch evaluation endpoint for dumps with pagination/chunking.

### Phase C: Chat Orchestration Layer
1. Add query router:
- detect eligibility intent vs general research intent.
2. If eligibility intent:
- resolve citizen (`uid`) and scheme,
- load active rule,
- execute evaluator,
- collect policy evidence from Qdrant,
- enrich with graph facts from Neo4j (optional).
3. Return structured answer with layman explanation.

### Phase D: Governance and Safety
1. Rule lifecycle:
- `DRAFT -> VALIDATED -> ACTIVE -> RETIRED`
2. Keep versioned rule history and audit log.
3. Block auto-activation if validation coverage is below threshold.
4. Persist all `REVIEW_REQUIRED` outcomes for schema evolution.

---

## 7. Frontend Implementation Plan

### Research Chat UX
1. Add answer mode badges:
- `General Research`
- `Eligibility Decision`
2. For eligibility answers, render cards:
- Decision card
- Why card (include/exclude breakdown)
- Policy evidence card
- Citizen data evidence card
- Review required warning card

### Rule Transparency UX
1. Show currently active scheme rule version used in answer.
2. Show extracted criteria summary in readable language.
3. Show unmapped criteria when present.

### Progress UX
1. For doc upload/extraction:
- `Uploaded -> Parsing -> OCR -> Extracting Criteria -> Rule Drafted`
2. For evaluation:
- `Loading Citizen -> Applying Rule -> Generating Evidence -> Final Decision`

---

## 8. Schema Evolution (Self-Learning Backend)
1. Capture unmapped criteria keys across documents.
2. Track frequency + sample evidence snippets.
3. Promote frequently recurring criteria to candidate normalized fields.
4. Human approval gate before enabling as executable rule fields.

---

## 9. Performance and Scale
1. Use async batched evaluation for large dumps.
2. Add indexed filters on key citizen fields in Postgres.
3. Keep Qdrant retrieval top-k bounded for latency.
4. Cache active rule versions by scheme.
5. Add background jobs for long-running extraction/evaluation with status polling.

---

## 10. Acceptance Criteria
1. Given uploaded policy PDF + known citizen UID + scheme:
- system returns deterministic eligibility decision with evidence.
2. If policy has unmapped conditions:
- returns `REVIEW_REQUIRED`, never false-valid.
3. Research chat can answer both:
- open-ended policy questions,
- structured eligibility decision questions.
4. Decision response always references:
- at least one policy source snippet,
- at least one citizen data field used.

---

## 11. Execution Order
1. Stabilize extraction -> normalized rule schema.
2. Finalize deterministic evaluator.
3. Integrate eligibility mode in research chat router.
4. Add UI evidence/decision cards.
5. Add schema-evolution loop and monitoring.
6. Harden with tests, load checks, and observability.

---

## 12. Test Strategy
1. Unit tests:
- condition comparators,
- evaluator outcomes,
- null/missing handling.
2. Integration tests:
- upload -> extract -> activate rule -> evaluate citizen.
3. Chat tests:
- intent routing correctness,
- eligibility response contract validation.
4. Regression tests:
- no eligibility decision when rule coverage is incomplete.

---

## 13. Immediate Next Step (when resuming work)
Implement eligibility-intent routing in Research Chat backend and return the structured decision contract (Section 5) for UID + scheme queries.
