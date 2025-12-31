"""Salesforce service - CRM integration tools."""

from langchain_core.tools import BaseTool

from sdrbot_cli.config import settings


def get_tools() -> list[BaseTool]:
    """Get all Salesforce tools (static + generated + admin).

    Returns:
        List of Salesforce tools available for the agent.
    """
    tools = []

    # Static tools (always available when service is enabled)
    from sdrbot_cli.services.salesforce.tools import get_static_tools

    tools.extend(get_static_tools())

    # Generated tools (if synced) - loaded from ./generated/salesforce_tools.py
    generated_path = settings.get_generated_dir() / "salesforce_tools.py"
    if generated_path.exists():
        try:
            # Create a namespace for the generated code
            namespace = {"__name__": "salesforce_generated", "__file__": str(generated_path)}
            exec(generated_path.read_text(), namespace)

            # Extract tools from namespace
            for name, obj in namespace.items():
                if name.startswith("salesforce_") and isinstance(obj, BaseTool):
                    tools.append(obj)
        except Exception:
            pass  # Failed to load generated tools - only static tools available

    # Admin tools (privileged - filtered by privileged mode setting)
    from sdrbot_cli.services.salesforce.admin_tools import get_admin_tools

    tools.extend(get_admin_tools())

    return tools


__all__ = ["get_tools"]
