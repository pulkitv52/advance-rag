"""Run master registry schema creation and data loading directly against Postgres."""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from typing import Any

from src.services.master_registry import build_registry_statements


def build_dsn(args: argparse.Namespace) -> str:
    user = (
        args.user
        or os.getenv("REGISTRY_POSTGRES_USER")
        or os.getenv("POSTGRES_USER")
        or "app_user"
    )
    password = (
        args.password
        or os.getenv("REGISTRY_POSTGRES_PASSWORD")
        or os.getenv("POSTGRES_PASSWORD")
        or "change-me"
    )
    host = (
        args.host
        or os.getenv("REGISTRY_POSTGRES_HOST")
        or os.getenv("POSTGRES_HOST")
        or "127.0.0.1"
    )
    port = int(
        args.port
        or os.getenv("REGISTRY_POSTGRES_PORT")
        or os.getenv("POSTGRES_PORT")
        or "5432"
    )
    database = (
        args.database
        or os.getenv("REGISTRY_POSTGRES_DB")
        or os.getenv("POSTGRES_DB")
        or "app_db"
    )
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create/update the master registry schema and load person/enrollment rows directly "
            "through PostgreSQL without relying on the dev API request lifecycle."
        )
    )
    parser.add_argument("--host", default=None, help="Postgres host override")
    parser.add_argument("--port", type=int, default=None, help="Postgres port override")
    parser.add_argument("--user", default=None, help="Postgres user override")
    parser.add_argument("--password", default=None, help="Postgres password override")
    parser.add_argument("--database", default=None, help="Postgres database override")
    parser.add_argument(
        "--district-code",
        type=int,
        default=None,
        help="Optional district filter for pilot-only loads. Omit for full rollout.",
    )
    parser.add_argument(
        "--skip-schema",
        action="store_true",
        help="Skip table/view/index creation and only run data loaders.",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Run only the schema/table/view/index creation steps.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the statements that would run without executing them.",
    )
    return parser.parse_args()


async def execute_rollout(args: argparse.Namespace) -> list[dict[str, Any]]:
    import asyncpg

    dsn = build_dsn(args)
    include_schema = not args.skip_schema
    include_person_detail = not args.schema_only
    include_person_scheme_enrollment = not args.schema_only

    statements = build_registry_statements(
        district_code=args.district_code,
        include_schema=include_schema,
        include_person_detail=include_person_detail,
        include_person_scheme_enrollment=include_person_scheme_enrollment,
        include_validation_queries=False,
    )

    if args.dry_run:
        for index, statement in enumerate(statements, start=1):
            print(f"\n[{index}] {statement.key} ({statement.kind})\n{statement.statement}\n")
        return []

    conn = await asyncpg.connect(dsn)
    try:
        results: list[dict[str, Any]] = []
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = '0'")
            for index, statement in enumerate(statements, start=1):
                started_at = time.perf_counter()
                sql = statement.statement
                params: list[Any] = []
                if ":district_code" in sql:
                    sql = sql.replace(":district_code", "$1")
                    params.append(args.district_code)
                status = await conn.execute(
                    sql,
                    *params,
                )
                elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
                result = {
                    "index": index,
                    "key": statement.key,
                    "kind": statement.kind,
                    "status": status,
                    "elapsed_ms": elapsed_ms,
                }
                results.append(result)
                print(
                    f"[{index}/{len(statements)}] {statement.key} ({statement.kind}) -> "
                    f"{status} in {elapsed_ms} ms"
                )
    finally:
        await conn.close()

    return results


def main() -> None:
    args = parse_args()
    results = asyncio.run(execute_rollout(args))
    if args.dry_run:
        print("Dry run complete.")
        return
    print(f"Completed {len(results)} registry rollout statements.")


if __name__ == "__main__":
    main()
