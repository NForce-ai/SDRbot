"""Twenty CRM service - Open source CRM integration tools."""

from langchain_core.tools import BaseTool

from sdrbot_cli.config import settings


def get_tools() -> list[BaseTool]:
    """Get all Twenty tools (static + generated).

    Returns:
        List of Twenty tools available for the agent.
    """
    tools = []

    # Static tools (always available when service is enabled)
    from sdrbot_cli.services.twenty.tools import get_static_tools

    tools.extend(get_static_tools())

    # Generated tools (if synced) - loaded from ./generated/twenty_tools.py
    generated_path = settings.get_generated_dir() / "twenty_tools.py"
    if generated_path.exists():
        try:
            # Create a namespace for the generated code
            namespace = {"__name__": "twenty_generated", "__file__": str(generated_path)}
            exec(generated_path.read_text(), namespace)

            # Extract tools from namespace
            for name, obj in namespace.items():
                if name.startswith("twenty_") and isinstance(obj, BaseTool):
                    tools.append(obj)
        except Exception:
            pass  # Failed to load generated tools - only static tools available

    return tools


__all__ = ["get_tools"]
