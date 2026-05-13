"""Google Drive service - file storage tools.

Google Drive is a file storage service for listing, reading, uploading,
and managing files. All tools are static (no schema sync required).
"""

from langchain_core.tools import BaseTool

from sdrbot_cli.services.google_drive.tools import get_static_tools


def get_tools() -> list[BaseTool]:
    """Get all Google Drive tools.

    Returns:
        List of Google Drive tools (all static, no generated tools).
    """
    return get_static_tools()


__all__ = ["get_tools"]
