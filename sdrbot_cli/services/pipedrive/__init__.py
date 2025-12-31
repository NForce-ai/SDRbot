"""Pipedrive service - CRM integration tools."""

from langchain_core.tools import BaseTool

from sdrbot_cli.config import settings


def get_tools() -> list[BaseTool]:
    """Get all Pipedrive tools (static + generated + admin).

    Returns:
        List of Pipedrive tools available for the agent.
    """
    tools = []

    # Static tools (always available when service is enabled)
    from sdrbot_cli.services.pipedrive.tools import get_static_tools

    tools.extend(get_static_tools())

    # Generated tools (if synced) - loaded from ./generated/pipedrive_tools.py
    generated_path = settings.get_generated_dir() / "pipedrive_tools.py"
    if generated_path.exists():
        try:
            # Create a namespace for the generated code
            namespace = {"__name__": "pipedrive_generated", "__file__": str(generated_path)}
            exec(generated_path.read_text(), namespace)

            # Extract tools from namespace
            for name, obj in namespace.items():
                if name.startswith("pipedrive_") and isinstance(obj, BaseTool):
                    tools.append(obj)
        except Exception:
            pass  # Failed to load generated tools - only static tools available

    # Privileged admin tools (filtered by get_enabled_tools() based on privileged mode)
    from sdrbot_cli.services.pipedrive.admin_tools import get_admin_tools

    tools.extend(get_admin_tools())

    return tools


__all__ = ["get_tools"]
