import asyncio

import asyncpg

from mcp.server.fastmcp import FastMCP
from src.core.config import get_settings
from src.services import ai_analytics

# Initialize the MCP Server
mcp = FastMCP("Unified Social Registry")
settings = get_settings()

# Database connection details
DB_CONFIG = {
    "user": settings.registry_postgres_user,
    "password": settings.registry_postgres_password,
    "database": settings.registry_postgres_db,
    "host": settings.registry_postgres_host,
    "port": settings.registry_postgres_port,
}

REGISTRY_SOURCE = f"{settings.REGISTRY_SCHEMA}.{settings.REGISTRY_BENEFICIARY_TABLE}"
REGISTRY_TRANSACTIONS = f"{settings.REGISTRY_SCHEMA}.{settings.REGISTRY_TRANSACTION_TABLE}"


async def get_db_connection():
    try:
        return await asyncpg.connect(**DB_CONFIG)
    except Exception as e:
        raise Exception(
            f"Failed to connect to PostgreSQL on {DB_CONFIG['host']}:{DB_CONFIG['port']}. Ensure the service is running. Error: {e}"
        )


@mcp.tool()
async def get_citizen_360(uid: str = None, beneficiary_id: str = None):
    """
    Retrieves a complete profile of a citizen using their UID (Aadhaar) or Scheme Beneficiary ID.
    This works across all partitions to provide a unified view.
    """
    try:
        conn = await get_db_connection()
    except Exception as e:
        return str(e)

    try:
        # We query the main table (Postgres handles redirecting to the correct partition)
        query = f"""
        SELECT * FROM {REGISTRY_SOURCE}
        WHERE uid = $1 OR scheme_beneficiary_id = $2
        LIMIT 1;
        """

        row = await conn.fetchrow(query, uid, beneficiary_id)
        if not row:
            return "Citizen not found in the registry."

        # Convert record to dict (handling timestamps/nulls)
        profile = {k: str(v) if v is not None else None for k, v in dict(row).items()}

        # We also fetch transaction history if available
        tran_query = f"""
        SELECT financial_year, installment_month, amount, transaction_timestamp 
        FROM {REGISTRY_TRANSACTIONS}
        WHERE scheme_beneficiary_id = $1
        ORDER BY transaction_timestamp DESC;
        """
        transactions = await conn.fetch(tran_query, profile["scheme_beneficiary_id"])
        profile["transactions"] = [{k: str(v) for k, v in dict(t).items()} for t in transactions]

        return profile
    finally:
        await conn.close()


@mcp.tool()
async def search_citizens(name_query: str):
    """
    Search for citizens by name. Supports partial matches.
    """
    conn = await get_db_connection()
    try:
        query = f"""
        SELECT fullname, lgd_district_name, lgd_block_name, scheme_beneficiary_id 
        FROM {REGISTRY_SOURCE}
        WHERE fullname ILIKE $1
        LIMIT 10;
        """
        rows = await conn.fetch(query, f"%{name_query}%")
        return [dict(r) for r in rows]
    finally:
        await conn.close()


@mcp.tool()
async def get_district_stats(district_code: int):
    """
    Get aggregated statistics for a specific district.
    """
    conn = await get_db_connection()
    try:
        query = f"""
        SELECT 
            COUNT(*) as total_beneficiaries,
            COUNT(CASE WHEN gender = 'FEMALE' THEN 1 END) as female_count,
            COUNT(CASE WHEN gender = 'MALE' THEN 1 END) as male_count
        FROM {REGISTRY_SOURCE}
        WHERE lgd_district_code = $1;
        """
        stats = await conn.fetchrow(query, district_code)
        return dict(stats)
    finally:
        await conn.close()


@mcp.tool()
async def get_fraud_report():
    """
    Analyzes the Knowledge Graph to find suspicious clusters of identities
    that may indicate fraudulent registrations.
    """
    clusters = await ai_analytics.find_identity_clusters()
    return clusters


@mcp.tool()
async def assess_eligibility(uid: str):
    """
    Uses AI to analyze a citizen's profile and assess their eligibility for
    various welfare schemes based on their graph context.
    """
    assessment = await ai_analytics.assess_eligibility_with_ai(uid)
    return assessment


@mcp.tool()
async def refresh_risk_scores():
    """
    Triggers a batch update of vulnerability and risk scores for all citizens
    in the Knowledge Graph.
    """
    count = await ai_analytics.calculate_vulnerability_scores()
    return f"Successfully updated risk scores for {count} citizens."


if __name__ == "__main__":
    mcp.run()
