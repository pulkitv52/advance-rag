from unittest.mock import Mock, patch

import pytest

from src.services import report_store


class DummySession:
    def __init__(self):
        self.added = []
        self.flush_calls = 0
        self.refresh_calls = 0

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_calls += 1

    async def refresh(self, _obj):
        self.refresh_calls += 1


@pytest.mark.asyncio
async def test_persist_report_uploads_to_expected_storage_key():
    session = DummySession()

    with patch("src.services.report_store.storage.upload_bytes") as mock_upload:
        report = await report_store.persist_report(
            session,
            analysis_id="analysis-123",
            pdf_bytes=b"pdf-bytes",
            filename="report.pdf",
        )

    mock_upload.assert_called_once()
    args, kwargs = mock_upload.call_args
    assert args[0] == b"pdf-bytes"
    assert args[1] == f"reports/analysis-123/{report.id}.pdf"
    assert kwargs["content_type"] == "application/pdf"
    assert report.storage_key == f"reports/analysis-123/{report.id}.pdf"
    assert session.flush_calls >= 2
    assert session.refresh_calls == 1
