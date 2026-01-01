"""Generic email tools using IMAP/SMTP.

Works with any email provider that supports IMAP/SMTP including:
- Yahoo Mail, AOL, iCloud
- ProtonMail (via Bridge)
- Fastmail, Zoho Mail
- Custom/corporate servers
"""

import email
import email.utils
import json
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from langchain_core.tools import BaseTool, tool

from sdrbot_cli.auth import generic_email as email_auth


def _decode_header_value(value: str | None) -> str:
    """Decode email header value handling various encodings."""
    if not value:
        return ""
    decoded_parts = []
    for part, charset in decode_header(value):
        if isinstance(part, bytes):
            charset = charset or "utf-8"
            try:
                decoded_parts.append(part.decode(charset, errors="replace"))
            except (LookupError, UnicodeDecodeError):
                decoded_parts.append(part.decode("utf-8", errors="replace"))
        else:
            decoded_parts.append(part)
    return " ".join(decoded_parts)


def _get_email_body(msg: email.message.Message) -> str:
    """Extract plain text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        return payload.decode(charset, errors="replace")
                    except (LookupError, UnicodeDecodeError):
                        return payload.decode("utf-8", errors="replace")
        # Fallback to HTML if no plain text
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        # Basic HTML stripping
                        import re

                        html = payload.decode(charset, errors="replace")
                        text = re.sub(r"<[^>]+>", "", html)
                        text = re.sub(r"\s+", " ", text).strip()
                        return text
                    except Exception:
                        pass
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                return payload.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                return payload.decode("utf-8", errors="replace")
    return ""


@tool
def email_list_folders() -> str:
    """
    List all mailbox folders.

    Returns:
        List of folder names available in the mailbox.
    """
    try:
        imap = email_auth.get_imap_connection()
        if not imap:
            return "Error: IMAP not configured or connection failed"

        try:
            status, folders = imap.list()
            if status != "OK":
                return f"Error listing folders: {status}"

            folder_names = []
            for folder in folders:
                if isinstance(folder, bytes):
                    # Parse folder response: (flags) "delimiter" "name"
                    parts = folder.decode("utf-8", errors="replace")
                    # Extract folder name (last quoted or unquoted part)
                    if '"' in parts:
                        name = parts.split('"')[-2]
                    else:
                        name = parts.split()[-1]
                    folder_names.append(name)

            return json.dumps({"folders": folder_names}, indent=2)
        finally:
            imap.logout()

    except Exception as e:
        return f"Error listing folders: {e}"


@tool
def email_list_folder(folder: str = "INBOX", max_results: int = 10) -> str:
    """
    List emails from a specific folder.

    Args:
        folder: Folder name (default: INBOX). Common folders: INBOX, Sent, Drafts, Trash.
        max_results: Maximum number of emails to return (default 10).

    Returns:
        List of emails with uid, subject, from, date, and preview.
    """
    try:
        imap = email_auth.get_imap_connection()
        if not imap:
            return "Error: IMAP not configured or connection failed"

        try:
            status, _ = imap.select(folder)
            if status != "OK":
                return f"Error selecting folder '{folder}': folder may not exist"

            # Search for all emails and get the most recent ones
            status, messages = imap.search(None, "ALL")
            if status != "OK":
                return f"Error searching folder: {status}"

            message_nums = messages[0].split()
            if not message_nums:
                return f"No emails found in {folder}"

            # Get most recent emails (last N)
            recent_nums = message_nums[-max_results:]
            recent_nums.reverse()  # Newest first

            results = []
            for num in recent_nums:
                # Fetch headers only for speed
                status, data = imap.fetch(num, "(UID BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                if status != "OK" or not data or not data[0]:
                    continue

                # Parse the response
                if isinstance(data[0], tuple):
                    uid_part = data[0][0].decode("utf-8", errors="replace")
                    header_data = data[0][1]

                    # Extract UID from response
                    uid = ""
                    if b"UID" in data[0][0]:
                        import re

                        uid_match = re.search(r"UID (\d+)", uid_part)
                        if uid_match:
                            uid = uid_match.group(1)

                    # Parse headers
                    msg = email.message_from_bytes(header_data)
                    results.append(
                        {
                            "uid": uid,
                            "seq": num.decode() if isinstance(num, bytes) else str(num),
                            "subject": _decode_header_value(msg.get("Subject")),
                            "from": _decode_header_value(msg.get("From")),
                            "date": msg.get("Date", ""),
                        }
                    )

            return json.dumps(results, indent=2)
        finally:
            imap.logout()

    except Exception as e:
        return f"Error listing folder: {e}"


@tool
def email_search(query: str, folder: str = "INBOX", max_results: int = 10) -> str:
    """
    Search emails using IMAP search criteria.

    Examples of search queries:
    - FROM "sender@example.com" - Emails from a specific sender
    - SUBJECT "meeting" - Emails with 'meeting' in subject
    - UNSEEN - Unread emails
    - SINCE 01-Jan-2024 - Emails since date
    - TO "recipient@example.com" - Emails to address
    - TEXT "keyword" - Full text search

    You can combine criteria: FROM "john" SUBJECT "project"

    Args:
        query: IMAP search query (e.g., "FROM sender@example.com").
        folder: Folder to search in (default: INBOX).
        max_results: Maximum number of results (default 10).

    Returns:
        List of matching emails with uid, subject, from, and date.
    """
    try:
        imap = email_auth.get_imap_connection()
        if not imap:
            return "Error: IMAP not configured or connection failed"

        try:
            status, _ = imap.select(folder)
            if status != "OK":
                return f"Error selecting folder '{folder}'"

            # Execute search
            status, messages = imap.search(None, query)
            if status != "OK":
                return f"Error searching: {status}"

            message_nums = messages[0].split()
            if not message_nums:
                return f"No emails found matching: {query}"

            # Limit results (get most recent matches)
            recent_nums = message_nums[-max_results:]
            recent_nums.reverse()

            results = []
            for num in recent_nums:
                status, data = imap.fetch(num, "(UID BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                if status != "OK" or not data or not data[0]:
                    continue

                if isinstance(data[0], tuple):
                    uid_part = data[0][0].decode("utf-8", errors="replace")
                    header_data = data[0][1]

                    uid = ""
                    if b"UID" in data[0][0]:
                        import re

                        uid_match = re.search(r"UID (\d+)", uid_part)
                        if uid_match:
                            uid = uid_match.group(1)

                    msg = email.message_from_bytes(header_data)
                    results.append(
                        {
                            "uid": uid,
                            "seq": num.decode() if isinstance(num, bytes) else str(num),
                            "subject": _decode_header_value(msg.get("Subject")),
                            "from": _decode_header_value(msg.get("From")),
                            "date": msg.get("Date", ""),
                        }
                    )

            return json.dumps(results, indent=2)
        finally:
            imap.logout()

    except Exception as e:
        return f"Error searching emails: {e}"


@tool
def email_read(uid: str, folder: str = "INBOX") -> str:
    """
    Read the full content of an email by UID.

    Args:
        uid: The email UID to read.
        folder: Folder containing the email (default: INBOX).

    Returns:
        Full email content including headers and body.
    """
    try:
        imap = email_auth.get_imap_connection()
        if not imap:
            return "Error: IMAP not configured or connection failed"

        try:
            status, _ = imap.select(folder)
            if status != "OK":
                return f"Error selecting folder '{folder}'"

            # Fetch by UID
            status, data = imap.uid("fetch", uid, "(RFC822)")
            if status != "OK" or not data or not data[0]:
                return f"Error fetching email UID {uid}"

            if isinstance(data[0], tuple):
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Extract recipients
                to_addrs = _decode_header_value(msg.get("To"))
                cc_addrs = _decode_header_value(msg.get("Cc"))

                body = _get_email_body(msg)

                result = {
                    "uid": uid,
                    "subject": _decode_header_value(msg.get("Subject")),
                    "from": _decode_header_value(msg.get("From")),
                    "to": to_addrs,
                    "cc": cc_addrs if cc_addrs else None,
                    "date": msg.get("Date", ""),
                    "message_id": msg.get("Message-ID", ""),
                    "body": body[:5000] if body else "(no body content)",
                }

                return json.dumps(result, indent=2)
            else:
                return f"Error: unexpected response format for UID {uid}"
        finally:
            imap.logout()

    except Exception as e:
        return f"Error reading email: {e}"


@tool
def email_send(to: str, subject: str, body: str, cc: str = "", bcc: str = "") -> str:
    """
    Send an email via SMTP.

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
        smtp = email_auth.get_smtp_connection()
        if not smtp:
            return "Error: SMTP not configured or connection failed"

        smtp_config = email_auth.get_smtp_config()
        if not smtp_config:
            return "Error: SMTP configuration not found"

        try:
            # Build email
            msg = MIMEMultipart()
            msg["From"] = smtp_config.username
            msg["To"] = to
            msg["Subject"] = subject

            if cc:
                msg["Cc"] = cc
            if bcc:
                msg["Bcc"] = bcc

            msg.attach(MIMEText(body, "plain"))

            # Build recipient list
            recipients = [addr.strip() for addr in to.split(",") if addr.strip()]
            if cc:
                recipients.extend([addr.strip() for addr in cc.split(",") if addr.strip()])
            if bcc:
                recipients.extend([addr.strip() for addr in bcc.split(",") if addr.strip()])

            smtp.sendmail(smtp_config.username, recipients, msg.as_string())

            return "Email sent successfully."
        finally:
            smtp.quit()

    except Exception as e:
        return f"Error sending email: {e}"


@tool
def email_reply(uid: str, body: str, reply_all: bool = False, folder: str = "INBOX") -> str:
    """
    Reply to an existing email.

    Args:
        uid: The UID of the email to reply to.
        body: Reply body text.
        reply_all: If True, reply to all recipients (default False).
        folder: Folder containing the original email (default: INBOX).

    Returns:
        Confirmation that the reply was sent.
    """
    try:
        # First, fetch the original email
        imap = email_auth.get_imap_connection()
        if not imap:
            return "Error: IMAP not configured or connection failed"

        try:
            status, _ = imap.select(folder)
            if status != "OK":
                return f"Error selecting folder '{folder}'"

            status, data = imap.uid("fetch", uid, "(RFC822)")
            if status != "OK" or not data or not data[0]:
                return f"Error fetching email UID {uid}"

            if not isinstance(data[0], tuple):
                return "Error: unexpected response format"

            raw_email = data[0][1]
            original_msg = email.message_from_bytes(raw_email)

        finally:
            imap.logout()

        # Now send the reply via SMTP
        smtp = email_auth.get_smtp_connection()
        if not smtp:
            return "Error: SMTP not configured or connection failed"

        smtp_config = email_auth.get_smtp_config()
        if not smtp_config:
            return "Error: SMTP configuration not found"

        try:
            # Build reply
            msg = MIMEMultipart()
            msg["From"] = smtp_config.username

            # Reply to sender
            reply_to = original_msg.get("Reply-To") or original_msg.get("From")
            msg["To"] = reply_to

            # Reply-all includes other recipients
            if reply_all:
                original_to = original_msg.get("To", "")
                original_cc = original_msg.get("Cc", "")
                all_recipients = []
                if original_to:
                    all_recipients.extend(original_to.split(","))
                if original_cc:
                    all_recipients.extend(original_cc.split(","))
                # Remove self from recipients
                all_recipients = [
                    r.strip()
                    for r in all_recipients
                    if smtp_config.username.lower() not in r.lower()
                ]
                if all_recipients:
                    msg["Cc"] = ", ".join(all_recipients)

            # Subject with Re:
            original_subject = _decode_header_value(original_msg.get("Subject", ""))
            if not original_subject.lower().startswith("re:"):
                msg["Subject"] = f"Re: {original_subject}"
            else:
                msg["Subject"] = original_subject

            # Set reply headers
            if original_msg.get("Message-ID"):
                msg["In-Reply-To"] = original_msg["Message-ID"]
                msg["References"] = (
                    original_msg.get("References", "") + " " + original_msg["Message-ID"]
                )

            # Quote original message
            original_body = _get_email_body(original_msg)
            quoted_body = "\n".join(f"> {line}" for line in original_body.split("\n")[:20])
            full_body = f"{body}\n\nOn {original_msg.get('Date', '')}, {_decode_header_value(original_msg.get('From', ''))} wrote:\n{quoted_body}"

            msg.attach(MIMEText(full_body, "plain"))

            # Build recipient list
            recipients = [msg["To"]]
            if msg.get("Cc"):
                recipients.extend([r.strip() for r in msg["Cc"].split(",")])

            smtp.sendmail(smtp_config.username, recipients, msg.as_string())

            return f"Reply sent successfully (reply_all={reply_all})."
        finally:
            smtp.quit()

    except Exception as e:
        return f"Error sending reply: {e}"


@tool
def email_mark_read(uid: str, is_read: bool = True, folder: str = "INBOX") -> str:
    """
    Mark an email as read or unread.

    Args:
        uid: The email UID to update.
        is_read: True to mark as read, False to mark as unread (default True).
        folder: Folder containing the email (default: INBOX).

    Returns:
        Confirmation of the update.
    """
    try:
        imap = email_auth.get_imap_connection()
        if not imap:
            return "Error: IMAP not configured or connection failed"

        try:
            status, _ = imap.select(folder)
            if status != "OK":
                return f"Error selecting folder '{folder}'"

            if is_read:
                status, _ = imap.uid("store", uid, "+FLAGS", "\\Seen")
            else:
                status, _ = imap.uid("store", uid, "-FLAGS", "\\Seen")

            if status != "OK":
                return f"Error updating email: {status}"

            state = "read" if is_read else "unread"
            return f"Email marked as {state}."
        finally:
            imap.logout()

    except Exception as e:
        return f"Error marking email: {e}"


@tool
def email_move(uid: str, destination_folder: str, source_folder: str = "INBOX") -> str:
    """
    Move an email to a different folder.

    Args:
        uid: The email UID to move.
        destination_folder: Target folder name (e.g., "Archive", "Trash").
        source_folder: Source folder (default: INBOX).

    Returns:
        Confirmation that the email was moved.
    """
    try:
        imap = email_auth.get_imap_connection()
        if not imap:
            return "Error: IMAP not configured or connection failed"

        try:
            status, _ = imap.select(source_folder)
            if status != "OK":
                return f"Error selecting folder '{source_folder}'"

            # Copy to destination
            status, _ = imap.uid("copy", uid, destination_folder)
            if status != "OK":
                return f"Error copying to '{destination_folder}': folder may not exist"

            # Mark original as deleted
            status, _ = imap.uid("store", uid, "+FLAGS", "\\Deleted")
            if status != "OK":
                return "Error marking original for deletion"

            # Expunge deleted emails
            imap.expunge()

            return f"Email moved to {destination_folder}."
        finally:
            imap.logout()

    except Exception as e:
        return f"Error moving email: {e}"


@tool
def email_delete(uid: str, folder: str = "INBOX") -> str:
    """
    Delete an email (mark as deleted and expunge).

    Args:
        uid: The email UID to delete.
        folder: Folder containing the email (default: INBOX).

    Returns:
        Confirmation that the email was deleted.
    """
    try:
        imap = email_auth.get_imap_connection()
        if not imap:
            return "Error: IMAP not configured or connection failed"

        try:
            status, _ = imap.select(folder)
            if status != "OK":
                return f"Error selecting folder '{folder}'"

            # Mark as deleted
            status, _ = imap.uid("store", uid, "+FLAGS", "\\Deleted")
            if status != "OK":
                return f"Error deleting email: {status}"

            # Expunge
            imap.expunge()

            return f"Email {uid} deleted."
        finally:
            imap.logout()

    except Exception as e:
        return f"Error deleting email: {e}"


@tool
def email_create_draft(to: str, subject: str, body: str, cc: str = "", bcc: str = "") -> str:
    """
    Create an email draft (saves to Drafts folder).

    Args:
        to: Recipient email address (required).
        subject: Email subject line (required).
        body: Email body text.
        cc: CC recipients (optional).
        bcc: BCC recipients (optional).

    Returns:
        Confirmation that the draft was created.
    """
    try:
        imap = email_auth.get_imap_connection()
        if not imap:
            return "Error: IMAP not configured or connection failed"

        smtp_config = email_auth.get_smtp_config()
        if not smtp_config:
            return "Error: SMTP configuration not found (needed for From address)"

        try:
            # Build draft email
            msg = MIMEMultipart()
            msg["From"] = smtp_config.username
            msg["To"] = to
            msg["Subject"] = subject
            msg["Date"] = email.utils.formatdate(localtime=True)

            if cc:
                msg["Cc"] = cc
            if bcc:
                msg["Bcc"] = bcc

            msg.attach(MIMEText(body, "plain"))

            # Try common draft folder names
            draft_folders = ["Drafts", "INBOX.Drafts", "[Gmail]/Drafts", "Draft"]

            for draft_folder in draft_folders:
                try:
                    status, _ = imap.append(draft_folder, "\\Draft", None, msg.as_bytes())
                    if status == "OK":
                        return f"Draft created in {draft_folder}."
                except Exception:
                    continue

            return "Error: Could not find Drafts folder. Try listing folders first."
        finally:
            imap.logout()

    except Exception as e:
        return f"Error creating draft: {e}"


def get_static_tools() -> list[BaseTool]:
    """Get all generic email tools."""
    return [
        email_list_folders,
        email_list_folder,
        email_search,
        email_read,
        email_send,
        email_reply,
        email_mark_read,
        email_move,
        email_delete,
        email_create_draft,
    ]
