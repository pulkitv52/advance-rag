import pytest

from src.routers import usr


@pytest.mark.asyncio
async def test_get_summary_stats_prefers_live_counts_over_cached_global_stats(monkeypatch):
    calls = 0

    async def fake_run_neo4j_query(query: str, params: dict = {}):
        nonlocal calls
        calls += 1
        if "citizen_cases + operator_cases + household_cases AS total" in query:
            return [{"total": 51}]
        assert "live_critical_count AS critical_count" in query
        return [{
            "persisted_total": 28000,
            "live_graph_total": 30839,
            "avg_vulnerability": 24.5,
            "critical_count": 27,
            "high_risk_count": 311,
            "female_count": 14002,
            "critical_tier_count": 12,
            "last_updated": "2026-06-07T12:00:00Z",
            "physical_registry_total": 2234522,
        }]

    monkeypatch.setattr(usr, "run_neo4j_query", fake_run_neo4j_query)

    result = await usr.get_summary_stats()

    assert result["total_citizens"] == 30839
    assert result["critical_count"] == 27
    assert result["flagged_review_cases"] == 51
    assert result["high_risk_count"] == 311
    assert result["female_count"] == 14002
    assert result["critical_tier_count"] == 12
    assert result["coverage_pct"] == 1.4
    assert calls == 2
