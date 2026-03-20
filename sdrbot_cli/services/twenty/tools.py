"""Twenty static tools - schema-independent operations.

These tools work regardless of the user's Twenty schema and don't require sync.
Schema-dependent CRUD tools are generated in twenty_tools.py after sync.
"""

import json
from datetime import UTC, datetime, timedelta

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
        "person": "targetPerson",
        "company": "targetCompany",
        "opportunity": "targetOpportunity",
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
    # Map target type to the correct relation field name
    target_field_map = {
        "person": "targetPerson",
        "company": "targetCompany",
        "opportunity": "targetOpportunity",
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
        "person": "targetPerson",
        "company": "targetCompany",
        "opportunity": "targetOpportunity",
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
        "person": "targetPerson",
        "company": "targetCompany",
        "opportunity": "targetOpportunity",
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
        # For composite fields (like FULL_NAME on people), use dot notation
        if query:
            if object_type == "people":
                # People have composite name field (FULL_NAME) with sub-fields
                params["filter"] = (
                    f'or(name.firstName[ilike]:"%{query}%",'
                    f'name.lastName[ilike]:"%{query}%",'
                    f'emails.primaryEmail[ilike]:"%{query}%")'
                )
            else:
                # Companies and other objects have simple name field
                params["filter"] = (
                    f'or(name[ilike]:"%{query}%",domainName.primaryLinkUrl[ilike]:"%{query}%")'
                )

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


TWENTY_OBJECTS = ["companies", "people", "opportunities", "tasks", "notes"]


@tool
def twenty_count_records(object_type: str | None = None) -> str:
    """Count records for each object type in Twenty.

    Args:
        object_type: Optional - count a specific object type only (plural form, e.g., "companies").
                     If not provided, counts all main business objects.

    Returns:
        Record counts for each object type.
    """
    client = get_twenty()

    if object_type:
        types_to_count = [object_type]
    else:
        types_to_count = TWENTY_OBJECTS

    results = {}
    for obj_name in types_to_count:
        try:
            response = client.get(f"/{obj_name}", params={"limit": 1})
            total_count = response.get("totalCount")

            if total_count is None:
                data = response.get("data", {})
                if isinstance(data, dict):
                    total_count = data.get("totalCount")

            if total_count is not None:
                results[obj_name] = total_count
            else:
                records = response.get(obj_name, []) or response.get("data", {}).get(obj_name, [])
                results[obj_name] = len(records) if records else 0
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


def _fetch_all_pages(client, query: str, key: str, variables: dict | None = None) -> list:
    """Paginate through all pages of a GraphQL query.

    Args:
        client: TwentyClient instance.
        query: GraphQL query string. Must accept $after: String and return pageInfo.
        key: The top-level data key to extract (e.g. "people", "opportunities").
        variables: Optional base variables dict.

    Returns:
        Flat list of all node dicts across all pages.
    """
    results = []
    after = None
    variables = dict(variables or {})

    while True:
        variables["after"] = after
        data = client.graphql(query, variables)
        collection = data.get("data", {}).get(key, {})
        edges = collection.get("edges", [])
        results.extend(edge["node"] for edge in edges)

        page_info = collection.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")

    return results


@tool
def twenty_get_pipeline_status(
    object_type: str = "people",
    stage_field: str = "emailStatus",
    display_fields: list[str] | None = None,
    filter_field: str | None = None,
    filter_value: str | None = None,
    terminal_field: str | None = None,
    terminal_values: list[str] | None = None,
    overdue_field: str | None = None,
    overdue_after_field: str | None = None,
    overdue_days: int | None = None,
    title: str | None = None,
) -> str:
    """Get a structured pipeline status report from Twenty CRM.

    Fetches records of any object type, groups them by a specified stage field,
    and optionally separates terminal states and flags overdue records.
    All business logic (which fields, which values, what counts as overdue)
    is provided by the caller — nothing is hardcoded.

    Args:
        object_type: Twenty plural object name to query (e.g. "people", "opportunities").
        stage_field: Field to group records by (e.g. "emailStatus", "resellerPipelineStage").
        display_fields: List of additional fields to show per record in the output.
                        Nested relation fields use dot notation (e.g. "company.name",
                        "name.firstName"). Defaults to ["id"] if not provided.
        filter_field: Optional field to pre-filter records on (e.g. "sourcePipeline").
        filter_value: Value for filter_field (e.g. "RESELLER_CHANNEL"). Must be an
                      unquoted enum value or a quoted string as appropriate for GraphQL.
        terminal_field: Optional field used to detect terminal states (e.g. "stage").
                        Records where this field matches a terminal_value are separated
                        into a Terminal section rather than grouped with active records.
        terminal_values: List of values on terminal_field that indicate terminal state
                         (e.g. ["WON", "LOST"]).
        overdue_field: Optional boolean/status field to flag overdue records — records
                       where this field is null or matches overdue_after_field criteria.
                       Used as the stage_field value to watch (e.g. "OUTREACH_SENT").
        overdue_after_field: Date field to compare against overdue_days
                             (e.g. "emailSentDate").
        overdue_days: Number of days after overdue_after_field before a record is
                      considered overdue. Only applies if overdue_after_field is set.
        title: Optional title for the report section. Defaults to
               "{object_type} grouped by {stage_field}".

    Returns:
        Formatted pipeline status report as a string.

    Examples:
        # Outreach pipeline — people grouped by emailStatus, flag overdue OUTREACH_SENT
        twenty_get_pipeline_status(
            object_type="people",
            stage_field="emailStatus",
            display_fields=["name.firstName", "name.lastName", "company.name", "emailSentDate"],
            overdue_field="OUTREACH_SENT",
            overdue_after_field="emailSentDate",
            overdue_days=6,
            title="Outreach Pipeline",
        )

        # Reseller opportunity pipeline — opportunities filtered to RESELLER_CHANNEL,
        # grouped by resellerPipelineStage, WON/LOST separated as terminal
        twenty_get_pipeline_status(
            object_type="opportunities",
            stage_field="resellerPipelineStage",
            display_fields=["name", "company.name", "pointOfContact.name.firstName", "pointOfContact.name.lastName"],
            filter_field="sourcePipeline",
            filter_value="RESELLER_CHANNEL",
            terminal_field="stage",
            terminal_values=["WON", "LOST"],
            title="Reseller Partner Pipeline",
        )
    """
    client = get_twenty()

    # --- Build GraphQL field selection ---
    fields = display_fields or []
    all_scalar_fields = {stage_field}
    if terminal_field:
        all_scalar_fields.add(terminal_field)
    if overdue_after_field:
        all_scalar_fields.add(overdue_after_field)

    def _build_field_selection(
        fields: list[str], extra_scalars: set[str], top_level: bool = False
    ) -> str:
        """Build GraphQL field selection, handling dot-notation for nested fields."""
        scalars = set(extra_scalars)
        nested: dict[str, list[str]] = {}

        for f in fields:
            parts = f.split(".", 1)
            if len(parts) == 1:
                scalars.add(f)
            else:
                parent, child = parts
                nested.setdefault(parent, []).append(child)

        lines = (["id"] if top_level else []) + sorted(scalars)
        for parent, children in sorted(nested.items()):
            inner = _build_field_selection(children, set(), top_level=False)
            lines.append(f"{parent} {{ {inner} }}")
        return " ".join(lines)

    field_selection = _build_field_selection(fields, all_scalar_fields, top_level=True)

    # --- Build GraphQL filter clause ---
    filter_clause = ""
    if filter_field and filter_value:
        filter_clause = f"filter: {{ {filter_field}: {{ eq: {filter_value} }} }}"

    query = f"""
    query GetPipelineStatus($after: String) {{
      {object_type}(
        {filter_clause}
        first: 100
        after: $after
      ) {{
        pageInfo {{ hasNextPage endCursor }}
        edges {{
          node {{
            {field_selection}
          }}
        }}
      }}
    }}
    """

    try:
        records = _fetch_all_pages(client, query, object_type)
    except Exception as e:
        return f"Error fetching {object_type}: {str(e)}"

    # --- Helper to extract a value from a nested dot-path ---
    def _get_nested(record: dict, path: str) -> str:
        parts = path.split(".")
        val = record
        for p in parts:
            if not isinstance(val, dict):
                return ""
            val = val.get(p, "")
        return str(val) if val else ""

    # --- Group records ---
    active_groups: dict[str, list] = {}
    terminal_groups: dict[str, list] = {}
    terminal_set = set(terminal_values or [])

    for r in records:
        # Check terminal first
        if terminal_field and terminal_set:
            t_val = r.get(terminal_field, "")
            if t_val in terminal_set:
                terminal_groups.setdefault(t_val, []).append(r)
                continue
        stage_val = r.get(stage_field) or "UNKNOWN"
        active_groups.setdefault(stage_val, []).append(r)

    # --- Flag overdue records ---
    overdue: list[dict] = []
    if overdue_field and overdue_after_field and overdue_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=overdue_days)
        for r in active_groups.get(overdue_field, []):
            date_raw = r.get(overdue_after_field)
            if date_raw:
                try:
                    date_dt = datetime.fromisoformat(str(date_raw)).replace(tzinfo=UTC)
                    if date_dt <= cutoff:
                        overdue.append(r)
                except ValueError:
                    pass

    # --- Format output ---
    report_title = title or f"{object_type} grouped by {stage_field}"
    total = len(records)
    lines = [f"## {report_title} ({total} total)"]

    if active_groups:
        for stage_val, recs in sorted(active_groups.items()):
            lines.append(f"\n### {stage_val} ({len(recs)})")
            for r in recs:
                parts = []
                for f in fields:
                    val = _get_nested(r, f)
                    if val:
                        parts.append(val)
                lines.append(f"  - {' | '.join(parts) if parts else r.get('id', '')}")

    if terminal_groups:
        lines.append("\n### Terminal")
        for t_val, recs in sorted(terminal_groups.items()):
            lines.append(f"  **{t_val}**: {len(recs)}")

    if overdue:
        lines.append(
            f"\n### OVERDUE ({len(overdue)}) — {overdue_field} for >{overdue_days}d with no follow-up"
        )
        for r in overdue:
            parts = []
            for f in fields:
                val = _get_nested(r, f)
                if val:
                    parts.append(val)
            lines.append(f"  - {' | '.join(parts) if parts else r.get('id', '')}")

    return "\n".join(lines)


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
        twenty_count_records,
        # Pipeline status
        twenty_get_pipeline_status,
    ]
