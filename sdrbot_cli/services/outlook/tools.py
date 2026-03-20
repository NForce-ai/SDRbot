"""Outlook email tools using Microsoft Graph API.

Outlook is an email service - all tools are static (no schema sync required).
"""

import base64
import json
import mimetypes
import os

import requests
from langchain_core.tools import BaseTool, tool

from sdrbot_cli.auth import outlook as outlook_auth

BASE_URL = "https://graph.microsoft.com/v1.0"


def _headers() -> dict:
    """Get authorization headers."""
    headers = outlook_auth.get_headers()
    if not headers:
        raise RuntimeError("Outlook not authenticated. Run /setup to configure Outlook.")
    headers["Content-Type"] = "application/json"
    return headers


def _extract_body(message: dict) -> str:
    """Extract body content from message, preferring text over HTML."""
    body = message.get("body", {})
    content = body.get("content", "")
    content_type = body.get("contentType", "text")

    if content_type == "html":
        # Basic HTML stripping for readability
        import re

        text = re.sub(r"<[^>]+>", "", content)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    return content


# Graph API limit for inline attachments in a JSON request body.
# Files larger than this must use an upload session.
_MAX_INLINE_BYTES = 3 * 1024 * 1024  # 3 MB (conservative, limit is 4 MB)

# Upload sessions accept chunks between 320 KiB and 4 MiB (must be 320 KiB-aligned).
_UPLOAD_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB – keeps round-trips low


def _validated_paths(file_paths: list[str]) -> list[str]:
    """Validate and return cleaned attachment paths."""
    paths: list[str] = []
    for file_path in file_paths:
        path = file_path.strip()
        if not path:
            continue
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Attachment not found: {path}")
        paths.append(path)
    return paths


def _build_small_attachments(paths: list[str]) -> list[dict]:
    """Build inline Graph API attachment objects for small files."""
    result = []
    for path in paths:
        if os.path.getsize(path) > _MAX_INLINE_BYTES:
            continue  # skip – handled by upload session
        content_type, _ = mimetypes.guess_type(path)
        if content_type is None:
            content_type = "application/octet-stream"
        with open(path, "rb") as f:
            content_bytes = base64.b64encode(f.read()).decode("utf-8")
        result.append(
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": os.path.basename(path),
                "contentType": content_type,
                "contentBytes": content_bytes,
            }
        )
    return result


def _upload_large_attachment(headers: dict, message_id: str, path: str) -> None:
    """Upload a large file to a message via an upload session.

    Uses the Graph API ``createUploadSession`` endpoint and streams the
    file in ≤4 MiB chunks.
    """
    file_size = os.path.getsize(path)
    file_name = os.path.basename(path)
    content_type, _ = mimetypes.guess_type(path)
    if content_type is None:
        content_type = "application/octet-stream"

    # 1. Create the upload session
    session_body = {
        "AttachmentItem": {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": file_name,
            "size": file_size,
            "contentType": content_type,
        }
    }
    session_resp = requests.post(
        f"{BASE_URL}/me/messages/{message_id}/attachments/createUploadSession",
        headers=headers,
        json=session_body,
    )
    if not session_resp.ok:
        raise RuntimeError(
            f"Failed to create upload session for {file_name}: "
            f"{session_resp.status_code} - {session_resp.text}"
        )
    upload_url = session_resp.json()["uploadUrl"]

    # 2. Upload in chunks
    with open(path, "rb") as f:
        offset = 0
        while offset < file_size:
            chunk = f.read(_UPLOAD_CHUNK_SIZE)
            chunk_len = len(chunk)
            end = offset + chunk_len - 1
            put_headers = {
                "Content-Type": "application/octet-stream",
                "Content-Length": str(chunk_len),
                "Content-Range": f"bytes {offset}-{end}/{file_size}",
            }
            put_resp = requests.put(upload_url, headers=put_headers, data=chunk)
            if not put_resp.ok:
                raise RuntimeError(
                    f"Upload chunk failed for {file_name}: {put_resp.status_code} - {put_resp.text}"
                )
            offset += chunk_len


def _has_large_files(paths: list[str]) -> bool:
    """Return True if any path exceeds the inline-attachment limit."""
    return any(os.path.getsize(p) > _MAX_INLINE_BYTES for p in paths)


def _attach_files_to_message(headers: dict, message_id: str, paths: list[str]) -> None:
    """Upload all large files in *paths* to an existing draft message."""
    for path in paths:
        if os.path.getsize(path) > _MAX_INLINE_BYTES:
            _upload_large_attachment(headers, message_id, path)


@tool
def outlook_search_emails(query: str = "", max_results: int = 10) -> str:
    """
    Search or list emails from Outlook.

    If no query is provided, lists most recent emails sorted by date.

    Examples of search queries:
    - from:user@example.com - Emails from a specific sender
    - subject:meeting - Emails with 'meeting' in subject
    - hasAttachments:true - Emails with attachments
    - importance:high - High importance emails

    Note: When using search, results cannot be sorted by date (Microsoft API limitation).
    To get newest emails, call with empty query.

    Args:
        query: Search query string (optional). Leave empty to list recent emails.
        max_results: Maximum number of results (default 10, max 100).

    Returns:
        List of matching emails with id, subject, from, date, and preview.
    """
    try:
        headers = _headers()

        params = {
            "$top": min(max_results, 100),
            "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead,importance",
        }

        if query:
            # Using $search - cannot combine with $orderby
            params["$search"] = f'"{query}"'
        else:
            # No query - list recent emails, can use $orderby
            params["$orderby"] = "receivedDateTime desc"

        resp = requests.get(f"{BASE_URL}/me/messages", headers=headers, params=params)

        if not resp.ok:
            return f"Error searching emails: {resp.status_code} - {resp.text}"

        messages = resp.json().get("value", [])
        if not messages:
            return "No emails found" + (f" matching query: {query}" if query else "")

        results = []
        for msg in messages:
            from_addr = msg.get("from", {}).get("emailAddress", {})
            results.append(
                {
                    "id": msg["id"],
                    "subject": msg.get("subject", "(no subject)"),
                    "from": f"{from_addr.get('name', '')} <{from_addr.get('address', '')}>",
                    "date": msg.get("receivedDateTime", ""),
                    "preview": msg.get("bodyPreview", "")[:150],
                    "isRead": msg.get("isRead", False),
                    "importance": msg.get("importance", "normal"),
                }
            )

        return json.dumps(results, indent=2)

    except Exception as e:
        return f"Error searching emails: {e}"


@tool
def outlook_read_email(message_id: str) -> str:
    """
    Read the full content of an email by its message ID.

    Use outlook_search_emails first to find message IDs.

    Args:
        message_id: The Outlook message ID to read.

    Returns:
        Full email content including headers and body.
    """
    try:
        headers = _headers()
        resp = requests.get(f"{BASE_URL}/me/messages/{message_id}", headers=headers)

        if not resp.ok:
            return f"Error reading email: {resp.status_code} - {resp.text}"

        msg = resp.json()
        from_addr = msg.get("from", {}).get("emailAddress", {})
        to_recipients = [
            f"{r.get('emailAddress', {}).get('name', '')} <{r.get('emailAddress', {}).get('address', '')}>"
            for r in msg.get("toRecipients", [])
        ]
        cc_recipients = [
            f"{r.get('emailAddress', {}).get('name', '')} <{r.get('emailAddress', {}).get('address', '')}>"
            for r in msg.get("ccRecipients", [])
        ]

        body = _extract_body(msg)

        result = {
            "id": msg["id"],
            "conversationId": msg.get("conversationId"),
            "subject": msg.get("subject", "(no subject)"),
            "from": f"{from_addr.get('name', '')} <{from_addr.get('address', '')}>",
            "to": to_recipients,
            "cc": cc_recipients if cc_recipients else None,
            "date": msg.get("receivedDateTime"),
            "isRead": msg.get("isRead"),
            "importance": msg.get("importance"),
            "hasAttachments": msg.get("hasAttachments"),
            "body": body[:5000] if body else "(no body content)",
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return f"Error reading email: {e}"


@tool
def outlook_send_email(
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
        content_type: Body format - "html" for HTML content (default) or "text" for plain text.
        attachments: File paths to attach, separated by commas (optional).

    Returns:
        Confirmation that the email was sent.
    """
    try:
        headers = _headers()

        # Build recipient lists
        to_recipients = [
            {"emailAddress": {"address": addr.strip()}} for addr in to.split(",") if addr.strip()
        ]
        cc_recipients = (
            [{"emailAddress": {"address": addr.strip()}} for addr in cc.split(",") if addr.strip()]
            if cc
            else []
        )
        bcc_recipients = (
            [{"emailAddress": {"address": addr.strip()}} for addr in bcc.split(",") if addr.strip()]
            if bcc
            else []
        )

        paths = _validated_paths(attachments.split(",")) if attachments else []

        # If any file is too large for inline JSON, use draft → upload → send.
        if paths and _has_large_files(paths):
            msg_body = {
                "subject": subject,
                "body": {"contentType": content_type, "content": body},
                "toRecipients": to_recipients,
            }
            if cc_recipients:
                msg_body["ccRecipients"] = cc_recipients
            if bcc_recipients:
                msg_body["bccRecipients"] = bcc_recipients

            # Inline the small attachments directly on the draft.
            small = _build_small_attachments(paths)
            if small:
                msg_body["attachments"] = small

            draft_resp = requests.post(
                f"{BASE_URL}/me/messages",
                headers=headers,
                json=msg_body,
            )
            if not draft_resp.ok:
                return (
                    f"Error creating draft for send: {draft_resp.status_code} - {draft_resp.text}"
                )

            draft_id = draft_resp.json()["id"]
            _attach_files_to_message(headers, draft_id, paths)

            send_resp = requests.post(
                f"{BASE_URL}/me/messages/{draft_id}/send",
                headers=headers,
            )
            if not send_resp.ok:
                return f"Error sending email: {send_resp.status_code} - {send_resp.text}"

            return "Email sent successfully."

        # --- Standard path: everything fits in a single JSON request ---
        message = {
            "message": {
                "subject": subject,
                "body": {"contentType": content_type, "content": body},
                "toRecipients": to_recipients,
            }
        }

        if cc_recipients:
            message["message"]["ccRecipients"] = cc_recipients
        if bcc_recipients:
            message["message"]["bccRecipients"] = bcc_recipients

        if paths:
            message["message"]["attachments"] = _build_small_attachments(paths)

        resp = requests.post(
            f"{BASE_URL}/me/sendMail",
            headers=headers,
            json=message,
        )

        if not resp.ok:
            return f"Error sending email: {resp.status_code} - {resp.text}"

        return "Email sent successfully."

    except Exception as e:
        return f"Error sending email: {e}"


@tool
def outlook_reply_to_email(
    message_id: str, body: str, reply_all: bool = False, send: bool = False
) -> str:
    """
    Reply to a received email. Creates a draft reply by default.

    Args:
        message_id: The message ID to reply to.
        body: Reply body text.
        reply_all: If True, reply to all recipients (default False).
        send: If True, send the reply immediately. If False, save as draft (default False).

    Returns:
        Confirmation with the draft or sent reply details.
    """
    try:
        headers = _headers()

        if send:
            endpoint = "replyAll" if reply_all else "reply"
            payload = {"comment": body}

            resp = requests.post(
                f"{BASE_URL}/me/messages/{message_id}/{endpoint}",
                headers=headers,
                json=payload,
            )

            if not resp.ok:
                return f"Error sending reply: {resp.status_code} - {resp.text}"

            return f"Reply sent successfully (reply_all={reply_all})."
        else:
            endpoint = "createReplyAll" if reply_all else "createReply"

            resp = requests.post(
                f"{BASE_URL}/me/messages/{message_id}/{endpoint}",
                headers=headers,
                json={},
            )

            if not resp.ok:
                return f"Error creating reply draft: {resp.status_code} - {resp.text}"

            draft = resp.json()
            draft_id = draft.get("id")

            # Update the draft body with the user's reply
            update_resp = requests.patch(
                f"{BASE_URL}/me/messages/{draft_id}",
                headers=headers,
                json={"body": {"contentType": "html", "content": body}},
            )

            if not update_resp.ok:
                return f"Reply draft created (ID: {draft_id}) but failed to update body: {update_resp.status_code} - {update_resp.text}"

            return f"Reply draft created successfully. Draft ID: {draft_id}"

    except Exception as e:
        action = "sending" if send else "drafting"
        return f"Error {action} reply: {e}"


@tool
def outlook_followup_email(
    message_id: str,
    body: str,
    content_type: str = "html",
    send: bool = False,
) -> str:
    """
    Follow up on a previously sent email. Creates a threaded draft by default.

    Use this when you sent an email and the recipient hasn't replied — it sends
    the follow-up to the original recipients (To/Cc) and keeps it in the same
    conversation thread.

    Args:
        message_id: The message ID of the sent email to follow up on.
        body: Follow-up body content.
        content_type: Body format - "html" for HTML content (default) or "text" for plain text.
        send: If True, send immediately. If False, save as draft (default False).

    Returns:
        Confirmation with the draft or sent follow-up details.
    """
    try:
        headers = _headers()

        # Fetch the original sent message to get recipients and conversation context
        orig_resp = requests.get(
            f"{BASE_URL}/me/messages/{message_id}",
            headers=headers,
            params={"$select": "subject,toRecipients,ccRecipients,conversationId,body"},
        )

        if not orig_resp.ok:
            return f"Error fetching original email: {orig_resp.status_code} - {orig_resp.text}"

        orig = orig_resp.json()
        to_recipients = orig.get("toRecipients", [])
        cc_recipients = orig.get("ccRecipients", [])

        if not to_recipients:
            return "Error: could not determine original recipients from sent message"

        # Build subject with Re: prefix
        orig_subject = orig.get("subject", "")
        if not orig_subject.lower().startswith("re:"):
            subject = f"Re: {orig_subject}"
        else:
            subject = orig_subject

        # Build quoted body
        orig_body = orig.get("body", {})
        orig_content = orig_body.get("content", "")
        if content_type == "html" and orig_content:
            full_body = (
                f"{body}"
                f"<br><br>"
                f'<blockquote style="margin:0 0 0 0.8ex;border-left:1px solid #ccc;padding-left:1ex">'
                f"{orig_content}"
                f"</blockquote>"
            )
        else:
            full_body = body

        # Create the follow-up message as a draft
        message = {
            "subject": subject,
            "body": {"contentType": content_type, "content": full_body},
            "toRecipients": to_recipients,
        }
        if cc_recipients:
            message["ccRecipients"] = cc_recipients

        # Link to same conversation
        conversation_id = orig.get("conversationId")
        if conversation_id:
            message["conversationId"] = conversation_id

        resp = requests.post(
            f"{BASE_URL}/me/messages",
            headers=headers,
            json=message,
        )

        if not resp.ok:
            return f"Error creating follow-up draft: {resp.status_code} - {resp.text}"

        draft = resp.json()
        draft_id = draft.get("id")

        if send:
            send_resp = requests.post(
                f"{BASE_URL}/me/messages/{draft_id}/send",
                headers=headers,
            )
            if not send_resp.ok:
                return f"Follow-up draft created (ID: {draft_id}) but failed to send: {send_resp.status_code} - {send_resp.text}"
            return "Follow-up sent successfully."
        else:
            return f"Follow-up draft created successfully. Draft ID: {draft_id}"

    except Exception as e:
        action = "sending" if send else "drafting"
        return f"Error {action} follow-up: {e}"


@tool
def outlook_create_draft(
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
        content_type: Body format - "html" for HTML content (default) or "text" for plain text.
        attachments: File paths to attach, separated by commas (optional).

    Returns:
        Confirmation with the draft ID.
    """
    try:
        headers = _headers()

        to_recipients = [
            {"emailAddress": {"address": addr.strip()}} for addr in to.split(",") if addr.strip()
        ]
        cc_recipients = (
            [{"emailAddress": {"address": addr.strip()}} for addr in cc.split(",") if addr.strip()]
            if cc
            else []
        )
        bcc_recipients = (
            [{"emailAddress": {"address": addr.strip()}} for addr in bcc.split(",") if addr.strip()]
            if bcc
            else []
        )

        paths = _validated_paths(attachments.split(",")) if attachments else []

        message = {
            "subject": subject,
            "body": {"contentType": content_type, "content": body},
            "toRecipients": to_recipients,
        }

        if cc_recipients:
            message["ccRecipients"] = cc_recipients
        if bcc_recipients:
            message["bccRecipients"] = bcc_recipients

        # Inline only the small attachments on the initial create.
        if paths:
            small = _build_small_attachments(paths)
            if small:
                message["attachments"] = small

        resp = requests.post(
            f"{BASE_URL}/me/messages",
            headers=headers,
            json=message,
        )

        if not resp.ok:
            return f"Error creating draft: {resp.status_code} - {resp.text}"

        result = resp.json()
        draft_id = result["id"]

        # Upload large attachments via upload sessions.
        if paths and _has_large_files(paths):
            _attach_files_to_message(headers, draft_id, paths)

        return f"Draft created successfully. Draft ID: {draft_id}"

    except Exception as e:
        return f"Error creating draft: {e}"


@tool
def outlook_schedule_email(
    to: str,
    subject: str,
    body: str,
    send_at: str,
    cc: str = "",
    bcc: str = "",
    content_type: str = "html",
    attachments: str = "",
) -> str:
    """
    Schedule an email to be sent at a future time.

    The email is created with a deferred delivery time and moved to Outbox.
    Outlook will automatically send it at the specified time.

    Args:
        to: Recipient email address (required). For multiple recipients, separate with commas.
        subject: Email subject line (required).
        body: Email body content.
        send_at: When to send the email in ISO 8601 format (e.g., "2024-12-25T09:00:00Z").
                 Must be in UTC timezone. Example: "2024-01-15T14:30:00Z" for 2:30 PM UTC.
        cc: CC recipients (optional). Separate multiple with commas.
        bcc: BCC recipients (optional). Separate multiple with commas.
        content_type: Body format - "html" for HTML content (default) or "text" for plain text.
        attachments: File paths to attach, separated by commas (optional).

    Returns:
        Confirmation that the email was scheduled.
    """
    try:
        headers = _headers()

        # Build recipient lists
        to_recipients = [
            {"emailAddress": {"address": addr.strip()}} for addr in to.split(",") if addr.strip()
        ]
        cc_recipients = (
            [{"emailAddress": {"address": addr.strip()}} for addr in cc.split(",") if addr.strip()]
            if cc
            else []
        )
        bcc_recipients = (
            [{"emailAddress": {"address": addr.strip()}} for addr in bcc.split(",") if addr.strip()]
            if bcc
            else []
        )

        paths = _validated_paths(attachments.split(",")) if attachments else []

        # Create message with deferred send time using extended property
        # PidTagDeferredSendTime property tag: 0x3FEF, type: SystemTime
        message = {
            "subject": subject,
            "body": {"contentType": content_type, "content": body},
            "toRecipients": to_recipients,
            "singleValueExtendedProperties": [
                {
                    "id": "SystemTime 0x3FEF",
                    "value": send_at,
                }
            ],
        }

        if cc_recipients:
            message["ccRecipients"] = cc_recipients
        if bcc_recipients:
            message["bccRecipients"] = bcc_recipients

        # Inline only small attachments.
        if paths:
            small = _build_small_attachments(paths)
            if small:
                message["attachments"] = small

        # Create the draft with deferred send time
        resp = requests.post(
            f"{BASE_URL}/me/messages",
            headers=headers,
            json=message,
        )

        if not resp.ok:
            return f"Error creating scheduled email: {resp.status_code} - {resp.text}"

        draft = resp.json()
        draft_id = draft["id"]

        # Upload large attachments via upload sessions.
        if paths and _has_large_files(paths):
            _attach_files_to_message(headers, draft_id, paths)

        # Get the Outbox folder ID
        outbox_resp = requests.get(
            f"{BASE_URL}/me/mailFolders/outbox",
            headers=headers,
        )

        if not outbox_resp.ok:
            return f"Error getting Outbox folder: {outbox_resp.status_code} - {outbox_resp.text}"

        outbox_id = outbox_resp.json()["id"]

        # Move to Outbox - Outlook will send at the deferred time
        move_resp = requests.post(
            f"{BASE_URL}/me/messages/{draft_id}/move",
            headers=headers,
            json={"destinationId": outbox_id},
        )

        if not move_resp.ok:
            return f"Error scheduling email: {move_resp.status_code} - {move_resp.text}"

        return f"Email scheduled successfully to be sent at {send_at}."

    except Exception as e:
        return f"Error scheduling email: {e}"


@tool
def outlook_send_draft(draft_id: str, send_at: str = "") -> str:
    """
    Send an existing draft, optionally scheduling it for later.

    Args:
        draft_id: The message ID of the draft to send.
        send_at: Optional. Schedule send time in ISO 8601 format (e.g., "2024-12-25T09:00:00Z").
                 If not provided, sends immediately.

    Returns:
        Confirmation that the draft was sent or scheduled.
    """
    try:
        headers = _headers()

        if send_at:
            # Add deferred send time to the draft
            patch_resp = requests.patch(
                f"{BASE_URL}/me/messages/{draft_id}",
                headers=headers,
                json={
                    "singleValueExtendedProperties": [
                        {
                            "id": "SystemTime 0x3FEF",
                            "value": send_at,
                        }
                    ]
                },
            )

            if not patch_resp.ok:
                return f"Error updating draft: {patch_resp.status_code} - {patch_resp.text}"

            # Get the Outbox folder ID
            outbox_resp = requests.get(
                f"{BASE_URL}/me/mailFolders/outbox",
                headers=headers,
            )

            if not outbox_resp.ok:
                return (
                    f"Error getting Outbox folder: {outbox_resp.status_code} - {outbox_resp.text}"
                )

            outbox_id = outbox_resp.json()["id"]

            # Move to Outbox for scheduled delivery
            move_resp = requests.post(
                f"{BASE_URL}/me/messages/{draft_id}/move",
                headers=headers,
                json={"destinationId": outbox_id},
            )

            if not move_resp.ok:
                return f"Error scheduling draft: {move_resp.status_code} - {move_resp.text}"

            return f"Draft scheduled successfully to be sent at {send_at}."
        else:
            # Send immediately
            send_resp = requests.post(
                f"{BASE_URL}/me/messages/{draft_id}/send",
                headers=headers,
            )

            if not send_resp.ok:
                return f"Error sending draft: {send_resp.status_code} - {send_resp.text}"

            return "Draft sent successfully."

    except Exception as e:
        return f"Error sending draft: {e}"


@tool
def outlook_list_folder_emails(folder: str = "inbox", max_results: int = 10) -> str:
    """
    List emails from a specific folder.

    Common folder names: Inbox, Drafts, SentItems, DeletedItems, Archive, JunkEmail, Outbox

    Args:
        folder: Folder name (default: inbox). Use "Outbox" to see scheduled emails.
        max_results: Maximum number of results (default 10).

    Returns:
        List of emails in the folder with id, subject, from, date, and preview.
    """
    try:
        headers = _headers()

        # Map common folder names to well-known folder names
        well_known_folders = {
            "inbox": "inbox",
            "drafts": "drafts",
            "sentitems": "sentitems",
            "sent": "sentitems",
            "deleteditems": "deleteditems",
            "deleted": "deleteditems",
            "trash": "deleteditems",
            "archive": "archive",
            "junkemail": "junkemail",
            "junk": "junkemail",
            "spam": "junkemail",
            "outbox": "outbox",
        }

        folder_key = folder.lower().replace(" ", "")
        folder_path = well_known_folders.get(folder_key, folder)

        params = {
            "$top": min(max_results, 100),
            "$select": "id,subject,from,toRecipients,receivedDateTime,createdDateTime,bodyPreview,isRead",
            "$orderby": "createdDateTime desc",
        }

        resp = requests.get(
            f"{BASE_URL}/me/mailFolders/{folder_path}/messages",
            headers=headers,
            params=params,
        )

        if not resp.ok:
            return f"Error listing folder emails: {resp.status_code} - {resp.text}"

        messages = resp.json().get("value", [])
        if not messages:
            return f"No emails found in {folder}"

        results = []
        for msg in messages:
            from_addr = msg.get("from", {}).get("emailAddress", {})
            to_addrs = [
                r.get("emailAddress", {}).get("address", "") for r in msg.get("toRecipients", [])
            ]
            results.append(
                {
                    "id": msg["id"],
                    "subject": msg.get("subject", "(no subject)"),
                    "from": f"{from_addr.get('name', '')} <{from_addr.get('address', '')}>".strip(),
                    "to": ", ".join(to_addrs),
                    "created": msg.get("createdDateTime", ""),
                    "preview": msg.get("bodyPreview", "")[:150],
                }
            )

        return json.dumps(results, indent=2)

    except Exception as e:
        return f"Error listing folder emails: {e}"


@tool
def outlook_list_folders() -> str:
    """
    List all mail folders.

    Returns:
        List of folders with their IDs and display names.
    """
    try:
        headers = _headers()
        resp = requests.get(f"{BASE_URL}/me/mailFolders", headers=headers)

        if not resp.ok:
            return f"Error listing folders: {resp.status_code} - {resp.text}"

        folders = resp.json().get("value", [])

        results = []
        for folder in folders:
            results.append(
                {
                    "id": folder["id"],
                    "name": folder["displayName"],
                    "totalItems": folder.get("totalItemCount", 0),
                    "unreadItems": folder.get("unreadItemCount", 0),
                }
            )

        return json.dumps(results, indent=2)

    except Exception as e:
        return f"Error listing folders: {e}"


@tool
def outlook_move_email(message_id: str, destination_folder: str) -> str:
    """
    Move an email to a different folder.

    Common folder names: Inbox, Drafts, SentItems, DeletedItems, Archive, JunkEmail

    Args:
        message_id: The message ID to move.
        destination_folder: Folder name or ID to move to.

    Returns:
        Confirmation that the email was moved.
    """
    try:
        headers = _headers()

        # Check if destination is a well-known folder name or an ID
        well_known_folders = {
            "inbox": "inbox",
            "drafts": "drafts",
            "sentitems": "sentitems",
            "deleteditems": "deleteditems",
            "archive": "archive",
            "junkemail": "junkemail",
        }

        folder_key = destination_folder.lower().replace(" ", "")
        if folder_key in well_known_folders:
            # Get the folder ID for well-known folder
            folder_resp = requests.get(
                f"{BASE_URL}/me/mailFolders/{well_known_folders[folder_key]}",
                headers=headers,
            )
            if folder_resp.ok:
                destination_id = folder_resp.json()["id"]
            else:
                destination_id = destination_folder
        else:
            destination_id = destination_folder

        resp = requests.post(
            f"{BASE_URL}/me/messages/{message_id}/move",
            headers=headers,
            json={"destinationId": destination_id},
        )

        if not resp.ok:
            return f"Error moving email: {resp.status_code} - {resp.text}"

        return f"Email moved to {destination_folder} successfully."

    except Exception as e:
        return f"Error moving email: {e}"


@tool
def outlook_mark_read(message_id: str, is_read: bool = True) -> str:
    """
    Mark an email as read or unread.

    Args:
        message_id: The message ID to update.
        is_read: True to mark as read, False to mark as unread (default True).

    Returns:
        Confirmation of the update.
    """
    try:
        headers = _headers()

        resp = requests.patch(
            f"{BASE_URL}/me/messages/{message_id}",
            headers=headers,
            json={"isRead": is_read},
        )

        if not resp.ok:
            return f"Error updating email: {resp.status_code} - {resp.text}"

        status = "read" if is_read else "unread"
        return f"Email marked as {status}."

    except Exception as e:
        return f"Error updating email: {e}"


@tool
def outlook_delete_email(message_id: str) -> str:
    """
    Delete an email (moves to Deleted Items).

    Args:
        message_id: The message ID to delete.

    Returns:
        Confirmation that the email was deleted.
    """
    try:
        headers = _headers()

        resp = requests.delete(f"{BASE_URL}/me/messages/{message_id}", headers=headers)

        if not resp.ok:
            return f"Error deleting email: {resp.status_code} - {resp.text}"

        return f"Email {message_id} deleted (moved to Deleted Items)."

    except Exception as e:
        return f"Error deleting email: {e}"


@tool
def outlook_get_conversation(conversation_id: str, max_results: int = 25) -> str:
    """
    Get all messages in an email conversation/thread.

    Args:
        conversation_id: The conversation ID (available from outlook_read_email).
        max_results: Maximum number of messages to return (default 25).

    Returns:
        List of all messages in the conversation.
    """
    try:
        headers = _headers()

        params = {
            "$filter": f"conversationId eq '{conversation_id}'",
            "$top": max_results,
            "$orderby": "receivedDateTime asc",
            "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead",
        }

        resp = requests.get(f"{BASE_URL}/me/messages", headers=headers, params=params)

        if not resp.ok:
            return f"Error getting conversation: {resp.status_code} - {resp.text}"

        messages = resp.json().get("value", [])

        results = []
        for msg in messages:
            from_addr = msg.get("from", {}).get("emailAddress", {})
            results.append(
                {
                    "id": msg["id"],
                    "from": f"{from_addr.get('name', '')} <{from_addr.get('address', '')}>",
                    "date": msg.get("receivedDateTime"),
                    "subject": msg.get("subject"),
                    "preview": msg.get("bodyPreview", "")[:150],
                    "isRead": msg.get("isRead"),
                }
            )

        return json.dumps({"conversationId": conversation_id, "messages": results}, indent=2)

    except Exception as e:
        return f"Error getting conversation: {e}"


def get_static_tools() -> list[BaseTool]:
    """Get all Outlook tools."""
    return [
        outlook_search_emails,
        outlook_read_email,
        outlook_send_email,
        outlook_reply_to_email,
        outlook_followup_email,
        outlook_create_draft,
        outlook_send_draft,
        outlook_schedule_email,
        outlook_list_folders,
        outlook_list_folder_emails,
        outlook_move_email,
        outlook_mark_read,
        outlook_delete_email,
        outlook_get_conversation,
    ]
