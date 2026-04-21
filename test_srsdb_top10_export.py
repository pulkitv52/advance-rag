"""Export top 10 rows from all SRSDB tables into a single CSV file.

Connection defaults intentionally mirror backend/src/mcp/usr_server.py:
- host: 127.0.0.1
- port: 5434
- database: srsdb
- user: postgres
- password: postgres
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from pathlib import Path
from typing import Any

import asyncpg

SYSTEM_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast"}
DEFAULT_DB_CONFIG = {
    "user": "postgres",
    "password": "postgres",
    "database": "srsdb",
    "host": "127.0.0.1",
    "port": 5434,
}


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export top N rows from all tables in srsdb to a CSV file."
    )
    parser.add_argument(
        "--limit", type=int, default=10, help="Rows per table (default: 10)"
    )
    parser.add_argument(
        "--output",
        default="srsdb_top10_all_tables.csv",
        help="Output CSV path (default: ./srsdb_top10_all_tables.csv)",
    )
    parser.add_argument(
        "--schemas",
        default="",
        help="Comma-separated schemas. Empty means all non-system schemas.",
    )
    return parser.parse_args()


def build_db_config() -> dict[str, Any]:
    return {
        "user": os.getenv(
            "SRSDB_USER", os.getenv("POSTGRES_USER", DEFAULT_DB_CONFIG["user"])
        ),
        "password": os.getenv(
            "SRSDB_PASSWORD",
            os.getenv("POSTGRES_PASSWORD", DEFAULT_DB_CONFIG["password"]),
        ),
        "database": os.getenv("SRSDB_NAME", DEFAULT_DB_CONFIG["database"]),
        "host": os.getenv(
            "SRSDB_HOST", os.getenv("POSTGRES_HOST", DEFAULT_DB_CONFIG["host"])
        ),
        "port": int(
            os.getenv(
                "SRSDB_PORT", os.getenv("POSTGRES_PORT", str(DEFAULT_DB_CONFIG["port"]))
            )
        ),
    }


def parse_schemas(raw_schemas: str) -> list[str]:
    schemas = [schema.strip() for schema in raw_schemas.split(",") if schema.strip()]
    return schemas


async def list_tables(
    conn: asyncpg.Connection, schemas: list[str]
) -> list[tuple[str, str]]:
    if schemas:
        rows = await conn.fetch(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema = ANY($1::text[])
            ORDER BY table_schema, table_name
            """,
            schemas,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema <> ALL($1::text[])
            ORDER BY table_schema, table_name
            """,
            list(SYSTEM_SCHEMAS),
        )
    return [(row["table_schema"], row["table_name"]) for row in rows]


async def fetch_top_rows(
    conn: asyncpg.Connection, schema_name: str, table_name: str, limit: int
) -> list[dict[str, Any]]:
    query = (
        f"SELECT * FROM {quote_identifier(schema_name)}.{quote_identifier(table_name)} "
        f"LIMIT {int(limit)}"
    )
    rows = await conn.fetch(query)
    return [dict(row) for row in rows]


def write_csv(output_path: Path, records: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["schema_name", "table_name", "row_number", "row_json", "error"],
        )
        writer.writeheader()
        writer.writerows(records)


async def run() -> None:
    args = parse_args()
    db_config = build_db_config()
    schemas = parse_schemas(args.schemas)
    output_path = Path(args.output)

    conn = await asyncpg.connect(**db_config)
    records: list[dict[str, Any]] = []
    try:
        tables = await list_tables(conn, schemas=schemas)
        for schema_name, table_name in tables:
            try:
                rows = await fetch_top_rows(conn, schema_name, table_name, args.limit)
                for index, row in enumerate(rows, start=1):
                    records.append(
                        {
                            "schema_name": schema_name,
                            "table_name": table_name,
                            "row_number": index,
                            "row_json": json.dumps(
                                row, default=str, ensure_ascii=False
                            ),
                            "error": "",
                        }
                    )
                if not rows:
                    records.append(
                        {
                            "schema_name": schema_name,
                            "table_name": table_name,
                            "row_number": 0,
                            "row_json": "",
                            "error": "",
                        }
                    )
            except Exception as exc:
                records.append(
                    {
                        "schema_name": schema_name,
                        "table_name": table_name,
                        "row_number": 0,
                        "row_json": "",
                        "error": str(exc),
                    }
                )
    finally:
        await conn.close()

    write_csv(output_path, records)
    print(f"Wrote {len(records)} rows to {output_path.resolve()}")


if __name__ == "__main__":
    asyncio.run(run())
