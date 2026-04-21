import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.database import get_session
from src.models.report import Report
from src.services import report_store

router = APIRouter(tags=["Reports"])


@router.get("/analyses/{analysis_id}/reports", summary="List reports generated for an analysis")
async def list_analysis_reports(analysis_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.exec(
        select(Report).where(Report.analysis_id == analysis_id).order_by(Report.created_at.desc())
    )
    return {"reports": list(result.all())}


@router.get("/reports/{report_id}/download", summary="Download a persisted report")
async def download_report(report_id: str, session: AsyncSession = Depends(get_session)):
    report = await session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")

    report_bytes = report_store.load_report_bytes(report.storage_key)
    return StreamingResponse(
        io.BytesIO(report_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={report.filename}",
            "Access-Control-Expose-Headers": "Content-Disposition, Content-Type, Content-Length",
            "Content-Length": str(len(report_bytes)),
        },
    )
