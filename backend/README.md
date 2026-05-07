# Advance-Rag Backend

Production-ready RAG pipeline backend powered by NVIDIA NIM, Qdrant, Minio, and PostgreSQL.

## Utility Scripts

- Export top rows from every table (all columns):
  - `uv run python scripts/export_top10_rows_all_tables.py --database registry_db --output /tmp/registry_top10.json`
- Clear all Neo4j graph data (safe-confirmed, batched delete):
  - `uv run python scripts/clear_neo4j_data.py --confirm yes-delete-all --batch-size 5000`
