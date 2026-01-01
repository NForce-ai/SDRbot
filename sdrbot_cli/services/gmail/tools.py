"""Gmail email tools.

Gmail is an email service - all tools are static (no schema sync required).
"""

import base64
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from langchain_core.tools import BaseTool, tool

from sdrbot_cli.auth import gmail as gmail_auth

BASE_URL = "https://gmail.googleapis.com/gmail/v1"


def _headers() -> dict:
    """Get authorization headers."""
    headers = gmail_auth.get_headers()
    if not headers:
        raise RuntimeError("Gmail not authenticated. Run /setup to configure Gmail.")
    return headers


def _parse_email_body(payload: dict) -> str:
    """Extract plain text body from email payload.

    Gmail API returns email bodies in a nested structure that varies
    depending on the email format (plain, html, multipart).
    """
    # Direct body data
    if "body" in payload and payload["body"].get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")

    # Multipart - look for text/plain first, then text/html
    if "parts" in payload:
        for part in payload["parts"]:
            mime_type = part.get("mimeType", "")
            if mime_type == "text/plain" and part.get("body", {}).get("data"):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")

        # Fallback to HTML if no plain text
        for part in payload["parts"]:
            mime_type = part.get("mimeType", "")
            if mime_type == "text/html" and part.get("body", {}).get("data"):
                html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                # Basic HTML stripping (for readability in chat)
                import re

                text = re.sub(r"<[^>]+>", "", html)
                text = re.sub(r"\s+", " ", text).strip()
                return text

        # Recursive check for nested multipart
        for part in payload["parts"]:
            if "parts" in part:
                result = _parse_email_body(part)
                if result:
                    return result

    return ""


@tool
def gmail_search_emails(query: str, max_results: int = 10) -> str:
    """
    Search emails using Gmail query syntax.

    Examples of query syntax:
    - from:user@example.com - Emails from a specific sender
    - to:user@example.com - Emails to a specific recipient
    - subject:meeting - Emails with 'meeting' in subject
    - is:unread - Unread emails
    - is:starred - Starred emails
    - has:attachment - Emails with attachments
    - after:2024/01/01 - Emails after a date
    - before:2024/12/31 - Emails before a date
    - label:important - Emails with a specific label
    - newer_than:7d - Emails from last 7 days
    - older_than:1m - Emails older than 1 month

    You can combine queries: "from:boss@company.com subject:urgent is:unread"

    Args:
        query: Gmail search query string.
        max_results: Maximum number of results (default 10, max 100).

    Returns:
        List of matching emails with id, subject, from, date, and snippet.
    """
    try:
        headers = _headers()
        resp = requests.get(
            f"{BASE_URL}/users/me/messages",
            headers=headers,
            params={"q": query, "maxResults": min(max_results, 100)},
        )

        if not resp.ok:
            return f"Error searching emails: {resp.status_code} - {resp.text}"

        messages = resp.json().get("messages", [])
        if not messages:
            return f"No emails found matching query: {query}"

        results = []
        for msg in messages[:max_results]:
            detail_resp = requests.get(
                f"{BASE_URL}/users/me/messages/{msg['id']}",
                headers=headers,
                params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            )
            if not detail_resp.ok:
                continue

            detail = detail_resp.json()
            headers_dict = {
                h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])
            }
            results.append(
                {
                    "id": msg["id"],
                    "threadId": detail.get("threadId"),
                    "subject": headers_dict.get("Subject", "(no subject)"),
                    "from": headers_dict.get("From", ""),
                    "date": headers_dict.get("Date", ""),
                    "snippet": detail.get("snippet", "")[:150],
                }
            )

        return json.dumps(results, indent=2)

    except Exception as e:
        return f"Error searching emails: {e}"


@tool
def gmail_read_email(message_id: str) -> str:
    """
    Read the full content of an email by its message ID.

    Use gmail_search_emails first to find message IDs.

    Args:
        message_id: The Gmail message ID to read.

    Returns:
        Full email content including headers and body.
    """
    try:
        headers = _headers()
        resp = requests.get(
            f"{BASE_URL}/users/me/messages/{message_id}",
            headers=headers,
            params={"format": "full"},
        )

        if not resp.ok:
            return f"Error reading email: {resp.status_code} - {resp.text}"

        data = resp.json()
        payload = data.get("payload", {})
        headers_list = payload.get("headers", [])
        headers_dict = {h["name"]: h["value"] for h in headers_list}

        body = _parse_email_body(payload)

        result = {
            "id": data["id"],
            "threadId": data.get("threadId"),
            "subject": headers_dict.get("Subject", "(no subject)"),
            "from": headers_dict.get("From"),
            "to": headers_dict.get("To"),
            "cc": headers_dict.get("Cc"),
            "date": headers_dict.get("Date"),
            "labels": data.get("labelIds", []),
            "body": body[:5000] if body else "(no body content)",
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return f"Error reading email: {e}"


@tool
def gmail_send_email(to: str, subject: str, body: str, cc: str = "", bcc: str = "") -> str:
    """
    Send an email.

    Args:
        to: Recipient email address (required). For multiple recipients, separate with commas.
        subject: Email subject line (required).
        body: Email body text (plain text).
        cc: CC recipients (optional). Separate multiple with commas.
        bcc: BCC recipients (optional). Separate multiple with commas.

    Returns:
        Confirmation with the sent message ID.
    """
    try:
        headers = _headers()

        message = MIMEMultipart()
        message["to"] = to
        message["subject"] = subject
        if cc:
            message["cc"] = cc
        if bcc:
            message["bcc"] = bcc
        message.attach(MIMEText(body, "plain"))

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        resp = requests.post(
            f"{BASE_URL}/users/me/messages/send",
            headers=headers,
            json={"raw": raw},
        )

        if not resp.ok:
            return f"Error sending email: {resp.status_code} - {resp.text}"

        result = resp.json()
        return f"Email sent successfully. Message ID: {result['id']}"

    except Exception as e:
        return f"Error sending email: {e}"


@tool
def gmail_reply_to_email(
    message_id: str, body: str, reply_all: bool = False, include_quote: bool = True
) -> str:
    """
    Reply to an existing email.

    Args:
        message_id: The message ID to reply to.
        body: Reply body text.
        reply_all: If True, reply to all recipients (default False).
        include_quote: If True, include original message in reply (default True).

    Returns:
        Confirmation with the sent reply message ID.
    """
    try:
        headers = _headers()

        # Get original message for thread context
        orig_resp = requests.get(
            f"{BASE_URL}/users/me/messages/{message_id}",
            headers=headers,
            params={"format": "full"},
        )

        if not orig_resp.ok:
            return f"Error fetching original email: {orig_resp.status_code}"

        orig_data = orig_resp.json()
        orig_headers = {
            h["name"]: h["value"] for h in orig_data.get("payload", {}).get("headers", [])
        }

        # Build reply recipients
        reply_to = orig_headers.get("Reply-To") or orig_headers.get("From", "")

        cc = ""
        if reply_all:
            # Include original To and Cc, excluding self
            orig_to = orig_headers.get("To", "")
            orig_cc = orig_headers.get("Cc", "")
            all_recipients = f"{orig_to},{orig_cc}".strip(",")
            if all_recipients:
                cc = all_recipients

        # Build subject with Re: prefix
        orig_subject = orig_headers.get("Subject", "")
        if not orig_subject.lower().startswith("re:"):
            subject = f"Re: {orig_subject}"
        else:
            subject = orig_subject

        # Build message body with quote if requested
        full_body = body
        if include_quote:
            orig_body = _parse_email_body(orig_data.get("payload", {}))
            orig_date = orig_headers.get("Date", "")
            orig_from = orig_headers.get("From", "")
            if orig_body:
                quoted = "\n".join(f"> {line}" for line in orig_body[:2000].split("\n"))
                full_body = f"{body}\n\nOn {orig_date}, {orig_from} wrote:\n{quoted}"

        message = MIMEMultipart()
        message["to"] = reply_to
        message["subject"] = subject
        if cc:
            message["cc"] = cc

        # Set threading headers
        message_id_header = orig_headers.get("Message-ID", "")
        if message_id_header:
            message["In-Reply-To"] = message_id_header
            message["References"] = message_id_header

        message.attach(MIMEText(full_body, "plain"))
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        resp = requests.post(
            f"{BASE_URL}/users/me/messages/send",
            headers=headers,
            json={"raw": raw, "threadId": orig_data.get("threadId")},
        )

        if not resp.ok:
            return f"Error sending reply: {resp.status_code} - {resp.text}"

        result = resp.json()
        return f"Reply sent successfully. Message ID: {result['id']}"

    except Exception as e:
        return f"Error sending reply: {e}"


@tool
def gmail_create_draft(to: str, subject: str, body: str, cc: str = "", bcc: str = "") -> str:
    """
    Create an email draft without sending.

    Args:
        to: Recipient email address (required).
        subject: Email subject line (required).
        body: Email body text.
        cc: CC recipients (optional).
        bcc: BCC recipients (optional).

    Returns:
        Confirmation with the draft ID.
    """
    try:
        headers = _headers()

        message = MIMEMultipart()
        message["to"] = to
        message["subject"] = subject
        if cc:
            message["cc"] = cc
        if bcc:
            message["bcc"] = bcc
        message.attach(MIMEText(body, "plain"))

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        resp = requests.post(
            f"{BASE_URL}/users/me/drafts",
            headers=headers,
            json={"message": {"raw": raw}},
        )

        if not resp.ok:
            return f"Error creating draft: {resp.status_code} - {resp.text}"

        result = resp.json()
        return f"Draft created successfully. Draft ID: {result['id']}"

    except Exception as e:
        return f"Error creating draft: {e}"


@tool
def gmail_list_labels() -> str:
    """
    List all Gmail labels (folders/categories).

    Returns:
        List of labels with their IDs and types.
    """
    try:
        headers = _headers()
        resp = requests.get(f"{BASE_URL}/users/me/labels", headers=headers)

        if not resp.ok:
            return f"Error listing labels: {resp.status_code} - {resp.text}"

        labels = resp.json().get("labels", [])

        # Group by type for better readability
        system_labels = []
        user_labels = []

        for label in labels:
            label_info = {
                "id": label["id"],
                "name": label["name"],
                "type": label.get("type", "user"),
            }
            if label.get("type") == "system":
                system_labels.append(label_info)
            else:
                user_labels.append(label_info)

        return json.dumps(
            {"system_labels": system_labels, "user_labels": user_labels},
            indent=2,
        )

    except Exception as e:
        return f"Error listing labels: {e}"


@tool
def gmail_modify_labels(
    message_id: str,
    add_labels: str = "",
    remove_labels: str = "",
) -> str:
    """
    Add or remove labels from an email.

    Common label IDs:
    - INBOX - Main inbox
    - STARRED - Starred messages
    - IMPORTANT - Important messages
    - UNREAD - Mark as unread
    - SPAM - Spam folder
    - TRASH - Trash folder

    Args:
        message_id: The message ID to modify.
        add_labels: Comma-separated label IDs to add (e.g., "STARRED,IMPORTANT").
        remove_labels: Comma-separated label IDs to remove (e.g., "UNREAD").

    Returns:
        Confirmation of the label changes.
    """
    try:
        headers = _headers()

        modify_request = {}
        if add_labels:
            modify_request["addLabelIds"] = [label.strip() for label in add_labels.split(",")]
        if remove_labels:
            modify_request["removeLabelIds"] = [label.strip() for label in remove_labels.split(",")]

        if not modify_request:
            return "Error: Specify at least one label to add or remove."

        resp = requests.post(
            f"{BASE_URL}/users/me/messages/{message_id}/modify",
            headers=headers,
            json=modify_request,
        )

        if not resp.ok:
            return f"Error modifying labels: {resp.status_code} - {resp.text}"

        result = resp.json()
        return f"Labels modified successfully. Current labels: {result.get('labelIds', [])}"

    except Exception as e:
        return f"Error modifying labels: {e}"


@tool
def gmail_trash_email(message_id: str) -> str:
    """
    Move an email to trash.

    Args:
        message_id: The message ID to trash.

    Returns:
        Confirmation that the email was trashed.
    """
    try:
        headers = _headers()
        resp = requests.post(
            f"{BASE_URL}/users/me/messages/{message_id}/trash",
            headers=headers,
        )

        if not resp.ok:
            return f"Error trashing email: {resp.status_code} - {resp.text}"

        return f"Email {message_id} moved to trash."

    except Exception as e:
        return f"Error trashing email: {e}"


@tool
def gmail_get_thread(thread_id: str) -> str:
    """
    Get all messages in an email thread/conversation.

    Args:
        thread_id: The thread ID (available from gmail_search_emails or gmail_read_email).

    Returns:
        List of all messages in the thread.
    """
    try:
        headers = _headers()
        resp = requests.get(
            f"{BASE_URL}/users/me/threads/{thread_id}",
            headers=headers,
            params={"format": "full"},
        )

        if not resp.ok:
            return f"Error getting thread: {resp.status_code} - {resp.text}"

        thread = resp.json()
        messages = thread.get("messages", [])

        results = []
        for msg in messages:
            payload = msg.get("payload", {})
            headers_dict = {h["name"]: h["value"] for h in payload.get("headers", [])}
            body = _parse_email_body(payload)

            results.append(
                {
                    "id": msg["id"],
                    "from": headers_dict.get("From"),
                    "to": headers_dict.get("To"),
                    "date": headers_dict.get("Date"),
                    "subject": headers_dict.get("Subject"),
                    "snippet": msg.get("snippet", "")[:150],
                    "body": body[:2000] if body else "(no body)",
                }
            )

        return json.dumps({"threadId": thread_id, "messages": results}, indent=2)

    except Exception as e:
        return f"Error getting thread: {e}"


def get_static_tools() -> list[BaseTool]:
    """Get all Gmail tools.

    Returns:
        List of Gmail tools (all static, no generated tools).
    """
    return [
        gmail_search_emails,
        gmail_read_email,
        gmail_send_email,
        gmail_reply_to_email,
        gmail_create_draft,
        gmail_list_labels,
        gmail_modify_labels,
        gmail_trash_email,
        gmail_get_thread,
    ]
