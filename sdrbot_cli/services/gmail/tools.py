"""Gmail email tools.

Gmail is an email service - all tools are static (no schema sync required).
"""

import base64
import json
import mimetypes
import os
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from langchain_core.tools import BaseTool, tool

from sdrbot_cli.auth import gmail as gmail_auth

BASE_URL = "https://gmail.googleapis.com/gmail/v1"
UPLOAD_URL = "https://www.googleapis.com/upload/gmail/v1"

# Gmail API limit for simple JSON-body requests is ~5 MB encoded.
# Beyond this we switch to multipart upload.
_MAX_SIMPLE_BYTES = 4 * 1024 * 1024  # 4 MB (conservative)


def _headers() -> dict:
    """Get authorization headers."""
    headers = gmail_auth.get_headers()
    if not headers:
        raise RuntimeError("Gmail not authenticated. Run /setup to configure Gmail.")
    return headers


def _gmail_api_request(
    endpoint: str,
    message: MIMEMultipart,
    extra_json: dict | None = None,
) -> requests.Response:
    """Send a MIME message to a Gmail API endpoint.

    Automatically chooses between a simple JSON request (small messages) and
    a multipart media upload (large messages / big attachments).

    Args:
        endpoint: API path *after* ``/users/me/``, e.g. ``"messages/send"``
                  or ``"drafts"``.
        message:  Fully-built MIME message.
        extra_json: Extra top-level JSON keys (e.g. ``{"threadId": "…"}``).
                    For drafts the raw payload is nested under ``message``.
    """
    headers = _headers()
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    is_draft = endpoint.startswith("drafts")
    body_json: dict = {}
    if extra_json:
        body_json.update(extra_json)

    if is_draft:
        # For drafts, threadId and raw must be inside the "message" object
        msg_obj = body_json.pop("message", {})
        msg_obj["raw"] = raw
        if "threadId" in body_json:
            msg_obj["threadId"] = body_json.pop("threadId")
        body_json["message"] = msg_obj
    else:
        body_json["raw"] = raw

    # If the encoded payload is small enough, use a plain JSON request.
    if len(raw) < _MAX_SIMPLE_BYTES:
        return requests.post(
            f"{BASE_URL}/users/me/{endpoint}",
            headers=headers,
            json=body_json,
        )

    # --- Large message: use multipart media upload ---
    import uuid

    boundary = f"==={uuid.uuid4().hex}==="

    # For multipart upload the JSON metadata should NOT contain "raw";
    # the raw RFC-822 bytes go in the second part instead.
    metadata: dict = {}
    if is_draft:
        # Draft resource wraps the message; strip "raw" from inner dict.
        inner = dict(body_json.get("message", {}))
        inner.pop("raw", None)
        if inner:
            metadata["message"] = inner
        # Preserve any top-level draft fields (there usually aren't any).
        for k, v in body_json.items():
            if k != "message":
                metadata[k] = v
    else:
        metadata = {k: v for k, v in body_json.items() if k != "raw"}

    metadata_bytes = json.dumps(metadata).encode() if metadata else b"{}"
    rfc822_bytes = message.as_bytes()

    # Build the multipart/related body: part 1 = JSON metadata,
    # part 2 = raw RFC-822 message bytes.
    parts: list[bytes] = []
    parts.append(f"--{boundary}".encode())
    parts.append(b"Content-Type: application/json; charset=UTF-8")
    parts.append(b"")
    parts.append(metadata_bytes)
    parts.append(f"--{boundary}".encode())
    parts.append(b"Content-Type: message/rfc822")
    parts.append(b"")
    parts.append(rfc822_bytes)
    parts.append(f"--{boundary}--".encode())
    body_bytes = b"\r\n".join(parts)

    upload_headers = {
        **headers,
        "Content-Type": f'multipart/related; boundary="{boundary}"',
        "Content-Length": str(len(body_bytes)),
    }

    url = f"{UPLOAD_URL}/users/me/{endpoint}?uploadType=multipart"
    return requests.post(url, headers=upload_headers, data=body_bytes)


def _attach_files(message: MIMEMultipart, file_paths: list[str]) -> None:
    """Attach files to a MIME message."""
    for file_path in file_paths:
        path = file_path.strip()
        if not path:
            continue
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Attachment not found: {path}")
        content_type, _ = mimetypes.guess_type(path)
        if content_type is None:
            content_type = "application/octet-stream"
        main_type, sub_type = content_type.split("/", 1)
        with open(path, "rb") as f:
            part = MIMEBase(main_type, sub_type)
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=os.path.basename(path))
        message.attach(part)


def _parse_email_body(payload: dict, prefer_html: bool = False) -> str:
    """Extract body from email payload.

    Gmail API returns email bodies in a nested structure that varies
    depending on the email format (plain, html, multipart).

    Args:
        payload: Gmail API message payload.
        prefer_html: If True, return raw HTML when available (for HTML quoting).
                     If False, return plain text (converting HTML if needed).
    """
    # Direct body data
    if "body" in payload and payload["body"].get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")

    if "parts" in payload:
        if prefer_html:
            # Try HTML first
            for part in payload["parts"]:
                mime_type = part.get("mimeType", "")
                if mime_type == "text/html" and part.get("body", {}).get("data"):
                    return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")

            # Fall back to plain text wrapped in HTML
            for part in payload["parts"]:
                mime_type = part.get("mimeType", "")
                if mime_type == "text/plain" and part.get("body", {}).get("data"):
                    import html as html_mod

                    text = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                    return "<p>" + html_mod.escape(text).replace("\n", "<br>") + "</p>"
        else:
            # Try plain text first
            for part in payload["parts"]:
                mime_type = part.get("mimeType", "")
                if mime_type == "text/plain" and part.get("body", {}).get("data"):
                    return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")

            # Fallback to HTML converted to plain text
            for part in payload["parts"]:
                mime_type = part.get("mimeType", "")
                if mime_type == "text/html" and part.get("body", {}).get("data"):
                    html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                    import re

                    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
                    text = re.sub(r"</(?:p|div|tr|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
                    text = re.sub(r"<[^>]+>", "", text)
                    text = re.sub(r"[^\S\n]+", " ", text)
                    text = re.sub(r"\n{3,}", "\n\n", text).strip()
                    return text

        # Recursive check for nested multipart
        for part in payload["parts"]:
            if "parts" in part:
                result = _parse_email_body(part, prefer_html=prefer_html)
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
def gmail_send_email(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    content_type: str = "html",
    attachments: str = "",
) -> str:
    """
    Send an email.

    Args:
        to: Recipient email address (required). For multiple recipients, separate with commas.
        subject: Email subject line (required).
        body: Email body content.
        cc: CC recipients (optional). Separate multiple with commas.
        bcc: BCC recipients (optional). Separate multiple with commas.
        content_type: Body format - "html" for HTML content (default) or "plain" for plain text.
        attachments: File paths to attach, separated by commas (optional).

    Returns:
        Confirmation with the sent message ID.
    """
    try:
        message = MIMEMultipart()
        message["to"] = to
        message["subject"] = subject
        if cc:
            message["cc"] = cc
        if bcc:
            message["bcc"] = bcc
        message.attach(MIMEText(body, content_type))

        if attachments:
            _attach_files(message, attachments.split(","))

        resp = _gmail_api_request("messages/send", message)

        if not resp.ok:
            return f"Error sending email: {resp.status_code} - {resp.text}"

        result = resp.json()
        return f"Email sent successfully. Message ID: {result['id']}"

    except Exception as e:
        return f"Error sending email: {e}"


@tool
def gmail_reply_to_email(
    message_id: str,
    body: str,
    reply_all: bool = False,
    include_quote: bool = True,
    content_type: str = "html",
    attachments: str = "",
    send: bool = False,
) -> str:
    """
    Reply to a received email. Creates a draft reply by default.

    Args:
        message_id: The message ID to reply to.
        body: Reply body content.
        reply_all: If True, reply to all recipients (default False).
        include_quote: If True, include original message in reply (default True).
        content_type: Body format - "html" for HTML content (default) or "plain" for plain text.
        attachments: File paths to attach, separated by commas (optional).
        send: If True, send the reply immediately. If False, save as draft (default False).

    Returns:
        Confirmation with the draft or sent reply message ID.
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
            orig_date = orig_headers.get("Date", "")
            orig_from = orig_headers.get("From", "")
            if content_type == "html":
                orig_body = _parse_email_body(orig_data.get("payload", {}), prefer_html=True)
                if orig_body:
                    full_body = (
                        f"{body}"
                        f"<br><br>"
                        f"<div>On {orig_date}, {orig_from} wrote:</div>"
                        f'<blockquote style="margin:0 0 0 0.8ex;border-left:1px solid #ccc;padding-left:1ex">'
                        f"{orig_body}"
                        f"</blockquote>"
                    )
            else:
                orig_body = _parse_email_body(orig_data.get("payload", {}))
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

        message.attach(MIMEText(full_body, content_type))

        if attachments:
            _attach_files(message, attachments.split(","))

        thread_id = orig_data.get("threadId")
        endpoint = "messages/send" if send else "drafts"
        resp = _gmail_api_request(
            endpoint,
            message,
            extra_json={"threadId": thread_id} if thread_id else None,
        )

        if not resp.ok:
            action = "sending" if send else "drafting"
            return f"Error {action} reply: {resp.status_code} - {resp.text}"

        result = resp.json()
        if send:
            return f"Reply sent successfully. Message ID: {result['id']}"
        else:
            return f"Reply draft created successfully. Draft ID: {result['id']}"

    except Exception as e:
        action = "sending" if send else "drafting"
        return f"Error {action} reply: {e}"


@tool
def gmail_followup_email(
    message_id: str,
    body: str,
    include_quote: bool = True,
    content_type: str = "html",
    attachments: str = "",
    send: bool = False,
) -> str:
    """
    Follow up on a previously sent email. Creates a threaded draft by default.

    Use this when you sent an email and the recipient hasn't replied — it sends
    the follow-up to the original recipients (To/Cc) and keeps it in the same
    thread.

    Args:
        message_id: The message ID of the sent email to follow up on.
        body: Follow-up body content.
        include_quote: If True, include original message in follow-up (default True).
        content_type: Body format - "html" for HTML content (default) or "plain" for plain text.
        attachments: File paths to attach, separated by commas (optional).
        send: If True, send immediately. If False, save as draft (default False).

    Returns:
        Confirmation with the draft or sent follow-up message ID.
    """
    try:
        headers = _headers()

        # Get original sent message
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

        # Follow-up goes to original recipients, not back to sender
        to = orig_headers.get("To", "")
        cc = orig_headers.get("Cc", "")

        if not to:
            return "Error: could not determine original recipients from sent message"

        # Build subject with Re: prefix
        orig_subject = orig_headers.get("Subject", "")
        if not orig_subject.lower().startswith("re:"):
            subject = f"Re: {orig_subject}"
        else:
            subject = orig_subject

        # Build message body with quote if requested
        full_body = body
        if include_quote:
            orig_date = orig_headers.get("Date", "")
            orig_from = orig_headers.get("From", "")
            if content_type == "html":
                orig_body = _parse_email_body(orig_data.get("payload", {}), prefer_html=True)
                if orig_body:
                    full_body = (
                        f"{body}"
                        f"<br><br>"
                        f"<div>On {orig_date}, {orig_from} wrote:</div>"
                        f'<blockquote style="margin:0 0 0 0.8ex;border-left:1px solid #ccc;padding-left:1ex">'
                        f"{orig_body}"
                        f"</blockquote>"
                    )
            else:
                orig_body = _parse_email_body(orig_data.get("payload", {}))
                if orig_body:
                    quoted = "\n".join(f"> {line}" for line in orig_body[:2000].split("\n"))
                    full_body = f"{body}\n\nOn {orig_date}, {orig_from} wrote:\n{quoted}"

        message = MIMEMultipart()
        message["to"] = to
        message["subject"] = subject
        if cc:
            message["cc"] = cc

        # Set threading headers
        message_id_header = orig_headers.get("Message-ID", "")
        if message_id_header:
            message["In-Reply-To"] = message_id_header
            message["References"] = message_id_header

        message.attach(MIMEText(full_body, content_type))

        if attachments:
            _attach_files(message, attachments.split(","))

        thread_id = orig_data.get("threadId")
        endpoint = "messages/send" if send else "drafts"
        resp = _gmail_api_request(
            endpoint,
            message,
            extra_json={"threadId": thread_id} if thread_id else None,
        )

        if not resp.ok:
            action = "sending" if send else "drafting"
            return f"Error {action} follow-up: {resp.status_code} - {resp.text}"

        result = resp.json()
        if send:
            return f"Follow-up sent successfully. Message ID: {result['id']}"
        else:
            return f"Follow-up draft created successfully. Draft ID: {result['id']}"

    except Exception as e:
        action = "sending" if send else "drafting"
        return f"Error {action} follow-up: {e}"


@tool
def gmail_create_draft(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    content_type: str = "html",
    attachments: str = "",
) -> str:
    """
    Create an email draft without sending.

    Args:
        to: Recipient email address (required).
        subject: Email subject line (required).
        body: Email body content.
        cc: CC recipients (optional).
        bcc: BCC recipients (optional).
        content_type: Body format - "html" for HTML content (default) or "plain" for plain text.
        attachments: File paths to attach, separated by commas (optional).

    Returns:
        Confirmation with the draft ID.
    """
    try:
        message = MIMEMultipart()
        message["to"] = to
        message["subject"] = subject
        if cc:
            message["cc"] = cc
        if bcc:
            message["bcc"] = bcc
        message.attach(MIMEText(body, content_type))

        if attachments:
            _attach_files(message, attachments.split(","))

        resp = _gmail_api_request("drafts", message)

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
        gmail_followup_email,
        gmail_create_draft,
        gmail_list_labels,
        gmail_modify_labels,
        gmail_trash_email,
        gmail_get_thread,
    ]
