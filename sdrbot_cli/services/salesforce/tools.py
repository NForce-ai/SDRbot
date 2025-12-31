"""Salesforce static tools - schema-independent operations.

These tools work regardless of the user's Salesforce schema and don't require sync.
Schema-dependent CRUD tools are generated in tools.generated.py after sync.
"""

import json

from langchain_core.tools import BaseTool, tool

from sdrbot_cli.auth.salesforce import get_client

# Shared client instance (lazy loaded)
_sf_client = None


def get_sf():
    """Get or create Salesforce client instance."""
    global _sf_client
    if _sf_client is None:
        _sf_client = get_client()
    return _sf_client


def reset_client() -> None:
    """Reset the cached client (for testing)."""
    global _sf_client
    _sf_client = None


@tool
def salesforce_soql_query(query: str) -> str:
    """
    Execute a SOQL query against Salesforce.
    Use this for complex queries, reporting, or when you need to join data across objects.

    Args:
        query: SOQL query string (e.g., "SELECT Id, Name, Email FROM Contact WHERE Name LIKE 'John%' LIMIT 10")

    Note: Only SELECT queries are allowed for safety.
    """
    sf = get_sf()
    try:
        # Sanity check: prevent destructive queries
        if not query.strip().upper().startswith("SELECT"):
            return "Error: Only SELECT queries are allowed via this tool."

        results = sf.query(query)

        records = results.get("records", [])
        if not records:
            return "Query returned 0 records."

        # Clean up attributes metadata to save tokens
        clean_records = []
        for rec in records:
            if "attributes" in rec:
                del rec["attributes"]
            clean_records.append(rec)

        return (
            f"Query returned {results['totalSize']} records:\n{json.dumps(clean_records, indent=2)}"
        )
    except Exception as e:
        return f"SOQL Error: {str(e)}"


@tool
def salesforce_sosl_search(search: str) -> str:
    """
    Execute a SOSL search across Salesforce objects.
    Use this for full-text search across multiple object types.

    Args:
        search: SOSL search string (e.g., "FIND {John Smith} IN ALL FIELDS RETURNING Contact(Id, Name), Lead(Id, Name)")
    """
    sf = get_sf()
    try:
        results = sf.search(search)

        if not results.get("searchRecords"):
            return "No records found."

        # Format results
        output = []
        for rec in results["searchRecords"]:
            obj_type = rec.get("attributes", {}).get("type", "Unknown")
            output.append(f"- [{obj_type}] {rec.get('Name', rec.get('Id'))} (ID: {rec.get('Id')})")

        return f"Found {len(results['searchRecords'])} records:\n" + "\n".join(output)
    except Exception as e:
        return f"SOSL Error: {str(e)}"


# =============================================================================
# NOTES - Note management on records
# =============================================================================


@tool
def salesforce_create_note_on_record(
    parent_id: str,
    title: str,
    body: str,
) -> str:
    """Create a note linked to a Salesforce record.

    Args:
        parent_id: The Salesforce ID of the record to attach the note to
                  (e.g., Account, Contact, Opportunity ID).
        title: Title of the note.
        body: Body content of the note.

    Returns:
        Success message with the new note ID.
    """
    sf = get_sf()
    try:
        result = sf.restful(
            "sobjects/Note",
            method="POST",
            json={
                "ParentId": parent_id,
                "Title": title,
                "Body": body,
            },
        )

        if result.get("success"):
            return f"Successfully created note '{title}' with ID: {result['id']}"
        else:
            errors = result.get("errors", [])
            return f"Failed to create note: {errors}"
    except Exception as e:
        return f"Error creating note: {str(e)}"


@tool
def salesforce_list_notes_on_record(parent_id: str, limit: int = 20) -> str:
    """List notes attached to a Salesforce record.

    Args:
        parent_id: The Salesforce ID of the record to list notes for.
        limit: Maximum number of notes to return (default 20).

    Returns:
        JSON list of notes with their details.
    """
    sf = get_sf()
    try:
        query = f"""
            SELECT Id, Title, Body, CreatedDate, CreatedBy.Name
            FROM Note
            WHERE ParentId = '{parent_id}'
            ORDER BY CreatedDate DESC
            LIMIT {limit}
        """

        result = sf.query(query)

        records = result.get("records", [])
        if not records:
            return f"No notes found for record {parent_id}."

        notes = []
        for rec in records:
            # Clean up attributes
            if "attributes" in rec:
                del rec["attributes"]
            if rec.get("CreatedBy"):
                rec["CreatedBy"] = rec["CreatedBy"].get("Name")
            notes.append(rec)

        return f"Found {len(notes)} notes:\n" + json.dumps(notes, indent=2)
    except Exception as e:
        return f"Error listing notes: {str(e)}"


# =============================================================================
# TASKS - Task management on records
# =============================================================================


@tool
def salesforce_create_task_on_record(
    record_id: str,
    subject: str,
    description: str | None = None,
    due_date: str | None = None,
    status: str = "Not Started",
    priority: str = "Normal",
    owner_id: str | None = None,
) -> str:
    """Create a task linked to a Salesforce record.

    Args:
        record_id: The Salesforce ID of the record to link the task to.
                   Supports Contacts, Leads, Accounts, Opportunities, etc.
        subject: Subject/title of the task.
        description: Detailed description of the task.
        due_date: Due date in YYYY-MM-DD format.
        status: Task status. Options: "Not Started", "In Progress",
               "Completed", "Waiting on someone else", "Deferred".
        priority: Task priority. Options: "High", "Normal", "Low".
        owner_id: User ID to assign the task to (defaults to current user).

    Returns:
        Success message with the new task ID.
    """
    sf = get_sf()
    try:
        # Contacts (003) and Leads (00Q) use WhoId, everything else uses WhatId
        id_field = "WhoId" if record_id.startswith(("003", "00Q")) else "WhatId"

        task_data = {
            id_field: record_id,
            "Subject": subject,
            "Status": status,
            "Priority": priority,
        }

        if description:
            task_data["Description"] = description
        if due_date:
            task_data["ActivityDate"] = due_date
        if owner_id:
            task_data["OwnerId"] = owner_id

        result = sf.restful("sobjects/Task", method="POST", json=task_data)

        if result.get("success"):
            return f"Successfully created task '{subject}' with ID: {result['id']}"
        else:
            errors = result.get("errors", [])
            return f"Failed to create task: {errors}"
    except Exception as e:
        return f"Error creating task: {str(e)}"


@tool
def salesforce_list_tasks_on_record(record_id: str, limit: int = 20) -> str:
    """List tasks linked to a Salesforce record.

    Args:
        record_id: The Salesforce ID of the record to list tasks for.
                   Supports Contacts, Leads, Accounts, Opportunities, etc.
        limit: Maximum number of tasks to return (default 20).

    Returns:
        JSON list of tasks with their details.
    """
    sf = get_sf()
    try:
        # Contacts (003) and Leads (00Q) use WhoId, everything else uses WhatId
        id_field = "WhoId" if record_id.startswith(("003", "00Q")) else "WhatId"

        query = f"""
            SELECT Id, Subject, Description, Status, Priority,
                   ActivityDate, Owner.Name, CreatedDate
            FROM Task
            WHERE {id_field} = '{record_id}'
            ORDER BY CreatedDate DESC
            LIMIT {limit}
        """

        result = sf.query(query)

        records = result.get("records", [])
        if not records:
            return f"No tasks found for record {record_id}."

        tasks = []
        for rec in records:
            # Clean up attributes
            if "attributes" in rec:
                del rec["attributes"]
            if rec.get("Owner"):
                rec["Owner"] = rec["Owner"].get("Name")
            tasks.append(rec)

        return f"Found {len(tasks)} tasks:\n" + json.dumps(tasks, indent=2)
    except Exception as e:
        return f"Error listing tasks: {str(e)}"


# =============================================================================
# GENERIC - Universal record operations
# =============================================================================


@tool
def salesforce_search_records(
    object_type: str,
    query: str | None = None,
    limit: int = 20,
) -> str:
    """Search or list records of any Salesforce object type.

    Args:
        object_type: The object API name (e.g., "Contact", "Account", "Lead").
        query: Optional search string to filter by Name field.
              If not provided, returns recent records.
        limit: Maximum number of records to return (default 20, max 200).

    Returns:
        JSON list of matching records.
    """
    sf = get_sf()
    try:
        limit = min(limit, 200)

        # Build WHERE clause
        where_clause = ""
        if query:
            # Escape single quotes in query
            safe_query = query.replace("'", "\\'")
            where_clause = f"WHERE Name LIKE '%{safe_query}%'"

        soql = f"""
            SELECT Id, Name, CreatedDate, LastModifiedDate
            FROM {object_type}
            {where_clause}
            ORDER BY LastModifiedDate DESC
            LIMIT {limit}
        """

        result = sf.query(soql)

        records = result.get("records", [])
        if not records:
            search_info = f" matching '{query}'" if query else ""
            return f"No {object_type} records found{search_info}."

        # Clean up records
        clean_records = []
        for rec in records:
            if "attributes" in rec:
                del rec["attributes"]
            clean_records.append(rec)

        total = result.get("totalSize", len(records))
        return f"Found {total} {object_type} records:\n" + json.dumps(clean_records, indent=2)
    except Exception as e:
        return f"Error searching {object_type}: {str(e)}"


@tool
def salesforce_get_record(object_type: str, record_id: str) -> str:
    """Get a specific record by ID from any Salesforce object type.

    Args:
        object_type: The object API name (e.g., "Contact", "Account").
        record_id: The Salesforce ID of the record.

    Returns:
        JSON with the record details.
    """
    sf = get_sf()
    try:
        result = sf.restful(f"sobjects/{object_type}/{record_id}")

        # Remove metadata
        if "attributes" in result:
            del result["attributes"]

        return f"{object_type} {record_id}:\n" + json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting {object_type}: {str(e)}"


def get_static_tools() -> list[BaseTool]:
    """Get all static Salesforce tools.

    Returns:
        List of schema-independent Salesforce tools.
    """
    return [
        # Query tools
        salesforce_soql_query,
        salesforce_sosl_search,
        # Notes
        salesforce_create_note_on_record,
        salesforce_list_notes_on_record,
        # Tasks
        salesforce_create_task_on_record,
        salesforce_list_tasks_on_record,
        # Generic
        salesforce_search_records,
        salesforce_get_record,
    ]
