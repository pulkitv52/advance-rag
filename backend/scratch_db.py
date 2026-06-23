import asyncio
import json
import os
import re
from pathlib import Path
import asyncpg
from dotenv import load_dotenv

# Load env file
dotenv_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path)

async def main():
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5434")
    database = os.getenv("POSTGRES_DB", "srsdb")
    dsn = f"postgresql://{user}:{password}@{host}:{port}/{database}"

    conn = await asyncpg.connect(dsn)
    try:
        # 1. Fetch all tables and views in srsadmin schema
        relations_raw = await conn.fetch("""
            SELECT table_name, table_type 
            FROM information_schema.tables 
            WHERE table_schema = 'srsadmin'
            ORDER BY table_name;
        """)
        relations = [dict(r) for r in relations_raw]
        
        # Group tables by base prefix
        groups = {}
        for r in relations:
            name = r["table_name"]
            # Classify into prefix groups
            if name.startswith("rc_beneficiary"):
                group_name = "rc_beneficiary"
            elif name.startswith("scheme_beneficiary_cash"):
                group_name = "scheme_beneficiary_cash"
            elif name.startswith("scheme_transaction_cash_2526"):
                group_name = "scheme_transaction_cash_2526"
            elif name.startswith("swasthya_sathi_beneficiary"):
                group_name = "swasthya_sathi_beneficiary"
            elif name.startswith("swasthya_sathi_transaction_2526"):
                group_name = "swasthya_sathi_transaction_2526"
            else:
                base_pattern = re.sub(r'_(?:\d+|mask_\d+|mask_\d+_\d+|\d+_\d+)$', '', name)
                group_name = base_pattern

            if group_name not in groups:
                groups[group_name] = []
            groups[group_name].append(r)

        result = {
            "total_relations": len(relations),
            "groups_count": len(groups),
            "groups": {}
        }

        # 2. Get column metadata and estimated row counts for each group
        for group_name, tables in groups.items():
            representative_table = tables[0]["table_name"]
            representative_type = tables[0]["table_type"]
            
            # Fetch columns for representative table
            cols_raw = await conn.fetch("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_schema = 'srsadmin' AND table_name = $1
                ORDER BY ordinal_position;
            """, representative_table)
            columns = [dict(c) for c in cols_raw]
            
            # Fetch indexes for representative table
            indexes_raw = await conn.fetch("""
                SELECT indexname, indexdef 
                FROM pg_indexes 
                WHERE schemaname = 'srsadmin' AND tablename = $1;
            """, representative_table)
            indexes = [dict(idx) for idx in indexes_raw]
            
            # Get estimated row count of representative table using pg_class
            try:
                rep_rows_est = await conn.fetchval("""
                    SELECT reltuples::bigint 
                    FROM pg_class 
                    WHERE oid = ($1 || '.' || $2)::regclass;
                """, 'srsadmin', representative_table)
            except Exception as e:
                rep_rows_est = f"Error: {e}"

            # Calculate total estimated row count in this group by summing reltuples
            total_group_rows_est = 0
            has_error = False
            for t in tables:
                t_name = t["table_name"]
                try:
                    cnt = await conn.fetchval("""
                        SELECT reltuples::bigint 
                        FROM pg_class 
                        WHERE oid = ($1 || '.' || $2)::regclass;
                    """, 'srsadmin', t_name)
                    # reltuples can be -1 if it was never analyzed, or float/int.
                    if cnt and cnt > 0:
                        total_group_rows_est += int(cnt)
                except Exception:
                    has_error = True
                    break

            result["groups"][group_name] = {
                "tables_count": len(tables),
                "representative_table": representative_table,
                "representative_type": representative_type,
                "representative_rows_est": rep_rows_est,
                "total_rows_est": total_group_rows_est if not has_error else "unknown",
                "tables_list": [t["table_name"] for t in tables],
                "columns": columns,
                "indexes": indexes
            }

        # 3. Check for views details
        views_raw = await conn.fetch("""
            SELECT table_name, view_definition 
            FROM information_schema.views 
            WHERE table_schema = 'srsadmin';
        """)
        result["views"] = [dict(v) for v in views_raw]

        print(json.dumps(result, indent=2, default=str))

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
