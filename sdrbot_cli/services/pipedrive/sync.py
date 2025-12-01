"""Pipedrive schema sync and tool generation.

This module:
1. Fetches the Pipedrive schema (object types and their fields)
2. Generates strongly-typed Python tools for each object type
3. Writes the generated code to ./generated/pipedrive_tools.py
"""

from typing import Any

from sdrbot_cli.auth.pipedrive import get_pipedrive_client
from sdrbot_cli.config import settings
from sdrbot_cli.services.registry import compute_schema_hash

# Standard Pipedrive objects and their field endpoints
STANDARD_OBJECTS = {
    "deals": "dealFields",
    "persons": "personFields",
    "organizations": "organizationFields",
    "products": "productFields",
    "activities": "activityFields",
    "leads": "leadFields",
}

# Fields to exclude from generated tools (system/read-only/calculated fields)
EXCLUDED_FIELD_KEYS = [
    "add_time",
    "update_time",
    "creator_user_id",
    "stage_change_time",
    "deleted",
    "activities_count",
    "done_activities_count",
    "undone_activities_count",
    "files_count",
    "notes_count",
    "followers_count",
    "email_messages_count",
    "last_activity_id",
    "last_activity_date",
    "next_activity_id",
    "next_activity_date",
    "next_activity_subject",
    "next_activity_type",
    "next_activity_duration",
    "next_activity_note",
    "formatted_value",
    "weighted_value",
    "formatted_weighted_value",
    "rotten_time",
    "cc_email",
    "won_deals_count",
    "lost_deals_count",
    "open_deals_count",
    "closed_deals_count",
    "related_lost_deals_count",
    "related_won_deals_count",
    "related_open_deals_count",
    "related_closed_deals_count",
    "first_char",
]

# Maximum fields per tool to keep signatures manageable
MAX_FIELDS_PER_TOOL = 20


def sync_schema() -> dict[str, Any]:
    """Fetch Pipedrive schema and generate tools.

    Returns:
        Dict with keys:
        - schema_hash: Hash of the schema for change detection
        - objects: List of object names that were synced
    """
    client = get_pipedrive_client()
    if not client:
        raise RuntimeError("Failed to authenticate with Pipedrive")

    # Fetch fields for each object type
    objects_schema = {}
    for obj_type, fields_endpoint in STANDARD_OBJECTS.items():
        try:
            fields = _fetch_object_fields(client, fields_endpoint)
            if fields:
                objects_schema[obj_type] = fields
        except Exception:
            # Skip objects we can't access
            continue

    # Generate the tools code
    generated_code = _generate_tools_code(objects_schema)

    # Write to ./generated/pipedrive_tools.py
    output_path = settings.ensure_generated_dir() / "pipedrive_tools.py"
    output_path.write_text(generated_code, encoding="utf-8")

    return {
        "schema_hash": compute_schema_hash(objects_schema),
        "objects": list(objects_schema.keys()),
    }


def _fetch_object_fields(client, fields_endpoint: str) -> list[dict[str, Any]]:
    """Fetch fields for a specific object type.

    Args:
        client: Pipedrive client instance.
        fields_endpoint: API endpoint for fields (e.g., "dealFields").

    Returns:
        List of field dictionaries with key, name, type, etc.
    """
    response = client.get(f"/{fields_endpoint}")
    raw_fields = response.get("data", [])

    fields = []
    for f in raw_fields:
        field_key = f.get("key", "")

        # Skip system/internal fields
        if field_key in EXCLUDED_FIELD_KEYS:
            continue

        # Skip fields starting with hash (internal/custom field IDs sometimes)
        if field_key.startswith("#"):
            continue

        # Get options for enum types
        options = []
        if f.get("options"):
            options = [opt.get("label", opt.get("id", "")) for opt in f["options"] if opt][:20]

        # In Pipedrive, add_visible_flag=True or bulk_edit_allowed=True means writable
        # edit_flag is misleading (often False for writable fields)
        is_writable = f.get("add_visible_flag", False) or f.get("bulk_edit_allowed", False)

        fields.append(
            {
                "key": field_key,
                "name": f.get("name", field_key),
                "field_type": f.get("field_type", "text"),
                "mandatory_flag": f.get("mandatory_flag", False),
                "is_writable": is_writable,
                "add_visible_flag": f.get("add_visible_flag", False),
                "options": options,
            }
        )

    return fields


def _generate_tools_code(schema: dict[str, list[dict]]) -> str:
    """Generate Python tool code from schema.

    Args:
        schema: Dict mapping object types to their field lists.

    Returns:
        Generated Python code as a string.
    """
    lines = [
        '"""Auto-generated Pipedrive tools based on schema sync.',
        "",
        "DO NOT EDIT - This file is regenerated when you run /sync pipedrive",
        '"""',
        "",
        "import json",
        "from langchain_core.tools import tool",
        "",
        "from sdrbot_cli.auth.pipedrive import get_pipedrive_client",
        "",
        "",
        "def _get_pipedrive():",
        '    """Get Pipedrive client, raising if not available."""',
        "    client = get_pipedrive_client()",
        "    if not client:",
        '        raise RuntimeError("Pipedrive client not available")',
        "    return client",
        "",
    ]

    for obj_type, fields in schema.items():
        # Handle singular forms correctly
        singular_map = {
            "deals": "deal",
            "persons": "person",
            "organizations": "organization",
            "products": "product",
            "activities": "activity",
            "leads": "lead",
        }
        singular = singular_map.get(obj_type, obj_type.rstrip("s"))

        # Filter to writable fields for create/update
        writable_fields = [f for f in fields if f.get("is_writable", False)]

        # Prioritize important fields
        writable_fields = _prioritize_fields(writable_fields, obj_type)

        # Limit fields per tool
        create_fields = writable_fields[:MAX_FIELDS_PER_TOOL]
        search_fields = [
            f
            for f in fields
            if f["field_type"] in ("text", "varchar", "enum", "set", "phone", "email")
        ][:10]

        # Generate create tool
        lines.extend(_generate_create_tool(obj_type, singular, create_fields))
        lines.append("")

        # Generate update tool
        lines.extend(_generate_update_tool(obj_type, singular, create_fields))
        lines.append("")

        # Generate search tool
        lines.extend(_generate_search_tool(obj_type, singular, search_fields))
        lines.append("")

        # Generate get tool
        lines.extend(_generate_get_tool(obj_type, singular))
        lines.append("")

        # Generate delete tool
        lines.extend(_generate_delete_tool(obj_type, singular))
        lines.append("")

    return "\n".join(lines)


def _prioritize_fields(fields: list[dict], obj_type: str) -> list[dict]:
    """Sort fields with most important ones first.

    Args:
        fields: List of field dicts.
        obj_type: Object type name.

    Returns:
        Sorted list with most important fields first.
    """
    # Priority fields by object type
    priority_map = {
        "deals": [
            "title",
            "value",
            "currency",
            "stage_id",
            "pipeline_id",
            "status",
            "expected_close_date",
        ],
        "persons": ["name", "email", "phone", "org_id", "label", "visible_to"],
        "organizations": ["name", "address", "owner_id", "visible_to", "label"],
        "products": ["name", "code", "unit", "tax", "prices"],
        "activities": [
            "subject",
            "type",
            "due_date",
            "due_time",
            "duration",
            "deal_id",
            "person_id",
            "org_id",
        ],
        "leads": [
            "title",
            "person_id",
            "organization_id",
            "value",
            "expected_close_date",
            "label_ids",
        ],
    }

    # Only these fields are truly required by Pipedrive API
    required_fields_map = {
        "deals": ["title"],
        "persons": ["name"],
        "organizations": ["name"],
        "products": ["name"],
        "activities": ["subject", "type"],
        "leads": ["title"],
    }

    # Mark fields as mandatory based on our knowledge of the API
    required_keys = set(required_fields_map.get(obj_type, []))
    for f in fields:
        f["mandatory_flag"] = f["key"] in required_keys

    priority_keys = priority_map.get(obj_type, [])

    def sort_key(f):
        key = f.get("key", "")
        if key in priority_keys:
            return (0, priority_keys.index(key))
        if f.get("mandatory_flag"):
            return (1, key)
        return (2, key)

    return sorted(fields, key=sort_key)


def _field_to_python_type(field: dict) -> str:
    """Convert Pipedrive field type to Python type hint."""
    field_type = field.get("field_type", "text")

    type_map = {
        "varchar": "str",
        "text": "str",
        "enum": "str",
        "set": "str",
        "phone": "str",
        "email": "str",
        "double": "float",
        "int": "int",
        "monetary": "float",
        "date": "str",
        "time": "str",
        "daterange": "str",
        "timerange": "str",
        "address": "str",
        "user": "int",
        "org": "int",
        "person": "int",
        "people": "str",
        "visible_to": "int",
    }

    return type_map.get(field_type, "str")


def _generate_create_tool(obj_type: str, singular: str, fields: list[dict]) -> list[str]:
    """Generate a create tool for an object type."""
    func_name = f"pipedrive_create_{singular}"

    # Build function signature
    params = []
    for f in fields:
        py_type = _field_to_python_type(f)
        key = f["key"]
        if f.get("mandatory_flag"):
            params.append(f"    {key}: {py_type},")
        else:
            params.append(f"    {key}: {py_type} | None = None,")

    params_str = "\n".join(params) if params else "    # No custom fields"

    # Build docstring
    doc_lines = [f'    """Create a new {singular} in Pipedrive.']
    doc_lines.append("")
    doc_lines.append("    Args:")
    for f in fields:
        doc_lines.append(f"        {f['key']}: {f.get('name', f['key'])}.")
        if f.get("options"):
            doc_lines.append(f"            Options: {', '.join(f['options'][:5])}")
    doc_lines.append("")
    doc_lines.append("    Returns:")
    doc_lines.append(f"        Success message with the new {singular} ID.")
    doc_lines.append('    """')

    # Build function body
    body = [
        "    pipedrive = _get_pipedrive()",
        "    try:",
        "        data = {}",
        "        local_vars = locals()",
        "        param_names = [",
    ]

    for f in fields:
        body.append(f"            '{f['key']}',")

    body.extend(
        [
            "        ]",
            "        for name in param_names:",
            "            value = local_vars.get(name)",
            "            if value is not None:",
            "                data[name] = value",
            "",
            "        if not data:",
            f'            return "Error: At least one field must be provided to create a {singular}."',
            "",
            f'        response = pipedrive.post("/{obj_type}", json=data)',
            '        result = response.get("data", {})',
            '        record_id = result.get("id", "unknown")',
            "",
            f'        return f"Successfully created {singular} with ID: {{record_id}}"',
            "    except Exception as e:",
            f'        return f"Error creating {singular}: {{str(e)}}"',
        ]
    )

    return [
        "@tool",
        f"def {func_name}(",
        params_str,
        ") -> str:",
        *doc_lines,
        *body,
    ]


def _generate_update_tool(obj_type: str, singular: str, fields: list[dict]) -> list[str]:
    """Generate an update tool for an object type."""
    func_name = f"pipedrive_update_{singular}"

    # Build function signature - ID is required, all others optional
    params = [f"    {singular}_id: int,"]
    for f in fields:
        py_type = _field_to_python_type(f)
        key = f["key"]
        params.append(f"    {key}: {py_type} | None = None,")

    params_str = "\n".join(params)

    # Build docstring
    doc_lines = [f'    """Update an existing {singular} in Pipedrive.']
    doc_lines.append("")
    doc_lines.append("    Args:")
    doc_lines.append(f"        {singular}_id: The ID of the {singular} to update.")
    for f in fields:
        doc_lines.append(f"        {f['key']}: {f.get('name', f['key'])}.")
    doc_lines.append("")
    doc_lines.append("    Returns:")
    doc_lines.append(f"        Success message confirming the {singular} was updated.")
    doc_lines.append('    """')

    # Build function body
    body = [
        "    pipedrive = _get_pipedrive()",
        "    try:",
        "        data = {}",
        "        local_vars = locals()",
        "        param_names = [",
    ]

    for f in fields:
        body.append(f"            '{f['key']}',")

    body.extend(
        [
            "        ]",
            "        for name in param_names:",
            "            value = local_vars.get(name)",
            "            if value is not None:",
            "                data[name] = value",
            "",
            "        if not data:",
            '            return "Error: At least one field must be provided to update."',
            "",
            f'        response = pipedrive.put(f"/{obj_type}/{{{singular}_id}}", json=data)',
            "",
            f'        return f"Successfully updated {singular} {{{singular}_id}}"',
            "    except Exception as e:",
            f'        return f"Error updating {singular}: {{str(e)}}"',
        ]
    )

    return [
        "@tool",
        f"def {func_name}(",
        params_str,
        ") -> str:",
        *doc_lines,
        *body,
    ]


def _generate_search_tool(obj_type: str, singular: str, fields: list[dict]) -> list[str]:
    """Generate a search tool for an object type."""
    func_name = f"pipedrive_search_{obj_type}"

    # For Pipedrive, search is done via the search endpoint
    # Build function signature
    params = ["    term: str | None = None,"]
    params.append("    limit: int = 10,")

    params_str = "\n".join(params)

    # Build docstring
    doc_lines = [f'    """Search for {obj_type} in Pipedrive.']
    doc_lines.append("")
    doc_lines.append("    Args:")
    doc_lines.append(f"        term: Search term to look for in {obj_type}.")
    doc_lines.append("        limit: Maximum results to return (default 10).")
    doc_lines.append("")
    doc_lines.append("    Returns:")
    doc_lines.append(f"        JSON string with matching {obj_type}.")
    doc_lines.append('    """')

    # The item_type for search varies
    item_type_map = {
        "deals": "deal",
        "persons": "person",
        "organizations": "organization",
        "products": "product",
        "leads": "lead",
    }
    item_type = item_type_map.get(obj_type, singular)

    body = [
        "    pipedrive = _get_pipedrive()",
        "    try:",
        "        if term:",
        "            # Use search endpoint",
        f'            response = pipedrive.get("/itemSearch", params={{"term": term, "item_types": "{item_type}", "limit": limit}})',
        '            items = response.get("data", {}).get("items", [])',
        "            if not items:",
        f"                return f\"No {obj_type} found matching '{{term}}'\"",
        '            records = [item.get("item", {}) for item in items]',
        "        else:",
        "            # Get recent records",
        f'            response = pipedrive.get("/{obj_type}", params={{"limit": limit}})',
        '            records = response.get("data", [])',
        "            if not records:",
        f'                return "No {obj_type} found."',
        "",
        '        results = [{"id": r.get("id"), "title": r.get("title") or r.get("name"), **{k: v for k, v in r.items() if k not in ["id", "title", "name"] and not k.startswith("$")}} for r in records[:limit]]',
        "",
        f'        return f"Found {{len(results)}} {obj_type}:\\n" + json.dumps(results, indent=2)',
        "    except Exception as e:",
        f'        return f"Error searching {obj_type}: {{str(e)}}"',
    ]

    return [
        "@tool",
        f"def {func_name}(",
        params_str,
        ") -> str:",
        *doc_lines,
        *body,
    ]


def _generate_get_tool(obj_type: str, singular: str) -> list[str]:
    """Generate a get-by-ID tool for an object type."""
    func_name = f"pipedrive_get_{singular}"

    doc_lines = [f'    """Get a {singular} by ID from Pipedrive.']
    doc_lines.append("")
    doc_lines.append("    Args:")
    doc_lines.append(f"        {singular}_id: The ID of the {singular} to retrieve.")
    doc_lines.append("")
    doc_lines.append("    Returns:")
    doc_lines.append(f"        JSON string with the {singular} data.")
    doc_lines.append('    """')

    body = [
        "    pipedrive = _get_pipedrive()",
        "    try:",
        f'        response = pipedrive.get(f"/{obj_type}/{{{singular}_id}}")',
        '        record = response.get("data", {})',
        "",
        "        if not record:",
        f'            return f"{singular.title()} with ID {{{singular}_id}} not found"',
        "",
        '        result = {k: v for k, v in record.items() if not k.startswith("$")}',
        "",
        f'        return f"{singular.title()} {{{singular}_id}}:\\n" + json.dumps(result, indent=2)',
        "    except Exception as e:",
        f'        return f"Error getting {singular}: {{str(e)}}"',
    ]

    return [
        "@tool",
        f"def {func_name}({singular}_id: int) -> str:",
        *doc_lines,
        *body,
    ]


def _generate_delete_tool(obj_type: str, singular: str) -> list[str]:
    """Generate a delete tool for an object type."""
    func_name = f"pipedrive_delete_{singular}"

    doc_lines = [f'    """Delete a {singular} from Pipedrive.']
    doc_lines.append("")
    doc_lines.append("    Args:")
    doc_lines.append(f"        {singular}_id: The ID of the {singular} to delete.")
    doc_lines.append("")
    doc_lines.append("    Returns:")
    doc_lines.append("        Success message confirming deletion.")
    doc_lines.append('    """')

    body = [
        "    pipedrive = _get_pipedrive()",
        "    try:",
        f'        pipedrive.delete(f"/{obj_type}/{{{singular}_id}}")',
        f'        return f"Successfully deleted {singular} {{{singular}_id}}"',
        "    except Exception as e:",
        f'        return f"Error deleting {singular}: {{str(e)}}"',
    ]

    return [
        "@tool",
        f"def {func_name}({singular}_id: int) -> str:",
        *doc_lines,
        *body,
    ]
