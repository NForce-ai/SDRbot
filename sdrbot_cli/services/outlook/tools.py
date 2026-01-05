"""Outlook email tools using Microsoft Graph API.

Outlook is an email service - all tools are static (no schema sync required).
"""

import json

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
def outlook_send_email(to: str, subject: str, body: str, cc: str = "", bcc: str = "") -> str:
    """
    Send an email.

    Args:
        to: Recipient email address (required). For multiple recipients, separate with commas.
        subject: Email subject line (required).
        body: Email body text (plain text).
        cc: CC recipients (optional). Separate multiple with commas.
        bcc: BCC recipients (optional). Separate multiple with commas.

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

        message = {
            "message": {
                "subject": subject,
                "body": {"contentType": "text", "content": body},
                "toRecipients": to_recipients,
            }
        }

        if cc_recipients:
            message["message"]["ccRecipients"] = cc_recipients
        if bcc_recipients:
            message["message"]["bccRecipients"] = bcc_recipients

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
def outlook_reply_to_email(message_id: str, body: str, reply_all: bool = False) -> str:
    """
    Reply to an existing email.

    Args:
        message_id: The message ID to reply to.
        body: Reply body text.
        reply_all: If True, reply to all recipients (default False).

    Returns:
        Confirmation that the reply was sent.
    """
    try:
        headers = _headers()

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

    except Exception as e:
        return f"Error sending reply: {e}"


@tool
def outlook_create_draft(to: str, subject: str, body: str, cc: str = "", bcc: str = "") -> str:
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

        message = {
            "subject": subject,
            "body": {"contentType": "text", "content": body},
            "toRecipients": to_recipients,
        }

        if cc_recipients:
            message["ccRecipients"] = cc_recipients
        if bcc_recipients:
            message["bccRecipients"] = bcc_recipients

        resp = requests.post(
            f"{BASE_URL}/me/messages",
            headers=headers,
            json=message,
        )

        if not resp.ok:
            return f"Error creating draft: {resp.status_code} - {resp.text}"

        result = resp.json()
        return f"Draft created successfully. Draft ID: {result['id']}"

    except Exception as e:
        return f"Error creating draft: {e}"


@tool
def outlook_schedule_email(
    to: str, subject: str, body: str, send_at: str, cc: str = "", bcc: str = ""
) -> str:
    """
    Schedule an email to be sent at a future time.

    The email is created with a deferred delivery time and moved to Outbox.
    Outlook will automatically send it at the specified time.

    Args:
        to: Recipient email address (required). For multiple recipients, separate with commas.
        subject: Email subject line (required).
        body: Email body text (plain text).
        send_at: When to send the email in ISO 8601 format (e.g., "2024-12-25T09:00:00Z").
                 Must be in UTC timezone. Example: "2024-01-15T14:30:00Z" for 2:30 PM UTC.
        cc: CC recipients (optional). Separate multiple with commas.
        bcc: BCC recipients (optional). Separate multiple with commas.

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

        # Create message with deferred send time using extended property
        # PidTagDeferredSendTime property tag: 0x3FEF, type: SystemTime
        message = {
            "subject": subject,
            "body": {"contentType": "text", "content": body},
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
