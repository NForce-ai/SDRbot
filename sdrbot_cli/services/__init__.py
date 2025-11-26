"""Services module - CRM integrations and tools.

This module provides:
- Service registry and configuration management
- Tool loading based on enabled services
- Schema sync and code generation for CRM integrations
"""

from typing import List

from langchain_core.tools import BaseTool

# All available services
SERVICES = ["hubspot", "salesforce", "attio", "lusha", "hunter"]

# Services that require schema sync (have user-specific schemas)
SYNCABLE_SERVICES = ["hubspot", "salesforce", "attio"]


def get_enabled_tools() -> List[BaseTool]:
    """Get all tools from enabled services.

    Returns:
        List of LangChain tools from all enabled services.
    """
    from sdrbot_cli.services.registry import load_config

    config = load_config()
    tools = []

    for service_name in SERVICES:
        if not config.is_enabled(service_name):
            continue

        # Import service module and get its tools
        try:
            service_module = __import__(
                f"sdrbot_cli.services.{service_name}",
                fromlist=["get_tools"]
            )
            if hasattr(service_module, "get_tools"):
                service_tools = service_module.get_tools()
                tools.extend(service_tools)
        except ImportError as e:
            # Log warning but continue
            import sys
            print(f"Warning: Could not load {service_name}: {e}", file=sys.stderr)

    return tools


__all__ = [
    "SERVICES",
    "SYNCABLE_SERVICES",
    "get_enabled_tools",
]
