"""Twenty static tools - schema-independent operations.

These tools work regardless of the user's Twenty schema and don't require sync.
Schema-dependent CRUD tools are generated in twenty_tools.py after sync.
"""

import json

from langchain_core.tools import BaseTool, tool

from sdrbot_cli.auth.twenty import TwentyClient

# Shared client instance
_twenty_client = None


def get_twenty():
    """Get or create Twenty client instance."""
    global _twenty_client
    if _twenty_client is None:
        _twenty_client = TwentyClient()
    return _twenty_client


def reset_client():
    """Reset the cached client (useful for testing)."""
    global _twenty_client
    _twenty_client = None


@tool
def twenty_create_note_on_record(
    target_type: str,
    target_record_id: str,
    title: str,
    body_markdown: str,
) -> str:
    """Create a note attached to a specific Twenty record.

    Use this to add notes to people, companies, opportunities, etc.
    For standalone note operations (update, delete), use the twenty_*_note tools.

    Args:
        target_type: Object type - one of "person", "company", or "opportunity".
        target_record_id: The record's UUID.
        title: Note title.
        body_markdown: Note content in markdown format.

    Returns:
        Success message with note ID or error message.
    """
    # Map target type to the correct ID field name
    target_field_map = {
        "person": "personId",
        "company": "companyId",
        "opportunity": "opportunityId",
    }

    target_field = target_field_map.get(target_type.lower())
    if not target_field:
        return f"Error: Invalid target_type '{target_type}'. Must be one of: person, company, opportunity"

    client = get_twenty()
    try:
        # First create the note
        payload = {
            "title": title,
            "bodyV2": {"markdown": body_markdown},
        }

        response = client.post("/notes", json=payload)
        note = response.get("data", {}).get("createNote", {})
        note_id = note.get("id")

        if not note_id:
            return "Error: Failed to create note - no ID returned"

        # Then create the noteTarget association
        target_payload = {
            "noteId": note_id,
            target_field: target_record_id,
        }
        client.post("/noteTargets", json=target_payload)

        return f"Successfully created note (ID: {note_id}) on {target_type} {target_record_id}"
    except Exception as e:
        return f"Error creating note: {str(e)}"


@tool
def twenty_list_notes_on_record(
    target_type: str,
    target_record_id: str,
    limit: int = 10,
) -> str:
    """List notes attached to a specific Twenty record.

    Args:
        target_type: Object type - one of "person", "company", or "opportunity".
        target_record_id: The record's UUID.
        limit: Maximum notes to return (default 10).

    Returns:
        Formatted list of notes or error message.
    """
    # Map target type to the correct ID field name
    target_field_map = {
        "person": "personId",
        "company": "companyId",
        "opportunity": "opportunityId",
    }

    target_field = target_field_map.get(target_type.lower())
    if not target_field:
        return f"Error: Invalid target_type '{target_type}'. Must be one of: person, company, opportunity"

    client = get_twenty()
    try:
        # First get noteTargets for this record
        params = {
            "filter": f'{target_field}[eq]:"{target_record_id}"',
            "limit": limit,
        }

        response = client.get("/noteTargets", params=params)
        targets = response.get("data", {}).get("noteTargets", [])

        if not targets:
            return f"No notes found on this {target_type}."

        # Get the note IDs and fetch notes
        note_ids = [t.get("noteId") for t in targets if t.get("noteId")]
        if not note_ids:
            return f"No notes found on this {target_type}."

        # Fetch notes by IDs
        output = ["Notes:"]
        for note_id in note_ids:
            try:
                note_response = client.get(f"/notes/{note_id}")
                note = note_response.get("data", {}).get("note", {})
                if note:
                    title = note.get("title", "(No title)")
                    created = note.get("createdAt", "")[:10] if note.get("createdAt") else ""
                    body = note.get("bodyV2", {}).get("markdown", "")
                    preview = body[:100] + "..." if len(body) > 100 else body
                    output.append(f"- [{note_id}] {title} (Created: {created})")
                    if preview:
                        output.append(f"  {preview}")
            except Exception:
                continue

        if len(output) == 1:
            return f"No notes found on this {target_type}."

        return "\n".join(output)
    except Exception as e:
        return f"Error listing notes: {str(e)}"


@tool
def twenty_update_note(
    note_id: str,
    title: str | None = None,
    body_markdown: str | None = None,
) -> str:
    """Update an existing note in Twenty.

    Args:
        note_id: The UUID of the note to update.
        title: New title for the note (optional).
        body_markdown: New content in markdown format (optional).

    Returns:
        Success message or error message.
    """
    client = get_twenty()
    try:
        payload = {}
        if title is not None:
            payload["title"] = title
        if body_markdown is not None:
            payload["bodyV2"] = {"markdown": body_markdown}

        if not payload:
            return "Error: No fields provided to update. Provide title and/or body_markdown."

        client.patch(f"/notes/{note_id}", json=payload)
        return f"Successfully updated note {note_id}"
    except Exception as e:
        return f"Error updating note: {str(e)}"


@tool
def twenty_delete_note(note_id: str) -> str:
    """Delete a note from Twenty.

    Args:
        note_id: The UUID of the note to delete.

    Returns:
        Success message or error message.
    """
    client = get_twenty()
    try:
        client.delete(f"/notes/{note_id}")
        return f"Successfully deleted note {note_id}"
    except Exception as e:
        return f"Error deleting note: {str(e)}"


@tool
def twenty_search_records(
    object_type: str,
    query: str,
    limit: int = 10,
) -> str:
    """Search records of a specific type in Twenty.

    Args:
        object_type: Object type to search (e.g., "people", "companies").
        query: Search query string.
        limit: Maximum results to return (default 10).

    Returns:
        JSON string with matching records or error message.
    """
    client = get_twenty()
    try:
        # Twenty REST API uses plural object names for endpoints
        params = {
            "limit": limit,
        }

        # Add search filter if query provided
        # Twenty uses query-string filter format: field[op]:value
        if query:
            params["filter"] = f'or(name[ilike]:"%{query}%",email[ilike]:"%{query}%")'

        response = client.get(f"/{object_type}", params=params)
        records = response.get("data", {}).get(object_type, [])

        if not records:
            return f"No {object_type} found matching '{query}'."

        # Format results
        results = []
        for record in records:
            record_data = {"id": record.get("id")}
            # Include common fields
            for field in ["name", "email", "phone", "domainName", "linkedinLink"]:
                if field in record and record[field]:
                    record_data[field] = record[field]
            results.append(record_data)

        return f"Found {len(records)} {object_type}:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error searching {object_type}: {str(e)}"


@tool
def twenty_get_record(object_type: str, record_id: str) -> str:
    """Get a single Twenty record by ID.

    Args:
        object_type: Object type (e.g., "people", "companies").
        record_id: The record's UUID.

    Returns:
        JSON string with record details or error message.
    """
    client = get_twenty()
    try:
        response = client.get(f"/{object_type}/{record_id}")
        data = response.get("data", {})

        # Twenty returns data nested under singular name or directly
        # Try common singular forms first
        singular_map = {"people": "person", "companies": "company"}
        singular = singular_map.get(object_type, object_type.rstrip("s"))

        record = data.get(singular) if isinstance(data, dict) else data

        # If not found under singular key, use data directly if it has an id
        if not record and isinstance(data, dict) and "id" in data:
            record = data

        if not record:
            return f"Record not found: {record_id}"

        return f"Record {record_id}:\n" + json.dumps(record, indent=2)
    except Exception as e:
        return f"Error getting record: {str(e)}"


def get_static_tools() -> list[BaseTool]:
    """Get all static Twenty tools.

    Returns:
        List of schema-independent Twenty tools.
    """
    return [
        twenty_create_note_on_record,
        twenty_list_notes_on_record,
        twenty_update_note,
        twenty_delete_note,
        twenty_search_records,
        twenty_get_record,
    ]
