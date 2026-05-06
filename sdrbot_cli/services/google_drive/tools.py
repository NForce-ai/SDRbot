"""Google Drive tools.

Google Drive is a file storage service - all tools are static (no schema sync required).
"""

import json
import os

import requests
from langchain_core.tools import BaseTool, tool

from sdrbot_cli.auth import google_drive as gdrive_auth

BASE_URL = "https://www.googleapis.com/drive/v3"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3"

# MIME types for Google Workspace formats and their export equivalents
GOOGLE_DOC_EXPORT_MIME = "text/plain"
GOOGLE_SHEET_EXPORT_MIME = "text/csv"
GOOGLE_SLIDES_EXPORT_MIME = "text/plain"

GOOGLE_MIME_TYPES = {
    "application/vnd.google-apps.document": ("Google Doc", GOOGLE_DOC_EXPORT_MIME),
    "application/vnd.google-apps.spreadsheet": ("Google Sheet", GOOGLE_SHEET_EXPORT_MIME),
    "application/vnd.google-apps.presentation": ("Google Slides", GOOGLE_SLIDES_EXPORT_MIME),
}


def _headers() -> dict:
    """Get authorization headers."""
    headers = gdrive_auth.get_headers()
    if not headers:
        raise RuntimeError(
            "Google Drive not authenticated. Run /setup to configure Google Drive."
        )
    return headers


@tool
def gdrive_list_files(
    folder_id: str = "root",
    max_results: int = 20,
    include_trashed: bool = False,
) -> str:
    """
    List files and folders in Google Drive.

    Args:
        folder_id: ID of the folder to list (default "root" for My Drive root).
                   Use "root" for the top-level drive.
        max_results: Maximum number of files to return (default 20, max 100).
        include_trashed: If True, include trashed files (default False).

    Returns:
        List of files with id, name, mimeType, size, and modifiedTime.
    """
    try:
        headers = _headers()
        query = f"'{folder_id}' in parents"
        if not include_trashed:
            query += " and trashed = false"

        resp = requests.get(
            f"{BASE_URL}/files",
            headers=headers,
            params={
                "q": query,
                "pageSize": min(max_results, 100),
                "fields": "files(id,name,mimeType,size,modifiedTime,parents)",
                "orderBy": "folder,name",
            },
        )

        if not resp.ok:
            return f"Error listing files: {resp.status_code} - {resp.text}"

        files = resp.json().get("files", [])
        if not files:
            return f"No files found in folder: {folder_id}"

        results = []
        for f in files:
            mime = f.get("mimeType", "")
            file_type = GOOGLE_MIME_TYPES.get(mime, (mime, None))[0]
            results.append(
                {
                    "id": f["id"],
                    "name": f["name"],
                    "type": file_type,
                    "size": f.get("size"),
                    "modifiedTime": f.get("modifiedTime"),
                }
            )

        return json.dumps(results, indent=2)

    except Exception as e:
        return f"Error listing files: {e}"


@tool
def gdrive_search_files(
    query: str,
    max_results: int = 20,
) -> str:
    """
    Search for files in Google Drive.

    Query syntax examples:
    - name contains 'report' - files with 'report' in the name
    - mimeType = 'application/vnd.google-apps.spreadsheet' - only Google Sheets
    - mimeType = 'application/vnd.google-apps.document' - only Google Docs
    - fullText contains 'quarterly' - files containing text 'quarterly'
    - modifiedTime > '2024-01-01T00:00:00' - recently modified files
    - name contains 'invoice' and mimeType = 'application/pdf' - PDF invoices

    Args:
        query: Google Drive search query string.
        max_results: Maximum number of results (default 20, max 100).

    Returns:
        List of matching files with id, name, mimeType, size, and modifiedTime.
    """
    try:
        headers = _headers()
        full_query = f"({query}) and trashed = false"

        resp = requests.get(
            f"{BASE_URL}/files",
            headers=headers,
            params={
                "q": full_query,
                "pageSize": min(max_results, 100),
                "fields": "files(id,name,mimeType,size,modifiedTime,parents)",
            },
        )

        if not resp.ok:
            return f"Error searching files: {resp.status_code} - {resp.text}"

        files = resp.json().get("files", [])
        if not files:
            return f"No files found matching query: {query}"

        results = []
        for f in files:
            mime = f.get("mimeType", "")
            file_type = GOOGLE_MIME_TYPES.get(mime, (mime, None))[0]
            results.append(
                {
                    "id": f["id"],
                    "name": f["name"],
                    "type": file_type,
                    "size": f.get("size"),
                    "modifiedTime": f.get("modifiedTime"),
                    "parents": f.get("parents", []),
                }
            )

        return json.dumps(results, indent=2)

    except Exception as e:
        return f"Error searching files: {e}"


@tool
def gdrive_get_file(file_id: str) -> str:
    """
    Get metadata for a specific file or folder.

    Args:
        file_id: The Google Drive file ID.

    Returns:
        File metadata including id, name, mimeType, size, createdTime, modifiedTime,
        webViewLink, and parents.
    """
    try:
        headers = _headers()
        resp = requests.get(
            f"{BASE_URL}/files/{file_id}",
            headers=headers,
            params={
                "fields": "id,name,mimeType,size,createdTime,modifiedTime,webViewLink,parents,owners,shared"
            },
        )

        if not resp.ok:
            return f"Error getting file: {resp.status_code} - {resp.text}"

        data = resp.json()
        mime = data.get("mimeType", "")
        file_type = GOOGLE_MIME_TYPES.get(mime, (mime, None))[0]

        result = {
            "id": data["id"],
            "name": data["name"],
            "type": file_type,
            "mimeType": mime,
            "size": data.get("size"),
            "createdTime": data.get("createdTime"),
            "modifiedTime": data.get("modifiedTime"),
            "webViewLink": data.get("webViewLink"),
            "parents": data.get("parents", []),
            "shared": data.get("shared", False),
            "owners": [o.get("emailAddress") for o in data.get("owners", [])],
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return f"Error getting file: {e}"


@tool
def gdrive_read_file(file_id: str, max_chars: int = 10000) -> str:
    """
    Read the text content of a file from Google Drive.

    Supports: Google Docs (exported as text), Google Sheets (exported as CSV),
    Google Slides (exported as text), plain text files, CSV files, JSON files,
    and other text-based formats.

    Binary files (images, PDFs, etc.) are not supported for content reading —
    use gdrive_download_file to download them locally instead.

    Args:
        file_id: The Google Drive file ID.
        max_chars: Maximum characters to return (default 10000).

    Returns:
        The text content of the file.
    """
    try:
        headers = _headers()

        # Get file metadata first
        meta_resp = requests.get(
            f"{BASE_URL}/files/{file_id}",
            headers=headers,
            params={"fields": "id,name,mimeType"},
        )

        if not meta_resp.ok:
            return f"Error getting file metadata: {meta_resp.status_code} - {meta_resp.text}"

        meta = meta_resp.json()
        mime = meta.get("mimeType", "")
        name = meta.get("name", file_id)

        # Google Workspace files need export
        if mime in GOOGLE_MIME_TYPES:
            _, export_mime = GOOGLE_MIME_TYPES[mime]
            resp = requests.get(
                f"{BASE_URL}/files/{file_id}/export",
                headers=headers,
                params={"mimeType": export_mime},
            )
        elif mime.startswith("text/") or mime in (
            "application/json",
            "application/xml",
            "application/javascript",
        ):
            resp = requests.get(
                f"{BASE_URL}/files/{file_id}",
                headers=headers,
                params={"alt": "media"},
            )
        else:
            return (
                f"File '{name}' has type '{mime}' which cannot be read as text. "
                f"Use gdrive_download_file to download it locally."
            )

        if not resp.ok:
            return f"Error reading file: {resp.status_code} - {resp.text}"

        content = resp.text
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n[truncated — {len(resp.text)} total chars]"

        return content

    except Exception as e:
        return f"Error reading file: {e}"


@tool
def gdrive_create_folder(name: str, parent_id: str = "root") -> str:
    """
    Create a new folder in Google Drive.

    Args:
        name: Name of the folder to create.
        parent_id: ID of the parent folder (default "root" for My Drive root).

    Returns:
        Confirmation with the new folder's ID and name.
    """
    try:
        headers = _headers()
        headers["Content-Type"] = "application/json"

        resp = requests.post(
            f"{BASE_URL}/files",
            headers=headers,
            json={
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            },
        )

        if not resp.ok:
            return f"Error creating folder: {resp.status_code} - {resp.text}"

        result = resp.json()
        return f"Folder created successfully. Name: '{result['name']}', ID: {result['id']}"

    except Exception as e:
        return f"Error creating folder: {e}"


@tool
def gdrive_upload_file(
    local_path: str,
    name: str = "",
    parent_id: str = "root",
) -> str:
    """
    Upload a local file to Google Drive.

    Args:
        local_path: Path to the local file to upload.
        name: Name for the file in Drive (defaults to the local filename).
        parent_id: ID of the destination folder (default "root" for My Drive root).

    Returns:
        Confirmation with the uploaded file's ID and name.
    """
    try:
        import mimetypes

        headers = _headers()

        if not os.path.isfile(local_path):
            return f"File not found: {local_path}"

        file_name = name or os.path.basename(local_path)
        content_type, _ = mimetypes.guess_type(local_path)
        if not content_type:
            content_type = "application/octet-stream"

        metadata = {"name": file_name, "parents": [parent_id]}

        with open(local_path, "rb") as f:
            file_data = f.read()

        # Use multipart upload
        import uuid

        boundary = f"==={uuid.uuid4().hex}==="
        meta_bytes = json.dumps(metadata).encode()

        parts: list[bytes] = []
        parts.append(f"--{boundary}".encode())
        parts.append(b"Content-Type: application/json; charset=UTF-8")
        parts.append(b"")
        parts.append(meta_bytes)
        parts.append(f"--{boundary}".encode())
        parts.append(f"Content-Type: {content_type}".encode())
        parts.append(b"")
        parts.append(file_data)
        parts.append(f"--{boundary}--".encode())
        body = b"\r\n".join(parts)

        upload_headers = {
            **headers,
            "Content-Type": f'multipart/related; boundary="{boundary}"',
        }

        resp = requests.post(
            f"{UPLOAD_URL}/files?uploadType=multipart",
            headers=upload_headers,
            data=body,
        )

        if not resp.ok:
            return f"Error uploading file: {resp.status_code} - {resp.text}"

        result = resp.json()
        return f"File uploaded successfully. Name: '{result['name']}', ID: {result['id']}"

    except Exception as e:
        return f"Error uploading file: {e}"


@tool
def gdrive_download_file(file_id: str, local_path: str) -> str:
    """
    Download a file from Google Drive to a local path.

    For Google Workspace files (Docs, Sheets, Slides), this exports them as:
    - Google Docs → .docx (Word format)
    - Google Sheets → .xlsx (Excel format)
    - Google Slides → .pptx (PowerPoint format)

    Args:
        file_id: The Google Drive file ID to download.
        local_path: Local file path where the file should be saved.

    Returns:
        Confirmation that the file was downloaded.
    """
    try:
        headers = _headers()

        meta_resp = requests.get(
            f"{BASE_URL}/files/{file_id}",
            headers=headers,
            params={"fields": "id,name,mimeType"},
        )

        if not meta_resp.ok:
            return f"Error getting file metadata: {meta_resp.status_code} - {meta_resp.text}"

        meta = meta_resp.json()
        mime = meta.get("mimeType", "")

        # Export Google Workspace files in Office formats
        google_export_map = {
            "application/vnd.google-apps.document": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".docx",
            ),
            "application/vnd.google-apps.spreadsheet": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".xlsx",
            ),
            "application/vnd.google-apps.presentation": (
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                ".pptx",
            ),
        }

        if mime in google_export_map:
            export_mime, ext = google_export_map[mime]
            if not local_path.endswith(ext):
                local_path = local_path + ext
            resp = requests.get(
                f"{BASE_URL}/files/{file_id}/export",
                headers=headers,
                params={"mimeType": export_mime},
                stream=True,
            )
        else:
            resp = requests.get(
                f"{BASE_URL}/files/{file_id}",
                headers=headers,
                params={"alt": "media"},
                stream=True,
            )

        if not resp.ok:
            return f"Error downloading file: {resp.status_code} - {resp.text}"

        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size = os.path.getsize(local_path)
        return f"File downloaded to '{local_path}' ({size} bytes)."

    except Exception as e:
        return f"Error downloading file: {e}"


@tool
def gdrive_delete_file(file_id: str) -> str:
    """
    Move a file or folder to trash in Google Drive.

    Args:
        file_id: The Google Drive file or folder ID to trash.

    Returns:
        Confirmation that the file was moved to trash.
    """
    try:
        headers = _headers()
        headers["Content-Type"] = "application/json"

        resp = requests.patch(
            f"{BASE_URL}/files/{file_id}",
            headers=headers,
            json={"trashed": True},
        )

        if not resp.ok:
            return f"Error deleting file: {resp.status_code} - {resp.text}"

        return f"File {file_id} moved to trash."

    except Exception as e:
        return f"Error deleting file: {e}"


@tool
def gdrive_move_file(file_id: str, new_parent_id: str) -> str:
    """
    Move a file to a different folder in Google Drive.

    Args:
        file_id: The file ID to move.
        new_parent_id: The ID of the destination folder.

    Returns:
        Confirmation that the file was moved.
    """
    try:
        headers = _headers()

        # Get current parents
        meta_resp = requests.get(
            f"{BASE_URL}/files/{file_id}",
            headers=headers,
            params={"fields": "id,name,parents"},
        )

        if not meta_resp.ok:
            return f"Error getting file metadata: {meta_resp.status_code} - {meta_resp.text}"

        meta = meta_resp.json()
        old_parents = ",".join(meta.get("parents", []))

        resp = requests.patch(
            f"{BASE_URL}/files/{file_id}",
            headers=headers,
            params={
                "addParents": new_parent_id,
                "removeParents": old_parents,
                "fields": "id,name,parents",
            },
        )

        if not resp.ok:
            return f"Error moving file: {resp.status_code} - {resp.text}"

        result = resp.json()
        return f"File '{result['name']}' moved to folder {new_parent_id}."

    except Exception as e:
        return f"Error moving file: {e}"


@tool
def gdrive_share_file(
    file_id: str,
    email: str,
    role: str = "reader",
    send_notification: bool = True,
) -> str:
    """
    Share a file or folder with a specific user.

    Args:
        file_id: The Google Drive file or folder ID to share.
        email: The email address of the user to share with.
        role: Permission role - "reader" (view only), "commenter" (can comment),
              or "writer" (can edit). Default is "reader".
        send_notification: If True, send an email notification to the user (default True).

    Returns:
        Confirmation that the file was shared.
    """
    try:
        headers = _headers()
        headers["Content-Type"] = "application/json"

        valid_roles = {"reader", "commenter", "writer"}
        if role not in valid_roles:
            return f"Invalid role '{role}'. Must be one of: {', '.join(valid_roles)}"

        resp = requests.post(
            f"{BASE_URL}/files/{file_id}/permissions",
            headers=headers,
            params={"sendNotificationEmail": str(send_notification).lower()},
            json={
                "type": "user",
                "role": role,
                "emailAddress": email,
            },
        )

        if not resp.ok:
            return f"Error sharing file: {resp.status_code} - {resp.text}"

        return f"File {file_id} shared with {email} as {role}."

    except Exception as e:
        return f"Error sharing file: {e}"


@tool
def gdrive_list_permissions(file_id: str) -> str:
    """
    List all permissions (sharing settings) for a file or folder.

    Args:
        file_id: The Google Drive file or folder ID.

    Returns:
        List of permissions with role and email address.
    """
    try:
        headers = _headers()
        resp = requests.get(
            f"{BASE_URL}/files/{file_id}/permissions",
            headers=headers,
            params={"fields": "permissions(id,role,type,emailAddress,displayName)"},
        )

        if not resp.ok:
            return f"Error listing permissions: {resp.status_code} - {resp.text}"

        permissions = resp.json().get("permissions", [])
        if not permissions:
            return "No permissions found (file may not be shared)."

        results = [
            {
                "id": p["id"],
                "role": p.get("role"),
                "type": p.get("type"),
                "email": p.get("emailAddress"),
                "name": p.get("displayName"),
            }
            for p in permissions
        ]

        return json.dumps(results, indent=2)

    except Exception as e:
        return f"Error listing permissions: {e}"


def get_static_tools() -> list[BaseTool]:
    """Get all Google Drive tools."""
    return [
        gdrive_list_files,
        gdrive_search_files,
        gdrive_get_file,
        gdrive_read_file,
        gdrive_create_folder,
        gdrive_upload_file,
        gdrive_download_file,
        gdrive_delete_file,
        gdrive_move_file,
        gdrive_share_file,
        gdrive_list_permissions,
    ]
