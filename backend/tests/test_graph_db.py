from unittest.mock import AsyncMock

import pytest

from src.services import graph_db


class DummyResult:
    def __init__(self, *, single_record=None, data_records=None):
        self._single_record = single_record
        self._data_records = data_records or []

    async def single(self):
        return self._single_record

    async def data(self):
        return self._data_records


class DummySession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.queries = []

    async def run(self, query, **params):
        self.queries.append((query, params))
        return self._responses.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class DummyDriver:
    def __init__(self, session):
        self._session = session

    def session(self):
        return self._session


@pytest.mark.asyncio
async def test_get_combined_graph_prefers_usr_view_when_only_entities_are_present(monkeypatch):
    session = DummySession(
        [
            DummyResult(single_record={"cnt": 5}),
            DummyResult(
                data_records=[
                    {
                        "c": {"uid": "citizen-1", "name": "Alice", "risk_tier": "LOW"},
                        "gp": {"code": "gp-1", "name": "GP One"},
                        "b": {"code": "block-1", "name": "Block One"},
                        "d": {"code": "district-1", "name": "District One"},
                        "s": None,
                        "enroll": None,
                        "dup": None,
                        "c2": None,
                        "flag_edge": None,
                        "f": None,
                    }
                ]
            ),
        ]
    )

    monkeypatch.setattr(graph_db, "get_driver", AsyncMock(return_value=DummyDriver(session)))

    result = await graph_db.get_combined_graph(entities=["alice"])

    assert len(result["nodes"]) == 4
    assert any(node["id"] == "citizen-1" for node in result["nodes"])
    assert "MATCH (c:Citizen)" in session.queries[1][0]


@pytest.mark.asyncio
async def test_get_combined_graph_scheme_mode_filters_by_scheme(monkeypatch):
    session = DummySession(
        [
            DummyResult(single_record={"cnt": 0}),
            DummyResult(
                data_records=[
                    {
                        "c": {"uid": "citizen-1", "name": "Alice", "risk_tier": "LOW"},
                        "gp": {"code": "gp-1", "name": "GP One"},
                        "b": {"code": "block-1", "name": "Block One"},
                        "d": {"code": "district-1", "name": "District One"},
                        "s": {"id": "S767", "name": "S767"},
                        "enroll": {"status": "Active"},
                        "dup": None,
                        "c2": None,
                        "flag_edge": None,
                        "f": None,
                    }
                ]
            ),
        ]
    )

    monkeypatch.setattr(graph_db, "get_driver", AsyncMock(return_value=DummyDriver(session)))

    result = await graph_db.get_combined_graph(scheme_id="S767")

    assert any(node["id"] == "S767" for node in result["nodes"])
    assert any(link["target"] == "S767" and link["label"] == "ENROLLED_IN" for link in result["links"])
    assert session.queries[1][1]["scheme_id"] == "S767"


@pytest.mark.asyncio
async def test_get_usr_schemes_returns_sorted_rollups(monkeypatch):
    session = DummySession(
        [
            DummyResult(
                data_records=[
                    {
                        "id": "S767",
                        "name": "S767",
                        "citizen_count": 879,
                        "enrollment_count": 1000,
                    },
                    {
                        "id": "S528",
                        "name": "S528",
                        "citizen_count": 1000,
                        "enrollment_count": 1000,
                    },
                ]
            )
        ]
    )

    monkeypatch.setattr(graph_db, "get_driver", AsyncMock(return_value=DummyDriver(session)))

    result = await graph_db.get_usr_schemes()

    assert result == [
        {"id": "S767", "name": "S767", "citizen_count": 879, "enrollment_count": 1000},
        {"id": "S528", "name": "S528", "citizen_count": 1000, "enrollment_count": 1000},
    ]
    assert "MATCH (s:Scheme)" in session.queries[0][0]
