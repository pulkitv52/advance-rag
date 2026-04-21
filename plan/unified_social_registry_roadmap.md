# Roadmap: Unified Social Registry (USR) Platform

This roadmap outlines the journey from a single database dump to a production-grade, federated Social Registry powered by AI and Graph RAG.

---

## 🟢 Phase 1: The Foundation (Current)
**Goal:** Transform raw data into an accessible "Intelligent Service."
1.  **Data Restoration:** Move `srsdb.dump` into a live, partitioned PostgreSQL instance.
2.  **MCP Server Implementation:** Create the "Translator" layer. This allows the AI to query the database using standardized tools (e.g., `get_citizen_360`).
3.  **Schema Mapping:** Use LLM to document the semantic meaning of every column in the Swasthya Sathi database.

## 🔵 Phase 2: Identity Resolution & Knowledge Graph
**Goal:** Connect the dots between different departments and resolve duplicate identities.
1.  **Entity Resolution (De-duplication):** Implement an AI pipeline to find duplicate beneficiaries across partitions (e.g., matching by masked mobile, address, and name).
2.  **Graph Linking:** Link Postgres records to your **Neo4j Knowledge Graph**. 
    *   *Result:* You can now query: *"Show me the family tree of this beneficiary and their combined claim history."*

## 🟡 Phase 3: AI/ML Intelligence Engines
**Goal:** Move from "Querying" to "Predicting" and "Analyzing."
1.  **Dynamic Eligibility Engine:** An AI model that checks complex, multi-scheme rules in real-time using Graph RAG.
2.  **Vulnerability Segmentation:** Use unsupervised learning (K-Means/Community Detection) to segment the population by risk scores (e.g., "High Risk of Health Crisis" based on age and transaction frequency).
3.  **Fraud & Anomaly Detection:** Deploy graph-based fraud analytics to detect "Ghost Beneficiaries" or "Clumped Claims" at specific hospitals.

## 🟣 Phase 4: Geo-Spatial & Last-Mile targeting
**Goal:** Visualize the "Underserved" gaps.
1.  **GIS Integration:** Map your `lgd_block_code` data onto a real map using OpenStreetMap/Mapbox.
2.  **Hyper-Local Targeting:** Use AI to identify "Ecologically Vulnerable" areas where beneficiary coverage is lower than the village average.

## 🟠 Phase 5: Federated Scale (Production Hardening)
**Goal:** Prepare for multi-departmental use.
1.  **Federated MCP Gateway:** Add a second "Mock" department (e.g., Dept of Education) to demonstrate how the USR can fetch data from two MCP servers without merging DBs.
2.  **Anonymization & Security:** Implement a robust PII-masking layer so specific names never reach the LLM provider, only the analyzed insights.
3.  **Production UI:** Build an "Executive Dashboard" in your NextJS frontend that shows real-time social registry insights.

---

### Why this plan wins:
- **Scalable:** It uses the **Model Context Protocol (MCP)**, meaning we can add 100 departments later without changing the core.
- **Explainable:** Every AI decision (e.g., "Ineligible") is backed by a path in the **Knowledge Graph**.
- **Secure:** It respects **Decentralized Ownership**—departments keep their data; we just provide the intelligence layer.
