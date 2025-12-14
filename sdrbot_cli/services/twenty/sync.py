"""Twenty schema sync and tool generation.

This module:
1. Fetches the Twenty OpenAPI spec for accurate schema info
2. Generates strongly-typed Python tools for each object type
3. Writes the generated code to ./generated/twenty_tools.py
"""

import re
from typing import Any

import requests

from sdrbot_cli.auth.twenty import TwentyClient
from sdrbot_cli.config import settings
from sdrbot_cli.services.registry import compute_schema_hash

# Maximum fields per tool to keep signatures manageable
MAX_FIELDS_PER_TOOL = 25

# System objects to skip (internal Twenty objects)
SYSTEM_OBJECTS = {
    "activity",
    "activityTarget",
    "apiKey",
    "attachment",
    "auditLog",
    "blocklist",
    "calendarChannel",
    "calendarChannelEventAssociation",
    "calendarEvent",
    "calendarEventParticipant",
    "connectedAccount",
    "favorite",
    "message",
    "messageChannel",
    "messageChannelMessageAssociation",
    "messageParticipant",
    "messageThread",
    "view",
    "viewField",
    "viewFilter",
    "viewSort",
    "webhook",
    "workspaceMember",
}

# Objects with static tools in tools.py - skip generating to avoid duplicates
STATIC_TOOL_OBJECTS = {
    "note",  # twenty_create_note, twenty_list_notes exist in tools.py
}


def sync_schema() -> dict[str, Any]:
    """Fetch Twenty schema and generate tools.

    Returns:
        Dict with keys:
        - schema_hash: Hash of the schema for change detection
        - objects: List of object names that were synced

    Raises:
        RuntimeError: If authentication fails or no objects can be accessed.
    """
    try:
        client = TwentyClient()
    except ValueError as e:
        raise RuntimeError(f"Twenty authentication failed: {e}") from e

    # Fetch and parse the OpenAPI spec
    openapi_spec = _fetch_openapi_spec(client)
    objects_schema = _parse_openapi_spec(openapi_spec)

    if not objects_schema:
        raise RuntimeError("Could not access any Twenty objects. Check your API key.")

    # Generate the tools code
    generated_code = _generate_tools_code(objects_schema)

    # Write to ./generated/twenty_tools.py
    output_path = settings.ensure_generated_dir() / "twenty_tools.py"
    output_path.write_text(generated_code, encoding="utf-8")

    return {
        "schema_hash": compute_schema_hash(objects_schema),
        "objects": list(objects_schema.keys()),
    }


def _fetch_openapi_spec(client: TwentyClient) -> dict:
    """Fetch the Core OpenAPI spec from Twenty.

    Args:
        client: Twenty client instance.

    Returns:
        Parsed OpenAPI spec as a dictionary.

    Raises:
        RuntimeError: If the spec cannot be fetched.
    """
    # Build the OpenAPI URL - base_url may or may not have /rest
    base = client.base_url.rstrip("/")
    if base.endswith("/rest"):
        base = base[:-5]

    url = f"{base}/rest/open-api/core?token={client.api_key}"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise RuntimeError(f"Failed to fetch Twenty OpenAPI spec: {e}") from e


def _parse_openapi_spec(spec: dict) -> dict[str, dict[str, Any]]:
    """Parse OpenAPI spec to extract objects and fields.

    Args:
        spec: Parsed OpenAPI spec.

    Returns:
        Dict mapping object names to their schema info (name_singular, name_plural, fields).
    """
    result = {}
    schemas = spec.get("components", {}).get("schemas", {})
    paths = spec.get("paths", {})

    # Find objects from paths - look for /{plural} patterns
    # OpenAPI spec paths may or may not have /rest prefix
    object_endpoints = {}
    for path in paths.keys():
        # Match /people, /companies, etc. or /rest/people (not /{plural}/{id})
        match = re.match(r"^(?:/rest)?/([a-zA-Z]+)$", path)
        if match:
            plural = match.group(1)
            object_endpoints[plural] = path

    for plural, _path in object_endpoints.items():
        # Skip system/internal objects
        if plural in SYSTEM_OBJECTS:
            continue
        if plural in STATIC_TOOL_OBJECTS:
            continue

        # Find the schema name - typically capitalized singular
        # e.g., "people" -> "Person", "companies" -> "Company"
        schema_name = _plural_to_schema_name(plural)

        if schema_name not in schemas:
            continue

        schema = schemas[schema_name]

        # Get singular name from schema or derive it
        singular = _to_singular(plural)

        # Skip if in our exclusion lists
        if singular in SYSTEM_OBJECTS or singular in STATIC_TOOL_OBJECTS:
            continue

        # Extract fields from schema properties
        fields = _extract_fields_from_schema(schema)

        if fields:
            result[singular] = {
                "name_singular": singular,
                "name_plural": plural,
                "fields": fields,
            }

    return result


def _plural_to_schema_name(plural: str) -> str:
    """Convert plural endpoint name to schema name.

    Args:
        plural: Plural name like 'people', 'companies'.

    Returns:
        Schema name like 'Person', 'Company'.
    """
    # Common irregular plurals
    irregulars = {
        "people": "Person",
        "companies": "Company",
        "opportunities": "Opportunity",
        "activities": "Activity",
    }

    if plural in irregulars:
        return irregulars[plural]

    # Regular plurals - remove 's' and capitalize
    singular = plural.rstrip("s")
    return singular.capitalize()


def _to_singular(plural: str) -> str:
    """Convert plural to singular form.

    Args:
        plural: Plural name.

    Returns:
        Singular form.
    """
    irregulars = {
        "people": "person",
        "companies": "company",
        "opportunities": "opportunity",
        "activities": "activity",
    }

    if plural in irregulars:
        return irregulars[plural]

    return plural.rstrip("s")


def _extract_fields_from_schema(schema: dict) -> list[dict[str, Any]]:
    """Extract fields from an OpenAPI schema, flattening nested objects.

    Args:
        schema: OpenAPI schema object.

    Returns:
        List of field dictionaries with flattened nested fields.
    """
    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))

    result = []
    for name, prop in properties.items():
        # Skip system/internal fields
        if name in EXCLUDED_FIELDS:
            continue

        # Handle nested objects by flattening them
        if prop.get("type") == "object" and "properties" in prop:
            nested_props = prop.get("properties", {})
            for nested_name, nested_prop in nested_props.items():
                # Skip array sub-fields (like additionalEmails, additionalPhones)
                if nested_prop.get("type") == "array":
                    continue
                # Skip internal nested fields
                if nested_name in ("secondaryLinks", "source", "workspaceMemberId", "context"):
                    continue

                nested_type = _openapi_to_field_type(nested_prop)
                if nested_type in EXCLUDED_FIELD_TYPES:
                    continue

                # Use unique param name: parent_field for ambiguous names
                # e.g., linkedinLink.primaryLinkUrl -> linkedinPrimaryLinkUrl
                # But for common ones like name.firstName, just use firstName
                if name in ("name", "emails", "phones"):
                    param_name = nested_name
                else:
                    # Prefix with parent to avoid collisions (linkedinLink vs xLink)
                    param_name = f"{name.replace('Link', '')}_{nested_name}"

                result.append(
                    {
                        "name": param_name,
                        "api_field": nested_name,  # Actual API field name
                        "label": _to_label(nested_name),
                        "type": nested_type,
                        "required": False,
                        "options": [],
                        "parent_field": name,  # Track parent for API calls
                    }
                )
            continue

        # Get the type for non-nested fields
        field_type = _openapi_to_field_type(prop)

        # Skip complex/excluded types
        if field_type in EXCLUDED_FIELD_TYPES or field_type in COMPLEX_FIELD_TYPES:
            continue

        result.append(
            {
                "name": name,
                "label": _to_label(name),
                "type": field_type,
                "required": name in required_fields,
                "options": [],
            }
        )

    return result


def _openapi_to_field_type(prop: dict) -> str:
    """Map OpenAPI property to our field type.

    Args:
        prop: OpenAPI property definition.

    Returns:
        Our internal field type string.
    """
    # Check for $ref first
    if "$ref" in prop:
        ref = prop["$ref"]
        # Extract schema name from #/components/schemas/SchemeName
        if "FullName" in ref:
            return "FULL_NAME"
        if "Address" in ref:
            return "ADDRESS"
        if "Currency" in ref:
            return "CURRENCY"
        if "Links" in ref:
            return "LINKS"
        if "Emails" in ref:
            return "EMAILS"
        if "Phones" in ref:
            return "PHONES"
        # Default to TEXT for unknown refs
        return "TEXT"

    prop_type = prop.get("type", "string")
    prop_format = prop.get("format", "")

    if prop_type == "string":
        if prop_format == "date-time":
            return "DATE_TIME"
        if prop_format == "date":
            return "DATE"
        if prop_format == "email":
            return "EMAIL"
        if prop_format == "uuid":
            return "UUID"
        if "enum" in prop:
            return "SELECT"
        return "TEXT"
    elif prop_type == "number" or prop_type == "integer":
        return "NUMBER"
    elif prop_type == "boolean":
        return "BOOLEAN"
    elif prop_type == "array":
        return "MULTI_SELECT"  # Simplified
    elif prop_type == "object":
        return "RAW_JSON"

    return "TEXT"


def _to_label(name: str) -> str:
    """Convert camelCase field name to human-readable label.

    Args:
        name: Field name like 'jobTitle'.

    Returns:
        Label like 'Job Title'.
    """
    # Insert space before capitals
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    # Capitalize first letter
    return spaced.capitalize()


# Fields to exclude (system fields present in response schemas)
EXCLUDED_FIELDS = {
    "id",
    "createdAt",
    "updatedAt",
    "deletedAt",
    "createdBy",
    "updatedBy",
    "position",
}


# Field types that are system/internal and should be excluded
EXCLUDED_FIELD_TYPES = {
    "DATE_TIME",  # System timestamps (createdAt, updatedAt, deletedAt)
    "ACTOR",  # System actor fields (createdBy)
    "RELATION",  # Handled via associations, not direct fields
    # Note: UUID is NOT excluded - companyId, etc. are foreign keys we want to expose
}

# Complex field types that need special handling (exclude for now)
COMPLEX_FIELD_TYPES = {
    "EMAILS",  # Array of email objects
    "PHONES",  # Array of phone objects
    "LINKS",  # Array of link objects
    "CURRENCY",  # Currency with amount and code
    "ADDRESS",  # Address object
}


def _generate_tools_code(schema: dict[str, dict]) -> str:
    """Generate Python tool code from schema.

    Args:
        schema: Dict mapping object names to their info and fields.

    Returns:
        Python source code as a string.
    """
    lines = [
        '"""Twenty generated tools - AUTO-GENERATED by sync. Do not edit manually.',
        "",
        "This file is regenerated when you run: /services sync twenty",
        "To customize, edit tools.py instead (static tools like notes).",
        '"""',
        "",
        "import json",
        "from typing import Optional",
        "",
        "from langchain_core.tools import tool",
        "",
        "from sdrbot_cli.auth.twenty import TwentyClient",
        "",
        "",
        "# Shared client instance",
        "_twenty_client = None",
        "",
        "",
        "def _get_twenty():",
        '    """Get or create Twenty client instance."""',
        "    global _twenty_client",
        "    if _twenty_client is None:",
        "        _twenty_client = TwentyClient()",
        "    return _twenty_client",
        "",
        "",
    ]

    for obj_name, obj_info in schema.items():
        singular = obj_info["name_singular"]
        plural = obj_info["name_plural"]
        fields = obj_info["fields"]

        # Prioritize fields and limit count
        fields = _prioritize_fields(fields, obj_name)[:MAX_FIELDS_PER_TOOL]

        # Generate create tool
        lines.extend(_generate_create_tool(singular, plural, fields))
        lines.append("")

        # Generate update tool
        lines.extend(_generate_update_tool(singular, plural, fields))
        lines.append("")

        # Generate list tool
        lines.extend(_generate_search_tool(singular, plural, fields))
        lines.append("")

        # Generate get tool
        lines.extend(_generate_get_tool(singular, plural))
        lines.append("")

        # Generate delete tool
        lines.extend(_generate_delete_tool(singular, plural))
        lines.append("")

    return "\n".join(lines)


def _prioritize_fields(fields: list[dict], obj_name: str) -> list[dict]:
    """Sort fields by importance.

    Args:
        fields: List of field dicts.
        obj_name: Object name.

    Returns:
        Sorted list with most important fields first.
    """
    # Priority fields by object type (only simple types that aren't filtered)
    priority_map = {
        "person": ["name", "jobTitle", "city"],
        "company": ["name", "domainName", "employees", "idealCustomerProfile"],
        "opportunity": ["name", "amount", "stage", "closeDate", "probability"],
        "task": ["title", "body", "status", "dueAt"],
        "workflow": ["name", "statuses"],
        "dashboard": ["name"],
    }

    priority_names = priority_map.get(obj_name, [])

    def sort_key(f):
        name = f["name"]
        if name in priority_names:
            return (0, priority_names.index(name))
        if f.get("required"):
            return (1, name)
        return (2, name)

    return sorted(fields, key=sort_key)


def _python_type(twenty_type: str) -> str:
    """Map Twenty field types to Python types.

    Args:
        twenty_type: Twenty field type.

    Returns:
        Python type annotation string.
    """
    type_mapping = {
        "TEXT": "str",
        "NUMBER": "float",
        "BOOLEAN": "bool",
        "DATE": "str",
        "DATE_TIME": "str",
        "EMAIL": "str",
        "PHONE": "str",
        "LINK": "str",
        "CURRENCY": "float",
        "SELECT": "str",
        "MULTI_SELECT": "str",
        "RELATION": "str",
        "UUID": "str",
        "RATING": "int",
        "POSITION": "int",
        "RAW_JSON": "str",
        "RICH_TEXT": "str",
        "ADDRESS": "str",
        "FULL_NAME": "str",
        "LINKS": "str",
        "EMAILS": "str",
        "PHONES": "str",
    }
    return type_mapping.get(twenty_type, "str")


def _safe_param_name(name: str) -> str:
    """Convert field name to safe Python parameter name."""
    # Replace problematic characters
    safe_name = name.replace("-", "_").replace(" ", "_")
    # Handle Python reserved words
    if safe_name in ("id", "type", "class", "from", "import", "return", "def", "if", "else"):
        safe_name = f"{safe_name}_"
    return safe_name


def _generate_create_tool(singular: str, plural: str, fields: list[dict]) -> list[str]:
    """Generate a create tool for an object.

    Args:
        singular: Object singular name.
        plural: Object plural name.
        fields: List of fields.

    Returns:
        List of code lines.
    """
    func_name = f"twenty_create_{singular.lower()}"

    # Build parameter list
    params = []
    for f in fields:
        param_type = _python_type(f["type"])
        param_name = _safe_param_name(f["name"])
        params.append(f"    {param_name}: Optional[{param_type}] = None,")

    params_str = "\n".join(params) if params else "    # No writable fields"

    # Build docstring
    doc_lines = [f'    """Create a new {singular} in Twenty.']
    doc_lines.append("")
    doc_lines.append("    Args:")
    for f in fields[:15]:
        desc = f.get("label", f["name"])
        if f.get("options"):
            desc += f" (options: {', '.join(f['options'][:5])})"
        param_name = _safe_param_name(f["name"])
        doc_lines.append(f"        {param_name}: {desc}")
    if len(fields) > 15:
        doc_lines.append(f"        ... and {len(fields) - 15} more parameters")
    doc_lines.append("")
    doc_lines.append("    Returns:")
    doc_lines.append(f"        Success message with the new {singular} ID.")
    doc_lines.append('    """')

    # Group fields by parent for nested object reconstruction
    nested_fields = {}
    flat_fields = []
    for f in fields:
        if f.get("parent_field"):
            parent = f["parent_field"]
            if parent not in nested_fields:
                nested_fields[parent] = []
            nested_fields[parent].append(f)
        else:
            flat_fields.append(f)

    # Build function body
    body = [
        "    client = _get_twenty()",
        "    try:",
        "        data = {}",
        "        local_vars = locals()",
        "",
    ]

    # Handle flat fields
    if flat_fields:
        body.append("        # Flat fields")
        for f in flat_fields:
            param_name = _safe_param_name(f["name"])
            body.append(f"        if local_vars.get('{param_name}') is not None:")
            body.append(f"            data['{f['name']}'] = local_vars['{param_name}']")
        body.append("")

    # Handle nested fields - reconstruct nested objects
    for parent, children in nested_fields.items():
        body.append(f"        # Nested object: {parent}")
        body.append(f"        {parent}_data = {{}}")
        for f in children:
            param_name = _safe_param_name(f["name"])
            api_field = f.get("api_field", f["name"])  # Use api_field if available
            body.append(f"        if local_vars.get('{param_name}') is not None:")
            body.append(f"            {parent}_data['{api_field}'] = local_vars['{param_name}']")
        body.append(f"        if {parent}_data:")
        body.append(f"            data['{parent}'] = {parent}_data")
        body.append("")

    body.extend(
        [
            "        if not data:",
            f'            return "Error: At least one field must be provided to create a {singular}."',
            "",
            f'        response = client.post("/{plural}", json=data)',
            '        record = response.get("data", {})',
            f'        record_id = record.get("{singular}", {{}}).get("id")',
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


def _generate_update_tool(singular: str, plural: str, fields: list[dict]) -> list[str]:
    """Generate an update tool for an object.

    Args:
        singular: Object singular name.
        plural: Object plural name.
        fields: List of fields.

    Returns:
        List of code lines.
    """
    func_name = f"twenty_update_{singular.lower()}"

    # Build parameter list
    params = [f"    {singular}_id: str,"]
    for f in fields:
        param_type = _python_type(f["type"])
        param_name = _safe_param_name(f["name"])
        params.append(f"    {param_name}: Optional[{param_type}] = None,")

    params_str = "\n".join(params)

    # Build docstring
    doc_lines = [f'    """Update an existing {singular} in Twenty.']
    doc_lines.append("")
    doc_lines.append("    Args:")
    doc_lines.append(f"        {singular}_id: The Twenty record ID of the {singular}.")
    for f in fields[:10]:
        param_name = _safe_param_name(f["name"])
        doc_lines.append(f"        {param_name}: {f.get('label', f['name'])}")
    if len(fields) > 10:
        doc_lines.append(f"        ... and {len(fields) - 10} more parameters")
    doc_lines.append("")
    doc_lines.append("    Returns:")
    doc_lines.append("        Success message confirming the update.")
    doc_lines.append('    """')

    # Group fields by parent for nested object reconstruction
    nested_fields = {}
    flat_fields = []
    for f in fields:
        if f.get("parent_field"):
            parent = f["parent_field"]
            if parent not in nested_fields:
                nested_fields[parent] = []
            nested_fields[parent].append(f)
        else:
            flat_fields.append(f)

    # Build function body
    body = [
        "    client = _get_twenty()",
        "    try:",
        "        data = {}",
        "        local_vars = locals()",
        "",
    ]

    # Handle flat fields
    if flat_fields:
        body.append("        # Flat fields")
        for f in flat_fields:
            param_name = _safe_param_name(f["name"])
            body.append(f"        if local_vars.get('{param_name}') is not None:")
            body.append(f"            data['{f['name']}'] = local_vars['{param_name}']")
        body.append("")

    # Handle nested fields
    for parent, children in nested_fields.items():
        body.append(f"        # Nested object: {parent}")
        body.append(f"        {parent}_data = {{}}")
        for f in children:
            param_name = _safe_param_name(f["name"])
            api_field = f.get("api_field", f["name"])  # Use api_field if available
            body.append(f"        if local_vars.get('{param_name}') is not None:")
            body.append(f"            {parent}_data['{api_field}'] = local_vars['{param_name}']")
        body.append(f"        if {parent}_data:")
        body.append(f"            data['{parent}'] = {parent}_data")
        body.append("")

    body.extend(
        [
            "        if not data:",
            '            return "Error: At least one field must be provided to update."',
            "",
            f'        client.patch(f"/{plural}/{{{singular}_id}}", json=data)',
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


def _generate_search_tool(singular: str, plural: str, fields: list[dict]) -> list[str]:
    """Generate a search tool for an object.

    Args:
        singular: Object singular name.
        plural: Object plural name.
        fields: List of searchable fields.

    Returns:
        List of code lines.
    """
    func_name = f"twenty_search_{plural.lower()}"

    # Limit to text/email/number searchable fields
    searchable = [f for f in fields if f["type"] in ("TEXT", "EMAIL", "NUMBER", "SELECT")][:10]

    # Build parameter list - actual API fields only, no fake "query" param
    params = []
    for f in searchable:
        param_type = _python_type(f["type"])
        param_name = _safe_param_name(f["name"])
        params.append(f"    {param_name}: Optional[{param_type}] = None,")
    params.append("    limit: int = 10,")

    params_str = "\n".join(params)

    # Build docstring
    doc_lines = [f'    """Search for {plural} in Twenty.']
    doc_lines.append("")
    doc_lines.append("    Args:")
    for f in searchable:
        param_name = _safe_param_name(f["name"])
        doc_lines.append(f"        {param_name}: Filter by {f.get('label', f['name'])}.")
    doc_lines.append("        limit: Maximum results to return (default 10).")
    doc_lines.append("")
    doc_lines.append("    Returns:")
    doc_lines.append(f"        JSON string with matching {plural}.")
    doc_lines.append('    """')

    # Build function body
    # Twenty filter format: field[operator]:"value" or or(filter1,filter2)
    # For nested fields, use dot notation: name.firstName[ilike]:"%value%"
    body = [
        "    client = _get_twenty()",
        "    try:",
        '        params = {"limit": limit}',
        "",
        "        # Build filter from field parameters",
        "        # Twenty uses query-string filter format: field[op]:value",
        "        filters = []",
        "        local_vars = locals()",
        "",
    ]

    # Generate filter code for each field
    for f in searchable:
        param_name = _safe_param_name(f["name"])
        # For nested fields, use dot notation in the filter
        if f.get("parent_field"):
            field_name = f.get("api_field", f["name"])  # Use api_field if available
            api_field = f"{f['parent_field']}.{field_name}"
        else:
            api_field = f["name"]

        body.append(f"        if local_vars.get('{param_name}') is not None:")
        body.append(f"            val = local_vars['{param_name}']")
        if f["type"] in ("TEXT", "EMAIL"):
            body.append(f"            filters.append(f'{api_field}[ilike]:\"%{{val}}%\"')")
        else:
            body.append(f"            filters.append(f'{api_field}[eq]:{{val}}')")
        body.append("")

    body.extend(
        [
            "        if filters:",
            "            if len(filters) == 1:",
            '                params["filter"] = filters[0]',
            "            else:",
            '                params["filter"] = f\'and({",".join(filters)})\'',
            "",
            f'        response = client.get("/{plural}", params=params)',
            f'        records = response.get("data", {{}}).get("{plural}", [])',
            "",
            "        if not records:",
            f'            return "No {plural} found matching the criteria."',
            "",
            "        # Format results",
            "        results = []",
            "        for r in records:",
            '            record_data = {"id": r.get("id")}',
            "            for key, value in r.items():",
            '                if key != "id" and value is not None:',
            "                    record_data[key] = value",
            "            results.append(record_data)",
            "",
            f'        return f"Found {{len(records)}} {plural}:\\n" + json.dumps(results, indent=2)',
            "    except Exception as e:",
            f'        return f"Error searching {plural}: {{str(e)}}"',
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


def _generate_get_tool(singular: str, plural: str) -> list[str]:
    """Generate a get-by-id tool for an object.

    Args:
        singular: Object singular name.
        plural: Object plural name.

    Returns:
        List of code lines.
    """
    func_name = f"twenty_get_{singular.lower()}"

    return [
        "@tool",
        f"def {func_name}({singular}_id: str) -> str:",
        f'    """Get a {singular} by ID from Twenty.',
        "",
        "    Args:",
        f"        {singular}_id: The Twenty record ID of the {singular}.",
        "",
        "    Returns:",
        f"        JSON string with the {singular} details.",
        '    """',
        "    client = _get_twenty()",
        "    try:",
        f'        response = client.get(f"/{plural}/{{{singular}_id}}")',
        f'        record = response.get("data", {{}}).get("{singular}", {{}})',
        "",
        "        if not record:",
        f'            return f"{singular.title()} not found: {{{singular}_id}}"',
        "",
        f'        return f"{singular.title()} {{{singular}_id}}:\\n" + json.dumps(record, indent=2)',
        "    except Exception as e:",
        f'        return f"Error getting {singular}: {{str(e)}}"',
    ]


def _generate_delete_tool(singular: str, plural: str) -> list[str]:
    """Generate a delete tool for an object.

    Args:
        singular: Object singular name.
        plural: Object plural name.

    Returns:
        List of code lines.
    """
    func_name = f"twenty_delete_{singular.lower()}"

    return [
        "@tool",
        f"def {func_name}({singular}_id: str) -> str:",
        f'    """Delete a {singular} from Twenty.',
        "",
        "    Args:",
        f"        {singular}_id: The Twenty record ID of the {singular} to delete.",
        "",
        "    Returns:",
        "        Success message confirming deletion.",
        '    """',
        "    client = _get_twenty()",
        "    try:",
        f'        client.delete(f"/{plural}/{{{singular}_id}}")',
        f'        return f"Successfully deleted {singular} {{{singular}_id}}"',
        "    except Exception as e:",
        f'        return f"Error deleting {singular}: {{str(e)}}"',
    ]
