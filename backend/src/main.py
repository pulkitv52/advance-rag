from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src import models
from src.core.config import get_settings
from src.core.database import init_db
from src.core.logger import logger
from src.routers import analyses, documents, eligibility, logs, projects, query, reports, usr
from src.services.storage import ensure_bucket_exists
from src.services.vector_db import ensure_collection_exists

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.NVIDIA_API_KEY:
        logger.error("NVIDIA_API_KEY is missing! Ingestion will fail.")
        logger.error("Please ensure your .env file is correctly placed and populated.")
    else:
        masked_key = f"{settings.NVIDIA_API_KEY[:6]}...{settings.NVIDIA_API_KEY[-4:]}"
        logger.info(f"NVIDIA AI Key loaded: {masked_key}")

    logger.info("Initializing Postgres...")
    await init_db()
    logger.info("Postgres initialized.")

    logger.info("Checking Minio...")
    ensure_bucket_exists()
    logger.info("Minio checked.")

    logger.info("Checking Qdrant...")
    await ensure_collection_exists()
    logger.info("Qdrant checked.")

    logger.info("All services ready.")
    yield
    logger.info("Shutting down Advance-Rag API...")


app = FastAPI(
    title="Advance-Rag API",
    description=(
        "Production-ready RAG pipeline powered by NVIDIA NIM.\n\n"
        "Supports multi-format document ingestion (PDF, DOCX, PPTX, XLSX, CSV, TXT, Images) "
        "with layout-aware parsing, semantic chunking, vector search, and grounded generation."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(query.router)
app.include_router(projects.router)
app.include_router(analyses.router)
app.include_router(reports.router)
app.include_router(logs.router)
app.include_router(usr.router)
app.include_router(eligibility.router)


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": settings.APP_NAME,
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=settings.BACKEND_PORT, reload=True)
