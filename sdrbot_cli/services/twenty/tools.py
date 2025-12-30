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
def twenty_link_note_to_record(
    note_id: str,
    target_type: str,
    target_record_id: str,
) -> str:
    """Link an existing note to a Twenty record via noteTargets.

    Use this after creating a note with twenty_create_note to associate it
    with a person, company, or opportunity.

    Args:
        note_id: The UUID of the note to link.
        target_type: Object type - one of "person", "company", or "opportunity".
        target_record_id: The record's UUID to link the note to.

    Returns:
        Success message or error message.
    """
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
        target_payload = {
            "noteId": note_id,
            target_field: target_record_id,
        }
        client.post("/noteTargets", json=target_payload)

        return f"Successfully linked note {note_id} to {target_type} {target_record_id}"
    except Exception as e:
        return f"Error linking note: {str(e)}"


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


# =============================================================================
# TASK TOOLS - Tasks with target associations
# =============================================================================


@tool
def twenty_link_task_to_record(
    task_id: str,
    target_type: str,
    target_record_id: str,
) -> str:
    """Link an existing task to a Twenty record via taskTargets.

    Use this after creating a task with twenty_create_task to associate it
    with a person, company, or opportunity.

    Args:
        task_id: The UUID of the task to link.
        target_type: Object type - one of "person", "company", or "opportunity".
        target_record_id: The record's UUID to link the task to.

    Returns:
        Success message or error message.
    """
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
        target_payload = {
            "taskId": task_id,
            target_field: target_record_id,
        }
        client.post("/taskTargets", json=target_payload)

        return f"Successfully linked task {task_id} to {target_type} {target_record_id}"
    except Exception as e:
        return f"Error linking task: {str(e)}"


@tool
def twenty_list_tasks_on_record(
    target_type: str,
    target_record_id: str,
    limit: int = 10,
) -> str:
    """List tasks attached to a specific Twenty record.

    Args:
        target_type: Object type - one of "person", "company", or "opportunity".
        target_record_id: The record's UUID.
        limit: Maximum tasks to return (default 10).

    Returns:
        Formatted list of tasks or error message.
    """
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
        # First get taskTargets for this record
        params = {
            "filter": f'{target_field}[eq]:"{target_record_id}"',
            "limit": limit,
        }

        response = client.get("/taskTargets", params=params)
        targets = response.get("data", {}).get("taskTargets", [])

        if not targets:
            return f"No tasks found on this {target_type}."

        # Get the task IDs and fetch tasks
        task_ids = [t.get("taskId") for t in targets if t.get("taskId")]
        if not task_ids:
            return f"No tasks found on this {target_type}."

        # Fetch tasks by IDs
        output = ["Tasks:"]
        for task_id in task_ids:
            try:
                task_response = client.get(f"/tasks/{task_id}")
                task = task_response.get("data", {}).get("task", {})
                if task:
                    title = task.get("title", "(No title)")
                    status = task.get("status", "")
                    created = task.get("createdAt", "")[:10] if task.get("createdAt") else ""
                    output.append(f"- [{task_id}] {title} ({status}) - Created: {created}")
            except Exception:
                continue

        if len(output) == 1:
            return f"No tasks found on this {target_type}."

        return "\n".join(output)
    except Exception as e:
        return f"Error listing tasks: {str(e)}"


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
        # Note/Task target associations (CRUD is generated, linking is static)
        twenty_link_note_to_record,
        twenty_list_notes_on_record,
        twenty_link_task_to_record,
        twenty_list_tasks_on_record,
        # Generic tools
        twenty_search_records,
        twenty_get_record,
    ]
