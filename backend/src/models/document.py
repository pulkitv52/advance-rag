import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Document(SQLModel, table=True):
    """Tracks every uploaded document and its ingestion state."""

    __tablename__ = "documents"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    filename: str
    object_key: str
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    elements_parsed: int = 0
    chunks_indexed: int = 0
    status: str = "pending"  # pending | processing | success | failed
    sub_status: Optional[str] = None  # e.g., "Parsing PDF", "Generating Knowledge Triplets"
    progress_percent: int = 0  # 0-100
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class QueryLog(SQLModel, table=True):
    """Audit log for every query made to the RAG system."""

    __tablename__ = "query_logs"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    query: str
    answer: str
    chunks_used: int = 0
    document_id: Optional[str] = Field(default=None, foreign_key="documents.id")
    latency_ms: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
