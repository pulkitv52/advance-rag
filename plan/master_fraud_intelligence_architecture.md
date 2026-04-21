# Master Fraud Intelligence: Architecture & Roadmap

This document serves as the permanent reference for the **Identity-Hub based Fraud Intelligence System**. It outlines the core architecture, the exhaustive permutation logic, and the intelligence rules designed to detect both external beneficiary fraud and internal systemic corruption.

## 🏗️ Core Architecture: The Hub-and-Spoke Model

Instead of a loose collection of citizens, the graph is organized around **Identity Anchors**. This allows the system to link seemingly unrelated citizens through hidden shared attributes.

### 1. Identity Anchors (Hubs)
-   📱 **Mobile Hub (`Mobile`)**: Links citizens sharing a phone number. Detects "Mobile Identity Rings."
-   🏠 **Household Hub (`RationCard`)**: Links primary and dependent members. Detects "Household Overload."
-   👤 **Audit Hub (`Operator`)**: Links every entry to the specific source/desk. Detects "Internal Trail Corruption."
-   📍 **Location Hub (`Address`)**: Links citizens to a physical factory location. Detects "Physical Address Factories."

---

## 🧠 Fraud Intelligence Matrix (Rule Sets)

The system identifies fraud through six distinct logic layers (Rules A-F).

| Rule ID | Name | Detection Logic | Confidence |
| :--- | :--- | :--- | :--- |
| **A** | **Ghost Detection** | Same DOB + Gender + Mobile shared across different names. | Critical (98%) |
| **B** | **Identity Theft** | Potential duplicate names with high similarity scores (APOC). | High (90%) |
| **C** | **Geographic Anomaly** | Abnormally high concentration of specific schemes in one GP. | Med (75%) |
| **D** | **Data Quality** | Missing DOBs, future-dated entries, or placeholder names. | Audit |
| **E** | **Household Overload** | Single Ration Card hub with >10 associated Citizen nodes. | High (95%) |
| **F** | **Internal Trail** | Operators whose total registrations have >15% fraud rate. | Critical (90%) |

---

## 📊 Data Intelligence Audit (Critical Columns)

For maximum accuracy, the ingestion pipeline MUST ingest the following columns from the social registry:
1.  `mobile`: Primary hub for identity ring detection.
2.  `ration_card`: Primary hub for household overloading.
3.  `entry_by`: Primary hub for operator audit trails.
4.  `address`: Primary hub for physical location factories.
5.  `dob`: Critical for ghost cluster detection (Same-DOB factories).

---

## 🎨 Visual Intelligence Grammar

The Knowledge Map follows a standardized color grammar to assist human investigators:

| Entity Type | Color Code | Rationale |
| :--- | :--- | :--- |
| **FraudFlag** | `#ef4444` (Red) | Immediate action required. |
| **Citizen** | `#eab308` (Yellow) | Active beneficiary entity. |
| **Mobile** | `#f97316` (Orange) | Critical identity anchor. |
| **RationCard**| `#fbbf24` (Gold) | Household grouping anchor. |
| **Operator** | `#059669` (Emerald)| Audit trail source. |
| **Scheme** | `#a855f7` (Purple)| Benefit delivery node. |

---

## 🚀 Future Roadmap

-   **Phase 6 (Predictive)**: Implement Temporal Analysis to detect registration "bursts" (e.g., 500 entries in 1 hour by one operator).
-   **Phase 7 (Geospatial)**: Map `LocationHub` nodes to actual coordinates for a real-time risk heatmap.
-   **Phase 8 (Inference)**: Deploy cross-scheme logic to detect illegal "Double Dipping" (e.g., Pensioner + NREGA simultaneously).

> [!TIP]
> **Maintenance**: Always run `POST /api/usr/run-sync` after bulk database updates to refresh the "Risk Scores" on GP and District nodes.
