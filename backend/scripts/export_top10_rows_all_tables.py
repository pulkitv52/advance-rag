"""Export top N rows from all non-system PostgreSQL tables."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import asyncpg

SYSTEM_SCHEMAS = {"pg_catalog", "information_schema"}


def quote_identifier(identifier: str) -> str:
    """Safely quote PostgreSQL identifiers."""
    return f'"{identifier.replace("\"", "\"\"")}"'


def parse_schemas(raw_schemas: str) -> list[str]:
    schemas = [item.strip() for item in raw_schemas.split(",") if item.strip()]
    return schemas or ["public"]


def build_dsn(args: argparse.Namespace) -> str:
    user = args.user or os.getenv("POSTGRES_USER", "postgres")
    password = args.password or os.getenv("POSTGRES_PASSWORD", "postgres")
    host = args.host or os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = args.port or int(os.getenv("POSTGRES_PORT", "5434"))
    database = args.database or os.getenv("POSTGRES_DB", "adv_rag")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


async def fetch_tables(conn: asyncpg.Connection, schemas: list[str]) -> list[tuple[str, str]]:
    rows = await conn.fetch(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema = ANY($1::text[])
          AND table_schema <> ALL($2::text[])
        ORDER BY table_schema, table_name
        """,
        schemas,
        list(SYSTEM_SCHEMAS),
    )
    return [(row["table_schema"], row["table_name"]) for row in rows]


async def fetch_top_rows(
    conn: asyncpg.Connection,
    schema_name: str,
    table_name: str,
    limit: int,
) -> list[dict[str, Any]]:
    safe_schema = quote_identifier(schema_name)
    safe_table = quote_identifier(table_name)
    query = f"SELECT * FROM {safe_schema}.{safe_table} LIMIT {limit}"
    rows = await conn.fetch(query)
    return [dict(row) for row in rows]


async def run_export(args: argparse.Namespace) -> dict[str, Any]:
    dsn = build_dsn(args)
    schemas = parse_schemas(args.schemas)
    output: dict[str, Any] = {
        "database": args.database or os.getenv("POSTGRES_DB", "adv_rag"),
        "schemas": schemas,
        "limit_per_table": args.limit,
        "tables": {},
    }

    conn = await asyncpg.connect(dsn)
    try:
        tables = await fetch_tables(conn, schemas)
        for schema_name, table_name in tables:
            table_key = f"{schema_name}.{table_name}"
            try:
                output["tables"][table_key] = await fetch_top_rows(
                    conn=conn,
                    schema_name=schema_name,
                    table_name=table_name,
                    limit=args.limit,
                )
            except Exception as exc:  # pragma: no cover - defensive per-table failure capture
                output["tables"][table_key] = {"error": str(exc)}
    finally:
        await conn.close()

    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export top N rows (all columns) for all tables in selected schemas."
    )
    parser.add_argument("--host", default=None, help="Postgres host (fallback: POSTGRES_HOST)")
    parser.add_argument(
        "--port", type=int, default=None, help="Postgres port (fallback: POSTGRES_PORT)"
    )
    parser.add_argument("--user", default=None, help="Postgres user (fallback: POSTGRES_USER)")
    parser.add_argument(
        "--password", default=None, help="Postgres password (fallback: POSTGRES_PASSWORD)"
    )
    parser.add_argument("--database", default=None, help="Postgres DB name (fallback: POSTGRES_DB)")
    parser.add_argument(
        "--schemas",
        default="public,srsadmin",
        help="Comma-separated schema list (default: public,srsadmin)",
    )
    parser.add_argument("--limit", type=int, default=10, help="Rows per table (default: 10)")
    parser.add_argument(
        "--output",
        default="top10_rows_all_tables.json",
        help="Output JSON file path",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = asyncio.run(run_export(args))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"Exported {len(result['tables'])} tables to {output_path}")


if __name__ == "__main__":
    main()
