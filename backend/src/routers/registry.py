from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.database import get_session
from src.models.registry import (
    RegistryBuildRequest,
    RegistryExecutionResult,
    RegistrySqlPreviewRequest,
    RegistryStatementResult,
)
from src.services import master_registry

router = APIRouter(prefix="/api/registry", tags=["Master Registry"])


@router.post("/sql-preview")
async def preview_registry_sql(
    request: RegistrySqlPreviewRequest,
):
    statements = master_registry.build_registry_statements(
        district_code=request.district_code,
        include_schema=request.include_schema,
        include_person_detail=request.include_person_detail,
        include_person_scheme_enrollment=request.include_person_scheme_enrollment,
        include_validation_queries=False,
    )
    return {
        "district_code": request.district_code,
        "statement_count": len(statements),
        "statements": [RegistryStatementResult(**statement.__dict__) for statement in statements],
    }


@router.get("/validation-queries")
async def list_validation_queries(
    district_code: int | None = None,
):
    queries = master_registry.build_validation_queries(district_code)
    return {
        "district_code": district_code,
        "query_count": len(queries),
        "queries": [RegistryStatementResult(**statement.__dict__) for statement in queries],
    }


@router.get("/validation-results")
async def run_validation_queries(
    district_code: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    try:
        results = await master_registry.execute_validation_queries(
            session=session,
            district_code=district_code,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Registry validation failed: {exc}") from exc

    return {
        "district_code": district_code,
        "result_count": len(results),
        "results": results,
    }


@router.get("/pilot-summary/{district_code}")
async def get_pilot_summary(
    district_code: int,
    session: AsyncSession = Depends(get_session),
):
    try:
        summary = await master_registry.fetch_pilot_summary(session, district_code)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Registry summary failed: {exc}") from exc

    return summary


@router.get("/pilot-quality/{district_code}")
async def get_pilot_quality_report(
    district_code: int,
    include_join_loss: bool = True,
    session: AsyncSession = Depends(get_session),
):
    try:
        report = await master_registry.fetch_pilot_quality_report(
            session,
            district_code,
            include_join_loss=include_join_loss,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Registry quality report failed: {exc}") from exc

    return report


@router.get("/join-loss/{district_code}")
async def get_join_loss_report(
    district_code: int,
    session: AsyncSession = Depends(get_session),
):
    try:
        report = await master_registry.fetch_join_loss_report(session, district_code)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Registry join-loss report failed: {exc}") from exc

    return report


@router.get("/rollout-summary")
async def get_rollout_summary(
    session: AsyncSession = Depends(get_session),
):
    try:
        summary = await master_registry.fetch_rollout_summary(session)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Registry rollout summary failed: {exc}") from exc

    return summary


@router.post("/build")
async def build_master_registry(
    request: RegistryBuildRequest,
    session: AsyncSession = Depends(get_session),
):
    if not request.include_schema and not (
        request.include_person_detail or request.include_person_scheme_enrollment
    ):
        raise HTTPException(
            status_code=400,
            detail="Nothing selected to build. Enable schema creation or at least one loader.",
        )

    try:
        execution_results = await master_registry.execute_registry_build(
            session=session,
            district_code=request.district_code,
            include_schema=request.include_schema,
            include_person_detail=request.include_person_detail,
            include_person_scheme_enrollment=request.include_person_scheme_enrollment,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Registry build failed: {exc}") from exc

    response = {
        "district_code": request.district_code,
        "executed_count": len(execution_results),
        "results": [RegistryExecutionResult(**item) for item in execution_results],
    }
    if request.include_validation_queries:
        response["validation_queries"] = [
            RegistryStatementResult(**statement.__dict__)
            for statement in master_registry.build_validation_queries(request.district_code)
        ]
    return response
