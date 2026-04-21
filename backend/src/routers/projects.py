from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.database import get_session
from src.models.document import Document
from src.models.project import Project, ProjectDocument

router = APIRouter(prefix="/projects", tags=["Projects"])


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProjectDocumentsLinkRequest(BaseModel):
    document_ids: list[str]


@router.post("/", summary="Create a project workspace")
async def create_project(request: ProjectCreate, session: AsyncSession = Depends(get_session)):
    project = Project(name=request.name.strip(), description=request.description)
    session.add(project)
    await session.flush()
    await session.refresh(project)
    return project


@router.get("/", summary="List all project workspaces")
async def list_projects(session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(Project).order_by(Project.created_at.desc()))
    return {"projects": list(result.all())}


@router.get("/{project_id}", summary="Get a single project workspace")
async def get_project(project_id: str, session: AsyncSession = Depends(get_session)):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@router.post("/{project_id}/documents", summary="Link existing documents to a project")
async def link_documents_to_project(
    project_id: str,
    request: ProjectDocumentsLinkRequest,
    session: AsyncSession = Depends(get_session),
):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    linked = 0
    for document_id in request.document_ids:
        document = await session.get(Document, document_id)
        if not document:
            continue

        existing = await session.get(ProjectDocument, (project_id, document_id))
        if existing:
            continue

        session.add(
            ProjectDocument(
                project_id=project_id, document_id=document_id, created_at=datetime.utcnow()
            )
        )
        linked += 1

    return {"project_id": project_id, "linked": linked}
