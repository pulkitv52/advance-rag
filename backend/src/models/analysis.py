import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel


class Analysis(SQLModel, table=True):
    __tablename__ = "analyses"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str | None = Field(default=None, foreign_key="projects.id")
    query: str
    answer: str
    confidence_score: float | None = None
    citation_coverage: float | None = None
    graph_enrichment_used: bool = False
    sources_json: str = "[]"
    created_at: datetime = Field(default_factory=datetime.utcnow)
