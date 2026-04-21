import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run_test():
    # Parameters to launch your server
    server_params = StdioServerParameters(
        command="python3",
        args=["backend/src/mcp/usr_server.py"],
    )

    print("--- Connecting to Unified Social Registry MCP Server ---")
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize the session
                await session.initialize()

                # 1. List available tools
                tools = await session.list_tools()
                print(f"\nAvailable Tools: {[t.name for t in tools.tools]}")

                # 2. Call search_citizens tool
                print("\nTesting 'search_citizens' with query 'RAHIMA'...")
                result = await session.call_tool(
                    "search_citizens", arguments={"name_query": "RAHIMA"}
                )
                print(f"Result: {result.content[0].text}")

                # 3. Call get_district_stats tool
                print("\nTesting 'get_district_stats' for District 303...")
                stats = await session.call_tool(
                    "get_district_stats", arguments={"district_code": 303}
                )
                print(f"Stats: {stats.content[0].text}")
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        print("\nNote: Ensure 'srsdb' is restored and Postgres is running on localhost:5432.")


if __name__ == "__main__":
    asyncio.run(run_test())
