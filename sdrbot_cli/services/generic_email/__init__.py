"""Generic Email service using IMAP/SMTP.

Works with any email provider that supports IMAP/SMTP including:
- Yahoo Mail, AOL, iCloud
- ProtonMail (via Bridge)
- Fastmail, Zoho Mail
- Custom/corporate servers
"""

from langchain_core.tools import BaseTool

from .tools import get_static_tools


def get_tools() -> list[BaseTool]:
    """Get all generic email tools."""
    return get_static_tools()


__all__ = ["get_tools"]
