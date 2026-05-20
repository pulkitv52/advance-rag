<div align="center">
  <img src="assets/banner.png" alt="Advance-Rag Banner" width="100%">

  # 🚀 Advance-Rag

  **Full-stack Intelligence Platform combining Document RAG, Neo4j Knowledge Graphs, and Fraud-Intelligence Workflows.**

  [![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
  [![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
  [![NVIDIA NIM](https://img.shields.io/badge/AI-NVIDIA%20NIM-green.svg)](https://www.nvidia.com/en-us/ai-data-science/generative-ai/nim/)
  [![Neo4j](https://img.shields.io/badge/Graph-Neo4j-008CC1.svg)](https://neo4j.com/)

  [Features](#-key-features) • [Architecture](#-architecture) • [Quick Start](#-quick-start) • [Documentation](#-documentation)
</div>

---

## 📖 Overview

Advance-Rag is not just another RAG application. It is a unified platform designed to solve complex intelligence problems by bridging the gap between **unstructured documents** and **structured registry data**.

> [!IMPORTANT]
> The system enables teams to ask grounded research questions over PDFs while simultaneously detecting fraud patterns, ghosts, and anomalies in connected citizen records.

---

## ✨ Key Features

| Feature | Description | Tech |
| :--- | :--- | :--- |
| **🔍 Research Chat** | Grounded Q&A with precise citations over uploaded document sets. | Qdrant, NVIDIA NIM |
| **🕸️ Knowledge Map** | Visual exploration of document entities and registry relationships. | Neo4j, React-Force-Graph |
| **📊 Social Registry** | Dashboard for fraud detection, audit prioritization, and risk clusters. | Postgres, FastAPI |
| **⚖️ Eligibility Studio** | Automated extraction of policy rules and citizen evaluation. | LLM, Document Parsing |

---

## 🖼️ Platform Preview

<div align="center">
  <img src="assets/dashboard_preview.png" alt="Advance-Rag Dashboard Preview" width="100%">
  <p><i>A unified view of Knowledge Graphs and Document Intelligence</i></p>
</div>

---

## 🏗️ Architecture

The platform follows a modern microservices architecture powered by the NVIDIA AI stack.

```mermaid
flowchart TB
  subgraph UI[Frontend - React/Vite]
    F1[Research Chat]
    F2[Knowledge Map]
    F3[Social Registry]
    F4[Eligibility Studio]
  end

  subgraph API[Backend - FastAPI]
    B1[Document Engine]
    B2[Query Engine]
    B3[Graph Sync Service]
    B4[Eligibility Engine]
  end

  subgraph AI[AI Stack - NVIDIA NIM]
    A1[Parser]
    A2[Embeddings]
    A3[Reranker]
    A4[LLM]
  end

  subgraph Data[Data Layer]
    D1[(Postgres)]
    D2[(Qdrant)]
    D3[(Neo4j)]
    D4[(Minio)]
    D5[(Redis)]
  end

  F1 & F2 & F3 & F4 --> API
  B1 & B2 & B4 --> AI
  B1 & B2 & B3 & B4 --> Data
  API --> D5
```

---

## 🚀 Quick Start

<details>
<summary><b>1. Prerequisites</b></summary>

- Python 3.12+ & `uv`
- Node.js 18+ & `pnpm`
- Docker + Docker Compose
- NVIDIA NIM API Key ([NemoRetriever OCR](https://build.nvidia.com/nvidia/nemoretriever-ocr-v1))
</details>

<details>
<summary><b>2. Environment Setup</b></summary>

```bash
# Copy template
cp .env.example .env

# Configure your keys in .env
# NVIDIA_API_KEY=your_key_here
```
</details>

<details>
<summary><b>3. Launching the App</b></summary>

```bash
# Install everything
make setup

# Start the full stack
make start
```
</details>

### 🌐 Default Endpoints

- **Frontend**: [http://localhost:5177](http://localhost:5177)
- **API Docs**: [http://localhost:8081/docs](http://localhost:8081/docs)
- **Neo4j Console**: [http://localhost:7474](http://localhost:7474)

---

## 🛠️ Project Structure

```text
├── backend/          # FastAPI, UV, SQLModel
├── frontend/         # React, Vite, shadcn/ui
├── docs/             # Technical deep-dives
├── assets/           # Visual media and banners
└── infra/            # Docker configurations
```

---

## 📚 Documentation

Deep dive into the core mechanics:

- 📑 [Master Pipeline Flow](docs/MASTER_PIPELINE_FLOW_DIAGRAM.md)
- 🕸️ [Knowledge Graph Guide](docs/KNOWLEDGE_GRAPH_GUIDE.md)
- 🎯 [Fraud Intelligence Presentation](docs/KG_FRAUD_INTELLIGENCE_PRESENTATION_GUIDE.md)
- 📝 [Eligibility Layman Brief](docs/USE_CASE_3_LAYMAN_BRIEF.md)
- 🗃️ [Database Curation](docs/DATABASE_CURATION.md)

---

<div align="center">
  <p>Built for scale and intelligence. Optimized for NVIDIA NIM.</p>
</div>
