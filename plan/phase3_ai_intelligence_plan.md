# Phase 3: AI Intelligence & Analytics Engine

This phase focuses on deploying AI-driven analysis across the Unified Social Registry to enable predictive governance, vulnerability mapping, and fraud prevention.

## 1. Dynamic Eligibility Engine
Instead of hard-coded rules, we will use the **120B NVIDIA LLM** to evaluate if a citizen qualifies for welfare benefits.
- **Workflow:**
    1. AI agent fetches the citizen's 360-degree profile (Age, Location, Cast, Assets).
    2. AI agent compares the profile against Scheme Policies.
    3. AI generates a reasoning report: "Eligible for Scheme X due to Y criteria."

## 2. Vulnerability & Risk Scoring
We will implement an automated scoring engine that flags citizens who are falling through the safety net.
- **Vulnerability Indicators:**
    - High-density household with low transaction volume.
    - Elderly individuals in remote (high-risk) LGD blocks.
    - Historical "transaction failures" indicating bureaucratic friction.
- **Output:** A `vulnerability_score` (0-100) added to nodes in Neo4j.

## 3. Fraud & Anomaly Detection (Graph-Based)
Deploy advanced graph analytics to identify systemic anomalies:
- **Identity Clusters:** Finding "clumped" identities sharing a single mobile number or address (potential shell registrations).
- **Ghost Detection:** Identifying citizens with active claims but zero demographic or verification activity for >24 months.

## 4. Proposed Changes

### [NEW] [ai_analytics.py](file:///wsl.localhost/Ubuntu/home/pulkitv52/Advance-rag/backend/src/services/ai_analytics.py)
A specialized service for batch processing intelligence reports.
- `calculate_vulnerability_scores()`: Runs graph patterns to score populations.
- `cluster_identities()`: Runs community detection to find potential fraud rings.

### [MODIFY] [usr_server.py](file:///wsl.localhost/Ubuntu/home/pulkitv52/Advance-rag/backend/src/mcp/usr_server.py)
Expose AI-powered analytic tools:
- `get_fraud_report()`: Returns a list of suspicious identity clusters.
- `assess_eligibility(uid)`: Provides AI reasoning for welfare eligibility.

## 5. Verification Plan
1. **Model Testing:** Run `assess_eligibility` for a test citizen and verify the logic is sound.
2. **Fraud Test:** Verify that the system flags the duplicate mobile numbers identified in Phase 0.
3. **Graph Integrity:** Ensure risk scores are correctly written back to Neo4j.
