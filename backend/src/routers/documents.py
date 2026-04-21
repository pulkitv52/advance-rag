"""Document upload and management router."""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.database import get_session
from src.core.logger import logger
from src.models.document import Document
from src.models.project import Project, ProjectDocument
from src.services import graph_db, processor, storage

router = APIRouter(prefix="/documents", tags=["Documents"])

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "text/html",
    "text/csv",
    "image/png",
    "image/jpeg",
    "image/tiff",
}

ALLOWED_EXTENSIONS = {
    "pdf",
    "docx",
    "pptx",
    "xlsx",
    "txt",
    "html",
    "htm",
    "csv",
    "png",
    "jpg",
    "jpeg",
    "tiff",
}


def _validate_file(file: UploadFile) -> None:
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"File type '.{ext}' is not supported. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )


async def _run_ingestion(document_id: str, file_bytes: bytes, filename: str, content_type: str):
    """Background ingestion task that updates the document status in Postgres."""
    from io import BytesIO

    from src.core.database import async_session

    async with async_session() as session:
        doc_result = await session.get(Document, document_id)
        if not doc_result:
            logger.error(f"[Upload] Document ID {document_id} not found in DB.")
            return

        try:
            doc_result.status = "processing"
            doc_result.updated_at = datetime.utcnow()
            await session.commit()

            fake_file = UploadFile(
                filename=filename,
                file=BytesIO(file_bytes),
                headers={"content-type": content_type},
            )

            result = await processor.ingest_document(fake_file, document_id)

            doc_result.status = result["status"]
            doc_result.object_key = result["object_key"]
            doc_result.file_size = result.get("file_size")
            doc_result.elements_parsed = result.get("elements_parsed", 0)
            doc_result.chunks_indexed = result.get("chunks_indexed", 0)
            doc_result.error_message = result.get("error_message")
            doc_result.updated_at = datetime.utcnow()
            await session.commit()

            if doc_result.status == "success":
                logger.info(f"[Upload] Document '{filename}' ingested successfully.")
            else:
                logger.warning(
                    f"[Upload] Document '{filename}' completed with status: {doc_result.status}"
                )

        except Exception as e:
            logger.error(f"[Upload] Ingestion failed for '{filename}': {e}")
            if doc_result:
                doc_result.status = "failed"
                doc_result.error_message = str(e)
                doc_result.updated_at = datetime.utcnow()
                await session.commit()


@router.post("/upload", summary="Upload one or more documents for ingestion")
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    project_id: Optional[str] = Form(default=None),
    session: AsyncSession = Depends(get_session),
):
    """
    Accept multiple file uploads. Each file is:
    1. Validated by extension.
    2. Registered in Postgres with a UUID.
    3. Sent to the background ingestion pipeline (Minio -> NIM Parse -> Qdrant).

    Returns immediately with document IDs to poll for status.
    """
    responses = []

    project: Optional[Project] = None
    if project_id:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found.")

    for file in files:
        _validate_file(file)

        document_id = str(uuid.uuid4())
        file_bytes = await file.read()
        content_type = file.content_type or "application/octet-stream"

        doc = Document(
            id=document_id,
            filename=file.filename,
            object_key="",
            content_type=content_type,
            status="pending",
        )
        session.add(doc)
        if project:
            session.add(ProjectDocument(project_id=project.id, document_id=document_id))
        await session.commit()

        background_tasks.add_task(
            _run_ingestion,
            document_id,
            file_bytes,
            file.filename,
            content_type,
        )

        responses.append(
            {
                "document_id": document_id,
                "filename": file.filename,
                "status": "pending",
                "project_id": project.id if project else None,
            }
        )
        logger.info(f"[Upload] Queued '{file.filename}' as doc_id={document_id}")

    return {"uploaded": len(responses), "documents": responses}


@router.get("/", summary="List all documents")
async def list_documents(
    project_id: Optional[str] = None, session: AsyncSession = Depends(get_session)
):
    if project_id:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found.")

        query = (
            select(Document)
            .join(ProjectDocument, ProjectDocument.document_id == Document.id)
            .where(ProjectDocument.project_id == project_id)
            .order_by(Document.created_at.desc())
        )
    else:
        query = select(Document).order_by(Document.created_at.desc())

    result = await session.exec(query)
    docs = result.all()
    return {"total": len(docs), "documents": docs}


@router.get("/{document_id}", summary="Get document details and ingestion status")
async def get_document(document_id: str, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/graph/all", summary="Get the combined knowledge graph for all or specific documents")
async def get_knowledge_graph(
    ids: Optional[str] = None,
    q: Optional[str] = None,
    project_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """
    Returns nodes and edges for the Knowledge Graph.
    - If 'ids' provided, filters by those documents.
    - If 'project_id' provided, scopes the graph to documents linked to that project.
    - If 'q' provided, extracts entities from the query and returns a filtered sub-graph.
    """
    doc_ids = ids.split(",") if ids else None

    if project_id:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found.")

        project_doc_rows = await session.exec(
            select(ProjectDocument.document_id).where(ProjectDocument.project_id == project_id)
        )
        project_doc_ids = set(project_doc_rows.all())

        if doc_ids is None:
            doc_ids = list(project_doc_ids)
        else:
            doc_ids = [doc_id for doc_id in doc_ids if doc_id in project_doc_ids]

    entities = None

    if q:
        from src.services import extractor

        entities = await extractor.extract_entities_from_query(q)

    graph_data = await graph_db.get_combined_graph(document_ids=doc_ids, entities=entities)
    return graph_data


@router.delete("/{document_id}", summary="Delete a document and all its indexed chunks")
async def delete_document(document_id: str, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    from src.services import vector_db

    await vector_db.delete_document_chunks(document_id)

    if doc.object_key:
        try:
            storage.delete_file(doc.object_key)
        except Exception as e:
            logger.warning(f"Could not delete Minio object '{doc.object_key}': {e}")

    await graph_db.delete_document_triplets(document_id)

    await session.delete(doc)
    await session.commit()

    return {"message": f"Document '{doc.filename}' deleted successfully."}
