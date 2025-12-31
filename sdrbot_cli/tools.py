"""Custom tools for the CLI agent."""

from collections.abc import Callable
from typing import Any

import requests
from langchain_core.tools import BaseTool
from langchain_core.tools import tool as langchain_tool
from markdownify import markdownify

# Tool scope levels (hierarchy: standard < extended < privileged)
SCOPE_STANDARD = "standard"
SCOPE_EXTENDED = "extended"
SCOPE_PRIVILEGED = "privileged"

# Metadata keys
SCOPE_METADATA_KEY = "scope"
SCHEMA_MODIFYING_KEY = "schema_modifying"
SERVICE_KEY = "service_name"

# Registry of schema-modifying tools: {tool_name: service_name}
# Populated automatically when tools are decorated with schema_modifying param
_SCHEMA_MODIFYING_REGISTRY: dict[str, str] = {}


def scoped_tool(
    func: Callable | None = None,
    *,
    scope: str = SCOPE_PRIVILEGED,
    schema_modifying: str | None = None,
) -> BaseTool | Callable[[Callable], BaseTool]:
    """Decorator to create a scoped tool.

    Scoped tools are filtered based on the current tool scope setting.
    Scope hierarchy: standard < extended < privileged

    Args:
        func: The function to wrap (when used without parentheses).
        scope: Tool scope level - "extended" or "privileged".
            Standard tools don't need this decorator.
        schema_modifying: Service name if this tool modifies schema
            (e.g., "twenty"). When set, triggers automatic schema
            resync and agent reload after successful execution.

    Usage:
        @scoped_tool(scope="extended")
        def my_extended_tool(arg: str) -> str:
            '''Tool available in extended+ scope.'''
            return "result"

        @scoped_tool(scope="privileged")
        def my_admin_tool(arg: str) -> str:
            '''Tool only available in privileged scope.'''
            return "result"

        @scoped_tool(scope="privileged", schema_modifying="twenty")
        def my_schema_changing_tool(arg: str) -> str:
            '''This tool modifies CRM schema.'''
            return "result"

    The resulting tool will have metadata["scope"] set to the scope level.
    Tools with schema_modifying set will also have:
    - metadata["schema_modifying"] = True
    - metadata["service_name"] = <service>

    And will be registered in _SCHEMA_MODIFYING_REGISTRY for auto-reload.
    """

    def decorator(f: Callable) -> BaseTool:
        # Create the tool using langchain's @tool decorator
        lc_tool = langchain_tool(f)
        # Set scope in metadata
        if lc_tool.metadata is None:
            lc_tool.metadata = {}
        lc_tool.metadata[SCOPE_METADATA_KEY] = scope

        # Add schema-modifying metadata if specified
        if schema_modifying:
            lc_tool.metadata[SCHEMA_MODIFYING_KEY] = True
            lc_tool.metadata[SERVICE_KEY] = schema_modifying
            # Register for auto-reload detection
            _SCHEMA_MODIFYING_REGISTRY[lc_tool.name] = schema_modifying

        return lc_tool

    # Support both @scoped_tool and @scoped_tool(scope="x")
    if func is not None:
        # Called without parentheses: @scoped_tool
        return decorator(func)
    # Called with parentheses: @scoped_tool(...) or @scoped_tool()
    return decorator


def get_schema_modifying_tools() -> dict[str, str]:
    """Get mapping of schema-modifying tool names to their services.

    Returns:
        Dict mapping tool_name -> service_name for tools that modify schema.
        Used by execution.py to detect when to trigger auto-reload.
    """
    return _SCHEMA_MODIFYING_REGISTRY.copy()


def get_tool_scope(tool: BaseTool) -> str:
    """Get the scope level of a tool.

    Args:
        tool: A LangChain tool instance.

    Returns:
        The tool's scope: "standard", "extended", or "privileged".
        Tools without explicit scope are considered "standard".
    """
    if tool.metadata is None:
        return SCOPE_STANDARD
    return tool.metadata.get(SCOPE_METADATA_KEY, SCOPE_STANDARD)


def is_tool_allowed(tool: BaseTool, current_scope: str) -> bool:
    """Check if a tool is allowed under the current scope setting.

    Scope hierarchy: standard < extended < privileged
    - Standard scope: only standard tools
    - Extended scope: standard + extended tools
    - Privileged scope: all tools

    Args:
        tool: A LangChain tool instance.
        current_scope: Current scope setting ("standard", "extended", "privileged").

    Returns:
        True if the tool is allowed, False otherwise.
    """
    tool_scope = get_tool_scope(tool)

    if current_scope == SCOPE_PRIVILEGED:
        return True
    if current_scope == SCOPE_EXTENDED:
        return tool_scope in (SCOPE_STANDARD, SCOPE_EXTENDED)
    # Standard scope - only standard tools
    return tool_scope == SCOPE_STANDARD


def http_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: str | dict | None = None,
    params: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Make HTTP requests to APIs and web services.

    Args:
        url: Target URL
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        headers: HTTP headers to include
        data: Request body data (string or dict)
        params: URL query parameters
        timeout: Request timeout in seconds

    Returns:
        Dictionary with response data including status, headers, and content
    """
    try:
        kwargs = {"url": url, "method": method.upper(), "timeout": timeout}

        if headers:
            kwargs["headers"] = headers
        if params:
            kwargs["params"] = params
        if data:
            if isinstance(data, dict):
                kwargs["json"] = data
            else:
                kwargs["data"] = data

        response = requests.request(**kwargs)

        try:
            content = response.json()
        except Exception:
            content = response.text

        return {
            "success": response.status_code < 400,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "content": content,
            "url": response.url,
        }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "status_code": 0,
            "headers": {},
            "content": f"Request timed out after {timeout} seconds",
            "url": url,
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "status_code": 0,
            "headers": {},
            "content": f"Request error: {e!s}",
            "url": url,
        }
    except Exception as e:
        return {
            "success": False,
            "status_code": 0,
            "headers": {},
            "content": f"Error making request: {e!s}",
            "url": url,
        }


def sync_crm_schema(service_name: str | None = None) -> str:
    """Sync CRM schema(s) and regenerate tools.

    Use this tool to refresh the available fields and tools for CRM services.
    This is useful after creating custom fields or modifying the CRM schema.

    Args:
        service_name: Optional. Name of a specific service to sync (e.g., "pipedrive",
                     "twenty", "hubspot", "salesforce", "attio", "zohocrm").
                     If not provided, syncs ALL enabled syncable services.

    Returns:
        Success message with synced services, or error message.
    """
    from sdrbot_cli.services import SYNCABLE_SERVICES, resync_service
    from sdrbot_cli.services.registry import load_config

    # If specific service requested, sync just that one
    if service_name:
        if service_name not in SYNCABLE_SERVICES:
            return f"Error: '{service_name}' is not a syncable service. Valid options: {', '.join(SYNCABLE_SERVICES)}"

        try:
            success = resync_service(service_name, verbose=False)
            if success:
                return f"Successfully synced {service_name} schema. Tools have been regenerated."
            else:
                return f"Failed to sync {service_name}. Check that the service is enabled and credentials are valid."
        except Exception as e:
            return f"Error syncing {service_name}: {str(e)}"

    # No service specified - sync all enabled syncable services
    config = load_config()
    enabled_syncable = [s for s in SYNCABLE_SERVICES if config.is_enabled(s)]

    if not enabled_syncable:
        return "No syncable services are enabled. Enable a CRM service first with /services enable <name>"

    results = []
    for svc in enabled_syncable:
        try:
            success = resync_service(svc, verbose=False)
            if success:
                results.append(f"✓ {svc}")
            else:
                results.append(f"✗ {svc} (failed)")
        except Exception as e:
            results.append(f"✗ {svc} ({str(e)[:50]})")

    return f"Synced {len(enabled_syncable)} service(s):\n" + "\n".join(results)


def fetch_url(url: str, timeout: int = 30) -> dict[str, Any]:
    """Fetch content from a URL and convert HTML to markdown format.

    This tool fetches web page content and converts it to clean markdown text,
    making it easy to read and process HTML content. After receiving the markdown,
    you MUST synthesize the information into a natural, helpful response for the user.

    Args:
        url: The URL to fetch (must be a valid HTTP/HTTPS URL)
        timeout: Request timeout in seconds (default: 30)

    Returns:
        Dictionary containing:
        - success: Whether the request succeeded
        - url: The final URL after redirects
        - markdown_content: The page content converted to markdown
        - status_code: HTTP status code
        - content_length: Length of the markdown content in characters

    IMPORTANT: After using this tool:
    1. Read through the markdown content
    2. Extract relevant information that answers the user's question
    3. Synthesize this into a clear, natural language response
    4. NEVER show the raw markdown to the user unless specifically requested
    """
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DeepAgents/1.0)"},
        )
        response.raise_for_status()

        # Convert HTML content to markdown
        markdown_content = markdownify(response.text)

        return {
            "url": str(response.url),
            "markdown_content": markdown_content,
            "status_code": response.status_code,
            "content_length": len(markdown_content),
        }
    except Exception as e:
        return {"error": f"Fetch URL error: {e!s}", "url": url}
