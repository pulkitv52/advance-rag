# Phase 4: Geo-Spatial Intelligence & Executive Dashboard

This phase visualizes the Social Registry intelligence on an interactive map and executive dashboard embedded in the existing Advance-RAG frontend.

## 1. Goals
- Display a **district-level risk heatmap** of West Bengal showing concentration of high-vulnerability citizens.
- Build an **Executive Summary Panel** showing total beneficiaries, vulnerability distribution, and fraud alerts.
- Expose `/api/usr/` REST endpoints from the FastAPI backend to serve the dashboard with live data.

## 2. Architecture

```
Neo4j Knowledge Graph
        ↓
FastAPI USR Router (/api/usr/stats, /api/usr/heatmap, /api/usr/fraud)
        ↓
Frontend USR Dashboard Page (/usr-dashboard)
        ↓
District Heatmap (using LGD codes)  +  Risk Charts  +  Fraud Alerts Panel
```

## 3. Proposed Changes

### [NEW] `backend/src/routers/usr.py`
New FastAPI router exposing:
- `GET /api/usr/stats` — Total beneficiaries, avg vulnerability score, scheme counts.
- `GET /api/usr/heatmap` — Per-district risk aggregates for map rendering.
- `GET /api/usr/fraud` — Top suspicious identity clusters.
- `GET /api/usr/top-risk` — Top 50 highest-risk citizens.

### [MODIFY] `backend/src/main.py`
Register the new `/api/usr` router.

### [NEW] `frontend/src/pages/UsrDashboard.jsx`
A rich dashboard page showing:
- KPI cards (Total Citizens, High Risk Count, Fraud Alerts).
- Bar chart of vulnerability score distribution by district.
- Table of top 20 most vulnerable citizens.

### [MODIFY] `frontend/src/App.jsx`
Add route `/usr-dashboard` and navigation link.

## 4. Verification Plan
1. Open `http://localhost:5177/usr-dashboard` and verify the dashboard loads.
2. Confirm the district risk bar chart reflects Neo4j data.
3. Confirm the top-risk citizen table matches Neo4j query results.
