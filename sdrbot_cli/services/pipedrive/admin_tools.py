"""Pipedrive Admin Tools - Custom field management for schema configuration.

These tools provide CRM configuration capabilities:
- DealFields: Create/modify custom fields on deals
- PersonFields: Create/modify custom fields on contacts
- OrganizationFields: Create/modify custom fields on companies
- ProductFields: Create/modify custom fields on products

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
# DEAL FIELDS
# =============================================================================


@privileged_tool
def pipedrive_admin_list_deal_fields() -> str:
    """List all deal fields in Pipedrive.

    Returns both standard and custom fields. Custom fields have
    edit_flag=True and their key is a 40-character hash.

    Returns:
        JSON list of deal fields with their metadata.
    """
    client = _get_admin_client()
    try:
        response = client.get("/dealFields")
        fields = response.get("data", [])
        if not fields:
            return "No deal fields found."

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

        return f"Found {len(results)} deal fields:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing deal fields: {str(e)}"


@privileged_tool
def pipedrive_admin_get_deal_field(field_id: int) -> str:
    """Get details of a specific deal field.

    Args:
        field_id: The field's numeric ID.

    Returns:
        JSON with field details.
    """
    client = _get_admin_client()
    try:
        response = client.get(f"/dealFields/{field_id}")
        field = response.get("data", {})
        return f"Deal field {field_id}:\n" + json.dumps(field, indent=2)
    except Exception as e:
        return f"Error getting deal field: {str(e)}"


@privileged_tool
def pipedrive_admin_create_deal_field(
    name: str,
    field_type: str,
    options: str | None = None,
) -> str:
    """Create a custom deal field.

    Args:
        name: Display name for the field.
        field_type: One of: varchar, varchar_auto, text, double, monetary,
                    date, daterange, time, timerange, enum, set, phone,
                    org, people, user, address.
        options: For enum/set fields: JSON array of option labels,
                 e.g., '["Hot", "Warm", "Cold"]'

    Returns:
        Success message with the new field ID and key.
    """
    client = _get_admin_client()
    try:
        payload = {
            "name": name,
            "field_type": field_type,
        }
        if options and field_type in ("enum", "set"):
            try:
                opts = json.loads(options)
                payload["options"] = opts
            except json.JSONDecodeError:
                return "Error: 'options' must be a valid JSON array of strings"

        response = client.post("/dealFields", json=payload)
        field = response.get("data", {})
        field_id = field.get("id", "unknown")
        field_key = field.get("key", "unknown")

        return f"Successfully created deal field '{name}' (ID: {field_id}, key: {field_key})"
    except Exception as e:
        return f"Error creating deal field: {str(e)}"


@privileged_tool
def pipedrive_admin_update_deal_field(
    field_id: int,
    name: str | None = None,
    options: str | None = None,
) -> str:
    """Update a deal field.

    Note: field_type cannot be changed after creation.

    Args:
        field_id: The field's numeric ID.
        name: New display name.
        options: For enum/set fields: JSON array of option objects,
                 e.g., '[{"id": 1, "label": "Hot"}, {"label": "New Option"}]'

    Returns:
        Success message confirming the update.
    """
    client = _get_admin_client()
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

        client.put(f"/dealFields/{field_id}", json=payload)
        return f"Successfully updated deal field {field_id}"
    except Exception as e:
        return f"Error updating deal field: {str(e)}"


@privileged_tool
def pipedrive_admin_delete_deal_field(field_id: int) -> str:
    """Delete a custom deal field.

    WARNING: This will delete the field and all its data from all deals!

    Args:
        field_id: The field's numeric ID.

    Returns:
        Success message confirming deletion.
    """
    client = _get_admin_client()
    try:
        client.delete(f"/dealFields/{field_id}")
        return f"Successfully deleted deal field {field_id}"
    except Exception as e:
        return f"Error deleting deal field: {str(e)}"


# =============================================================================
# PERSON FIELDS
# =============================================================================


@privileged_tool
def pipedrive_admin_list_person_fields() -> str:
    """List all person (contact) fields in Pipedrive.

    Returns both standard and custom fields.

    Returns:
        JSON list of person fields with their metadata.
    """
    client = _get_admin_client()
    try:
        response = client.get("/personFields")
        fields = response.get("data", [])
        if not fields:
            return "No person fields found."

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

        return f"Found {len(results)} person fields:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing person fields: {str(e)}"


@privileged_tool
def pipedrive_admin_get_person_field(field_id: int) -> str:
    """Get details of a specific person field.

    Args:
        field_id: The field's numeric ID.

    Returns:
        JSON with field details.
    """
    client = _get_admin_client()
    try:
        response = client.get(f"/personFields/{field_id}")
        field = response.get("data", {})
        return f"Person field {field_id}:\n" + json.dumps(field, indent=2)
    except Exception as e:
        return f"Error getting person field: {str(e)}"


@privileged_tool
def pipedrive_admin_create_person_field(
    name: str,
    field_type: str,
    options: str | None = None,
) -> str:
    """Create a custom person (contact) field.

    Args:
        name: Display name for the field.
        field_type: One of: varchar, varchar_auto, text, double, monetary,
                    date, daterange, time, timerange, enum, set, phone,
                    org, people, user, address.
        options: For enum/set fields: JSON array of option labels.

    Returns:
        Success message with the new field ID and key.
    """
    client = _get_admin_client()
    try:
        payload = {
            "name": name,
            "field_type": field_type,
        }
        if options and field_type in ("enum", "set"):
            try:
                payload["options"] = json.loads(options)
            except json.JSONDecodeError:
                return "Error: 'options' must be a valid JSON array"

        response = client.post("/personFields", json=payload)
        field = response.get("data", {})
        field_id = field.get("id", "unknown")
        field_key = field.get("key", "unknown")

        return f"Successfully created person field '{name}' (ID: {field_id}, key: {field_key})"
    except Exception as e:
        return f"Error creating person field: {str(e)}"


@privileged_tool
def pipedrive_admin_update_person_field(
    field_id: int,
    name: str | None = None,
    options: str | None = None,
) -> str:
    """Update a person field.

    Args:
        field_id: The field's numeric ID.
        name: New display name.
        options: For enum/set fields: JSON array of option objects.

    Returns:
        Success message confirming the update.
    """
    client = _get_admin_client()
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

        client.put(f"/personFields/{field_id}", json=payload)
        return f"Successfully updated person field {field_id}"
    except Exception as e:
        return f"Error updating person field: {str(e)}"


@privileged_tool
def pipedrive_admin_delete_person_field(field_id: int) -> str:
    """Delete a custom person field.

    WARNING: This will delete the field and all its data!

    Args:
        field_id: The field's numeric ID.

    Returns:
        Success message confirming deletion.
    """
    client = _get_admin_client()
    try:
        client.delete(f"/personFields/{field_id}")
        return f"Successfully deleted person field {field_id}"
    except Exception as e:
        return f"Error deleting person field: {str(e)}"


# =============================================================================
# ORGANIZATION FIELDS
# =============================================================================


@privileged_tool
def pipedrive_admin_list_organization_fields() -> str:
    """List all organization (company) fields in Pipedrive.

    Returns both standard and custom fields.

    Returns:
        JSON list of organization fields with their metadata.
    """
    client = _get_admin_client()
    try:
        response = client.get("/organizationFields")
        fields = response.get("data", [])
        if not fields:
            return "No organization fields found."

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

        return f"Found {len(results)} organization fields:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing organization fields: {str(e)}"


@privileged_tool
def pipedrive_admin_get_organization_field(field_id: int) -> str:
    """Get details of a specific organization field.

    Args:
        field_id: The field's numeric ID.

    Returns:
        JSON with field details.
    """
    client = _get_admin_client()
    try:
        response = client.get(f"/organizationFields/{field_id}")
        field = response.get("data", {})
        return f"Organization field {field_id}:\n" + json.dumps(field, indent=2)
    except Exception as e:
        return f"Error getting organization field: {str(e)}"


@privileged_tool
def pipedrive_admin_create_organization_field(
    name: str,
    field_type: str,
    options: str | None = None,
) -> str:
    """Create a custom organization (company) field.

    Args:
        name: Display name for the field.
        field_type: One of: varchar, varchar_auto, text, double, monetary,
                    date, daterange, time, timerange, enum, set, phone,
                    org, people, user, address.
        options: For enum/set fields: JSON array of option labels.

    Returns:
        Success message with the new field ID and key.
    """
    client = _get_admin_client()
    try:
        payload = {
            "name": name,
            "field_type": field_type,
        }
        if options and field_type in ("enum", "set"):
            try:
                payload["options"] = json.loads(options)
            except json.JSONDecodeError:
                return "Error: 'options' must be a valid JSON array"

        response = client.post("/organizationFields", json=payload)
        field = response.get("data", {})
        field_id = field.get("id", "unknown")
        field_key = field.get("key", "unknown")

        return (
            f"Successfully created organization field '{name}' (ID: {field_id}, key: {field_key})"
        )
    except Exception as e:
        return f"Error creating organization field: {str(e)}"


@privileged_tool
def pipedrive_admin_update_organization_field(
    field_id: int,
    name: str | None = None,
    options: str | None = None,
) -> str:
    """Update an organization field.

    Args:
        field_id: The field's numeric ID.
        name: New display name.
        options: For enum/set fields: JSON array of option objects.

    Returns:
        Success message confirming the update.
    """
    client = _get_admin_client()
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

        client.put(f"/organizationFields/{field_id}", json=payload)
        return f"Successfully updated organization field {field_id}"
    except Exception as e:
        return f"Error updating organization field: {str(e)}"


@privileged_tool
def pipedrive_admin_delete_organization_field(field_id: int) -> str:
    """Delete a custom organization field.

    WARNING: This will delete the field and all its data!

    Args:
        field_id: The field's numeric ID.

    Returns:
        Success message confirming deletion.
    """
    client = _get_admin_client()
    try:
        client.delete(f"/organizationFields/{field_id}")
        return f"Successfully deleted organization field {field_id}"
    except Exception as e:
        return f"Error deleting organization field: {str(e)}"


# =============================================================================
# PRODUCT FIELDS
# =============================================================================


@privileged_tool
def pipedrive_admin_list_product_fields() -> str:
    """List all product fields in Pipedrive.

    Returns both standard and custom fields.

    Returns:
        JSON list of product fields with their metadata.
    """
    client = _get_admin_client()
    try:
        response = client.get("/productFields")
        fields = response.get("data", [])
        if not fields:
            return "No product fields found."

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

        return f"Found {len(results)} product fields:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing product fields: {str(e)}"


@privileged_tool
def pipedrive_admin_get_product_field(field_id: int) -> str:
    """Get details of a specific product field.

    Args:
        field_id: The field's numeric ID.

    Returns:
        JSON with field details.
    """
    client = _get_admin_client()
    try:
        response = client.get(f"/productFields/{field_id}")
        field = response.get("data", {})
        return f"Product field {field_id}:\n" + json.dumps(field, indent=2)
    except Exception as e:
        return f"Error getting product field: {str(e)}"


@privileged_tool
def pipedrive_admin_create_product_field(
    name: str,
    field_type: str,
    options: str | None = None,
) -> str:
    """Create a custom product field.

    Args:
        name: Display name for the field.
        field_type: One of: varchar, varchar_auto, text, double, monetary,
                    date, daterange, time, timerange, enum, set, phone,
                    org, people, user, address.
        options: For enum/set fields: JSON array of option labels.

    Returns:
        Success message with the new field ID and key.
    """
    client = _get_admin_client()
    try:
        payload = {
            "name": name,
            "field_type": field_type,
        }
        if options and field_type in ("enum", "set"):
            try:
                payload["options"] = json.loads(options)
            except json.JSONDecodeError:
                return "Error: 'options' must be a valid JSON array"

        response = client.post("/productFields", json=payload)
        field = response.get("data", {})
        field_id = field.get("id", "unknown")
        field_key = field.get("key", "unknown")

        return f"Successfully created product field '{name}' (ID: {field_id}, key: {field_key})"
    except Exception as e:
        return f"Error creating product field: {str(e)}"


@privileged_tool
def pipedrive_admin_update_product_field(
    field_id: int,
    name: str | None = None,
    options: str | None = None,
) -> str:
    """Update a product field.

    Args:
        field_id: The field's numeric ID.
        name: New display name.
        options: For enum/set fields: JSON array of option objects.

    Returns:
        Success message confirming the update.
    """
    client = _get_admin_client()
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

        client.put(f"/productFields/{field_id}", json=payload)
        return f"Successfully updated product field {field_id}"
    except Exception as e:
        return f"Error updating product field: {str(e)}"


@privileged_tool
def pipedrive_admin_delete_product_field(field_id: int) -> str:
    """Delete a custom product field.

    WARNING: This will delete the field and all its data!

    Args:
        field_id: The field's numeric ID.

    Returns:
        Success message confirming deletion.
    """
    client = _get_admin_client()
    try:
        client.delete(f"/productFields/{field_id}")
        return f"Successfully deleted product field {field_id}"
    except Exception as e:
        return f"Error deleting product field: {str(e)}"


# =============================================================================
# TOOL EXPORT
# =============================================================================


def get_admin_tools() -> list[BaseTool]:
    """Get all Pipedrive admin tools.

    Returns:
        List of admin tools for field management.
    """
    return [
        # Deal Fields
        pipedrive_admin_list_deal_fields,
        pipedrive_admin_get_deal_field,
        pipedrive_admin_create_deal_field,
        pipedrive_admin_update_deal_field,
        pipedrive_admin_delete_deal_field,
        # Person Fields
        pipedrive_admin_list_person_fields,
        pipedrive_admin_get_person_field,
        pipedrive_admin_create_person_field,
        pipedrive_admin_update_person_field,
        pipedrive_admin_delete_person_field,
        # Organization Fields
        pipedrive_admin_list_organization_fields,
        pipedrive_admin_get_organization_field,
        pipedrive_admin_create_organization_field,
        pipedrive_admin_update_organization_field,
        pipedrive_admin_delete_organization_field,
        # Product Fields
        pipedrive_admin_list_product_fields,
        pipedrive_admin_get_product_field,
        pipedrive_admin_create_product_field,
        pipedrive_admin_update_product_field,
        pipedrive_admin_delete_product_field,
    ]
