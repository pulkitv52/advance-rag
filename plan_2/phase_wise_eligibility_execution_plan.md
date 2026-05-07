# Phase-Wise Plan: Deterministic Inclusion/Exclusion Engine

## Goal
Build a production-ready pipeline where uploaded policy documents produce executable eligibility rules and final citizen outcomes:
- `INCLUSION_ERROR`: enrolled but not eligible
- `EXCLUSION_ERROR`: eligible but not enrolled

This plan assumes primary data source is `srsadmin` schema.

## Phase 0: Baseline Stabilization
- Lock scheme detection priority to: `manual override > filename > llm > text`.
- Ensure per-document scheme auto-fill in UI from filename (`doc_*_<SCHEMEID>_*.pdf`).
- Ensure extraction and evaluation run without stale scheme carry-over.
- Deliverables:
  - Stable upload -> extract -> evaluate flow.
  - Rule metadata stores detection trace and confidence.

## Phase 1: Canonical Rule Schema (Executable)
- Define canonical rule JSON v1 for evaluation:
  - `age_min`, `age_max`
  - `gender_in`
  - `marital_status_in`
  - `income_max`
  - `employment_status_in`, `employment_status_not_in`
  - `min_service_months`
  - `ida_covered_required`
  - `exclude_if_receives_pension`
  - `exclude_if_retired_or_terminated`
  - `exclude_if_reemployed_same_factory`
  - `conflict_scheme_ids`
- Version schema with `rule_schema_version`.
- Deliverables:
  - Backend schema contract doc.
  - Validation layer for allowed keys/types.

## Phase 2: LLM Extraction Contract (LLM as Source of Truth)
- Prompt LLM to return only canonical fields + field-level evidence quotes.
- Keep intent output (`document_intent`) as context, but decisions run only on validated fields.
- Unknown or non-canonical fields go to `unmapped_criteria`.
- Deliverables:
  - Strict parser/validator.
  - Stored `evidence` by field in metadata.
  - No regex fallback for executable conditions.

## Phase 3: Multi-Table Citizen Feature Resolver (`srsadmin`)
- Build resolver to assemble citizen features from relevant tables (not only `swasthya_sathi_beneficiary`).
- Join by `uid` (primary) and controlled fallback keys where required.
- Add provenance metadata per resolved field (`source_table`, `source_column`).
- Deliverables:
  - Reusable feature resolver service.
  - Coverage metrics by field.

## Phase 4: Deterministic Decision Engine
- Evaluate include/exclude predicates against resolved feature vector.
- Decision matrix:
  - enrolled + fails criteria -> `INCLUSION_ERROR`
  - eligible + not enrolled -> `EXCLUSION_ERROR`
  - eligible + enrolled -> `VALID_ENROLLMENT`
  - not eligible + not enrolled -> `NOT_APPLICABLE`
- `REVIEW_REQUIRED` only when critical required features are missing/unusable.
- Deliverables:
  - Deterministic evaluator with explainable outputs.
  - Field-level pass/fail checks persisted per decision.

## Phase 5: Explainability + Reason Quality
- Add reason templates with explicit failures/passes.
- Example reason outputs:
  - Inclusion: enrolled in S767 but failed `age <= 58` (actual 72).
  - Exclusion: eligible (passed age/employment/service checks) but not enrolled in target scheme.
- Deliverables:
  - Human-readable reason builder.
  - API response includes compact explainability payload.

## Phase 6: UI Enhancements (Eligibility Studio)
- Show extracted canonical rule fields and mapping status.
- Show field evidence snippets from document.
- Show pre-run data coverage warning (e.g., `% citizens with service_months`).
- Decision table gets “Why” details panel with failed/passed checks.
- Deliverables:
  - Cleaner extraction/result UX.
  - Better operator trust and triage.

## Phase 7: Quality Gates & Tests
- Unit tests:
  - Schema validation.
  - Extracted field normalization.
  - Decision matrix and reason generation.
- Integration tests:
  - Upload PDF -> extract rule -> evaluate citizens end-to-end.
  - Multi-table resolver correctness.
- Deliverables:
  - CI-ready test suite.
  - Regression coverage for S767 + additional scheme samples (e.g., S051).

## Phase 8: Rollout Strategy
- Stage A: Dry-run mode (compute only, no persistence).
- Stage B: Persist decisions and expose analytics.
- Stage C: Tune prompts/schema mappings based on observed `unmapped_criteria`.
- Deliverables:
  - Safe rollout with measurable checkpoints.

## Success Metrics
- `REVIEW_REQUIRED` appears only for true missing-data or truly unmapped policy criteria.
- Deterministic decisions available for most citizens where required data exists.
- Every `INCLUSION_ERROR` and `EXCLUSION_ERROR` has explicit machine-checkable reason text.

## Execution Order (Recommended)
1. Phase 1
2. Phase 2
3. Phase 3
4. Phase 4
5. Phase 5
6. Phase 6
7. Phase 7
8. Phase 8
