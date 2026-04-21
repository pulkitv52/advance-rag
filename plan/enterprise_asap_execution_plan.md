# Enterprise ASAP Execution Plan

## Objective

Turn Advance-Rag from a strong prototype into an enterprise-grade research platform that can credibly serve consulting, banking, and advisory workflows.

This plan is intentionally impact-first, not timeline-first. The goal is to prioritize what materially improves trust, usability, defensibility, and enterprise perception as fast as possible.

## Product North Star

The platform should feel like a research operating system for high-stakes teams. A user should be able to:

- create a project workspace
- upload and organize documents by project
- ask questions and get defensible answers
- inspect evidence, confidence, and source support
- save analyses and reopen them later
- generate polished client-ready reports
- compare multiple documents and detect contradictions
- use the knowledge graph as an explainable investigation tool
- collaborate with teammates
- operate with basic access control and auditability

## Build Order

The implementation order below is strict by value and urgency.

### 1. Saved Analyses And Report Persistence

Reason:
Without persistence, the product still feels like a session demo instead of an enterprise system.

Deliver:

- save analysis records in Postgres
- save generated reports in MinIO
- list past analyses
- reopen a saved analysis
- list report history for an analysis
- download previous reports from history

Backend:

- add `Analysis` model
- add `Report` model
- add `analysis.py` router
- add `report_store.py` service

Frontend:

- add save analysis action
- add analysis history panel
- add report history section

Suggested schema:

- `analyses`
  - `id`
  - `project_id`
  - `query`
  - `answer`
  - `confidence_score`
  - `citation_coverage`
  - `created_at`
- `reports`
  - `id`
  - `analysis_id`
  - `format`
  - `storage_key`
  - `created_at`

APIs:

- `POST /analyses`
- `GET /analyses`
- `GET /analyses/{id}`
- `GET /analyses/{id}/reports`
- `GET /reports/{id}/download`

Definition of done:

- a user can save an answer
- a user can revisit a previous analysis
- a generated report is available later without regenerating it

### 2. Project Workspaces

Reason:
Enterprise users think in engagements, deals, studies, or cases, not loose files.

Deliver:

- create project
- attach documents to project
- view project-scoped analyses
- project dashboard
- active project context in UI

Backend:

- add `Project` model
- add `project_documents` mapping
- add project-aware filtering to analysis and graph endpoints

Frontend:

- add project selector
- add project create dialog
- add project dashboard
- make uploads project-aware

Suggested schema:

- `projects`
  - `id`
  - `name`
  - `description`
  - `created_at`
- `project_documents`
  - `project_id`
  - `document_id`

APIs:

- `POST /projects`
- `GET /projects`
- `GET /projects/{id}`
- `POST /projects/{id}/documents`
- `GET /projects/{id}/analyses`

Definition of done:

- every upload and analysis can belong to a project
- user can switch context between projects cleanly

### 3. Trust Signals In Answering

Reason:
This is one of the most important enterprise differentiators. Buyers care less about AI magic and more about whether output is defensible.

Deliver:

- confidence score
- citation coverage score
- evidence strength indicator
- weak support warning
- graph enrichment indicator
- answer-to-source linking

Backend:

- add `confidence.py` service
- compute answer metadata after generation
- return structured evidence support in query response

Frontend:

- confidence badge
- citation coverage badge
- expandable evidence inspector
- section-level source mapping

API response additions:

- `confidence_score`
- `citation_coverage`
- `supporting_sources`
- `weak_claims`
- `graph_enrichment_used`

Definition of done:

- answers are no longer just text
- users can quickly understand how trustworthy an answer is

### 4. Executive-Grade Export System

Reason:
The app must produce outputs that can move into client, board, investment, or audit workflows.

Deliver:

- multiple export templates
- improved PDF report structure
- report type selector
- executive summary template
- due diligence brief template
- risk memo template
- source appendix
- report metadata and branding

Backend:

- extend `reporting.py`
- create report template selection
- persist report metadata

Frontend:

- export modal
- template selector
- report preview metadata

Export types:

- Executive Summary
- Due Diligence Brief
- Risk Memo
- Research Synthesis

Definition of done:

- user can generate different report styles from the same analysis
- reports feel presentation-ready and reusable

### 5. Structured Document Intelligence

Reason:
This pushes the product from question answering into real enterprise document analysis.

Deliver:

- key entities extraction
- dates and timeline extraction
- obligations extraction
- risk extraction
- KPI and amount extraction
- table summaries

Backend:

- add `intelligence.py` service
- store extracted facts for documents
- run extraction at ingestion or on demand

Frontend:

- intelligence panel per document
- cards for risks, dates, KPIs, obligations
- timeline view

Suggested schema:

- `document_entities`
- `document_risks`
- `document_obligations`
- `document_dates`
- `document_metrics`

APIs:

- `GET /documents/{id}/intelligence`
- `GET /documents/{id}/timeline`

Definition of done:

- every important document can expose structured business intelligence beyond plain text chunks

### 6. Knowledge Graph Provenance And Filtering

Reason:
The graph is already visually useful, but enterprise users need provenance and explainability.

Deliver:

- source references per node
- source references per edge
- confidence score per edge
- node details drawer
- graph filters by type, source, and confidence
- graph search

Backend:

- enrich graph records with provenance metadata
- expose node and edge detail endpoints

Frontend:

- right-side graph details drawer
- filter chips
- search bar for nodes
- evidence panel for selected node/edge

Graph model additions:

- `document_ids`
- `chunk_refs`
- `confidence`
- `created_at`

APIs:

- `GET /graph/node/{id}`
- `GET /graph/edge/{id}`
- `GET /graph/search`

Definition of done:

- users can click a graph node and understand exactly why it exists

### 7. Cross-Document Compare

Reason:
This is a premium workflow for consulting, legal review, due diligence, and financial research.

Deliver:

- compare two or more documents
- overlapping themes
- contradictions
- unique findings
- summary diff

Backend:

- add `compare.py` service
- use chunk retrieval plus structured diff logic

Frontend:

- compare mode
- document picker
- sections for common findings, differences, contradictions

APIs:

- `POST /compare`

Definition of done:

- users can compare multiple selected documents in one workflow

### 8. Collaboration Basics

Reason:
This helps the product feel like a team platform rather than a solo tool.

Deliver:

- comments on analyses
- pinned findings
- saved prompts/templates
- mark analysis as important

Backend:

- add `comments.py` and `findings.py`
- store reusable prompt templates

Frontend:

- comment thread on analysis
- pin finding button
- saved prompt picker

Suggested schema:

- `analysis_comments`
- `saved_findings`
- `saved_prompts`

Definition of done:

- teammates can leave context around analyses instead of copying text elsewhere

### 9. Basic Auth And Audit Logs

Reason:
This is the minimum governance layer needed for enterprise credibility.

Deliver:

- login
- user model
- role field
- audit log for uploads, queries, exports, deletes

Backend:

- add `auth.py`
- add `audit.py`
- log user actions in critical endpoints

Frontend:

- login page
- session-aware top bar
- admin audit screen

Suggested schema:

- `users`
- `audit_logs`

Definition of done:

- system actions are attributable to users
- export activity and deletions are traceable

### 10. Background Tasks And Reliability Layer

Reason:
As features grow, ingestion and report generation need better reliability.

Deliver:

- Redis-backed task queue
- async report generation
- retry support
- task status tracking
- better progress feedback

Backend:

- add `tasks.py`
- move expensive work into background tasks

Frontend:

- task center
- progress states
- retry action for failures

Suggested schema:

- `tasks`
  - `id`
  - `type`
  - `status`
  - `payload`
  - `result_ref`
  - `created_at`

Definition of done:

- long-running actions no longer block request/response flow

## Must-Build-Now Scope

If the goal is to move as fast as possible while still transforming the product, only focus on these first:

1. saved analyses
2. saved report history
3. project workspaces
4. confidence and citation metadata
5. export templates
6. document intelligence panels
7. graph provenance
8. cross-document compare

These features create the biggest jump in enterprise value.

## Features To Delay

To avoid losing momentum, do not prioritize these yet:

- SSO/SAML
- SharePoint, Slack, and Confluence integrations
- PowerPoint generation
- multi-tenant billing
- deep observability dashboards
- advanced evaluation harness
- complex multi-agent orchestration

## Backend Implementation Order

Build in this sequence:

1. models for projects, analyses, reports
2. save/load analysis APIs
3. report persistence APIs
4. query response metadata for confidence/evidence
5. project-scoped uploads and filtering
6. intelligence extraction endpoints
7. graph provenance endpoints
8. compare endpoint
9. comments/findings
10. auth and audit logs

## Frontend Implementation Order

Build in this sequence:

1. split current `App.tsx` into modular components
2. add project context UI
3. add analysis history and report history
4. add trust metadata cards in result view
5. add export modal and template selector
6. add intelligence panel
7. add graph details drawer
8. add compare view
9. add comments and pinned findings
10. add login and audit views

## Repo Changes Needed

Backend:

- add new routers under `backend/src/routers`
- add services under `backend/src/services`
- add new SQLModel tables under `backend/src/models`
- add tests for every new route/service

Frontend:

- break `frontend/src/App.tsx` into domain components
- add project, reports, graph, and analysis components
- add route-level organization if needed

Infra:

- extend `.env.example`
- update `docker-compose.yml` if worker service is introduced
- update `Makefile` for worker and new test commands

## Quality Bar

Every feature added under this plan must include:

- backend tests
- frontend verification path
- type-safe models
- error states
- user-facing loading states
- wiki or plan documentation updates

## Immediate Next Build Recommendation

Start here in the repo:

1. add `Project`, `Analysis`, and `Report` models
2. add save/list/get analysis APIs
3. add report persistence after PDF generation
4. add project-aware UI shell
5. add confidence/citation metadata in query responses

This is the fastest path from prototype to enterprise-grade product behavior.
