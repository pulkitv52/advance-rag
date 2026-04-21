# Advance-Rag Backend

Production-ready RAG pipeline backend powered by NVIDIA NIM, Qdrant, Minio, and PostgreSQL.

## Utility Scripts

- Export top rows from every table (all columns):
  - `uv run python scripts/export_top10_rows_all_tables.py --database srsdb --output /tmp/srsdb_top10.json`
