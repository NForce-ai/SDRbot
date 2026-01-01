"""Generic Email Authentication using IMAP/SMTP.

Supports any email provider with IMAP/SMTP access including:
- Yahoo Mail
- AOL
- ProtonMail (via Bridge)
- iCloud
- Custom/corporate servers
"""

import imaplib
import os
import smtplib
import ssl
from dataclasses import dataclass

from sdrbot_cli.config import COLORS, console


@dataclass
class IMAPConfig:
    """IMAP connection configuration."""

    host: str
    port: int
    username: str
    password: str
    use_ssl: bool = True


@dataclass
class SMTPConfig:
    """SMTP connection configuration."""

    host: str
    port: int
    username: str
    password: str
    use_ssl: bool = True


# Provider presets for common email services
PROVIDER_PRESETS = {
    "yahoo": {
        "name": "Yahoo Mail",
        "imap_host": "imap.mail.yahoo.com",
        "imap_port": 993,
        "smtp_host": "smtp.mail.yahoo.com",
        "smtp_port": 465,
        "use_ssl": True,
        "note": "Requires App Password (not regular password)",
    },
    "aol": {
        "name": "AOL Mail",
        "imap_host": "imap.aol.com",
        "imap_port": 993,
        "smtp_host": "smtp.aol.com",
        "smtp_port": 465,
        "use_ssl": True,
        "note": "Requires App Password",
    },
    "protonmail": {
        "name": "ProtonMail Bridge",
        "imap_host": "127.0.0.1",
        "imap_port": 1143,
        "smtp_host": "127.0.0.1",
        "smtp_port": 1025,
        "use_ssl": False,
        "note": "Requires ProtonMail Bridge running locally",
    },
    "icloud": {
        "name": "iCloud Mail",
        "imap_host": "imap.mail.me.com",
        "imap_port": 993,
        "smtp_host": "smtp.mail.me.com",
        "smtp_port": 587,
        "use_ssl": True,
        "note": "Requires App-Specific Password from Apple ID",
    },
    "fastmail": {
        "name": "Fastmail",
        "imap_host": "imap.fastmail.com",
        "imap_port": 993,
        "smtp_host": "smtp.fastmail.com",
        "smtp_port": 465,
        "use_ssl": True,
        "note": "Requires App Password",
    },
    "zoho": {
        "name": "Zoho Mail",
        "imap_host": "imap.zoho.com",
        "imap_port": 993,
        "smtp_host": "smtp.zoho.com",
        "smtp_port": 465,
        "use_ssl": True,
        "note": "Use Zoho account password or App Password",
    },
}


def get_imap_config() -> IMAPConfig | None:
    """Get IMAP configuration from environment variables."""
    host = os.getenv("IMAP_HOST")
    port = os.getenv("IMAP_PORT")
    username = os.getenv("IMAP_USER")
    password = os.getenv("IMAP_PASSWORD")

    if not all([host, port, username, password]):
        return None

    use_ssl = os.getenv("IMAP_SSL", "true").lower() in ("true", "1", "yes")

    return IMAPConfig(
        host=host,
        port=int(port),
        username=username,
        password=password,
        use_ssl=use_ssl,
    )


def get_smtp_config() -> SMTPConfig | None:
    """Get SMTP configuration from environment variables."""
    host = os.getenv("SMTP_HOST")
    port = os.getenv("SMTP_PORT")
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")

    if not all([host, port, username, password]):
        return None

    use_ssl = os.getenv("SMTP_SSL", "true").lower() in ("true", "1", "yes")

    return SMTPConfig(
        host=host,
        port=int(port),
        username=username,
        password=password,
        use_ssl=use_ssl,
    )


def is_configured() -> bool:
    """Check if generic email (IMAP/SMTP) is configured."""
    imap = get_imap_config()
    smtp = get_smtp_config()
    return imap is not None and smtp is not None


def get_imap_connection() -> imaplib.IMAP4 | imaplib.IMAP4_SSL | None:
    """Create and return an IMAP connection."""
    config = get_imap_config()
    if not config:
        console.print(
            f"[{COLORS['tool']}]IMAP not configured. "
            f"Set IMAP_HOST, IMAP_PORT, IMAP_USER, IMAP_PASSWORD.[/{COLORS['tool']}]"
        )
        return None

    try:
        if config.use_ssl:
            context = ssl.create_default_context()
            imap = imaplib.IMAP4_SSL(config.host, config.port, ssl_context=context)
        else:
            imap = imaplib.IMAP4(config.host, config.port)

        imap.login(config.username, config.password)
        return imap
    except Exception as e:
        console.print(f"[{COLORS['tool']}]IMAP connection failed: {e}[/{COLORS['tool']}]")
        return None


def get_smtp_connection() -> smtplib.SMTP | smtplib.SMTP_SSL | None:
    """Create and return an SMTP connection."""
    config = get_smtp_config()
    if not config:
        console.print(
            f"[{COLORS['tool']}]SMTP not configured. "
            f"Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD.[/{COLORS['tool']}]"
        )
        return None

    try:
        if config.use_ssl:
            context = ssl.create_default_context()
            # Port 465 uses implicit SSL, port 587 uses STARTTLS
            if config.port == 587:
                smtp = smtplib.SMTP(config.host, config.port)
                smtp.starttls(context=context)
            else:
                smtp = smtplib.SMTP_SSL(config.host, config.port, context=context)
        else:
            smtp = smtplib.SMTP(config.host, config.port)

        smtp.login(config.username, config.password)
        return smtp
    except Exception as e:
        console.print(f"[{COLORS['tool']}]SMTP connection failed: {e}[/{COLORS['tool']}]")
        return None


def _format_error(e: Exception) -> str:
    """Format exception message, handling bytes and cleaning up."""
    msg = str(e)
    # Handle bytes in error messages
    if msg.startswith("b'") or msg.startswith('b"'):
        msg = msg[2:-1]  # Strip b'...' wrapper
    # Clean up common IMAP error prefixes
    if "LOGIN" in msg:
        msg = msg.split("LOGIN", 1)[-1].strip()
    return msg


def test_imap() -> tuple[bool, str]:
    """Test IMAP connection only.

    Returns:
        Tuple of (success, message)
    """
    imap_config = get_imap_config()
    if not imap_config:
        missing = []
        if not os.getenv("IMAP_HOST"):
            missing.append("host")
        if not os.getenv("IMAP_PORT"):
            missing.append("port")
        if not os.getenv("IMAP_USER"):
            missing.append("user")
        if not os.getenv("IMAP_PASSWORD"):
            missing.append("password")
        return False, f"Missing: {', '.join(missing)}"

    try:
        if imap_config.use_ssl:
            context = ssl.create_default_context()
            imap = imaplib.IMAP4_SSL(imap_config.host, imap_config.port, ssl_context=context)
        else:
            imap = imaplib.IMAP4(imap_config.host, imap_config.port)
        imap.login(imap_config.username, imap_config.password)
        imap.logout()
        return True, "Connected"
    except Exception as e:
        return False, _format_error(e)


def test_smtp() -> tuple[bool, str]:
    """Test SMTP connection only.

    Returns:
        Tuple of (success, message)
    """
    smtp_config = get_smtp_config()
    if not smtp_config:
        missing = []
        if not os.getenv("SMTP_HOST"):
            missing.append("host")
        if not os.getenv("SMTP_PORT"):
            missing.append("port")
        if not os.getenv("SMTP_USER"):
            missing.append("user")
        if not os.getenv("SMTP_PASSWORD"):
            missing.append("password")
        return False, f"Missing: {', '.join(missing)}"

    try:
        if smtp_config.use_ssl:
            context = ssl.create_default_context()
            if smtp_config.port == 587:
                smtp = smtplib.SMTP(smtp_config.host, smtp_config.port)
                smtp.starttls(context=context)
            else:
                smtp = smtplib.SMTP_SSL(smtp_config.host, smtp_config.port, context=context)
        else:
            smtp = smtplib.SMTP(smtp_config.host, smtp_config.port)
        smtp.login(smtp_config.username, smtp_config.password)
        smtp.quit()
        return True, "Connected"
    except Exception as e:
        return False, _format_error(e)


def test_connection() -> tuple[bool, bool, str]:
    """Test both IMAP and SMTP connections.

    Returns:
        Tuple of (imap_ok, smtp_ok, message)
    """
    imap_ok, imap_msg = test_imap()
    smtp_ok, smtp_msg = test_smtp()
    return imap_ok, smtp_ok, f"IMAP: {imap_msg} | SMTP: {smtp_msg}"
