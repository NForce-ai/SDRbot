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


ATTIO_OBJECTS = ["people", "companies"]


def _count_attio_records(client, object_slug: str, max_pages: int = 100) -> int:
    """Count records by paginating through results."""
    count = 0
    page_token = None
    limit = 500

    for _ in range(max_pages):
        payload = {"limit": limit}
        if page_token:
            payload["page_token"] = page_token

        response = client.request("POST", f"/objects/{object_slug}/records/query", json=payload)
        data = response.get("data", [])
        count += len(data)

        page_token = response.get("next_page_token")
        if not page_token:
            break

    return count


@tool
def attio_count_records(object_slug: str | None = None) -> str:
    """Count records for each object type in Attio.

    Args:
        object_slug: Optional - count a specific object only (e.g., "people").
                     If not provided, counts standard objects.

    Returns:
        Record counts for each object type.
    """
    client = get_attio()

    if object_slug:
        types_to_count = [object_slug]
    else:
        types_to_count = ATTIO_OBJECTS

    results = {}
    for obj_name in types_to_count:
        try:
            results[obj_name] = _count_attio_records(client, obj_name)
        except Exception as e:
            results[obj_name] = f"Error: {str(e)}"

    lines = ["Record counts:"]
    total = 0
    for obj_name, count in results.items():
        lines.append(f"  {obj_name}: {count}")
        if isinstance(count, int):
            total += count
    if len(results) > 1:
        lines.append("  ---")
        lines.append(f"  Total: {total}")

    return "\n".join(lines)


def get_static_tools() -> list[BaseTool]:
    """Get all static Attio tools.

    Returns:
        List of schema-independent Attio tools.
    """
    return [
        attio_create_note,
        attio_list_notes,
        attio_get_record,
        attio_count_records,
    ]
