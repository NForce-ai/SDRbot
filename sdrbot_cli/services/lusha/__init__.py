"""Lusha service - prospecting and enrichment tools.

Lusha does not have user-specific schemas, so all tools are static.
No sync required.
"""

from typing import List

from langchain_core.tools import BaseTool


def get_tools() -> List[BaseTool]:
    """Get all Lusha tools.

    Returns:
        List of Lusha tools available for the agent.
    """
    from sdrbot_cli.services.lusha.tools import get_static_tools
    return get_static_tools()


__all__ = ["get_tools"]
