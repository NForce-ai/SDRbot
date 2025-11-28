"""Hunter.io service - email discovery and verification tools.

Hunter does not have user-specific schemas, so all tools are static.
No sync required.
"""

from langchain_core.tools import BaseTool


def get_tools() -> list[BaseTool]:
    """Get all Hunter tools.

    Returns:
        List of Hunter tools available for the agent.
    """
    from sdrbot_cli.services.hunter.tools import get_static_tools

    return get_static_tools()


__all__ = ["get_tools"]
