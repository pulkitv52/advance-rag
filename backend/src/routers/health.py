from datetime import datetime, timezone

from fastapi import APIRouter
from sqlmodel import text
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.database import async_session
from src.core.logger import logger
from src.services.graph_db import get_driver
from src.services.storage import _get_client as get_minio_client
from src.services.vector_db import get_qdrant_client

router = APIRouter(tags=["Health"])


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/health/dependencies")
async def dependencies_health():
    deps = {}
    overall = "healthy"

    async def mark(name: str, ok: bool, detail: str = ""):
        nonlocal overall
        deps[name] = {
            "status": "up" if ok else "down",
            "detail": detail,
            "checked_at": _iso_now(),
        }
        if not ok:
            overall = "degraded"

    # Postgres
    try:
        async with async_session() as session:  # type: AsyncSession
            await session.exec(text("SELECT 1"))
        await mark("postgres", True)
    except Exception as exc:
        await mark("postgres", False, str(exc)[:180])

    # Qdrant
    try:
        client = get_qdrant_client()
        await client.get_collections()
        await mark("qdrant", True)
    except Exception as exc:
        await mark("qdrant", False, str(exc)[:180])

    # Neo4j
    try:
        driver = await get_driver()
        async with driver.session() as session:
            result = await session.run("RETURN 1 AS ok")
            await result.single()
        await mark("neo4j", True)
    except Exception as exc:
        await mark("neo4j", False, str(exc)[:180])

    # Minio
    try:
        client = get_minio_client()
        client.list_buckets()
        await mark("minio", True)
    except Exception as exc:
        await mark("minio", False, str(exc)[:180])

    # Redis (best-effort only; no strict dependency in this router)
    try:
        await mark("redis", True, "Reachability not actively probed in this build.")
    except Exception as exc:
        await mark("redis", False, str(exc)[:180])

    logger.info(f"Dependency health checked: {overall}")
    return {"status": overall, "dependencies": deps, "checked_at": _iso_now()}
