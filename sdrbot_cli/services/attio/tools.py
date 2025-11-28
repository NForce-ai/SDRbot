"""Attio static tools - schema-independent operations.

These tools work regardless of the user's Attio schema and don't require sync.
Schema-dependent CRUD tools are generated in tools.generated.py after sync.
"""

from langchain_core.tools import BaseTool, tool

from sdrbot_cli.auth.attio import AttioClient

# Shared client instance
_attio_client = None


def get_attio():
    """Get or create Attio client instance."""
    global _attio_client
    if _attio_client is None:
        _attio_client = AttioClient()
    return _attio_client


@tool
def attio_create_note(object_slug: str, record_id: str, title: str, body: str) -> str:
    """
    Add a note to an Attio record.

    Args:
        object_slug: Object type (e.g., "people", "companies")
        record_id: The record's UUID
        title: Note title
        body: Note content (markdown supported)
    """
    client = get_attio()
    try:
        payload = {
            "data": {
                "title": title,
                "content": body,
                "parent_object": object_slug,
                "parent_record_id": record_id,
            }
        }

        data = client.request("POST", "/notes", json=payload)
        note = data.get("data", {})

        return f"Successfully created note (ID: {note.get('id', {}).get('note_id')})"
    except Exception as e:
        return f"Error creating note: {str(e)}"


@tool
def attio_list_notes(object_slug: str, record_id: str, limit: int = 10) -> str:
    """
    List notes on an Attio record.

    Args:
        object_slug: Object type (e.g., "people", "companies")
        record_id: The record's UUID
        limit: Maximum notes to return (default 10)
    """
    client = get_attio()
    try:
        params = {
            "parent_object": object_slug,
            "parent_record_id": record_id,
            "limit": limit,
        }

        data = client.request("GET", "/notes", params=params)
        notes = data.get("data", [])

        if not notes:
            return "No notes found on this record."

        output = ["Notes:"]
        for note in notes:
            title = note.get("title", "(No title)")
            created = note.get("created_at", "")[:10]
            output.append(f"- {title} (Created: {created})")

        return "\n".join(output)
    except Exception as e:
        return f"Error listing notes: {str(e)}"


@tool
def attio_get_record(object_slug: str, record_id: str) -> str:
    """
    Get a single Attio record by ID.

    Args:
        object_slug: Object type (e.g., "people", "companies")
        record_id: The record's UUID
    """
    client = get_attio()
    try:
        data = client.request("GET", f"/objects/{object_slug}/records/{record_id}")
        record = data.get("data", {})

        if not record:
            return f"Record not found: {record_id}"

        # Format values for display
        values = record.get("values", {})
        output = [f"Record ID: {record.get('id', {}).get('record_id')}"]

        for attr_slug, attr_values in values.items():
            if attr_values:
                # Attio values are lists of typed objects
                display_vals = []
                for v in attr_values[:3]:  # Limit displayed values
                    if isinstance(v, dict):
                        # Extract the actual value based on type
                        for key in ["value", "text", "email_address", "full_name", "domain"]:
                            if key in v:
                                display_vals.append(str(v[key]))
                                break
                    else:
                        display_vals.append(str(v))
                output.append(f"- {attr_slug}: {', '.join(display_vals)}")

        return "\n".join(output)
    except Exception as e:
        return f"Error getting record: {str(e)}"


def get_static_tools() -> list[BaseTool]:
    """Get all static Attio tools.

    Returns:
        List of schema-independent Attio tools.
    """
    return [
        attio_create_note,
        attio_list_notes,
        attio_get_record,
    ]
