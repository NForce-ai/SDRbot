"""Pipedrive Admin Tools - Schema discovery and custom field management.

These tools provide CRM configuration capabilities:
- List all objects (deals, persons, organizations, products, activities, leads)
- List/create/update/delete fields on any object type

These are privileged tools - they require Privileged Mode to be enabled
via /setup > Privileged Mode. When disabled, these tools are not available.
"""

import json

from langchain_core.tools import BaseTool

from sdrbot_cli.auth.pipedrive import PipedriveClient, get_pipedrive_client
from sdrbot_cli.tools import privileged_tool

# Shared client instance for admin operations
_admin_client: PipedriveClient | None = None


def _get_admin_client() -> PipedriveClient:
    """Get or create Pipedrive client for admin operations."""
    global _admin_client
    if _admin_client is None:
        _admin_client = get_pipedrive_client()
        if _admin_client is None:
            raise RuntimeError("Failed to get Pipedrive client - check credentials")
    return _admin_client


def reset_admin_client() -> None:
    """Reset the cached admin client."""
    global _admin_client
    _admin_client = None


# Pipedrive object types and their field endpoints
PIPEDRIVE_OBJECTS = {
    "deals": {"fields_endpoint": "dealFields", "singular": "deal"},
    "persons": {"fields_endpoint": "personFields", "singular": "person"},
    "organizations": {"fields_endpoint": "organizationFields", "singular": "organization"},
    "products": {"fields_endpoint": "productFields", "singular": "product"},
    "activities": {"fields_endpoint": "activityFields", "singular": "activity"},
    "leads": {"fields_endpoint": "leadFields", "singular": "lead"},
}

# Field type reference for docstrings
FIELD_TYPES = """
Field types available in Pipedrive:
- varchar: Single-line text (max 255 chars)
- varchar_auto: Autocomplete text field
- text: Multi-line text
- double: Decimal number
- monetary: Currency amount
- date: Date (YYYY-MM-DD)
- daterange: Date range
- time: Time (HH:MM:SS)
- timerange: Time range
- enum: Single-select dropdown (requires options)
- set: Multi-select (requires options)
- phone: Phone number
- org: Link to organization
- people: Link to person
- user: Link to Pipedrive user
- address: Address with components
"""


# =============================================================================
# GENERIC OBJECT/FIELD TOOLS (like Twenty)
# =============================================================================


@privileged_tool
def pipedrive_admin_list_objects() -> str:
    """List all object types in Pipedrive.

    Returns:
        JSON list of objects with their names and field endpoints.
    """
    results = []
    for obj_name, obj_info in PIPEDRIVE_OBJECTS.items():
        results.append(
            {
                "name": obj_name,
                "singular": obj_info["singular"],
                "fields_endpoint": obj_info["fields_endpoint"],
            }
        )
    return f"Found {len(results)} object types:\n" + json.dumps(results, indent=2)


@privileged_tool
def pipedrive_admin_list_fields(object_type: str) -> str:
    """List all fields for an object type in Pipedrive.

    Args:
        object_type: Object type name (deals, persons, organizations, products, activities, leads)

    Returns:
        JSON list of fields with their metadata.
    """
    if object_type not in PIPEDRIVE_OBJECTS:
        return f"Error: Unknown object type '{object_type}'. Valid types: {', '.join(PIPEDRIVE_OBJECTS.keys())}"

    client = _get_admin_client()
    endpoint = PIPEDRIVE_OBJECTS[object_type]["fields_endpoint"]

    try:
        response = client.get(f"/{endpoint}")
        fields = response.get("data", [])
        if not fields:
            return f"No fields found for {object_type}."

        results = []
        for field in fields:
            results.append(
                {
                    "id": field.get("id"),
                    "key": field.get("key"),
                    "name": field.get("name"),
                    "field_type": field.get("field_type"),
                    "edit_flag": field.get("edit_flag", False),
                    "mandatory_flag": field.get("mandatory_flag", False),
                    "options": field.get("options")
                    if field.get("field_type") in ("enum", "set")
                    else None,
                }
            )

        return f"Found {len(results)} {object_type} fields:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing {object_type} fields: {str(e)}"


@privileged_tool
def pipedrive_admin_get_field(object_type: str, field_id: int) -> str:
    """Get details of a specific field.

    Args:
        object_type: Object type name (deals, persons, organizations, products, activities, leads)
        field_id: The field's numeric ID.

    Returns:
        JSON with field details.
    """
    if object_type not in PIPEDRIVE_OBJECTS:
        return f"Error: Unknown object type '{object_type}'. Valid types: {', '.join(PIPEDRIVE_OBJECTS.keys())}"

    client = _get_admin_client()
    endpoint = PIPEDRIVE_OBJECTS[object_type]["fields_endpoint"]

    try:
        response = client.get(f"/{endpoint}/{field_id}")
        field = response.get("data", {})
        return f"{object_type} field {field_id}:\n" + json.dumps(field, indent=2)
    except Exception as e:
        return f"Error getting field: {str(e)}"


@privileged_tool
def pipedrive_admin_create_field(
    object_type: str,
    name: str,
    field_type: str,
    options: str | None = None,
) -> str:
    """Create a custom field on an object type.

    Args:
        object_type: Object type name (deals, persons, organizations, products)
        name: Display name for the field.
        field_type: One of: varchar, varchar_auto, text, double, monetary,
                    date, daterange, time, timerange, enum, set, phone,
                    org, people, user, address.
        options: For enum/set fields: JSON array of option labels,
                 e.g., '["Hot", "Warm", "Cold"]'

    Returns:
        Success message with the new field ID and key.
    """
    # Activities and leads don't support custom fields
    if object_type not in PIPEDRIVE_OBJECTS:
        return f"Error: Unknown object type '{object_type}'. Valid types: {', '.join(PIPEDRIVE_OBJECTS.keys())}"
    if object_type in ("activities", "leads"):
        return f"Error: Pipedrive doesn't support custom fields on {object_type}."

    client = _get_admin_client()
    endpoint = PIPEDRIVE_OBJECTS[object_type]["fields_endpoint"]

    try:
        payload = {"name": name, "field_type": field_type}
        if options and field_type in ("enum", "set"):
            try:
                payload["options"] = json.loads(options)
            except json.JSONDecodeError:
                return "Error: 'options' must be a valid JSON array of strings"

        response = client.post(f"/{endpoint}", json=payload)
        field = response.get("data", {})
        field_id = field.get("id", "unknown")
        field_key = field.get("key", "unknown")

        return (
            f"Successfully created {object_type} field '{name}' (ID: {field_id}, key: {field_key})"
        )
    except Exception as e:
        return f"Error creating field: {str(e)}"


@privileged_tool
def pipedrive_admin_update_field(
    object_type: str,
    field_id: int,
    name: str | None = None,
    options: str | None = None,
) -> str:
    """Update a field.

    Note: field_type cannot be changed after creation.

    Args:
        object_type: Object type name (deals, persons, organizations, products)
        field_id: The field's numeric ID.
        name: New display name.
        options: For enum/set fields: JSON array of option objects,
                 e.g., '[{"id": 1, "label": "Hot"}, {"label": "New Option"}]'

    Returns:
        Success message confirming the update.
    """
    if object_type not in PIPEDRIVE_OBJECTS:
        return f"Error: Unknown object type '{object_type}'. Valid types: {', '.join(PIPEDRIVE_OBJECTS.keys())}"

    client = _get_admin_client()
    endpoint = PIPEDRIVE_OBJECTS[object_type]["fields_endpoint"]

    try:
        payload = {}
        if name:
            payload["name"] = name
        if options:
            try:
                payload["options"] = json.loads(options)
            except json.JSONDecodeError:
                return "Error: 'options' must be valid JSON"

        if not payload:
            return "Error: At least one field must be provided to update."

        client.put(f"/{endpoint}/{field_id}", json=payload)
        return f"Successfully updated {object_type} field {field_id}"
    except Exception as e:
        return f"Error updating field: {str(e)}"


@privileged_tool
def pipedrive_admin_delete_field(object_type: str, field_id: int) -> str:
    """Delete a custom field.

    WARNING: This will delete the field and all its data!

    Args:
        object_type: Object type name (deals, persons, organizations, products)
        field_id: The field's numeric ID.

    Returns:
        Success message confirming deletion.
    """
    if object_type not in PIPEDRIVE_OBJECTS:
        return f"Error: Unknown object type '{object_type}'. Valid types: {', '.join(PIPEDRIVE_OBJECTS.keys())}"

    client = _get_admin_client()
    endpoint = PIPEDRIVE_OBJECTS[object_type]["fields_endpoint"]

    try:
        client.delete(f"/{endpoint}/{field_id}")
        return f"Successfully deleted {object_type} field {field_id}"
    except Exception as e:
        return f"Error deleting field: {str(e)}"


# =============================================================================
# TOOL EXPORT
# =============================================================================


def get_admin_tools() -> list[BaseTool]:
    """Get all Pipedrive admin tools.

    Returns:
        List of admin tools for schema discovery and field management.
    """
    return [
        pipedrive_admin_list_objects,
        pipedrive_admin_list_fields,
        pipedrive_admin_get_field,
        pipedrive_admin_create_field,
        pipedrive_admin_update_field,
        pipedrive_admin_delete_field,
    ]
