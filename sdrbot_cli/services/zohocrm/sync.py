"""Zoho CRM schema sync and tool generation.

This module:
1. Fetches the Zoho CRM schema (modules and their fields)
2. Generates strongly-typed Python tools for each module
3. Writes the generated code to ./generated/zohocrm_tools.py
"""

from typing import Any

from sdrbot_cli.auth.zohocrm import get_zoho_client
from sdrbot_cli.config import settings
from sdrbot_cli.services.registry import compute_schema_hash

# Standard Zoho CRM modules that are commonly used
STANDARD_MODULES = [
    "Leads",
    "Contacts",
    "Accounts",
    "Deals",
    "Tasks",
    "Events",
    "Calls",
    "Cases",
    "Products",
    "Quotes",
    "Sales_Orders",
    "Purchase_Orders",
    "Invoices",
    "Campaigns",
    "Vendors",
]

# Fields to exclude from generated tools (system/internal fields)
EXCLUDED_FIELDS = [
    "id",
    "Created_Time",
    "Modified_Time",
    "Created_By",
    "Modified_By",
    "Tag",
    "$approval_state",
    "$approved",
    "$editable",
    "$review_process",
    "$orchestration",
    "$in_merge",
    "$approval",
    "$zia_owner_assignment",
    "$zia_visions",
    "$pathfinder",
    "$review",
]

# Maximum fields per tool to keep signatures manageable
MAX_FIELDS_PER_TOOL = 25


def sync_schema() -> dict[str, Any]:
    """Fetch Zoho CRM schema and generate tools.

    Returns:
        Dict with keys:
        - schema_hash: Hash of the schema for change detection
        - objects: List of module names that were synced
    """
    client = get_zoho_client()
    if not client:
        raise RuntimeError("Failed to authenticate with Zoho CRM")

    # 1. Discover all modules (standard + custom)
    all_modules = _discover_modules(client)

    # 2. Fetch fields for each module
    modules_schema = {}
    for module in all_modules:
        try:
            fields = _fetch_module_fields(client, module["api_name"])
            if fields:  # Only include modules we can access
                modules_schema[module["api_name"]] = {
                    "singular_label": module.get("singular_label", module["api_name"]),
                    "plural_label": module.get("plural_label", module["api_name"]),
                    "fields": fields,
                }
        except Exception:
            # Skip modules we can't access (permissions, etc.)
            continue

    if not modules_schema:
        raise RuntimeError("Could not access any Zoho CRM modules. Check your API permissions.")

    # 3. Generate the tools code
    generated_code = _generate_tools_code(modules_schema)

    # 4. Write to ./generated/zohocrm_tools.py
    output_path = settings.ensure_generated_dir() / "zohocrm_tools.py"
    output_path.write_text(generated_code, encoding="utf-8")

    # 5. Return metadata
    return {
        "schema_hash": compute_schema_hash(modules_schema),
        "objects": list(modules_schema.keys()),
    }


def _discover_modules(client) -> list[dict]:
    """Discover all available Zoho CRM modules.

    Args:
        client: Zoho CRM client instance.

    Returns:
        List of module dicts with api_name, singular_label, plural_label.
    """
    modules = []

    try:
        response = client.get("/settings/modules")
        all_modules = response.get("modules", [])

        for module in all_modules:
            # Skip modules that aren't API-supported or accessible
            if not module.get("api_supported", False):
                continue

            # Include if creatable, editable, or viewable
            if not (module.get("creatable") or module.get("editable") or module.get("viewable")):
                continue

            # Include standard modules and custom modules
            api_name = module.get("api_name", "")
            is_standard = api_name in STANDARD_MODULES
            is_custom = module.get("generated_type") == "custom"

            if is_standard or is_custom:
                modules.append(
                    {
                        "api_name": api_name,
                        "singular_label": module.get("singular_label", api_name),
                        "plural_label": module.get("plural_label", api_name),
                        "creatable": module.get("creatable", False),
                        "editable": module.get("editable", False),
                    }
                )

    except Exception:
        # If modules API fails, use standard modules only
        for api_name in STANDARD_MODULES:
            modules.append(
                {
                    "api_name": api_name,
                    "singular_label": api_name.rstrip("s"),
                    "plural_label": api_name,
                    "creatable": True,
                    "editable": True,
                }
            )

    return modules


def _fetch_module_fields(client, module_name: str) -> list[dict[str, Any]]:
    """Fetch fields for a specific module.

    Args:
        client: Zoho CRM client instance.
        module_name: The module API name (e.g., "Leads").

    Returns:
        List of field dictionaries with api_name, label, data_type, etc.
    """
    response = client.get(f"/settings/fields?module={module_name}")

    fields = []
    for f in response.get("fields", []):
        api_name = f.get("api_name", "")

        # Skip excluded fields
        if api_name in EXCLUDED_FIELDS or api_name.startswith("$"):
            continue

        # Skip read-only system fields
        if f.get("read_only") and not f.get("custom_field"):
            continue

        # Get picklist values
        pick_list_values = []
        if f.get("pick_list_values"):
            pick_list_values = [
                p.get("display_value", p.get("actual_value", ""))
                for p in f["pick_list_values"]
                if p.get("display_value") or p.get("actual_value")
            ][:20]  # Limit to keep code manageable

        fields.append(
            {
                "api_name": api_name,
                "field_label": f.get("field_label", api_name),
                "data_type": f.get("data_type", "text"),
                "system_mandatory": f.get("system_mandatory", False),
                "custom_field": f.get("custom_field", False),
                "read_only": f.get("read_only", False),
                "pick_list_values": pick_list_values,
                "length": f.get("length"),
            }
        )

    return fields


def _generate_tools_code(schema: dict[str, dict]) -> str:
    """Generate Python tool code from schema.

    Args:
        schema: Dict mapping module names to their metadata and fields.

    Returns:
        Python source code as a string.
    """
    lines = [
        '"""Zoho CRM generated tools - AUTO-GENERATED by sync. Do not edit manually.',
        "",
        "This file is regenerated when you run: /services sync zohocrm",
        "To customize, edit tools.py instead (static tools).",
        '"""',
        "",
        "import json",
        "from typing import Optional",
        "",
        "from langchain_core.tools import tool",
        "",
        "from sdrbot_cli.auth.zohocrm import get_zoho_client",
        "",
        "",
        "# Shared client instance",
        "_zoho_client = None",
        "",
        "",
        "def _get_zoho():",
        '    """Get or create Zoho CRM client instance."""',
        "    global _zoho_client",
        "    if _zoho_client is None:",
        "        _zoho_client = get_zoho_client()",
        "    if _zoho_client is None:",
        '        raise RuntimeError("Zoho CRM authentication failed. Check ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, and ZOHO_REGION in .env")',
        "    return _zoho_client",
        "",
        "",
    ]

    for module_name, module_data in schema.items():
        fields = module_data.get("fields", [])
        singular = module_data.get("singular_label", module_name)
        plural = module_data.get("plural_label", module_name)

        # Filter to writable fields for create/update
        writable_fields = [f for f in fields if not f.get("read_only")]

        # Prioritize important fields
        writable_fields = _prioritize_fields(writable_fields, module_name)

        # Limit fields per tool
        create_fields = writable_fields[:MAX_FIELDS_PER_TOOL]
        search_fields = [
            f for f in fields if f["data_type"] in ("text", "email", "phone", "picklist")
        ][:15]

        # Generate create tool
        lines.extend(_generate_create_tool(module_name, singular, create_fields))
        lines.append("")

        # Generate update tool
        lines.extend(_generate_update_tool(module_name, singular, create_fields))
        lines.append("")

        # Generate search tool
        lines.extend(_generate_search_tool(module_name, plural, search_fields))
        lines.append("")

        # Generate get tool
        lines.extend(_generate_get_tool(module_name, singular))
        lines.append("")

        # Generate delete tool
        lines.extend(_generate_delete_tool(module_name, singular))
        lines.append("")

    return "\n".join(lines)


def _prioritize_fields(fields: list[dict], module_name: str) -> list[dict]:
    """Sort fields by importance for the given module.

    Args:
        fields: List of field dicts.
        module_name: Module API name.

    Returns:
        Sorted list with most important fields first.
    """
    # Priority fields by module
    priority_map = {
        "Leads": [
            "Email",
            "First_Name",
            "Last_Name",
            "Company",
            "Phone",
            "Lead_Status",
            "Lead_Source",
        ],
        "Contacts": ["Email", "First_Name", "Last_Name", "Account_Name", "Phone", "Mailing_City"],
        "Accounts": [
            "Account_Name",
            "Website",
            "Phone",
            "Industry",
            "Billing_City",
            "Account_Type",
        ],
        "Deals": ["Deal_Name", "Amount", "Stage", "Closing_Date", "Account_Name", "Contact_Name"],
        "Tasks": ["Subject", "Due_Date", "Status", "Priority", "What_Id", "Who_Id"],
        "Events": ["Event_Title", "Start_DateTime", "End_DateTime", "What_Id", "Who_Id"],
        "Calls": ["Subject", "Call_Type", "Call_Start_Time", "Call_Duration", "What_Id", "Who_Id"],
        "Cases": ["Subject", "Status", "Priority", "Case_Origin", "Account_Name", "Contact_Name"],
    }

    priority_names = priority_map.get(module_name, [])

    def sort_key(f):
        name = f["api_name"]
        if name in priority_names:
            return (0, priority_names.index(name))
        if f.get("system_mandatory"):
            return (1, name)
        return (2, name)

    return sorted(fields, key=sort_key)


def _python_type(zoho_type: str) -> str:
    """Map Zoho data types to Python types.

    Args:
        zoho_type: Zoho field data_type.

    Returns:
        Python type annotation string.
    """
    type_mapping = {
        "text": "str",
        "textarea": "str",
        "email": "str",
        "phone": "str",
        "website": "str",
        "picklist": "str",
        "multiselectpicklist": "str",
        "lookup": "str",
        "ownerlookup": "str",
        "boolean": "bool",
        "integer": "int",
        "bigint": "int",
        "double": "float",
        "currency": "float",
        "percent": "float",
        "date": "str",
        "datetime": "str",
        "autonumber": "str",
    }
    return type_mapping.get(zoho_type, "str")


def _safe_func_name(module_name: str) -> str:
    """Convert module name to a safe function name part.

    Args:
        module_name: Module API name (e.g., "Sales_Orders").

    Returns:
        Safe lowercase name (e.g., "sales_order").
    """
    # Convert to lowercase and handle underscores
    name = module_name.lower()
    # Remove trailing 's' for singular form
    if name.endswith("s") and not name.endswith("ss"):
        name = name[:-1]
    return name


def _generate_create_tool(module_name: str, singular: str, fields: list[dict]) -> list[str]:
    """Generate a create tool for a module.

    Args:
        module_name: Module API name.
        singular: Singular label for the module.
        fields: List of field dicts.

    Returns:
        List of code lines.
    """
    func_name_part = _safe_func_name(module_name)
    func_name = f"zohocrm_create_{func_name_part}"

    # Build parameter list
    params = []
    for f in fields:
        param_type = _python_type(f["data_type"])
        default = " = None"
        params.append(f"    {f['api_name']}: Optional[{param_type}]{default},")

    params_str = "\n".join(params) if params else "    # No writable fields"

    # Build docstring
    doc_lines = [f'    """Create a new {singular} in Zoho CRM.']
    doc_lines.append("")
    doc_lines.append("    Args:")
    for f in fields[:15]:  # Limit docstring length
        desc = f.get("field_label", f["api_name"])
        if f.get("pick_list_values"):
            desc += f" (options: {', '.join(f['pick_list_values'][:5])})"
        doc_lines.append(f"        {f['api_name']}: {desc}")
    if len(fields) > 15:
        doc_lines.append(f"        ... and {len(fields) - 15} more parameters")
    doc_lines.append("")
    doc_lines.append("    Returns:")
    doc_lines.append(f"        Success message with the new {singular} ID.")
    doc_lines.append('    """')

    # Build function body
    body = [
        "    zoho = _get_zoho()",
        "    try:",
        "        # Build data dict from non-None arguments",
        "        data = {}",
        "        local_vars = locals()",
        "        param_names = [",
    ]

    # Add parameter names
    for f in fields:
        body.append(f"            '{f['api_name']}',")

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
            f'        response = zoho.post("/{module_name}", json={{"data": [data]}})',
            '        result = response.get("data", [{}])[0]',
            '        record_id = result.get("details", {}).get("id", "unknown")',
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


def _generate_update_tool(module_name: str, singular: str, fields: list[dict]) -> list[str]:
    """Generate an update tool for a module.

    Args:
        module_name: Module API name.
        singular: Singular label for the module.
        fields: List of field dicts.

    Returns:
        List of code lines.
    """
    func_name_part = _safe_func_name(module_name)
    func_name = f"zohocrm_update_{func_name_part}"

    # Build parameter list (id is required, others optional)
    params = [f"    {func_name_part}_id: str,"]
    for f in fields:
        param_type = _python_type(f["data_type"])
        params.append(f"    {f['api_name']}: Optional[{param_type}] = None,")

    params_str = "\n".join(params)

    # Build docstring
    doc_lines = [f'    """Update an existing {singular} in Zoho CRM.']
    doc_lines.append("")
    doc_lines.append("    Args:")
    doc_lines.append(f"        {func_name_part}_id: The Zoho CRM ID of the {singular} to update.")
    for f in fields[:10]:
        desc = f.get("field_label", f["api_name"])
        doc_lines.append(f"        {f['api_name']}: {desc}")
    if len(fields) > 10:
        doc_lines.append(f"        ... and {len(fields) - 10} more parameters")
    doc_lines.append("")
    doc_lines.append("    Returns:")
    doc_lines.append("        Success message confirming the update.")
    doc_lines.append('    """')

    # Build function body
    body = [
        "    zoho = _get_zoho()",
        "    try:",
        "        # Build data dict from non-None arguments",
        "        data = {}",
        "        local_vars = locals()",
        "        param_names = [",
    ]

    for f in fields:
        body.append(f"            '{f['api_name']}',")

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
            f'        response = zoho.put(f"/{module_name}/{{{func_name_part}_id}}", json={{"data": [data]}})',
            "",
            f'        return f"Successfully updated {singular} {{{func_name_part}_id}}"',
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


def _generate_search_tool(module_name: str, plural: str, fields: list[dict]) -> list[str]:
    """Generate a search tool for a module.

    Args:
        module_name: Module API name.
        plural: Plural label for the module.
        fields: List of searchable field dicts.

    Returns:
        List of code lines.
    """
    func_name = f"zohocrm_search_{module_name.lower()}"

    # Build parameter list
    params = ["    criteria: Optional[str] = None,"]
    for f in fields[:10]:  # Limit search parameters
        param_type = _python_type(f["data_type"])
        params.append(f"    {f['api_name']}: Optional[{param_type}] = None,")
    params.append("    limit: int = 10,")

    params_str = "\n".join(params)

    # Field names for search
    field_names = [f["api_name"] for f in fields[:10]]

    # Build docstring
    doc_lines = [f'    """Search for {plural} in Zoho CRM.']
    doc_lines.append("")
    doc_lines.append("    You can search by COQL criteria string OR by specific field values.")
    doc_lines.append("")
    doc_lines.append("    Args:")
    doc_lines.append(
        '        criteria: COQL criteria string (e.g., "(Email:equals:test@example.com)").'
    )
    for f in fields[:10]:
        doc_lines.append(
            f"        {f['api_name']}: Filter by {f.get('field_label', f['api_name'])}."
        )
    doc_lines.append("        limit: Maximum results to return (default 10).")
    doc_lines.append("")
    doc_lines.append("    Returns:")
    doc_lines.append(f"        JSON string with matching {plural}.")
    doc_lines.append('    """')

    body = [
        "    zoho = _get_zoho()",
        "    try:",
        "        if criteria:",
        "            # Use provided COQL criteria",
        "            search_criteria = criteria",
        "        else:",
        "            # Build criteria from provided parameters",
        "            conditions = []",
        "            local_vars = locals()",
        f"            filter_params = {field_names}",
        "            for name in filter_params:",
        "                value = local_vars.get(name)",
        "                if value is not None:",
        '                    conditions.append(f"({name}:equals:{value})")',
        "",
        "            if conditions:",
        '                search_criteria = " and ".join(conditions)',
        "            else:",
        "                # No criteria - get recent records",
        f'                response = zoho.get(f"/{module_name}?per_page={{limit}}")',
        '                records = response.get("data", [])',
        "                if not records:",
        f'                    return "No {plural} found."',
        '                results = [{"id": r.get("id"), **{k: v for k, v in r.items() if not k.startswith("$")}} for r in records[:limit]]',
        f'                return f"Found {{len(results)}} {plural}:\\n" + json.dumps(results, indent=2)',
        "",
        "        # Search with criteria",
        f'        response = zoho.get(f"/{module_name}/search?criteria={{search_criteria}}&per_page={{limit}}")',
        '        records = response.get("data", [])',
        "",
        "        if not records:",
        f'            return "No {plural} found matching criteria."',
        "",
        '        results = [{"id": r.get("id"), **{k: v for k, v in r.items() if not k.startswith("$")}} for r in records]',
        f'        return f"Found {{len(results)}} {plural}:\\n" + json.dumps(results, indent=2)',
        "    except Exception as e:",
        f'        return f"Error searching {plural}: {{str(e)}}"',
    ]

    return [
        "@tool",
        f"def {func_name}(",
        params_str,
        ") -> str:",
        *doc_lines,
        *body,
    ]


def _generate_get_tool(module_name: str, singular: str) -> list[str]:
    """Generate a get-by-id tool for a module.

    Args:
        module_name: Module API name.
        singular: Singular label for the module.

    Returns:
        List of code lines.
    """
    func_name_part = _safe_func_name(module_name)
    func_name = f"zohocrm_get_{func_name_part}"

    return [
        "@tool",
        f"def {func_name}({func_name_part}_id: str) -> str:",
        f'    """Get a {singular} by ID from Zoho CRM.',
        "",
        "    Args:",
        f"        {func_name_part}_id: The Zoho CRM ID of the {singular}.",
        "",
        "    Returns:",
        f"        JSON string with the {singular} details.",
        '    """',
        "    zoho = _get_zoho()",
        "    try:",
        f'        response = zoho.get(f"/{module_name}/{{{func_name_part}_id}}")',
        '        record = response.get("data", [{}])[0]',
        "        # Filter out internal fields",
        '        filtered = {k: v for k, v in record.items() if not k.startswith("$")}',
        f'        return f"{singular} {{{func_name_part}_id}}:\\n" + json.dumps(filtered, indent=2)',
        "    except Exception as e:",
        f'        return f"Error getting {singular}: {{str(e)}}"',
    ]


def _generate_delete_tool(module_name: str, singular: str) -> list[str]:
    """Generate a delete tool for a module.

    Args:
        module_name: Module API name.
        singular: Singular label for the module.

    Returns:
        List of code lines.
    """
    func_name_part = _safe_func_name(module_name)
    func_name = f"zohocrm_delete_{func_name_part}"

    return [
        "@tool",
        f"def {func_name}({func_name_part}_id: str) -> str:",
        f'    """Delete a {singular} from Zoho CRM.',
        "",
        "    Args:",
        f"        {func_name_part}_id: The Zoho CRM ID of the {singular} to delete.",
        "",
        "    Returns:",
        "        Success message confirming deletion.",
        '    """',
        "    zoho = _get_zoho()",
        "    try:",
        f'        zoho.delete(f"/{module_name}/{{{func_name_part}_id}}")',
        f'        return f"Successfully deleted {singular} {{{func_name_part}_id}}"',
        "    except Exception as e:",
        f'        return f"Error deleting {singular}: {{str(e)}}"',
    ]
