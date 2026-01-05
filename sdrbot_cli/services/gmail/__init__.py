"""Gmail service - email tools.

Gmail is an email service for reading, sending, and managing emails.
All tools are static (no schema sync required).
"""

from langchain_core.tools import BaseTool

from sdrbot_cli.services.gmail.tools import get_static_tools


def get_tools() -> list[BaseTool]:
    """Get all Gmail tools.

    Returns:
        List of Gmail tools (all static, no generated tools).
    """
    return get_static_tools()


__all__ = ["get_tools"]
