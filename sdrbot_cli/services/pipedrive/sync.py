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

# Standard Pipedrive fields that can be sent at the top level of API requests
# Custom fields (with hash keys) must be sent in a custom_fields object
STANDARD_FIELDS = {
    "deals": {
        "title",
        "value",
        "currency",
        "user_id",
        "person_id",
        "org_id",
        "pipeline_id",
        "stage_id",
        "status",
        "probability",
        "lost_reason",
        "visible_to",
        "close_time",
        "won_time",
        "lost_time",
        "expected_close_date",
        "label",
        "origin",
        "channel",
        "channel_id",
    },
    "persons": {
        "name",
        "first_name",
        "last_name",
        "owner_id",
        "org_id",
        "email",
        "phone",
        "visible_to",
        "marketing_status",
        "label",
    },
    "organizations": {
        "name",
        "owner_id",
        "visible_to",
        "address",
        "label_ids",
    },
    "products": {
        "name",
        "code",
        "description",
        "unit",
        "tax",
        "active_flag",
        "visible_to",
        "owner_id",
        "prices",
    },
    "activities": {
        "subject",
        "type",
        "due_date",
        "due_time",
        "duration",
        "user_id",
        "deal_id",
        "person_id",
        "org_id",
        "note",
        "location",
        "public_description",
        "done",
        "busy_flag",
        "participants",
        "attendees",
    },
    "leads": {
        "title",
        "owner_id",
        "person_id",
        "organization_id",
        "label_ids",
        "value",
        "expected_close_date",
        "visible_to",
        "channel",
        "channel_id",
    },
}

# Field name mappings for leads - Pipedrive's leadFields endpoint returns different
# field names than what the Leads API actually accepts
LEADS_FIELD_MAPPING = {
    "related_person_id": "person_id",
    "related_org_id": "organization_id",
    "labels": "label_ids",  # API expects label_ids as array of UUIDs
}

# Fields that should be integers (not strings) in the API request
LEADS_INTEGER_FIELDS = {"person_id", "organization_id", "owner_id", "channel"}

# Lead fields that are READ-ONLY or should be excluded from create/update tools
LEADS_READONLY_FIELDS = {
    "org_name",  # Auto-populated from organization_id
    "org_address",  # Auto-populated from organization_id
    "person_name",  # Auto-populated from person_id
    "person_phone",  # Auto-populated from person_id
    "person_email",  # Auto-populated from person_id
    "is_archived",  # Use archive endpoint instead
    "source",  # Read-only
    "channel",  # Requires valid Marketing channel ID configured in account
    "channel_id",  # Related to channel - rarely needed
}


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

    # Map endpoint to object type for standard field lookup
    endpoint_to_obj = {
        "dealFields": "deals",
        "personFields": "persons",
        "organizationFields": "organizations",
        "productFields": "products",
        "activityFields": "activities",
        "leadFields": "leads",
    }
    obj_type = endpoint_to_obj.get(fields_endpoint, "")
    standard_keys = STANDARD_FIELDS.get(obj_type, set())

    # Determine if this is leads (need special handling)
    is_lead = fields_endpoint == "leadFields"

    fields = []
    for f in raw_fields:
        field_key = f.get("key", "")

        # Skip system/internal fields
        if field_key in EXCLUDED_FIELD_KEYS:
            continue

        # Skip fields starting with hash (internal/custom field IDs sometimes)
        if field_key.startswith("#"):
            continue

        # Skip read-only lead fields
        if is_lead and field_key in LEADS_READONLY_FIELDS:
            continue

        # Determine if this is a standard field or custom field
        is_standard = field_key in standard_keys

        # For custom fields, generate a Python-friendly parameter name from the display name
        # Standard fields use their key directly
        if is_standard:
            param_name = field_key
        else:
            # Convert display name to snake_case parameter name
            display_name = f.get("name", field_key)
            param_name = _sanitize_param_name(display_name)
            # If sanitized name conflicts with a standard field, prefix with custom_
            if param_name in standard_keys:
                param_name = f"custom_{param_name}"

        # Get options for enum types
        options = []
        if f.get("options"):
            options = [opt.get("label", opt.get("id", "")) for opt in f["options"] if opt][:20]

        # In Pipedrive, add_visible_flag=True or bulk_edit_allowed=True means writable
        # edit_flag is misleading (often False for writable fields)
        is_writable = f.get("add_visible_flag", False) or f.get("bulk_edit_allowed", False)

        fields.append(
            {
                "key": field_key,  # The actual API key (may be hash for custom fields)
                "param_name": param_name,  # Python parameter name (human-readable)
                "name": f.get("name", field_key),  # Display name for docstring
                "field_type": f.get("field_type", "text"),
                "mandatory_flag": f.get("mandatory_flag", False),
                "is_writable": is_writable,
                "add_visible_flag": f.get("add_visible_flag", False),
                "options": options,
                "is_standard": is_standard,
            }
        )

    return fields


def _sanitize_param_name(name: str) -> str:
    """Convert a display name to a valid Python parameter name.

    Args:
        name: Human-readable field name (e.g., "Employee Count", "Industry Type")

    Returns:
        Snake_case parameter name (e.g., "employee_count", "industry_type")
    """
    import re

    # Convert to lowercase
    result = name.lower()
    # Replace spaces and special chars with underscores
    result = re.sub(r"[^a-z0-9]+", "_", result)
    # Remove leading/trailing underscores
    result = result.strip("_")
    # Ensure it starts with a letter (prefix with 'field_' if needed)
    if result and not result[0].isalpha():
        result = f"field_{result}"
    # Fallback for empty result
    if not result:
        result = "custom_field"
    return result


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
    is_lead = obj_type == "leads"

    # Separate standard and custom fields
    standard_fields = [f for f in fields if f.get("is_standard", True)]
    custom_fields = [f for f in fields if not f.get("is_standard", True)]

    # Build function signature using param_name (human-readable)
    params = []
    for f in fields:
        py_type = _field_to_python_type(f)
        param_name = f.get("param_name", f["key"])
        # For leads, fix types for certain fields
        if is_lead:
            api_key = LEADS_FIELD_MAPPING.get(f["key"], f["key"])
            if api_key in LEADS_INTEGER_FIELDS:
                py_type = "int"
        if f.get("mandatory_flag"):
            params.append(f"    {param_name}: {py_type},")
        else:
            params.append(f"    {param_name}: {py_type} | None = None,")

    params_str = "\n".join(params) if params else "    # No custom fields"

    # Build docstring
    doc_lines = [f'    """Create a new {singular} in Pipedrive.']
    if is_lead:
        # Find the actual param names for person and org links
        person_param = next(
            (
                f.get("param_name", f["key"])
                for f in fields
                if f["key"] in ("related_person_id", "contact_person")
            ),
            "contact_person",
        )
        org_param = next(
            (
                f.get("param_name", f["key"])
                for f in fields
                if f["key"] in ("related_org_id", "organization")
            ),
            "organization",
        )
        doc_lines.append("")
        doc_lines.append("    NOTE: Leads MUST be linked to a person or organization.")
        doc_lines.append(f"    Provide {person_param} OR {org_param} (or both).")
    doc_lines.append("")
    doc_lines.append("    Args:")
    for f in fields:
        param_name = f.get("param_name", f["key"])
        doc_lines.append(f"        {param_name}: {f.get('name', f['key'])}.")
        if f.get("options"):
            # For labels field, explain it needs UUIDs not names
            if is_lead and f["key"] == "labels":
                doc_lines.append(
                    "            Comma-separated label UUIDs. Use pipedrive_get_lead_labels to get IDs."
                )
                doc_lines.append(f"            Label names: {', '.join(f['options'][:5])}")
            else:
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
    ]

    if is_lead:
        # For leads, we need to map field names and ensure correct types
        body.append(
            "        # Lead field mappings (API uses different names than leadFields endpoint)"
        )
        body.append("        field_mapping = {")
        for f in fields:
            param_name = f.get("param_name", f["key"])
            api_key = LEADS_FIELD_MAPPING.get(f["key"], f["key"])
            body.append(f"            '{param_name}': '{api_key}',")
        body.append("        }")
        body.append("        for param_name, api_name in field_mapping.items():")
        body.append("            value = local_vars.get(param_name)")
        body.append("            if value is not None:")
        body.append("                # label_ids must be an array")
        body.append("                if api_name == 'label_ids' and isinstance(value, str):")
        body.append(
            "                    value = [v.strip() for v in value.split(',') if v.strip()]"
        )
        body.append("                data[api_name] = value")
    else:
        # Handle standard fields - go directly in data dict
        if standard_fields:
            body.append("        # Standard fields go at top level")
            body.append("        standard_field_mapping = {")
            for f in standard_fields:
                param_name = f.get("param_name", f["key"])
                body.append(f"            '{param_name}': '{f['key']}',")
            body.append("        }")
            body.append("        for param_name, api_key in standard_field_mapping.items():")
            body.append("            value = local_vars.get(param_name)")
            body.append("            if value is not None:")
            body.append("                data[api_key] = value")

        # Handle custom fields - go in custom_fields object
        if custom_fields:
            body.append("")
            body.append("        # Custom fields go in custom_fields object with hash keys")
            body.append("        custom_fields_data = {}")
            body.append("        custom_field_mapping = {")
            for f in custom_fields:
                param_name = f.get("param_name", f["key"])
                body.append(f"            '{param_name}': '{f['key']}',  # {f.get('name', '')}")
            body.append("        }")
            body.append("        for param_name, api_key in custom_field_mapping.items():")
            body.append("            value = local_vars.get(param_name)")
            body.append("            if value is not None:")
            body.append("                custom_fields_data[api_key] = value")
            body.append("        if custom_fields_data:")
            body.append("            data['custom_fields'] = custom_fields_data")

    body.extend(
        [
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

    # Separate standard and custom fields
    standard_fields = [f for f in fields if f.get("is_standard", True)]
    custom_fields = [f for f in fields if not f.get("is_standard", True)]

    # Build function signature - ID is required, all others optional
    params = [f"    {singular}_id: int,"]
    for f in fields:
        py_type = _field_to_python_type(f)
        param_name = f.get("param_name", f["key"])
        params.append(f"    {param_name}: {py_type} | None = None,")

    params_str = "\n".join(params)

    # Build docstring
    doc_lines = [f'    """Update an existing {singular} in Pipedrive.']
    doc_lines.append("")
    doc_lines.append("    Args:")
    doc_lines.append(f"        {singular}_id: The ID of the {singular} to update.")
    for f in fields:
        param_name = f.get("param_name", f["key"])
        doc_lines.append(f"        {param_name}: {f.get('name', f['key'])}.")
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
    ]

    # Handle standard fields - go directly in data dict
    if standard_fields:
        body.append("        # Standard fields go at top level")
        body.append("        standard_field_mapping = {")
        for f in standard_fields:
            param_name = f.get("param_name", f["key"])
            body.append(f"            '{param_name}': '{f['key']}',")
        body.append("        }")
        body.append("        for param_name, api_key in standard_field_mapping.items():")
        body.append("            value = local_vars.get(param_name)")
        body.append("            if value is not None:")
        body.append("                data[api_key] = value")

    # Handle custom fields - go in custom_fields object
    if custom_fields:
        body.append("")
        body.append("        # Custom fields go in custom_fields object with hash keys")
        body.append("        custom_fields_data = {}")
        body.append("        custom_field_mapping = {")
        for f in custom_fields:
            param_name = f.get("param_name", f["key"])
            body.append(f"            '{param_name}': '{f['key']}',  # {f.get('name', '')}")
        body.append("        }")
        body.append("        for param_name, api_key in custom_field_mapping.items():")
        body.append("            value = local_vars.get(param_name)")
        body.append("            if value is not None:")
        body.append("                custom_fields_data[api_key] = value")
        body.append("        if custom_fields_data:")
        body.append("            data['custom_fields'] = custom_fields_data")

    body.extend(
        [
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
