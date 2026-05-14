# Advance RAG System Architecture & Pipelines

This document outlines the end-to-end pipelines, database strategies, and technical mechanisms utilized across the four primary pillars of the Advance RAG system: **Research Chat**, **Knowledge Graph**, **Eligibility Evaluation**, and **Social Registry Intelligence**.

---

## 1. Research Chat Pipeline
The Research Chat pipeline provides highly accurate, context-aware RAG (Retrieval-Augmented Generation) across unstructured policy documents and uploaded datasets.

### Strategy & Flow
1. **Document Ingestion & Parsing:**
   - PDFs and visual documents are routed to **PyMuPDF** for direct text extraction. If the text density is low (e.g., scanned images), it falls back to **NVIDIA NeMo Retriever Parse NIM**, which performs layout-aware OCR.
   - Structured files (Excel, Word) are parsed and explicitly converted to Markdown tables to preserve table context for the LLM.
2. **Vectorization:**
   - Parsed chunks are sent to the **NVIDIA Embedding API** (`nv-embedqa-e5-v5`) using the `passage` input type.
3. **Vector Storage:**
   - The embedded chunks are upserted into **Qdrant**, which acts as the core vector database for semantic similarity searches.
4. **Retrieval & Reranking:**
   - User queries are embedded (using the `query` input type) and searched against Qdrant.
   - The top candidate chunks are passed to the **NVIDIA Reranker NIM** (`nv-rerankqa-mistral-4b-v3`), which adjusts their relevance scores using relative normalization (mapped from 50% to 95%).
5. **Generation:**
   - The highest-ranked chunks are passed as context to the **NVIDIA NIM LLM** (e.g., Llama 3) along with a strictly formatted system prompt (McKinsey/KPMG style analysis) to synthesize a highly objective and cited response.

### Databases Used
* **Qdrant:** Semantic chunk storage.
* **MinIO:** S3-compatible raw document and object storage.

---

## 2. Knowledge Graph Pipeline
The Knowledge Graph builds a multi-hop, highly connected entity map for visual fraud investigation and relational analysis.

### Strategy & Flow
1. **Document Information Extraction:**
   - The system extracts Subject-Predicate-Object triplets from unstructured text. 
   - These are pushed as nodes (`:Entity`) and edges (`:RELATED`) into the graph.
2. **Social Registry Graph (Primary Intelligence):**
   - The graph models the physical and systemic reality of a region. It builds geographic hierarchies (`District -> Block -> GP`) and maps `Citizen` nodes to their location (`:RESIDES_IN`).
   - **Fraud Representation:** High-risk citizens or those caught by validation rules are linked to `:FraudFlag` nodes (`:FLAGGED_AS`), or linked to other citizens via `:POTENTIAL_DUPLICATE` edges.
3. **Multi-Hop Context Generation:**
   - The backend runs a `UNION` Cypher query to simultaneously extract 1-hop neighbor contexts and 2-hop relational bridges. This ensures that the RAG LLM is aware if "Citizen A is linked to Citizen B through Operator C", which a standard vector database might miss.

### Databases Used
* **Neo4j:** Native graph database storing all entities, hierarchies, and relational paths. Cypher queries are heavily used for entity resolution and sub-graph extraction.

---

## 3. Eligibility Evaluation Pipeline
This engine transforms verbose legal text from government gazettes into strictly executable JSON rule schemas to evaluate citizen inclusion and exclusion automatically.

### Strategy & Techniques
1. **Two-Stage Rule Extraction:**
   - **Stage 1 (Intent Analysis):** Document text is scanned using heuristic Regex parsers and lightweight LLM classification to detect if the text actually contains eligibility criteria (e.g., detecting keywords like "must be between", "annual income below").
   - **Stage 2 (Deep Structured Extraction):** The relevant text chunks (`[HEAD]`, `[MIDDLE]`, `[TAIL]`) are sent to the **NVIDIA NIM LLM** using a highly constrained, few-shot prompt. This forces the LLM to output a strict JSON schema containing `include_conditions` and `exclude_conditions`.
2. **Dynamic Schema Learning (Self-Healing Rules):**
   - The system maps known variables like `age`, `income`, `employment_status`, `ida_covered_required`, `caste_allowed`, and `conflict_schemes`. 
   - When the LLM finds conditions that the backend doesn't currently support in the SQL schema (e.g., "Must have a BPL card"), it adds them to an `unmapped_criteria` list.
   - A self-learning loop tracks these unmapped fields in Postgres. If an unmapped field occurs frequently across multiple documents (e.g., occurrence threshold = 3), it is "auto-promoted" to an `ACTIVE` status in the schema vocabulary, alerting engineers to add the database column.
   - Certain generic tags like "eligibility" and "exclusion" are safely ignored using a `non_blocking_unmapped` list to prevent false-positive manual review requests.
3. **Deterministic Citizen Evaluation (The Decision Engine):**
   - The engine runs a strict ruleset comparing millions of citizen database rows against the extracted JSON thresholds.
   - It outputs one of four decisive statuses:
     - `VALID_ENROLLMENT`: Citizen meets all inclusion rules and violates no exclusion rules.
     - `INCLUSION_ERROR`: Citizen is enrolled but fails an inclusion rule or triggers an exclusion rule (Fraud/Ghost).
     - `EXCLUSION_ERROR`: Citizen is NOT enrolled but fully meets the criteria (Systemic Gap).
     - `REVIEW_REQUIRED`: The document contained blocking unmapped criteria, or the citizen is missing critical data points, mandating human audit.

### Databases Used
* **PostgreSQL (via SQLModel):** The core relational database managing the rule engine.
  - `EligibilityRule`: Stores the structured JSON rules linked to specific schemes and documents.
  - `EligibilitySchemaSignal`: Tracks the frequency of unmapped criteria for the self-learning vocabulary loop.
  - `Citizen Registry Tables`: The actual citizen data rows (e.g., Swasthya Sathi beneficiaries) evaluated against the rules.

---

## 4. Social Registry Intelligence Pipeline
This pipeline bridges structured tabular databases and unstructured AI by converting standard row-data into "Citizen Profiles" that the LLM can read and reason over.

### Strategy & Flow
1. **Tabular Ingestion:**
   - Reads directly from the `swasthya_sathi_beneficiary` (or related registry) tables in Postgres using high-speed `asyncpg`.
2. **Profile Text Synthesis:**
   - Each tabular row is serialized into a highly dense "Citizen Profile" text chunk. 
   - *Example Format:* "Citizen Profile: Pramila Das. UID: 1234. Location: GP X. System Flags: Duplicate Alert, High Risk..."
3. **Bulk Vectorization:**
   - These textual profiles are chunked in batches of 100, embedded using NVIDIA API, and stored in Qdrant with a dedicated virtual document ID (`USR_DUMP_001`).
4. **Hybrid RAG Usage:**
   - When a user asks a question like "Are there any ghost citizens in GP Rampur?", the system retrieves these exact profiles from Qdrant, allowing the Chat LLM to read the tabular data as if it were unstructured text.

### Databases Used
* **PostgreSQL (Unified Social Registry DB):** The source of truth for citizen and demographic data.
* **Qdrant:** Stores the vectorized string representations of the SQL rows for RAG.
* **Neo4j:** Parallel indexing for the same citizens to allow geographic clustering and visual layout.
