import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ProjectDocument(SQLModel, table=True):
    __tablename__ = "project_documents"

    project_id: str = Field(foreign_key="projects.id", primary_key=True)
    document_id: str = Field(foreign_key="documents.id", primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
