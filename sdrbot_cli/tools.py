"""Custom tools for the CLI agent."""

from collections.abc import Callable
from typing import Any

import requests
from langchain_core.tools import BaseTool
from langchain_core.tools import tool as langchain_tool
from markdownify import markdownify

PRIVILEGED_METADATA_KEY = "privileged"


def privileged_tool(func: Callable) -> BaseTool:
    """Decorator to create a privileged tool.

    Privileged tools are only available when privileged mode is enabled.
    They include schema/metadata management and code execution capabilities.

    Usage:
        @privileged_tool
        def my_admin_tool(arg: str) -> str:
            '''Tool docstring.'''
            return "result"

    The resulting tool will have metadata["privileged"] = True,
    which is checked during tool loading to filter out privileged tools
    when privileged mode is disabled.
    """
    # Create the tool using langchain's @tool decorator
    lc_tool = langchain_tool(func)
    # Mark it as privileged using the metadata field
    if lc_tool.metadata is None:
        lc_tool.metadata = {}
    lc_tool.metadata[PRIVILEGED_METADATA_KEY] = True
    return lc_tool


def is_privileged_tool(tool: BaseTool) -> bool:
    """Check if a tool is marked as privileged.

    Args:
        tool: A LangChain tool instance.

    Returns:
        True if the tool is privileged, False otherwise.
    """
    if tool.metadata is None:
        return False
    return tool.metadata.get(PRIVILEGED_METADATA_KEY, False)


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
