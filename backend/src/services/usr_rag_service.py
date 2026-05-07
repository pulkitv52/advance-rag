import asyncio
from typing import Any, Dict, List

import asyncpg

from src.core.config import get_settings
from src.core.logger import logger
from src.services.nvidia import get_embeddings
from src.services.vector_db import upsert_chunks

settings = get_settings()

DB_CONFIG = {
    "user": "postgres",
    "password": "postgres",
    "database": "srsdb",
    "host": "127.0.0.1",
    "port": 5434,
}

BATCH_SIZE = 100


def create_citizen_profile(row: Dict[str, Any]) -> str:
    """Format a citizen record into a high-density textual profile for RAG."""
    # Build context string
    risk_info = f"Risk Tier: {row.get('risk_tier', 'LOW')}. " if row.get("risk_tier") else ""
    flags = []
    if row.get("is_ghost_flag"):
        flags.append("Ghost Detection")
    if row.get("is_dup_flag"):
        flags.append("Duplicate Alert")

    flag_str = f"System Flags: {', '.join(flags)}. " if flags else ""

    profile = (
        f"Citizen Profile: {row.get('fullname', 'Unknown')}\n"
        f"UID: {row.get('uid')}\n"
        f"Location: GP {row.get('lgd_gp_name')}, Block {row.get('lgd_block_name')}, District {row.get('lgd_district_name')}\n"
        f"Identity Hubs: Mobile {row.get('mobile') or 'N/A'}, Ration Card {row.get('ration_card_number') or 'N/A'}, Operator {row.get('entry_by') or 'N/A'}\n"
        f"Demographics: Gender {row.get('gender')}, DOB {row.get('member_dob')}\n"
        f"Intelligence: {risk_info}{flag_str}"
        f"Summary: This citizen is part of the Unified Social Registry data dump for scheme eligibility audit."
    )
    return profile


async def index_usr_for_research(limit: int = 5000):
    """
    Pulls citizens from PostgreSQL, creates textual profiles,
    and indexes them into Qdrant for the Research Chat.
    """
    logger.info(f"Starting USR RAG Indexing (Target: {limit} records)...")

    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        # Fetch high risk citizens first
        query = """
            SELECT * FROM srsadmin.swasthya_sathi_beneficiary 
            WHERE uid IS NOT NULL
            ORDER BY uid
            LIMIT $1
        """
        rows = await conn.fetch(query, limit)
        logger.info(f"Fetched {len(rows)} citizens for indexing.")

        profiles = []
        doc_ids = []
        for row in rows:
            profiles.append(create_citizen_profile(dict(row)))
            # We use a virtual document ID for the USR dump
            doc_ids.append(f"USR_CITIZEN_{row['uid']}")

        # Process in chunks for embeddings
        for i in range(0, len(profiles), BATCH_SIZE):
            batch_texts = profiles[i : i + BATCH_SIZE]
            batch_ids = doc_ids[i : i + BATCH_SIZE]

            logger.info(f"Generating embeddings for batch {i//BATCH_SIZE + 1}...")
            embeddings = await get_embeddings(batch_texts)

            # Format for Qdrant upsert
            chunks = [{"text": t, "chunk_index": 0} for t in batch_texts]

            # Upsert into Qdrant
            # We use a reserved doc_id 'USR_DUMP_001' to categorize all these
            await upsert_chunks(
                chunks=chunks,
                embeddings=embeddings,
                document_id="USR_DUMP_001",
                filename="Unified_Social_Registry_Database",
                object_key="sql://srsdb/beneficiaries",
            )

        logger.info("USR RAG Indexing complete.")

    except Exception as e:
        logger.error(f"USR RAG Indexing failed: {e}")
    finally:
        await conn.close()


if __name__ == "__main__":
    import sys

    lim = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    asyncio.run(index_usr_for_research(lim))
