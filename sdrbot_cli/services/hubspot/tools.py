"""HubSpot static tools - schema-independent operations.

These tools work regardless of the user's HubSpot schema and don't require sync.
Schema-dependent CRUD tools are generated in tools.generated.py after sync.
"""

import json
from datetime import UTC

from langchain_core.tools import BaseTool, tool

from sdrbot_cli.auth.hubspot import get_client

# Shared client instance (lazy loaded)
_hs_client = None


def get_hs():
    """Get or create HubSpot client instance.

    Returns fresh client on each call if previous call returned None.
    """
    global _hs_client
    if _hs_client is None:
        _hs_client = get_client()
    # If still None, auth failed - don't cache the failure
    if _hs_client is None:
        raise RuntimeError("HubSpot authentication failed. Check HUBSPOT_ACCESS_TOKEN in .env")
    return _hs_client


def reset_client():
    """Reset the cached client (useful after env reload)."""
    global _hs_client
    _hs_client = None


@tool
def hubspot_list_pipelines(object_type: str = "deals") -> str:
    """
    List all pipelines for an object type.

    Args:
        object_type: Either "deals" or "tickets" (the objects that support pipelines)
    """
    hs = get_hs()
    try:
        response = hs.crm.pipelines.pipelines_api.get_all(object_type=object_type)

        output = [f"Pipelines for {object_type}:"]
        for pipeline in response.results:
            output.append(f"- {pipeline.label} (ID: {pipeline.id})")
            for stage in pipeline.stages:
                output.append(f"    Stage: {stage.label} (ID: {stage.id})")

        return "\n".join(output)
    except Exception as e:
        return f"Error listing pipelines: {str(e)}"


@tool
def hubspot_create_association(
    from_object_type: str,
    from_object_id: str,
    to_object_type: str,
    to_object_id: str,
) -> str:
    """
    Create an association between two HubSpot records.

    Args:
        from_object_type: Source object type (e.g., "contacts", "companies", "deals")
        from_object_id: Source record ID
        to_object_type: Target object type (e.g., "contacts", "companies", "deals")
        to_object_id: Target record ID
    """
    hs = get_hs()
    try:
        # Get association types between these objects
        types_response = hs.crm.associations.v4.schema.definitions_api.get_all(
            from_object_type=from_object_type,
            to_object_type=to_object_type,
        )

        if not types_response.results:
            return f"No association types found between {from_object_type} and {to_object_type}"

        # Use the first (default) association type
        assoc_type = types_response.results[0]

        # Create the association
        # Note: HubSpot SDK v4 uses object_type/object_id (not from_object_type/from_object_id)
        from hubspot.crm.associations.v4.models import AssociationSpec

        hs.crm.associations.v4.basic_api.create(
            object_type=from_object_type,
            object_id=from_object_id,
            to_object_type=to_object_type,
            to_object_id=to_object_id,
            association_spec=[
                AssociationSpec(
                    association_category=assoc_type.category,
                    association_type_id=assoc_type.type_id,
                )
            ],
        )

        return f"Successfully associated {from_object_type}/{from_object_id} with {to_object_type}/{to_object_id}"
    except Exception as e:
        return f"Error creating association: {str(e)}"


@tool
def hubspot_list_associations(
    from_object_type: str,
    from_object_id: str,
    to_object_type: str,
) -> str:
    """
    List all associations from a record to another object type.

    Args:
        from_object_type: Source object type (e.g., "contacts")
        from_object_id: Source record ID
        to_object_type: Target object type to find associations to (e.g., "companies")
    """
    hs = get_hs()
    try:
        # Note: HubSpot SDK v4 uses object_type/object_id (not from_object_type/from_object_id)
        response = hs.crm.associations.v4.basic_api.get_page(
            object_type=from_object_type,
            object_id=from_object_id,
            to_object_type=to_object_type,
        )

        if not response.results:
            return f"No {to_object_type} associated with {from_object_type}/{from_object_id}"

        output = [f"Associated {to_object_type} records:"]
        for assoc in response.results:
            output.append(f"- ID: {assoc.to_object_id}")

        return "\n".join(output)
    except Exception as e:
        return f"Error listing associations: {str(e)}"


@tool
def hubspot_delete_association(
    from_object_type: str,
    from_object_id: str,
    to_object_type: str,
    to_object_id: str,
) -> str:
    """
    Remove an association between two HubSpot records.

    Args:
        from_object_type: Source object type
        from_object_id: Source record ID
        to_object_type: Target object type
        to_object_id: Target record ID
    """
    hs = get_hs()
    try:
        # Note: HubSpot SDK v4 uses object_type/object_id (not from_object_type/from_object_id)
        hs.crm.associations.v4.basic_api.archive(
            object_type=from_object_type,
            object_id=from_object_id,
            to_object_type=to_object_type,
            to_object_id=to_object_id,
        )

        return f"Successfully removed association between {from_object_type}/{from_object_id} and {to_object_type}/{to_object_id}"
    except Exception as e:
        return f"Error deleting association: {str(e)}"


# =============================================================================
# NOTES - Note management on records
# =============================================================================


@tool
def hubspot_create_note_on_record(
    object_type: str,
    object_id: str,
    body: str,
    timestamp: str | None = None,
) -> str:
    """Create a note and associate it with a record.

    Args:
        object_type: The object type (e.g., "contacts", "companies", "deals").
        object_id: The record ID to attach the note to.
        body: The note content (can include HTML formatting).
        timestamp: Optional timestamp in ISO format. Defaults to now.

    Returns:
        Success message with the new note ID.
    """
    from datetime import datetime

    hs = get_hs()
    try:
        from hubspot.crm.objects.notes import SimplePublicObjectInputForCreate

        # hs_timestamp is required - use provided or current time
        ts = timestamp or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        # Create the note with association
        note_input = SimplePublicObjectInputForCreate(
            properties={"hs_note_body": body, "hs_timestamp": ts},
            associations=[
                {
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": _get_note_association_type_id(object_type),
                        }
                    ],
                    "to": {"id": object_id},
                }
            ],
        )

        response = hs.crm.objects.notes.basic_api.create(
            simple_public_object_input_for_create=note_input
        )

        return f"Successfully created note (ID: {response.id}) on {object_type}/{object_id}"
    except Exception as e:
        return f"Error creating note: {str(e)}"


def _get_note_association_type_id(object_type: str) -> int:
    """Get the association type ID for notes to a given object type.

    HubSpot uses specific type IDs for note associations.
    """
    # Standard HubSpot association type IDs for notes
    type_ids = {
        "contacts": 202,  # Note to Contact
        "companies": 190,  # Note to Company
        "deals": 214,  # Note to Deal
        "tickets": 226,  # Note to Ticket
    }
    return type_ids.get(object_type, 202)  # Default to contact


@tool
def hubspot_list_notes_on_record(
    object_type: str,
    object_id: str,
    limit: int = 10,
) -> str:
    """List notes associated with a record.

    Args:
        object_type: The object type (e.g., "contacts", "companies", "deals").
        object_id: The record ID to get notes for.
        limit: Maximum notes to return (default 10).

    Returns:
        JSON list of notes with their content.
    """
    hs = get_hs()
    try:
        # Get associations from the record to notes
        assoc_response = hs.crm.associations.v4.basic_api.get_page(
            object_type=object_type,
            object_id=object_id,
            to_object_type="notes",
            limit=limit,
        )

        if not assoc_response.results:
            return f"No notes found on {object_type}/{object_id}"

        # Fetch each note's details
        notes = []
        for assoc in assoc_response.results:
            try:
                note = hs.crm.objects.notes.basic_api.get_by_id(
                    note_id=assoc.to_object_id,
                    properties=["hs_note_body", "hs_timestamp", "hubspot_owner_id"],
                )
                notes.append(
                    {
                        "id": note.id,
                        "body": note.properties.get("hs_note_body", ""),
                        "timestamp": note.properties.get("hs_timestamp"),
                        "ownerId": note.properties.get("hubspot_owner_id"),
                    }
                )
            except Exception:
                continue  # Skip notes we can't access

        if not notes:
            return f"No accessible notes found on {object_type}/{object_id}"

        return f"Found {len(notes)} notes on {object_type}/{object_id}:\n" + json.dumps(
            notes, indent=2
        )
    except Exception as e:
        return f"Error listing notes: {str(e)}"


# =============================================================================
# TASKS - Task management on records
# =============================================================================


@tool
def hubspot_create_task_on_record(
    object_type: str,
    object_id: str,
    subject: str,
    body: str | None = None,
    due_date: str | None = None,
    priority: str = "MEDIUM",
    status: str = "NOT_STARTED",
    owner_id: str | None = None,
) -> str:
    """Create a task and associate it with a record.

    Args:
        object_type: The object type (e.g., "contacts", "companies", "deals").
        object_id: The record ID to attach the task to.
        subject: Task title/subject.
        body: Optional task description.
        due_date: Due date in ISO format (e.g., "2024-12-31"). Defaults to now.
        priority: Task priority - "LOW", "MEDIUM", or "HIGH" (default "MEDIUM").
        status: Task status - "NOT_STARTED", "IN_PROGRESS", "WAITING",
                "COMPLETED", or "DEFERRED" (default "NOT_STARTED").
        owner_id: HubSpot owner ID to assign the task to.

    Returns:
        Success message with the new task ID.
    """
    from datetime import datetime

    hs = get_hs()
    try:
        from hubspot.crm.objects.tasks import SimplePublicObjectInputForCreate

        # hs_timestamp is required - use due_date or current time
        ts = due_date or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        properties = {
            "hs_task_subject": subject,
            "hs_task_priority": priority,
            "hs_task_status": status,
            "hs_timestamp": ts,
        }

        if body:
            properties["hs_task_body"] = body
        if owner_id:
            properties["hubspot_owner_id"] = owner_id

        task_input = SimplePublicObjectInputForCreate(
            properties=properties,
            associations=[
                {
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": _get_task_association_type_id(object_type),
                        }
                    ],
                    "to": {"id": object_id},
                }
            ],
        )

        response = hs.crm.objects.tasks.basic_api.create(
            simple_public_object_input_for_create=task_input
        )

        return f"Successfully created task '{subject}' (ID: {response.id}) on {object_type}/{object_id}"
    except Exception as e:
        return f"Error creating task: {str(e)}"


def _get_task_association_type_id(object_type: str) -> int:
    """Get the association type ID for tasks to a given object type.

    HubSpot uses specific type IDs for task associations.
    """
    # Standard HubSpot association type IDs for tasks
    type_ids = {
        "contacts": 204,  # Task to Contact
        "companies": 192,  # Task to Company
        "deals": 216,  # Task to Deal
        "tickets": 228,  # Task to Ticket
    }
    return type_ids.get(object_type, 204)  # Default to contact


@tool
def hubspot_list_tasks_on_record(
    object_type: str,
    object_id: str,
    limit: int = 10,
) -> str:
    """List tasks associated with a record.

    Args:
        object_type: The object type (e.g., "contacts", "companies", "deals").
        object_id: The record ID to get tasks for.
        limit: Maximum tasks to return (default 10).

    Returns:
        JSON list of tasks with their details.
    """
    hs = get_hs()
    try:
        # Get associations from the record to tasks
        assoc_response = hs.crm.associations.v4.basic_api.get_page(
            object_type=object_type,
            object_id=object_id,
            to_object_type="tasks",
            limit=limit,
        )

        if not assoc_response.results:
            return f"No tasks found on {object_type}/{object_id}"

        # Fetch each task's details
        tasks = []
        for assoc in assoc_response.results:
            try:
                task = hs.crm.objects.tasks.basic_api.get_by_id(
                    task_id=assoc.to_object_id,
                    properties=[
                        "hs_task_subject",
                        "hs_task_body",
                        "hs_task_status",
                        "hs_task_priority",
                        "hs_timestamp",
                        "hubspot_owner_id",
                    ],
                )
                tasks.append(
                    {
                        "id": task.id,
                        "subject": task.properties.get("hs_task_subject", ""),
                        "body": task.properties.get("hs_task_body"),
                        "status": task.properties.get("hs_task_status"),
                        "priority": task.properties.get("hs_task_priority"),
                        "dueDate": task.properties.get("hs_timestamp"),
                        "ownerId": task.properties.get("hubspot_owner_id"),
                    }
                )
            except Exception:
                continue  # Skip tasks we can't access

        if not tasks:
            return f"No accessible tasks found on {object_type}/{object_id}"

        return f"Found {len(tasks)} tasks on {object_type}/{object_id}:\n" + json.dumps(
            tasks, indent=2
        )
    except Exception as e:
        return f"Error listing tasks: {str(e)}"


# =============================================================================
# GENERIC OPERATIONS - Work with any object type
# =============================================================================


@tool
def hubspot_search_records(
    object_type: str,
    query: str | None = None,
    limit: int = 10,
) -> str:
    """Search for records of any object type.

    This is a generic search tool that works with any HubSpot object type,
    including custom objects.

    Args:
        object_type: The object type to search (e.g., "contacts", "companies",
                     "deals", "tickets", or custom object type ID like "2-12345").
        query: Free-text search query (searches across all searchable fields).
        limit: Maximum results to return (default 10).

    Returns:
        JSON list of matching records with their properties.
    """
    hs = get_hs()
    try:
        from hubspot.crm.objects import PublicObjectSearchRequest

        search_request = PublicObjectSearchRequest(limit=limit)

        if query:
            search_request.query = query

        response = hs.crm.objects.search_api.do_search(
            object_type=object_type, public_object_search_request=search_request
        )

        if not response.results:
            return f"No {object_type} found matching the search criteria."

        results = []
        for r in response.results:
            results.append({"id": r.id, "properties": r.properties})

        return f"Found {response.total} {object_type}:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error searching {object_type}: {str(e)}"


@tool
def hubspot_get_record(object_type: str, record_id: str) -> str:
    """Get a record of any object type by ID.

    This is a generic get tool that works with any HubSpot object type,
    including custom objects.

    Args:
        object_type: The object type (e.g., "contacts", "companies",
                     "deals", "tickets", or custom object type ID like "2-12345").
        record_id: The record's HubSpot ID.

    Returns:
        JSON with the record's properties.
    """
    hs = get_hs()
    try:
        response = hs.crm.objects.basic_api.get_by_id(object_type=object_type, object_id=record_id)

        result = {"id": response.id, "properties": response.properties}

        return f"{object_type.title()} {record_id}:\n" + json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting {object_type}: {str(e)}"


def get_static_tools() -> list[BaseTool]:
    """Get all static HubSpot tools.

    Returns:
        List of schema-independent HubSpot tools.
    """
    return [
        # Pipelines
        hubspot_list_pipelines,
        # Associations
        hubspot_create_association,
        hubspot_list_associations,
        hubspot_delete_association,
        # Notes
        hubspot_create_note_on_record,
        hubspot_list_notes_on_record,
        # Tasks
        hubspot_create_task_on_record,
        hubspot_list_tasks_on_record,
        # Generic
        hubspot_search_records,
        hubspot_get_record,
    ]
