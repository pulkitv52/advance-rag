import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.database import get_session
from src.services import analysis_service

router = APIRouter(prefix="/analyses", tags=["Analyses"])


class AnalysisCreate(BaseModel):
    project_id: str | None = None
    query: str
    answer: str
    confidence_score: float | None = None
    citation_coverage: float | None = None
    graph_enrichment_used: bool = False
    sources: list[dict[str, Any]] = []


def _serialize_analysis(analysis) -> dict[str, Any]:
    return {
        "id": analysis.id,
        "project_id": analysis.project_id,
        "query": analysis.query,
        "answer": analysis.answer,
        "confidence_score": analysis.confidence_score,
        "citation_coverage": analysis.citation_coverage,
        "graph_enrichment_used": analysis.graph_enrichment_used,
        "sources": json.loads(analysis.sources_json or "[]"),
        "created_at": analysis.created_at,
    }


@router.post("/", summary="Save an analysis")
async def create_analysis(request: AnalysisCreate, session: AsyncSession = Depends(get_session)):
    analysis = await analysis_service.create_analysis(
        session,
        project_id=request.project_id,
        query=request.query,
        answer=request.answer,
        confidence_score=request.confidence_score,
        citation_coverage=request.citation_coverage,
        graph_enrichment_used=request.graph_enrichment_used,
        sources=request.sources,
    )
    return {"id": analysis.id, "created_at": analysis.created_at}


@router.get("/", summary="List saved analyses")
async def list_saved_analyses(
    project_id: str | None = None, session: AsyncSession = Depends(get_session)
):
    analyses = await analysis_service.list_analyses(session, project_id=project_id)
    return {"analyses": [_serialize_analysis(analysis) for analysis in analyses]}


@router.get("/{analysis_id}", summary="Get a saved analysis")
async def get_saved_analysis(analysis_id: str, session: AsyncSession = Depends(get_session)):
    analysis = await analysis_service.get_analysis(session, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return _serialize_analysis(analysis)
