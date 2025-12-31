"""Twenty CRM service - Open source CRM integration tools."""

import re

from langchain_core.tools import BaseTool

from sdrbot_cli.config import settings
from sdrbot_cli.tools import SCOPE_EXTENDED, SCOPE_METADATA_KEY

# Standard objects - tools for these remain in "standard" scope
# All other objects are "extended" scope
STANDARD_OBJECTS = {"person", "company", "opportunity", "note", "task"}


def _extract_object_from_tool_name(tool_name: str) -> str | None:
    """Extract object name from a generated tool name.

    Examples:
        twenty_create_person -> person
        twenty_update_company -> company
        twenty_search_customobj -> customobj
    """
    match = re.match(r"twenty_(?:create|update|search|get|delete)_(.+)", tool_name)
    return match.group(1) if match else None


def get_tools() -> list[BaseTool]:
    """Get all Twenty tools (static + generated + privileged).

    Note: Privileged tools are always returned here but filtered out
    at the global level by get_enabled_tools() based on current scope.

    Returns:
        List of Twenty tools available for the agent.
    """
    tools = []

    # Static tools (always available when service is enabled - standard scope)
    from sdrbot_cli.services.twenty.tools import get_static_tools

    tools.extend(get_static_tools())

    # Generated tools (if synced) - loaded from ./generated/twenty_tools.py
    generated_path = settings.get_generated_dir() / "twenty_tools.py"
    if generated_path.exists():
        try:
            # Create a namespace for the generated code
            namespace = {"__name__": "twenty_generated", "__file__": str(generated_path)}
            exec(generated_path.read_text(), namespace)

            # Extract tools from namespace and set scope based on object
            for name, obj in namespace.items():
                if name.startswith("twenty_") and isinstance(obj, BaseTool):
                    # Set scope based on object type
                    obj_name = _extract_object_from_tool_name(name)
                    if obj_name and obj_name not in STANDARD_OBJECTS:
                        # Non-standard objects get extended scope
                        if obj.metadata is None:
                            obj.metadata = {}
                        obj.metadata[SCOPE_METADATA_KEY] = SCOPE_EXTENDED
                    tools.append(obj)
        except Exception:
            pass  # Failed to load generated tools - only static tools available

    # Privileged tools (metadata operations for schema management)
    # These are marked as privileged and filtered by get_enabled_tools()
    from sdrbot_cli.services.twenty.admin_tools import get_admin_tools

    tools.extend(get_admin_tools())

    return tools


__all__ = ["get_tools"]
