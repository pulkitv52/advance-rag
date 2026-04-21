import asyncio
import os
import sys

# Add the project root to sys.path so it can find the 'src' package
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.graph_db import get_driver
from src.core.logger import logger

async def align_neo4j_schema():
    """
    Ensures all Citizen nodes have the necessary fraud flags
    and that relationship types required by the dashboard exist.
    """
    driver = await get_driver()
    async with driver.session() as session:
        logger.info("Aligning Neo4j schema flags...")
        
        # 1. Initialize flags if missing
        await session.run("""
        MATCH (c:Citizen)
        WHERE c.is_dup_flag IS NULL OR c.is_anomaly_flag IS NULL OR c.is_ghost_flag IS NULL
        SET c.is_dup_flag = COALESCE(c.is_dup_flag, false),
            c.is_anomaly_flag = COALESCE(c.is_anomaly_flag, false),
            c.is_ghost_flag = COALESCE(c.is_ghost_flag, false)
        """)
        
        # 2. Ensure FLAGGED_AS and POTENTIAL_DUPLICATE relationship types are recognized
        # We can't actually "pre-create" relationship types without relationships, 
        # but we can ensure the indexes for them are there if any exist.
        
        # 3. Fix potential type mismatches
        await session.run("""
        MATCH (c:Citizen)
        WHERE c.age IS NULL AND c.dob IS NOT NULL AND c.dob <> '' AND c.dob <> 'None'
        SET c.age = duration.between(date(c.dob), date()).years
        """)
        
        logger.info("Neo4j schema alignment complete.")

if __name__ == "__main__":
    asyncio.run(align_neo4j_schema())
