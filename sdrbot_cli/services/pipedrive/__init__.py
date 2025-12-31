"""Pipedrive service - CRM integration tools."""

import re

from langchain_core.tools import BaseTool

from sdrbot_cli.config import settings
from sdrbot_cli.tools import SCOPE_EXTENDED, SCOPE_METADATA_KEY

# Standard objects - tools for these remain in "standard" scope
# All other objects are "extended" scope
STANDARD_OBJECTS = {"deal", "person", "organization"}


def _extract_object_from_tool_name(tool_name: str) -> str | None:
    """Extract object name from a generated tool name.

    Examples:
        pipedrive_create_deal -> deal
        pipedrive_update_person -> person
    """
    match = re.match(r"pipedrive_(?:create|update|search|get|delete)_(.+)", tool_name)
    return match.group(1) if match else None


def get_tools() -> list[BaseTool]:
    """Get all Pipedrive tools (static + generated + admin).

    Returns:
        List of Pipedrive tools available for the agent.
    """
    tools = []

    # Static tools (always available when service is enabled - standard scope)
    from sdrbot_cli.services.pipedrive.tools import get_static_tools

    tools.extend(get_static_tools())

    # Generated tools (if synced) - loaded from ./generated/pipedrive_tools.py
    generated_path = settings.get_generated_dir() / "pipedrive_tools.py"
    if generated_path.exists():
        try:
            # Create a namespace for the generated code
            namespace = {"__name__": "pipedrive_generated", "__file__": str(generated_path)}
            exec(generated_path.read_text(), namespace)

            # Extract tools from namespace and set scope based on object
            for name, obj in namespace.items():
                if name.startswith("pipedrive_") and isinstance(obj, BaseTool):
                    # Set scope based on object type
                    obj_name = _extract_object_from_tool_name(name)
                    if obj_name and obj_name not in STANDARD_OBJECTS:
                        if obj.metadata is None:
                            obj.metadata = {}
                        obj.metadata[SCOPE_METADATA_KEY] = SCOPE_EXTENDED
                    tools.append(obj)
        except Exception:
            pass  # Failed to load generated tools - only static tools available

    # Privileged admin tools (filtered by scope setting)
    from sdrbot_cli.services.pipedrive.admin_tools import get_admin_tools

    tools.extend(get_admin_tools())

    return tools


__all__ = ["get_tools"]
