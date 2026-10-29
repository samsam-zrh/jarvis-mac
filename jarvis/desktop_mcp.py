"""Proxy MCP vers les outils utiles de Cua Driver, en conservant images et schémas."""
import asyncio
import os

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.server import Server
from mcp.server.stdio import stdio_server
from jarvis.paths import RUNTIME

ALLOWED = {"list_apps", "list_windows", "launch_app", "get_window_state", "get_desktop_state", "click", "double_click",
           "type_text", "press_key", "hotkey", "scroll", "set_value", "invoke_menu", "bring_to_front", "get_guide",
           "browser_prepare", "get_browser_state", "browser_navigate", "browser_click", "browser_type", "browser_scroll"}


async def main():
    server = Server("bureau")
    parameters = StdioServerParameters(command=str(RUNTIME / "cua/cua-driver"), args=["mcp"], env={**os.environ, "DO_NOT_TRACK": "1"})
    async with stdio_client(parameters) as streams, ClientSession(*streams) as client:
        await client.initialize()
        tools = [tool for tool in (await client.list_tools()).tools if tool.name in ALLOWED]
        names = {tool.name for tool in tools}

        @server.list_tools()
        async def list_tools():
            return tools

        @server.call_tool()
        async def call_tool(name: str, arguments: dict):
            if name not in names:
                return types.CallToolResult(isError=True, content=[types.TextContent(type="text", text="Outil non exposé dans ce profil")])
            return await client.call_tool(name, arguments)

        async with stdio_server() as streams:
            await server.run(*streams, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
