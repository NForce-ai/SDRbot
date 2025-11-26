"""Attio service - CRM integration tools."""

from typing import List

from langchain_core.tools import BaseTool


def get_tools() -> List[BaseTool]:
    """Get all Attio tools (static + generated).

    Returns:
        List of Attio tools available for the agent.
    """
    tools = []

    # Static tools (always available when service is enabled)
    from sdrbot_cli.services.attio.tools import get_static_tools
    tools.extend(get_static_tools())

    # Generated tools (if synced)
    try:
        from sdrbot_cli.services.attio import tools_generated
        for name in dir(tools_generated):
            if not name.startswith("attio_"):
                continue
            obj = getattr(tools_generated, name)
            # Check if it's a LangChain tool (BaseTool instance)
            if isinstance(obj, BaseTool):
                tools.append(obj)
    except ImportError:
        pass  # Not synced yet - only static tools available

    return tools


__all__ = ["get_tools"]
