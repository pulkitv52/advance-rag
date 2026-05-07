# Advance-Rag

Advance-Rag is a full-stack intelligence platform that combines document RAG, a Neo4j knowledge graph, a Unified Social Registry fraud-intelligence workflow, and policy-based eligibility evaluation.

In simple terms, the system does two big jobs:

- it lets users upload documents and ask grounded research questions over them
- it turns structured welfare registry data into a connected graph for fraud detection, explainability, and audit prioritization

## What This Project Solves

Most systems handle these problems separately:

- document search lives in one tool
- fraud review lives in dashboards and spreadsheets
- policy eligibility logic lives in PDFs and manual interpretation

Advance-Rag brings them together into one application so teams can:

- ingest documents and query them with citations
- build a document graph from extracted entities and relationships
- sync social-registry data into a fraud-intelligence graph
- detect duplicate, ghost, and anomaly patterns across connected records
- extract eligibility criteria from policy documents
- evaluate citizens against structured inclusion and exclusion rules

## Main Product Areas

- `Research Chat`
  Grounded Q&A over uploaded documents using chunking, embeddings, reranking, and answer generation.

- `Knowledge Map`
  Graph visualization over both document-extracted entities and the USR fraud-intelligence graph.

- `Social Registry Dashboard`
  Registry-wide fraud, anomaly, risk, audit, and operator-intelligence views.

- `Eligibility Studio`
  PDF-to-rule extraction plus citizen-level eligibility evaluation.

## High-Level Architecture

```mermaid
flowchart LR
  subgraph UI[Frontend]
    F1[Research Chat]
    F2[Knowledge Map]
    F3[Social Registry Dashboard]
    F4[Eligibility Studio]
  end

  subgraph API[FastAPI Backend]
    B1[Document APIs]
    B2[Query APIs]
    B3[USR APIs]
    B4[Eligibility APIs]
  end

  subgraph AI[AI Services]
    A1[NVIDIA NIM Parser]
    A2[NVIDIA Embeddings]
    A3[NVIDIA Reranker]
    A4[NVIDIA LLM]
  end

  subgraph Data[Data Layer]
    D1[(Postgres)]
    D2[(Qdrant)]
    D3[(Neo4j)]
    D4[(Minio)]
    D5[(Redis)]
  end

  F1 --> B2
  F2 --> B1
  F2 --> B3
  F3 --> B3
  F4 --> B4

  B1 --> A1
  B1 --> A2
  B1 --> D2
  B1 --> D3
  B1 --> D4

  B2 --> A3
  B2 --> A4
  B2 --> D2
  B2 --> D3

  B3 --> D1
  B3 --> D3

  B4 --> A4
  B4 --> D1

  API --> D5
```

## Two Core Pipelines

This repo has two different but connected intelligence pipelines.

### 1. Document Research Pipeline

Used when a user uploads PDFs or other supported files and asks research questions.

```mermaid
flowchart LR
  U1[Upload Document] --> P1[Parse Document]
  P1 --> P2[Extract Elements and Chunks]
  P2 --> P3[Create Embeddings]
  P3 --> Q1[Store in Qdrant]
  P2 --> G1[Extract Entity Triplets]
  G1 --> G2[Store Document Graph in Neo4j]
  Q1 --> R1[Retrieve Relevant Chunks]
  G2 --> R2[Retrieve Graph Context]
  R1 --> A1[Generate Grounded Answer]
  R2 --> A1
```

### 2. Unified Social Registry Fraud-Intelligence Pipeline

Used when social-registry data is synced from a configured registry source into Neo4j.

```mermaid
flowchart LR
  S1[Registry Source Tables] --> S2[Graph Sync Service]
  S2 --> S3[Citizen Nodes by uid]
  S2 --> S4[Geography and Scheme Links]
  S2 --> S5[Identity Hubs<br/>Ration Card, Mobile, Address, Operator]
  S3 --> F1[Fraud Edge Creation]
  S4 --> F1
  S5 --> F1
  F1 --> F2[POTENTIAL_DUPLICATE]
  F1 --> F3[SAME_DOB_AT_GP]
  F1 --> F4[FLAGGED_AS]
  F1 --> F5[HIGH_RISK_CLUSTER]
  F2 --> O1[Social Registry Dashboard]
  F3 --> O1
  F4 --> O1
  F5 --> O1
  F2 --> O2[Knowledge Map]
  F3 --> O2
  F4 --> O2
```

## Tech Stack

- Backend: Python, FastAPI, SQLModel, asyncpg, uv
- Frontend: React, TypeScript, Vite, shadcn/ui, pnpm
- Databases: Postgres, Qdrant, Neo4j, Redis
- Object storage: Minio
- AI stack: NVIDIA NIM parser, embeddings, reranker, and LLM models
- Infra: Docker Compose

## Repository Layout

```text
backend/     FastAPI app, services, routers, tests, utility scripts
frontend/    React/Vite application
docs/        Architecture, graph, and product documentation
logs/        Local runtime logs
plan/        Design notes and execution plans
docker-compose.yml
Makefile
.env.example
```

## Important Data Concepts

### Document Knowledge Graph

The document graph is built from entity triplets extracted from uploaded documents.

- nodes are generic entities like `Person`, `Organization`, `Location`, `Event`, `Concept`
- edges are stored as `:RELATED`
- this graph helps multi-hop RAG and visual knowledge exploration

### USR Fraud-Intelligence Graph

The registry graph is built from structured citizen data and modeled around:

- `Citizen`
- `District`
- `Block`
- `GP`
- `Scheme`
- `RationCard`
- `Mobile`
- `Address`
- `Operator`
- `FraudFlag`

Key relationships include:

- `RESIDES_IN`
- `PART_OF`
- `ENROLLED_IN`
- `MEMBER_OF`
- `HAS_MOBILE`
- `REGISTERED_BY`
- `LIVES_AT`
- `POTENTIAL_DUPLICATE`
- `SAME_DOB_AT_GP`
- `FLAGGED_AS`
- `HIGH_RISK_CLUSTER`

## Identity and De-duplication Model

The current system treats `uid` as the canonical citizen key during graph sync.

- one `Citizen` node is created per `uid`
- repeated source rows with the same `uid` merge into the same graph citizen
- different `uid` values are not auto-merged into one citizen node

Instead, suspicious duplication is represented as graph evidence:

- `POTENTIAL_DUPLICATE`
  created for suspicious duplicate pairs

- `SAME_DOB_AT_GP`
  created for same-DOB cluster behavior at the GP level

- `FLAGGED_AS`
  used for ghost, anomaly, and data-quality flags

This is important: the graph preserves traceability. It flags suspicious identity overlap instead of silently collapsing people together.

## Eligibility Workflow

Eligibility Studio supports a policy-to-decision flow:

1. upload a scheme document
2. parse and extract eligibility metadata
3. store inclusion and exclusion conditions
4. evaluate registry citizens against those rules
5. mark outcomes such as eligible, ineligible, or review required

This gives the project both intelligence and actionability:

- the graph explains suspicious cases
- the eligibility engine explains benefit decisions

## Local Development Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- Docker + Docker Compose
- `uv`
- `pnpm`
- NVIDIA NIM API key

### Environment

Copy the template:

```bash
cp .env.example .env
```

Then fill in required values, especially:

- `NVIDIA_API_KEY`
- any password overrides you want for local infra
- port overrides if your machine is already using defaults

Note:

- root `.env` is for the main local app stack
- `frontend/.env` can be used for frontend-specific overrides when needed

## Running the Project

### Install Dependencies

```bash
make setup
```

### Start Infrastructure Only

```bash
make up
```

### Start the Main Local Development Stack

```bash
make start
```

### Stop Everything

```bash
make stop
```

## Common Commands

Infrastructure:

```bash
make up
make down
make nuke
make ps
make health
```

Backend:

```bash
make backend-setup
make backend-start
make backend-stop
make logs-backend
```

Frontend:

```bash
make frontend-setup
make frontend-start
make frontend-stop
make frontend-preview
make logs-frontend
```

Full app:

```bash
make setup
make start
make stop
make restart
make logs
```

## Default Local Endpoints

In the current Makefile-based local flow:

- Frontend: `http://127.0.0.1:5177`
- Backend API: `http://127.0.0.1:8081`
- Backend OpenAPI docs: `http://127.0.0.1:8081/docs`
- Neo4j Browser: `http://127.0.0.1:7474`
- Minio Console: `http://127.0.0.1:9091`
- Qdrant: `http://127.0.0.1:6343`
- Postgres: `127.0.0.1:5434`

## Key Backend Areas

- `backend/src/routers/documents.py`
  document upload, graph retrieval, deletion

- `backend/src/routers/query.py`
  research query flow and graph-enriched answering

- `backend/src/routers/usr.py`
  social-registry APIs, graph stats, audit and fraud endpoints

- `backend/src/routers/eligibility.py`
  rule extraction and eligibility evaluation APIs

- `backend/src/services/graph_sync.py`
  registry-to-Neo4j sync plus fraud-edge creation

- `backend/src/services/graph_db.py`
  graph retrieval, graph context search, and citizen graph snapshots

- `backend/src/services/eligibility.py`
  extracted-rule interpretation and decision logic

## Key Frontend Areas

- `frontend/src/App.tsx`
  main workspace shell, research chat, knowledge map

- `frontend/src/components/UsrDashboard.tsx`
  fraud-intelligence and audit dashboard

- `frontend/src/components/EligibilityStudio.tsx`
  eligibility workflow UI

## Testing and Validation

Backend tests:

```bash
cd backend
uv run pytest -s
```

Frontend production build:

```bash
cd frontend
pnpm build
```

Backend formatting:

```bash
cd backend
uv run black src tests
uv run isort src tests
```

## Documentation

Useful deeper references in [`docs/`](/home/pulkitv52/Advance-rag/docs):

- [MASTER_PIPELINE_FLOW_DIAGRAM.md](/home/pulkitv52/Advance-rag/docs/MASTER_PIPELINE_FLOW_DIAGRAM.md)
- [KNOWLEDGE_GRAPH_GUIDE.md](/home/pulkitv52/Advance-rag/docs/KNOWLEDGE_GRAPH_GUIDE.md)
- [KG_FRAUD_INTELLIGENCE_PRESENTATION_GUIDE.md](/home/pulkitv52/Advance-rag/docs/KG_FRAUD_INTELLIGENCE_PRESENTATION_GUIDE.md)
- [USE_CASE_3_LAYMAN_BRIEF.md](/home/pulkitv52/Advance-rag/docs/USE_CASE_3_LAYMAN_BRIEF.md)

## Current Reality

This repo is not just a generic RAG app.

It is a combined platform for:

- document intelligence
- graph intelligence
- fraud detection support
- explainability
- eligibility automation

That combination is what makes Advance-Rag valuable, and the README should help a new engineer or reviewer understand that quickly.
