"""Convert MCP tools to LangChain tools."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.tools import BaseTool, ToolException
from pydantic import BaseModel, Field, create_model


def json_schema_to_pydantic(
    schema: dict[str, Any], model_name: str = "Arguments"
) -> type[BaseModel]:
    """
    Convert a JSON schema to a Pydantic model.

    Args:
        schema: JSON schema dict (typically from MCP tool inputSchema)
        model_name: Name for the generated model

    Returns:
        A Pydantic model class
    """
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    field_definitions = {}

    for prop_name, prop_schema in properties.items():
        # Determine Python type from JSON schema type
        json_type = prop_schema.get("type", "string")
        python_type: Any = str

        if json_type == "string":
            python_type = str
        elif json_type == "integer":
            python_type = int
        elif json_type == "number":
            python_type = float
        elif json_type == "boolean":
            python_type = bool
        elif json_type == "array":
            python_type = list
        elif json_type == "object":
            python_type = dict
        elif json_type == "null":
            python_type = type(None)

        # Get description and default
        description = prop_schema.get("description", "")
        default = prop_schema.get("default", ...)

        # Handle required vs optional
        if prop_name in required:
            if default is ...:
                field_definitions[prop_name] = (python_type, Field(description=description))
            else:
                field_definitions[prop_name] = (
                    python_type,
                    Field(default=default, description=description),
                )
        else:
            # Optional field
            if default is ...:
                default = None
            field_definitions[prop_name] = (
                python_type | None,
                Field(default=default, description=description),
            )

    # Create the model dynamically
    return create_model(model_name, **field_definitions)


class MCPToolWrapper(BaseTool):
    """LangChain tool that wraps an MCP tool."""

    name: str
    description: str
    args_schema: type[BaseModel] | None = None
    server_name: str
    mcp_tool_name: str
    connection: Any  # MCPServerConnection - using Any to avoid Pydantic type resolution issues
    _reconnect_attempted: bool = False

    class Config:
        arbitrary_types_allowed = True

    def _run(self, **kwargs: Any) -> str:
        """Synchronous run - wraps async."""
        return asyncio.get_event_loop().run_until_complete(self._arun(**kwargs))

    async def _arun(self, **kwargs: Any) -> str:
        """Execute the MCP tool asynchronously with auto-reconnect on failure."""
        try:
            result = await self.connection.call_tool(self.mcp_tool_name, kwargs)
            # Reset reconnect flag on success
            self._reconnect_attempted = False
            return self._format_result(result)
        except Exception as e:
            # Try to reconnect once if we haven't already
            if not self._reconnect_attempted:
                self._reconnect_attempted = True
                reconnected = await self._try_reconnect()
                if reconnected:
                    # Retry the call after reconnecting
                    try:
                        result = await self.connection.call_tool(self.mcp_tool_name, kwargs)
                        self._reconnect_attempted = False
                        return self._format_result(result)
                    except Exception as retry_error:
                        # Reconnect succeeded but call still failed
                        await self._handle_persistent_failure()
                        raise ToolException(
                            f"MCP tool error ({self.server_name}/{self.mcp_tool_name}): {retry_error}"
                        ) from retry_error
                else:
                    # Reconnect failed - disable the server
                    await self._handle_persistent_failure()

            raise ToolException(
                f"MCP tool error ({self.server_name}/{self.mcp_tool_name}): {e}"
            ) from e

    async def _try_reconnect(self) -> bool:
        """Attempt to reconnect to the MCP server."""
        from sdrbot_cli.config import console

        console.print(
            f"[yellow]MCP connection to {self.server_name} lost, attempting reconnect...[/yellow]"
        )

        try:
            # Disconnect first (cleanup)
            await self.connection.disconnect()
            # Try to reconnect
            success = await self.connection.connect()
            if success:
                console.print(f"[green]✓ Reconnected to {self.server_name}[/green]")
                return True
            return False
        except Exception:
            return False

    async def _handle_persistent_failure(self) -> None:
        """Handle persistent connection failure by disabling the server."""
        from sdrbot_cli.config import console

        from .config import disable_mcp_server
        from .manager import get_mcp_manager

        console.print(
            f"[red]✗ Failed to reconnect to {self.server_name}. "
            f"Disabling server. Use /mcp to re-enable.[/red]"
        )

        # Disable in config
        disable_mcp_server(self.server_name)

        # Remove from active connections
        manager = get_mcp_manager()
        if self.server_name in manager.connections:
            try:
                await manager.connections[self.server_name].disconnect()
            except Exception:
                pass
            del manager.connections[self.server_name]

    def _format_result(self, result: Any) -> str:
        """Format MCP result content to string."""
        if isinstance(result, list):
            parts = []
            for content in result:
                if hasattr(content, "text"):
                    parts.append(content.text)
                elif hasattr(content, "data"):
                    # Binary content
                    mime_type = getattr(content, "mimeType", "unknown")
                    parts.append(f"[Binary data: {mime_type}]")
                else:
                    parts.append(str(content))
            return "\n".join(parts)

        if hasattr(result, "text"):
            return result.text

        if isinstance(result, dict | list):
            return json.dumps(result, indent=2)

        return str(result)


def create_langchain_tool(server_name: str, mcp_tool: Any, connection: Any) -> BaseTool:
    """
    Create a LangChain tool from an MCP tool.

    Args:
        server_name: Name of the MCP server
        mcp_tool: MCP Tool object
        connection: Active MCP connection

    Returns:
        LangChain BaseTool instance
    """
    # Generate args schema from MCP tool's input schema
    input_schema = getattr(mcp_tool, "inputSchema", {})
    args_schema = None

    if input_schema and input_schema.get("properties"):
        try:
            args_schema = json_schema_to_pydantic(
                input_schema, model_name=f"{server_name}_{mcp_tool.name}_args"
            )
        except Exception:
            # Fall back to no schema if conversion fails
            args_schema = None

    # Create prefixed tool name to avoid conflicts
    tool_name = f"mcp_{server_name}_{mcp_tool.name}"

    # Get description
    description = mcp_tool.description or f"MCP tool from {server_name}"

    return MCPToolWrapper(
        name=tool_name,
        description=description,
        args_schema=args_schema,
        server_name=server_name,
        mcp_tool_name=mcp_tool.name,
        connection=connection,
    )


def get_mcp_tools() -> list[BaseTool]:
    """
    Get all MCP tools from connected servers.

    This is a convenience function that gets tools from the global manager.
    """
    from .manager import get_mcp_manager

    manager = get_mcp_manager()
    return manager.get_all_tools()
