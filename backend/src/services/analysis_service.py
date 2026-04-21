import json
from typing import Any

from sqlalchemy import desc
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.analysis import Analysis


async def create_analysis(
    session: AsyncSession,
    *,
    project_id: str | None,
    query: str,
    answer: str,
    confidence_score: float | None,
    citation_coverage: float | None,
    graph_enrichment_used: bool,
    sources: list[dict[str, Any]],
) -> Analysis:
    analysis = Analysis(
        project_id=project_id,
        query=query,
        answer=answer,
        confidence_score=confidence_score,
        citation_coverage=citation_coverage,
        graph_enrichment_used=graph_enrichment_used,
        sources_json=json.dumps(sources),
    )
    session.add(analysis)
    await session.flush()
    await session.refresh(analysis)
    return analysis


async def list_analyses(session: AsyncSession, project_id: str | None = None) -> list[Analysis]:
    stmt = select(Analysis)
    if project_id:
        stmt = stmt.where(Analysis.project_id == project_id)
    stmt = stmt.order_by(desc(Analysis.created_at))
    result = await session.exec(stmt)
    return list(result.all())


async def get_analysis(session: AsyncSession, analysis_id: str) -> Analysis | None:
    return await session.get(Analysis, analysis_id)
