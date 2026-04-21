import time

from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.report import Report
from src.services import storage


async def persist_report(
    session: AsyncSession,
    *,
    analysis_id: str,
    pdf_bytes: bytes,
    filename: str | None = None,
    report_format: str = "pdf",
) -> Report:
    report = Report(
        analysis_id=analysis_id,
        format=report_format,
        filename=filename or f"Research_Report_{int(time.time())}.pdf",
        storage_key="pending",
    )
    session.add(report)
    await session.flush()

    storage_key = f"reports/{analysis_id}/{report.id}.pdf"
    storage.upload_bytes(pdf_bytes, storage_key, content_type="application/pdf")
    report.storage_key = storage_key

    await session.flush()
    await session.refresh(report)
    return report


def load_report_bytes(storage_key: str) -> bytes:
    return storage.download_file_bytes(storage_key)
