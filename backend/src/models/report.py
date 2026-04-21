import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel


class Report(SQLModel, table=True):
    __tablename__ = "reports"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    analysis_id: str = Field(foreign_key="analyses.id", index=True)
    format: str = "pdf"
    filename: str
    storage_key: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
