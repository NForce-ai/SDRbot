"""Apollo.io service - prospecting and enrichment tools.

Apollo is an enrichment/prospecting service like Lusha and Hunter.
All tools are static (no schema sync required).
"""

from langchain_core.tools import BaseTool

from sdrbot_cli.services.apollo.tools import get_static_tools


def get_tools() -> list[BaseTool]:
    """Get all Apollo tools.

    Returns:
        List of Apollo tools (all static, no generated tools).
    """
    return get_static_tools()


__all__ = ["get_tools"]
