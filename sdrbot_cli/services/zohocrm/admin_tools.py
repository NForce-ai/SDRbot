"""Zoho CRM Admin Tools - Schema and field management operations.

These tools provide CRM configuration capabilities:
- Modules: List/get/create/update custom modules
- Fields: List/get/create/update/delete custom fields

These are privileged tools - they require Privileged Mode to be enabled
via /setup > Privileged Mode. When disabled, these tools are not available.
"""

import json
from datetime import datetime
from pathlib import Path

from langchain_core.tools import BaseTool

from sdrbot_cli.auth.zohocrm import get_zoho_client
from sdrbot_cli.tools import SCOPE_PRIVILEGED, scoped_tool

# Shared client instance for admin operations
_admin_client = None

# Error log file
_ERROR_LOG = Path("files/zohocrm_admin_errors.log")


def _log_error(tool_name: str, params: dict, error: str) -> None:
    """Log admin tool errors to file for debugging."""
    try:
        _ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_ERROR_LOG, "a") as f:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"Time: {datetime.now().isoformat()}\n")
            f.write(f"Tool: {tool_name}\n")
            f.write(f"Params: {json.dumps(params, indent=2)}\n")
            f.write(f"Error: {error}\n")
    except Exception:
        pass  # Don't fail if logging fails


def _get_admin_client():
    """Get or create Zoho CRM client for admin operations."""
    global _admin_client
    if _admin_client is None:
        _admin_client = get_zoho_client()
    if _admin_client is None:
        raise RuntimeError(
            "Zoho CRM authentication failed. Check ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, and ZOHO_REGION in .env"
        )
    return _admin_client


def reset_admin_client() -> None:
    """Reset the cached admin client."""
    global _admin_client
    _admin_client = None


# =============================================================================
# MODULES - Schema management
# =============================================================================


@scoped_tool(scope=SCOPE_PRIVILEGED)
def zohocrm_admin_list_modules() -> str:
    """List all modules (objects) in Zoho CRM.

    Use this to discover what module types exist in the CRM before
    creating fields or migrating data.

    Returns:
        JSON list of modules with their metadata.
    """
    zoho = _get_admin_client()
    try:
        response = zoho.get("/settings/modules")
        modules = response.get("modules", [])

        if not modules:
            return "No modules found."

        results = []
        for m in modules:
            # Only include API-accessible modules
            if not m.get("api_supported", False):
                continue

            results.append(
                {
                    "api_name": m.get("api_name"),
                    "singular_label": m.get("singular_label"),
                    "plural_label": m.get("plural_label"),
                    "module_name": m.get("module_name"),
                    "id": m.get("id"),
                    "generated_type": m.get("generated_type"),  # "default" or "custom"
                    "creatable": m.get("creatable", False),
                    "editable": m.get("editable", False),
                    "viewable": m.get("viewable", False),
                    "deletable": m.get("deletable", False),
                }
            )

        return f"Found {len(results)} API-accessible modules:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing modules: {str(e)}"


@scoped_tool(scope=SCOPE_PRIVILEGED)
def zohocrm_admin_get_module(module_api_name: str) -> str:
    """Get detailed information about a specific module.

    Args:
        module_api_name: The module API name (e.g., "Leads", "Contacts", "Accounts").

    Returns:
        JSON with module details including available fields count.
    """
    zoho = _get_admin_client()
    try:
        # Get module info
        response = zoho.get("/settings/modules")
        modules = response.get("modules", [])

        target_module = None
        for m in modules:
            if m.get("api_name") == module_api_name:
                target_module = m
                break

        if not target_module:
            return f"Module '{module_api_name}' not found."

        # Get field count
        fields_response = zoho.get(f"/settings/fields?module={module_api_name}")
        fields = fields_response.get("fields", [])

        result = {
            "api_name": target_module.get("api_name"),
            "singular_label": target_module.get("singular_label"),
            "plural_label": target_module.get("plural_label"),
            "module_name": target_module.get("module_name"),
            "id": target_module.get("id"),
            "generated_type": target_module.get("generated_type"),
            "api_supported": target_module.get("api_supported"),
            "creatable": target_module.get("creatable"),
            "editable": target_module.get("editable"),
            "viewable": target_module.get("viewable"),
            "deletable": target_module.get("deletable"),
            "convertable": target_module.get("convertable"),
            "presence_sub_menu": target_module.get("presence_sub_menu"),
            "web_link": target_module.get("web_link"),
            "field_count": len(fields),
            "custom_field_count": len([f for f in fields if f.get("custom_field")]),
        }

        return f"Module '{module_api_name}':\n" + json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting module: {str(e)}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="zohocrm")
def zohocrm_admin_create_module(
    singular_label: str,
    plural_label: str,
    profile_ids: str,
    api_name: str | None = None,
    display_field_label: str = "Name",
    display_field_type: str = "text",
) -> str:
    """Create a new custom module in Zoho CRM.

    Note: Requires Enterprise edition or higher. Module deletion is only
    available through the Zoho CRM UI, not via API.

    Args:
        singular_label: Singular name for the module (e.g., "Project").
                       Max 25 characters, letters/numbers/spaces only.
        plural_label: Plural name for the module (e.g., "Projects").
                     Max 25 characters, letters/numbers/spaces only.
        profile_ids: JSON array of profile IDs that can access this module.
                    Use zohocrm_admin_list_profiles to get available profiles.
                    Example: '["12345678901234"]'
        api_name: Optional custom API name. If omitted, auto-generated from label.
                 Max 50 characters.
        display_field_label: Label for the primary display field (default "Name").
        display_field_type: Type of display field: "text" or "autonumber" (default "text").

    Returns:
        Success message with the new module ID.
    """
    zoho = _get_admin_client()
    try:
        # Parse profile IDs
        try:
            profiles = json.loads(profile_ids)
            if not isinstance(profiles, list) or not profiles:
                return "Error: profile_ids must be a JSON array with at least one profile ID"
            profile_list = [{"id": pid} for pid in profiles]
        except json.JSONDecodeError:
            return "Error: profile_ids must be a valid JSON array (e.g., '[\"123456789\"]')"

        module_data = {
            "singular_label": singular_label,
            "plural_label": plural_label,
            "profiles": profile_list,
            "display_field": {
                "field_label": display_field_label,
                "data_type": display_field_type,
            },
        }

        if api_name:
            module_data["api_name"] = api_name

        response = zoho.post("/settings/modules", json={"modules": [module_data]})

        modules_result = response.get("modules", [{}])[0]
        if modules_result.get("status") == "success":
            module_id = modules_result.get("details", {}).get("id")
            return (
                f"Successfully created module '{singular_label}' (ID: {module_id}). "
                "Note: Use sync to generate CRUD tools for this module."
            )
        else:
            error_msg = modules_result.get("message", "Unknown error")
            code = modules_result.get("code", "UNKNOWN")
            return f"Failed to create module: [{code}] {error_msg}"

    except Exception as e:
        error_str = str(e)
        _log_error(
            "zohocrm_admin_create_module",
            {
                "singular_label": singular_label,
                "plural_label": plural_label,
            },
            error_str,
        )
        return f"Error creating module: {error_str}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="zohocrm")
def zohocrm_admin_update_module(
    module_id_or_api_name: str,
    singular_label: str | None = None,
    plural_label: str | None = None,
    profile_ids: str | None = None,
) -> str:
    """Update a custom module's configuration.

    Note: Only custom modules can be updated. Standard Zoho modules cannot be modified.
    The module's API name can only be changed through the UI.

    Args:
        module_id_or_api_name: The module ID or API name (e.g., "12345" or "Custom_Module").
        singular_label: New singular name (max 25 characters).
        plural_label: New plural name (max 25 characters).
        profile_ids: JSON array of profile IDs that can access this module.
                    Example: '["12345678901234", "56789012345678"]'

    Returns:
        Success message confirming the update.
    """
    zoho = _get_admin_client()
    try:
        update_data = {}

        if singular_label is not None:
            update_data["singular_label"] = singular_label

        if plural_label is not None:
            update_data["plural_label"] = plural_label

        if profile_ids is not None:
            try:
                profiles = json.loads(profile_ids)
                if not isinstance(profiles, list) or not profiles:
                    return "Error: profile_ids must be a JSON array with at least one profile ID"
                update_data["profiles"] = [{"id": pid} for pid in profiles]
            except json.JSONDecodeError:
                return "Error: profile_ids must be a valid JSON array"

        if not update_data:
            return "Error: At least one field must be provided to update."

        response = zoho.put(
            f"/settings/modules/{module_id_or_api_name}",
            json={"modules": [update_data]},
        )

        modules_result = response.get("modules", [{}])[0]
        if modules_result.get("status") == "success":
            return f"Successfully updated module '{module_id_or_api_name}'"
        else:
            error_msg = modules_result.get("message", "Unknown error")
            code = modules_result.get("code", "UNKNOWN")
            return f"Failed to update module: [{code}] {error_msg}"

    except Exception as e:
        error_str = str(e)
        _log_error(
            "zohocrm_admin_update_module",
            {"module_id_or_api_name": module_id_or_api_name},
            error_str,
        )
        return f"Error updating module: {error_str}"


# =============================================================================
# FIELDS - Field management
# =============================================================================


@scoped_tool(scope=SCOPE_PRIVILEGED)
def zohocrm_admin_list_fields(module_api_name: str, include_system: bool = False) -> str:
    """List all fields for a module.

    Args:
        module_api_name: The module API name (e.g., "Leads", "Contacts").
        include_system: Whether to include system fields (default False).

    Returns:
        JSON list of fields with their metadata.
    """
    zoho = _get_admin_client()
    try:
        response = zoho.get(f"/settings/fields?module={module_api_name}")
        fields = response.get("fields", [])

        if not fields:
            return f"No fields found for module {module_api_name}."

        results = []
        for f in fields:
            # Skip system fields unless requested
            if not include_system:
                api_name = f.get("api_name", "")
                if (
                    api_name.startswith("$")
                    or f.get("system_mandatory")
                    and not f.get("custom_field")
                ):
                    # Keep system mandatory fields but skip internal $ fields
                    if api_name.startswith("$"):
                        continue

            field_info = {
                "api_name": f.get("api_name"),
                "field_label": f.get("field_label"),
                "data_type": f.get("data_type"),
                "id": f.get("id"),
                "custom_field": f.get("custom_field", False),
                "system_mandatory": f.get("system_mandatory", False),
                "read_only": f.get("read_only", False),
                "visible": f.get("visible", True),
                "length": f.get("length"),
            }

            # Include picklist values if present
            if f.get("pick_list_values"):
                field_info["pick_list_values"] = [
                    p.get("display_value") for p in f["pick_list_values"][:10]
                ]
                if len(f["pick_list_values"]) > 10:
                    field_info["pick_list_count"] = len(f["pick_list_values"])

            results.append(field_info)

        return f"Found {len(results)} fields for {module_api_name}:\n" + json.dumps(
            results, indent=2
        )
    except Exception as e:
        return f"Error listing fields: {str(e)}"


@scoped_tool(scope=SCOPE_PRIVILEGED)
def zohocrm_admin_get_field(module_api_name: str, field_api_name: str) -> str:
    """Get detailed information about a specific field.

    Args:
        module_api_name: The module API name (e.g., "Leads").
        field_api_name: The field API name (e.g., "Email", "Custom_Field").

    Returns:
        JSON with field details.
    """
    zoho = _get_admin_client()
    try:
        response = zoho.get(f"/settings/fields?module={module_api_name}")
        fields = response.get("fields", [])

        target_field = None
        for f in fields:
            if f.get("api_name") == field_api_name:
                target_field = f
                break

        if not target_field:
            return f"Field '{field_api_name}' not found in module '{module_api_name}'."

        # Build detailed result
        result = {
            "api_name": target_field.get("api_name"),
            "field_label": target_field.get("field_label"),
            "data_type": target_field.get("data_type"),
            "id": target_field.get("id"),
            "custom_field": target_field.get("custom_field", False),
            "system_mandatory": target_field.get("system_mandatory", False),
            "read_only": target_field.get("read_only", False),
            "visible": target_field.get("visible", True),
            "length": target_field.get("length"),
            "decimal_place": target_field.get("decimal_place"),
            "tooltip": target_field.get("tooltip"),
            "created_source": target_field.get("created_source"),
            "unique": target_field.get("unique"),
        }

        # Include full picklist values
        if target_field.get("pick_list_values"):
            result["pick_list_values"] = [
                {
                    "display_value": p.get("display_value"),
                    "actual_value": p.get("actual_value"),
                    "id": p.get("id"),
                }
                for p in target_field["pick_list_values"]
            ]

        # Include lookup info if present
        if target_field.get("lookup"):
            result["lookup"] = target_field["lookup"]

        # Include formula info if present
        if target_field.get("formula"):
            result["formula"] = target_field["formula"]

        return f"Field '{field_api_name}' in {module_api_name}:\n" + json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting field: {str(e)}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="zohocrm")
def zohocrm_admin_create_field(
    module_api_name: str,
    field_label: str,
    data_type: str,
    length: int | None = None,
    pick_list_values: str | None = None,
    tooltip: str | None = None,
) -> str:
    """Create a custom field in a Zoho CRM module.

    Args:
        module_api_name: The module API name (e.g., "Leads", "Contacts").
        field_label: Display label for the field (must be unique in the module).
        data_type: Field type. Options:
                   - text: Single-line text
                   - textarea: Multi-line text
                   - email: Email address
                   - phone: Phone number
                   - integer: Whole numbers
                   - double: Decimal numbers
                   - currency: Money values
                   - percent: Percentage
                   - date: Date only
                   - datetime: Date and time
                   - boolean: Checkbox (true/false)
                   - picklist: Single-select dropdown
                   - multiselectpicklist: Multi-select dropdown
                   - website: URL
        length: Maximum length (required for text, optional for others).
                Text: 1-255, Email: 1-100, Phone: 1-30, Integer: 1-9
        pick_list_values: For picklist/multiselectpicklist: JSON array of options.
                          Example: '["Hot", "Warm", "Cold"]'
        tooltip: Optional help text shown on hover.

    Returns:
        Success message with the new field ID.
    """
    zoho = _get_admin_client()
    try:
        field_data = {
            "field_label": field_label,
            "data_type": data_type,
        }

        # Add length for applicable types
        if length is not None:
            field_data["length"] = length
        elif data_type == "text" and length is None:
            field_data["length"] = 255  # Default for text

        # Add tooltip if provided
        if tooltip:
            field_data["tooltip"] = {"name": "static_text", "value": tooltip}

        # Parse picklist values
        if pick_list_values:
            try:
                values = json.loads(pick_list_values)
                field_data["pick_list_values"] = [
                    {"display_value": v, "actual_value": v} for v in values
                ]
            except json.JSONDecodeError:
                return 'Error: pick_list_values must be a valid JSON array (e.g., \'["Option1", "Option2"]\')'

        response = zoho.post(
            f"/settings/fields?module={module_api_name}",
            json={"fields": [field_data]},
        )

        # Check response
        fields_result = response.get("fields", [{}])[0]
        if fields_result.get("status") == "success":
            field_id = fields_result.get("details", {}).get("id")
            return (
                f"Successfully created field '{field_label}' (ID: {field_id}) in {module_api_name}"
            )
        else:
            error_msg = fields_result.get("message", "Unknown error")
            code = fields_result.get("code", "UNKNOWN")
            return f"Failed to create field: [{code}] {error_msg}"

    except Exception as e:
        error_str = str(e)
        _log_error(
            "zohocrm_admin_create_field",
            {
                "module_api_name": module_api_name,
                "field_label": field_label,
                "data_type": data_type,
                "length": length,
            },
            error_str,
        )
        return f"Error creating field: {error_str}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="zohocrm")
def zohocrm_admin_update_field(
    module_api_name: str,
    field_id: str,
    field_label: str | None = None,
    length: int | None = None,
    pick_list_values: str | None = None,
    tooltip: str | None = None,
) -> str:
    """Update a custom field's properties.

    Note: Only custom fields can be updated. System fields cannot be modified.
    The field's data_type cannot be changed.

    Args:
        module_api_name: The module API name (e.g., "Leads").
        field_id: The field ID (use zohocrm_admin_get_field to find it).
        field_label: New display label for the field.
        length: New maximum length (for applicable types).
        pick_list_values: For picklist fields: JSON array of ALL options
                          (replaces existing). Example: '["Hot", "Warm", "Cold"]'
        tooltip: New help text (or empty string to remove).

    Returns:
        Success message confirming the update.
    """
    zoho = _get_admin_client()
    try:
        update_data = {"id": field_id}

        if field_label is not None:
            update_data["field_label"] = field_label

        if length is not None:
            update_data["length"] = length

        if tooltip is not None:
            if tooltip:
                update_data["tooltip"] = {"name": "static_text", "value": tooltip}
            else:
                update_data["tooltip"] = None

        if pick_list_values is not None:
            try:
                values = json.loads(pick_list_values)
                update_data["pick_list_values"] = [
                    {"display_value": v, "actual_value": v} for v in values
                ]
            except json.JSONDecodeError:
                return "Error: pick_list_values must be a valid JSON array"

        if len(update_data) == 1:  # Only has 'id'
            return "Error: At least one field property must be provided to update."

        response = zoho.request(
            "PATCH",
            f"/settings/fields?module={module_api_name}",
            json={"fields": [update_data]},
        )

        fields_result = response.get("fields", [{}])[0]
        if fields_result.get("status") == "success":
            return f"Successfully updated field {field_id} in {module_api_name}"
        else:
            error_msg = fields_result.get("message", "Unknown error")
            code = fields_result.get("code", "UNKNOWN")
            return f"Failed to update field: [{code}] {error_msg}"

    except Exception as e:
        error_str = str(e)
        _log_error(
            "zohocrm_admin_update_field",
            {
                "module_api_name": module_api_name,
                "field_id": field_id,
            },
            error_str,
        )
        return f"Error updating field: {error_str}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="zohocrm")
def zohocrm_admin_delete_field(module_api_name: str, field_id: str) -> str:
    """Delete a custom field from a module.

    WARNING: This will delete the field and all its data permanently!

    Note: Only custom fields can be deleted. System fields cannot be removed.
    Fields used in workflows, scoring rules, approval processes, etc. cannot
    be deleted until those dependencies are removed.

    Args:
        module_api_name: The module API name (e.g., "Leads").
        field_id: The field ID to delete (use zohocrm_admin_get_field to find it).

    Returns:
        Success message confirming deletion.
    """
    zoho = _get_admin_client()
    try:
        response = zoho.delete(f"/settings/fields/{field_id}?module={module_api_name}")

        fields_result = response.get("fields", [{}])[0]
        if fields_result.get("status") == "success":
            return f"Successfully deleted field {field_id} from {module_api_name}"
        else:
            error_msg = fields_result.get("message", "Unknown error")
            code = fields_result.get("code", "UNKNOWN")
            if "cannot be deleted" in error_msg.lower() or "dependency" in error_msg.lower():
                return (
                    f"Error: Cannot delete field {field_id}. "
                    "The field may be used in workflows, scoring rules, or other automation. "
                    "Remove those dependencies first."
                )
            return f"Failed to delete field: [{code}] {error_msg}"

    except Exception as e:
        error_str = str(e)
        if "system" in error_str.lower() or "standard" in error_str.lower():
            return (
                f"Error: Cannot delete field {field_id}. "
                "Only custom fields can be deleted, not system/standard fields."
            )
        _log_error(
            "zohocrm_admin_delete_field",
            {
                "module_api_name": module_api_name,
                "field_id": field_id,
            },
            error_str,
        )
        return f"Error deleting field: {error_str}"


# =============================================================================
# USERS - User management (admin version with more details)
# =============================================================================


@scoped_tool(scope=SCOPE_PRIVILEGED)
def zohocrm_admin_list_users(type_filter: str = "AllUsers", include_inactive: bool = False) -> str:
    """List users in the Zoho CRM organization with detailed info.

    Args:
        type_filter: Filter by user type. Options:
                     - AllUsers: All users (default)
                     - ActiveUsers: Only active users
                     - DeactiveUsers: Only deactivated users
                     - AdminUsers: Only admin users
                     - ActiveConfirmedUsers: Active and confirmed
        include_inactive: Whether to include inactive users (default False).

    Returns:
        JSON list of users with their details.
    """
    zoho = _get_admin_client()
    try:
        response = zoho.get(f"/users?type={type_filter}")
        users = response.get("users", [])

        if not users:
            return f"No users found with filter '{type_filter}'."

        results = []
        for user in users:
            # Skip inactive unless requested
            if not include_inactive and user.get("status") != "active":
                continue

            results.append(
                {
                    "id": user.get("id"),
                    "name": user.get("full_name"),
                    "email": user.get("email"),
                    "role": user.get("role", {}).get("name"),
                    "profile": user.get("profile", {}).get("name"),
                    "status": user.get("status"),
                    "confirm": user.get("confirm"),
                    "created_time": user.get("created_time"),
                    "modified_time": user.get("Modified_Time"),
                    "timezone": user.get("time_zone"),
                    "country_locale": user.get("country_locale"),
                }
            )

        return f"Found {len(results)} users:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing users: {str(e)}"


# =============================================================================
# PROFILES - Profile management (needed for module creation)
# =============================================================================


@scoped_tool(scope=SCOPE_PRIVILEGED)
def zohocrm_admin_list_profiles() -> str:
    """List all profiles in Zoho CRM.

    Profiles control user permissions and module access. You need profile IDs
    when creating custom modules to specify which profiles can access them.

    Returns:
        JSON list of profiles with their IDs and names.
    """
    zoho = _get_admin_client()
    try:
        response = zoho.get("/settings/profiles")
        profiles = response.get("profiles", [])

        if not profiles:
            return "No profiles found."

        results = []
        for p in profiles:
            results.append(
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "description": p.get("description"),
                    "default": p.get("default", False),
                    "created_time": p.get("created_time"),
                    "modified_time": p.get("modified_time"),
                }
            )

        return f"Found {len(results)} profiles:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing profiles: {str(e)}"


# =============================================================================
# TOOL EXPORT
# =============================================================================


def get_admin_tools() -> list[BaseTool]:
    """Get all Zoho CRM admin tools.

    Returns:
        List of admin tools for schema and field operations.
    """
    return [
        # Modules
        zohocrm_admin_list_modules,
        zohocrm_admin_get_module,
        zohocrm_admin_create_module,
        zohocrm_admin_update_module,
        # Fields
        zohocrm_admin_list_fields,
        zohocrm_admin_get_field,
        zohocrm_admin_create_field,
        zohocrm_admin_update_field,
        zohocrm_admin_delete_field,
        # Users & Profiles
        zohocrm_admin_list_users,
        zohocrm_admin_list_profiles,
    ]
