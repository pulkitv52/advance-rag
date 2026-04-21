import asyncio
from src.services.graph_db import get_driver
from src.core.logger import logger

async def harden_identity_hubs():
    driver = await get_driver()
    async with driver.session() as session:
        logger.info("--- Starting Identity Hub Hardening ---")

        # 1. Merge RationCard duplicates
        logger.info("Merging duplicate RationCard nodes...")
        merge_rc_query = """
        MATCH (rc:RationCard)
        WHERE rc.number IS NOT NULL
        WITH rc.number AS number, collect(rc) AS nodes
        WHERE size(nodes) > 1
        CALL apoc.refactor.mergeNodes(nodes, {properties: 'combine', mergeRels: true}) YIELD node
        RETURN count(node) as count
        """
        # Fallback if APOC is not installed
        # (Actually we will try direct manual merge if APOC fails)
        try:
            res = await session.run(merge_rc_query)
            data = await res.single()
            logger.info(f"Merged {data['count']} RationCard duplicate groups via APOC.")
        except Exception as e:
            logger.warning(f"APOC merge failed, attempting manual relationship rebinding: {e}")
            # Manual fallback: This is safer for simple hubs
            manual_query = """
            MATCH (rc:RationCard)
            WITH rc.number AS num, collect(rc) AS nodes
            WHERE size(nodes) > 1
            UNWIND tail(nodes) as other
            WITH head(nodes) as master, other
            MATCH (citizen:Citizen)-[rel:MEMBER_OF]->(other)
            MERGE (citizen)-[:MEMBER_OF]->(master)
            DETACH DELETE other
            """
            await session.run(manual_query)
            logger.info("Manual RationCard merge complete.")

        # 2. Merge Mobile duplicates
        logger.info("Merging duplicate Mobile nodes...")
        manual_mobile_query = """
        MATCH (m:Mobile)
        WITH m.number AS num, collect(m) AS nodes
        WHERE size(nodes) > 1
        UNWIND tail(nodes) as other
        WITH head(nodes) as master, other
        MATCH (citizen:Citizen)-[rel:HAS_MOBILE]->(other)
        MERGE (citizen)-[:HAS_MOBILE]->(master)
        DETACH DELETE other
        """
        await session.run(manual_mobile_query)
        logger.info("Mobile merge complete.")

        # 3. Add Constraints
        logger.info("Adding Unique Constraints to harden schema...")
        constraints = [
            "CREATE CONSTRAINT ration_card_number_unique IF NOT EXISTS FOR (r:RationCard) REQUIRE r.number IS UNIQUE",
            "CREATE CONSTRAINT mobile_number_unique IF NOT EXISTS FOR (m:Mobile) REQUIRE m.number IS UNIQUE"
        ]
        for c in constraints:
            try:
                await session.run(c)
                logger.info(f"Constraint applied: {c}")
            except Exception as e:
                logger.error(f"Failed to apply constraint: {e}")

        # 4. Remove internal orphaned hubs
        logger.info("Removing orphaned identity hubs...")
        cleanup_orphans = """
        MATCH (h)
        WHERE (h:RationCard OR h:Mobile OR h:Address)
          AND NOT (h)--()
        DELETE h
        RETURN count(*) as count
        """
        res = await session.run(cleanup_orphans)
        data = await res.single()
        logger.info(f"Removed {data['count']} orphaned hubs.")

    logger.info("--- Identity Hub Hardening Complete ---")

if __name__ == "__main__":
    asyncio.run(harden_identity_hubs())
