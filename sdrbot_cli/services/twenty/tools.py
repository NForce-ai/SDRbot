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
def twenty_create_note(
    target_object: str,
    target_record_id: str,
    title: str,
    body: str,
) -> str:
    """Create a note on a Twenty record.

    Args:
        target_object: Object type the note is attached to (e.g., "person", "company").
        target_record_id: The record's UUID.
        title: Note title.
        body: Note content (markdown supported).

    Returns:
        Success message with note ID or error message.
    """
    client = get_twenty()
    try:
        payload = {
            "title": title,
            "body": body,
            "targetObjectNameSingular": target_object,
            "targetRecordId": target_record_id,
        }

        response = client.post("/notes", json=payload)
        note = response.get("data", {})
        note_id = note.get("id", "unknown")

        return f"Successfully created note (ID: {note_id})"
    except Exception as e:
        return f"Error creating note: {str(e)}"


@tool
def twenty_list_notes(
    target_object: str,
    target_record_id: str,
    limit: int = 10,
) -> str:
    """List notes on a Twenty record.

    Args:
        target_object: Object type (e.g., "person", "company").
        target_record_id: The record's UUID.
        limit: Maximum notes to return (default 10).

    Returns:
        Formatted list of notes or error message.
    """
    client = get_twenty()
    try:
        # Twenty uses query-string filter format: field[op]:value
        params = {
            "filter": f'and(targetObjectNameSingular[eq]:"{target_object}",targetRecordId[eq]:"{target_record_id}")',
            "limit": limit,
        }

        response = client.get("/notes", params=params)
        notes = response.get("data", {}).get("notes", [])

        if not notes:
            return "No notes found on this record."

        output = ["Notes:"]
        for note in notes:
            title = note.get("title", "(No title)")
            created = note.get("createdAt", "")[:10] if note.get("createdAt") else ""
            output.append(f"- {title} (Created: {created})")

        return "\n".join(output)
    except Exception as e:
        return f"Error listing notes: {str(e)}"


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
        twenty_create_note,
        twenty_list_notes,
        twenty_search_records,
        twenty_get_record,
    ]
