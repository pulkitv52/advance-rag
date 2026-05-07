import argparse
import asyncio
import os
import sys

# Add project root so script can import src.*
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.logger import logger
from src.services.graph_db import get_driver


CONFIRM_TOKEN = "yes-delete-all"


async def clear_graph_data(batch_size: int) -> int:
    driver = await get_driver()
    total_deleted = 0

    async with driver.session() as session:
        while True:
            result = await session.run(
                """
                CALL {
                    MATCH (n)
                    WITH n
                    LIMIT $batch_size
                    DETACH DELETE n
                    RETURN count(n) AS deleted
                }
                RETURN deleted
                """,
                batch_size=batch_size,
            )
            record = await result.single()
            deleted = int(record["deleted"]) if record and record.get("deleted") is not None else 0
            total_deleted += deleted
            if deleted == 0:
                break
            logger.info(f"Deleted {deleted} nodes in current batch (total: {total_deleted}).")

    logger.info(f"Neo4j data clear complete. Total nodes deleted: {total_deleted}.")
    return total_deleted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete all Neo4j graph data (nodes and relationships) in batches."
    )
    parser.add_argument(
        "--confirm",
        required=True,
        help=f"Safety token. Must be exactly '{CONFIRM_TOKEN}' to run deletion.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Number of nodes to delete per batch (default: 5000).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.confirm != CONFIRM_TOKEN:
        raise SystemExit(
            f"Refusing to run. Pass --confirm {CONFIRM_TOKEN} to delete all Neo4j data."
        )
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be a positive integer.")

    asyncio.run(clear_graph_data(batch_size=args.batch_size))
