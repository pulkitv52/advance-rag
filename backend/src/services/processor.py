"""
Document processor: orchestrates the full ingestion pipeline.
1. Upload raw file → Minio
2. Parse document → NVIDIA NeMo Retriever Parse
3. Chunk parsed elements
4. Embed chunks → NVIDIA nv-embedqa-e5-v5
5. Upsert into Qdrant
6. Save metadata → Postgres
"""

from datetime import datetime
from typing import List

from fastapi import UploadFile

from src.core.database import async_session
from src.core.logger import logger
from src.models.document import Document
from src.services import extractor, graph_db, nvidia, storage, vector_db


def _chunk_elements(
    elements: List[dict], max_chars: int = 1500, overlap_chars: int = 200
) -> List[dict]:
    """
    Merge small parsed elements into semantic chunks of ~max_chars characters.
    Tables and headings are kept intact regardless of size.
    Applies character-level overlap between consecutive text chunks.
    """
    chunks = []
    buffer_text = ""
    buffer_meta: dict = {}

    for el in elements:
        el_type = el.get("type", "paragraph")
        el_text = el.get("text", "").strip()
        el_page = el.get("page")

        # Force-flush structural elements separately
        if el_type in ("table", "heading", "code"):
            if buffer_text:
                chunks.append({"text": buffer_text.strip(), **buffer_meta})
                # carry-over overlap into next buffer
                buffer_text = (
                    buffer_text[-overlap_chars:]
                    if len(buffer_text) > overlap_chars
                    else buffer_text
                )
            chunks.append({"text": el_text, "element_type": el_type, "page": el_page})
            buffer_text = ""
            buffer_meta = {}
            continue

        # Accumulate text chunks — also hard-split if single element exceeds max_chars
        if not buffer_meta:
            buffer_meta = {"element_type": el_type, "page": el_page}

        # Hard-split a single oversized element into sub-chunks
        while len(el_text) > max_chars:
            slice_text = el_text[:max_chars]
            if buffer_text:
                chunks.append({"text": buffer_text.strip(), **buffer_meta})
            chunks.append({"text": slice_text.strip(), "element_type": el_type, "page": el_page})
            el_text = el_text[max_chars - overlap_chars :]
            buffer_text = ""
            buffer_meta = {"element_type": el_type, "page": el_page}

        if len(buffer_text) + len(el_text) > max_chars:
            if buffer_text:
                chunks.append({"text": buffer_text.strip(), **buffer_meta})
                buffer_text = buffer_text[-overlap_chars:] + "\n" + el_text
                buffer_meta = {"element_type": el_type, "page": el_page}
            else:
                buffer_text = el_text
        else:
            buffer_text += "\n" + el_text

    if buffer_text.strip():
        chunks.append({"text": buffer_text.strip(), **buffer_meta})

    # Attach chunk index
    for i, c in enumerate(chunks):
        c["chunk_index"] = i

    logger.info(f"Produced {len(chunks)} chunks from {len(elements)} elements")
    return chunks


async def _update_progress(document_id: str, sub_status: str, progress: int):
    """Internal helper to update document progress in DB."""
    async with async_session() as session:
        doc = await session.get(Document, document_id)
        if doc:
            doc.sub_status = sub_status
            doc.progress_percent = progress
            doc.updated_at = datetime.utcnow()
            await session.commit()


async def ingest_document(file: UploadFile, document_id: str) -> dict:
    """
    Full ingestion pipeline for a single uploaded file.
    """
    import time

    start_total = time.perf_counter()
    filename = file.filename
    logger.info(f"--- [INGEST START] --- File: {filename} | ID: {document_id}")

    # ── Step 1: Upload raw file to Minio ──────────────────────────────
    try:
        await _update_progress(document_id, "Uploading to Secure Storage", 15)
        upload_info = await storage.upload_file(file, folder="documents")
        object_key = upload_info["object_key"]
        file_size = upload_info["size"]
        logger.info(f"[1/6] [MINIO] Uploaded: {object_key} ({file_size} bytes)")
    except Exception as e:
        logger.error(f"[1/6] [MINIO] Failed: {e}")
        raise

    # ── Step 2: Download bytes for parsing ────────────────────────────
    file_bytes = storage.download_file_bytes(object_key)
    logger.info(f"[2/6] [STORAGE] Retrieved for processing")

    # ── Step 3: Parse with NVIDIA NeMo Retriever Parse ────────────────
    await _update_progress(document_id, "NVIDIA Visual Decomposition (OCR/Parse)", 35)
    logger.info(f"[3/6] [NIM-PARSE] Requesting document decomposition...")
    t0 = time.perf_counter()
    elements = await nvidia.parse_document_bytes(file_bytes, filename)
    parse_time = time.perf_counter() - t0
    logger.info(f"[3/6] [NIM-PARSE] Extracted {len(elements)} elements in {parse_time:.2f}s")

    if not elements:
        # (Error handling remains same...)
        return {
            "document_id": document_id,
            "filename": filename,
            "object_key": object_key,
            "status": "no_content",
            "chunks_indexed": 0,
            "error_message": "NIM Parse returned no content.",
        }

    # ── Step 4: Chunk elements ─────────────────────────────────────────
    await _update_progress(document_id, "Semantic Chunking", 50)
    chunks = _chunk_elements(elements)

    # ── Step 5: Extract Knowledge Triplets (Graph RAG) ─────────────────
    await _update_progress(document_id, "Knowledge Graph Extraction (120B Reasoning)", 70)
    all_triplets = []
    # Process graph extraction in smaller batches to avoid LLM timeouts/limits
    full_text = "\n".join(
        [c["text"] for c in chunks[:10]]
    )  # Limit to first few chunks for graph to keep it snappy
    triplets = await extractor.extract_triplets(full_text)
    if triplets:
        await graph_db.save_triplets(document_id, triplets)
        all_triplets = triplets

    # ── Step 6: Embed chunks ──────────────────────────────────────────
    await _update_progress(document_id, "Generating Semantic Vectors", 85)
    t0 = time.perf_counter()
    texts = [c["text"] for c in chunks]
    embeddings = await nvidia.get_embeddings(texts, input_type="passage")
    embed_time = time.perf_counter() - t0
    logger.info(f"[5/6] [NIM-EMBED] Embedded in {embed_time:.2f}s")

    # ── Step 7: Upsert into Qdrant ────────────────────────────────────
    await _update_progress(document_id, "Finalizing Multi-Index Sync", 95)
    await vector_db.ensure_collection_exists()
    count = await vector_db.upsert_chunks(
        chunks=chunks,
        embeddings=embeddings,
        document_id=document_id,
        filename=filename,
        object_key=object_key,
    )

    await _update_progress(document_id, "Successfully Indexed", 100)

    total_time = time.perf_counter() - start_total
    logger.info(
        f"--- [INGEST FINISH] --- ✓ Indexed {count} chunks for '{filename}' in {total_time:.2f}s"
    )

    return {
        "document_id": document_id,
        "filename": filename,
        "object_key": object_key,
        "file_size": file_size,
        "elements_parsed": len(elements),
        "chunks_indexed": count,
        "status": "success",
    }
