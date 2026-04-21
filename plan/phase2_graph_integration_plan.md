# Phase 2: Identity Resolution & Knowledge Graph Integration

This plan focuses on linking the **PostgreSQL (Structured)** social registry data with the **Neo4j (Relational)** Knowledge Graph to enable cross-departmental intelligence and de-duplication.

## 1. Graph Schema Design
We will introduce new node labels and relationships to represents the Social Registry:

- **Labels:**
    - `Citizen`: Properties: `uid`, `beneficiary_id`, `name`, `gender`, `dob`, `mobile_masked`.
    - `Scheme`: e.g., "Swasthya Sathi".
    - `Location`: Hierarchical nodes for District, Block, and GP.
- **Relationships:**
    - `(:Citizen)-[:ENROLLED_IN]->(:Scheme)`
    - `(:Citizen)-[:RESIDES_IN]->(:Location)`
    - `(:Location)-[:PART_OF]->(:Location)` (Parent child for GP -> Block -> District).

## 2. Identity Resolution Logic
To prevent duplicate identities:
- **UID Match:** Primary key for merging nodes.
- **Fuzzy Match:** A fallback for records without UID, comparing `name` + `dob` + `mobile`.

## 3. Implementation Steps
1. **[NEW] [graph_sync.py](file:///wsl.localhost/Ubuntu/home/pulkitv52/Advance-rag/backend/src/services/graph_sync.py):**
   - Implement `sync_initial_batch(limit=5000)`: Fetches from SQL and MERGEs into Neo4j.
   - Implement `associate_with_docs()`: Finds mentions of citizen names in uploaded PDF documents.
2. **[MODIFY] [graph_db.py](file:///wsl.localhost/Ubuntu/home/pulkitv52/Advance-rag/backend/src/services/graph_db.py):**
   - Add labels for specialized nodes to the visualization logic.

## 4. Verification Plan
1. **Counts:** Run `MATCH (n:Citizen) RETURN count(n)` in Neo4j.
2. **Connectivity:** Ensure `(:Citizen)-[:RESIDES_IN]->(:Location)` exists.
3. **UI:** Verify "Citizen" nodes appear in the Knowledge Map.
