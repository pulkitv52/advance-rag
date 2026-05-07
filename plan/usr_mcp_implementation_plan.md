# Implementation Plan: USR MCP Server (Phase 1)

This plan outlines the steps to build the first Model Context Protocol (MCP) server for the Unified Social Registry.

## Phase 0: Database Restoration
**Goal:** Prepare the live source of truth.
1.  **Command:** `createdb -h localhost -U postgres registry_db`
2.  **Command:** `pg_restore -h localhost -U postgres -d registry_db registry_source.dump`
3.  **Verification:** Run `SELECT count(*) FROM public.swasthya_sathi_beneficiary;` in pgAdmin.

## Phase 1: MCP Server Core
**Goal:** Expose the database tools to the AI.
1.  **Environment:** Install `mcp` library via pip.
2.  **Server logic:**
    *   **Resource:** `registry://schema` - Returns the table structure.
    *   **Tool:** `get_citizen_360(uid)` - Fetches comprehensive data across partitions.
    *   **Tool:** `list_beneficiaries(district_code)` - Lists records for a specific region.
3.  **Transport:** Set up `stdio` transport for the MCP server.

## Phase 2: Integration
**Goal:** Connect to the Advance-RAG backend.
1.  Configure the `usr_mcp_config.json`.
2.  Verify the AI can successfully invoke tools to fetch beneficiary data.

## Verification Plan
1.  Verify DB tables in pgAdmin4.
2.  Test `get_citizen_360` with a known `uid` (e.g., `200001856164`).
