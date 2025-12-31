"""Salesforce Admin Tools - Schema and field management operations.

These tools provide CRM configuration capabilities:
- Objects: List/get object schemas and metadata
- Fields: List/get/create/update/delete custom fields
- Users: List users for owner assignment

These are privileged tools - they require Privileged Mode to be enabled
via /setup > Privileged Mode. When disabled, these tools are not available.
"""

import json
from datetime import datetime
from pathlib import Path

from langchain_core.tools import BaseTool

from sdrbot_cli.auth.salesforce import get_client
from sdrbot_cli.tools import SCOPE_PRIVILEGED, scoped_tool

# Shared client instance for admin operations
_admin_client = None

# Error log file
_ERROR_LOG = Path("files/salesforce_admin_errors.log")


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
    """Get or create Salesforce client for admin operations."""
    global _admin_client
    if _admin_client is None:
        _admin_client = get_client()
    if _admin_client is None:
        raise RuntimeError("Salesforce authentication failed. Check your credentials in .env")
    return _admin_client


def reset_admin_client() -> None:
    """Reset the cached admin client."""
    global _admin_client
    _admin_client = None


# =============================================================================
# OBJECTS - Schema management
# =============================================================================


@scoped_tool(scope=SCOPE_PRIVILEGED)
def salesforce_admin_list_objects(include_all: bool = False) -> str:
    """List all available object types in Salesforce.

    Use this to discover what object types exist in the CRM before
    creating fields or migrating data.

    Args:
        include_all: If True, include all objects. If False (default),
                    only show standard CRM objects and custom objects.

    Returns:
        JSON list of objects with their metadata.
    """
    sf = _get_admin_client()
    try:
        desc = sf.describe()

        if not desc.get("sobjects"):
            return "No objects found."

        # Standard CRM objects to always include
        standard_crm = {
            "Lead",
            "Contact",
            "Account",
            "Opportunity",
            "Case",
            "Task",
            "Event",
            "Campaign",
            "Note",
            "User",
        }

        results = []
        for obj in desc.get("sobjects", []):
            name = obj.get("name", "")

            # Filter unless include_all
            if not include_all:
                is_custom = name.endswith("__c")
                is_standard_crm = name in standard_crm
                if not is_custom and not is_standard_crm:
                    continue

            results.append(
                {
                    "name": name,
                    "label": obj.get("label"),
                    "labelPlural": obj.get("labelPlural"),
                    "keyPrefix": obj.get("keyPrefix"),
                    "custom": obj.get("custom", False),
                    "createable": obj.get("createable", False),
                    "updateable": obj.get("updateable", False),
                    "queryable": obj.get("queryable", False),
                }
            )

        # Sort: custom objects first, then alphabetically
        results.sort(key=lambda x: (not x["custom"], x["name"]))

        return f"Found {len(results)} objects:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing objects: {str(e)}"


@scoped_tool(scope=SCOPE_PRIVILEGED)
def salesforce_admin_get_object(object_name: str) -> str:
    """Get details of a specific object type including its fields.

    Args:
        object_name: The object API name (e.g., "Contact", "Account", "Custom__c").

    Returns:
        JSON with object schema details including fields.
    """
    sf = _get_admin_client()
    try:
        desc = sf.restful(f"sobjects/{object_name}/describe")

        # Extract key metadata
        result = {
            "name": desc.get("name"),
            "label": desc.get("label"),
            "labelPlural": desc.get("labelPlural"),
            "keyPrefix": desc.get("keyPrefix"),
            "custom": desc.get("custom", False),
            "createable": desc.get("createable", False),
            "updateable": desc.get("updateable", False),
            "queryable": desc.get("queryable", False),
            "fieldCount": len(desc.get("fields", [])),
            "recordTypeCount": len(desc.get("recordTypeInfos", [])),
        }

        # Include summary of fields (just names and types, not full details)
        fields_summary = []
        for f in desc.get("fields", [])[:50]:  # Limit to first 50
            fields_summary.append(
                {
                    "name": f.get("name"),
                    "label": f.get("label"),
                    "type": f.get("type"),
                    "required": not f.get("nillable", True),
                    "custom": f.get("custom", False),
                }
            )

        result["fields"] = fields_summary
        if len(desc.get("fields", [])) > 50:
            result["moreFields"] = len(desc.get("fields", [])) - 50

        return f"Object '{object_name}':\n" + json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting object: {str(e)}"


# =============================================================================
# FIELDS - Field management
# =============================================================================


@scoped_tool(scope=SCOPE_PRIVILEGED)
def salesforce_admin_list_fields(object_name: str, include_system: bool = False) -> str:
    """List all fields for an object type.

    Args:
        object_name: The object API name (e.g., "Contact").
        include_system: Whether to include system fields like Id, CreatedDate (default False).

    Returns:
        JSON list of fields with their metadata.
    """
    sf = _get_admin_client()
    try:
        desc = sf.restful(f"sobjects/{object_name}/describe")

        # System fields to exclude unless requested
        system_fields = {
            "Id",
            "IsDeleted",
            "CreatedDate",
            "CreatedById",
            "LastModifiedDate",
            "LastModifiedById",
            "SystemModstamp",
            "LastActivityDate",
            "LastViewedDate",
            "LastReferencedDate",
        }

        results = []
        for f in desc.get("fields", []):
            name = f.get("name")

            # Skip system fields unless requested
            if not include_system and name in system_fields:
                continue

            field_info = {
                "name": name,
                "label": f.get("label"),
                "type": f.get("type"),
                "required": not f.get("nillable", True),
                "createable": f.get("createable", False),
                "updateable": f.get("updateable", False),
                "custom": f.get("custom", False),
                "length": f.get("length"),
            }

            # Include picklist values
            if f.get("type") == "picklist":
                values = [p.get("value") for p in f.get("picklistValues", []) if p.get("active")]
                field_info["picklistValues"] = values[:10]
                if len(values) > 10:
                    field_info["moreValues"] = len(values) - 10

            # Include reference info
            if f.get("type") == "reference":
                field_info["referenceTo"] = f.get("referenceTo", [])

            results.append(field_info)

        # Sort: custom fields first, then alphabetically
        results.sort(key=lambda x: (not x["custom"], x["name"]))

        return f"Found {len(results)} fields on {object_name}:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing fields: {str(e)}"


@scoped_tool(scope=SCOPE_PRIVILEGED)
def salesforce_admin_get_field(object_name: str, field_name: str) -> str:
    """Get details of a specific field.

    Args:
        object_name: The object API name (e.g., "Contact").
        field_name: The field API name (e.g., "Email", "Custom_Field__c").

    Returns:
        JSON with field details.
    """
    sf = _get_admin_client()
    try:
        desc = sf.restful(f"sobjects/{object_name}/describe")

        # Find the specific field
        field = None
        for f in desc.get("fields", []):
            if f.get("name") == field_name:
                field = f
                break

        if not field:
            return f"Field '{field_name}' not found on {object_name}."

        result = {
            "name": field.get("name"),
            "label": field.get("label"),
            "type": field.get("type"),
            "soapType": field.get("soapType"),
            "length": field.get("length"),
            "precision": field.get("precision"),
            "scale": field.get("scale"),
            "required": not field.get("nillable", True),
            "unique": field.get("unique", False),
            "createable": field.get("createable", False),
            "updateable": field.get("updateable", False),
            "custom": field.get("custom", False),
            "externalId": field.get("externalId", False),
            "defaultValue": field.get("defaultValue"),
            "inlineHelpText": field.get("inlineHelpText"),
        }

        # Include all picklist values
        if field.get("type") == "picklist":
            result["picklistValues"] = [
                {
                    "value": p.get("value"),
                    "label": p.get("label"),
                    "active": p.get("active"),
                    "defaultValue": p.get("defaultValue"),
                }
                for p in field.get("picklistValues", [])
            ]

        # Include reference info
        if field.get("type") == "reference":
            result["referenceTo"] = field.get("referenceTo", [])
            result["relationshipName"] = field.get("relationshipName")

        return f"Field '{field_name}' on {object_name}:\n" + json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting field: {str(e)}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="salesforce")
def salesforce_admin_create_field(
    object_name: str,
    field_name: str,
    field_label: str,
    field_type: str,
    length: int | None = None,
    precision: int | None = None,
    scale: int | None = None,
    required: bool = False,
    unique: bool = False,
    external_id: bool = False,
    description: str | None = None,
    picklist_values: str | None = None,
) -> str:
    """Create a custom field on an object.

    Note: Requires Tooling API access. Field name will have __c suffix added.

    Args:
        object_name: The object API name (e.g., "Contact", "Account").
        field_name: API name for the field (without __c suffix, e.g., "Lead_Score").
        field_label: Display label (e.g., "Lead Score").
        field_type: Field type. Options:
                   - Text: Short text (requires length)
                   - TextArea: Multi-line text
                   - LongTextArea: Large text (requires length)
                   - Number: Numeric (requires precision, scale)
                   - Currency: Money value (requires precision, scale)
                   - Percent: Percentage (requires precision, scale)
                   - Checkbox: Boolean
                   - Date: Date only
                   - DateTime: Date and time
                   - Email: Email address
                   - Phone: Phone number
                   - Url: Web address
                   - Picklist: Dropdown (requires picklist_values)
        length: For Text fields, max length (1-255). For LongTextArea (up to 131072).
        precision: For Number/Currency/Percent, total digits (up to 18).
        scale: For Number/Currency/Percent, decimal places (up to precision).
        required: Whether the field is required (default False).
        unique: Whether values must be unique (default False).
        external_id: Whether this is an external ID field (default False).
        description: Help text for the field.
        picklist_values: For Picklist type: JSON array of values.
                        Example: '["Hot", "Warm", "Cold"]'

    Returns:
        Success message with the new field API name.
    """
    sf = _get_admin_client()
    try:
        # Build the field metadata
        full_field_name = f"{field_name}__c"

        metadata = {
            "FullName": f"{object_name}.{full_field_name}",
            "Metadata": {
                "label": field_label,
                "type": field_type,
                "required": required,
                "unique": unique,
                "externalId": external_id,
            },
        }

        # Add type-specific attributes
        if field_type in ("Text",) and length:
            metadata["Metadata"]["length"] = length
        elif field_type == "LongTextArea" and length:
            metadata["Metadata"]["length"] = length
            metadata["Metadata"]["visibleLines"] = 3
        elif field_type in ("Number", "Currency", "Percent"):
            metadata["Metadata"]["precision"] = precision or 18
            metadata["Metadata"]["scale"] = scale or 0
        elif field_type == "Picklist" and picklist_values:
            try:
                values = json.loads(picklist_values)
                metadata["Metadata"]["valueSet"] = {
                    "restricted": False,
                    "valueSetDefinition": {
                        "sorted": False,
                        "value": [
                            {"fullName": v, "label": v, "default": i == 0}
                            for i, v in enumerate(values)
                        ],
                    },
                }
            except json.JSONDecodeError:
                return "Error: 'picklist_values' must be a valid JSON array"

        if description:
            metadata["Metadata"]["inlineHelpText"] = description

        # Use Tooling API to create the field
        result = sf.restful("tooling/sobjects/CustomField", method="POST", json=metadata)

        if result.get("success"):
            return (
                f"Successfully created field '{field_label}' "
                f"(API name: {full_field_name}) on {object_name}"
            )
        else:
            errors = result.get("errors", [])
            return f"Failed to create field: {errors}"

    except Exception as e:
        error_str = str(e)
        _log_error(
            "salesforce_admin_create_field",
            {
                "object_name": object_name,
                "field_name": field_name,
                "field_label": field_label,
                "field_type": field_type,
            },
            error_str,
        )
        return f"Error creating field: {error_str}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="salesforce")
def salesforce_admin_update_field(
    object_name: str,
    field_name: str,
    field_label: str | None = None,
    description: str | None = None,
    required: bool | None = None,
    picklist_values: str | None = None,
) -> str:
    """Update a custom field's configuration.

    Note: Only custom fields (ending in __c) can be updated.

    Args:
        object_name: The object API name (e.g., "Contact").
        field_name: The field API name (e.g., "Custom_Field__c").
        field_label: New display label.
        description: New help text.
        required: Whether the field is required.
        picklist_values: For Picklist type: JSON array of values to replace existing.

    Returns:
        Success message confirming the update.
    """
    sf = _get_admin_client()
    try:
        if not field_name.endswith("__c"):
            return "Error: Only custom fields (ending in __c) can be updated."

        # First, get the field ID from Tooling API
        query = (
            f"SELECT Id FROM CustomField "
            f"WHERE DeveloperName = '{field_name.replace('__c', '')}' "
            f"AND TableEnumOrId = '{object_name}'"
        )
        result = sf.restful(f"tooling/query/?q={query}")

        records = result.get("records", [])
        if not records:
            return f"Field '{field_name}' not found on {object_name}."

        field_id = records[0]["Id"]

        # Build update metadata
        update_data = {"Metadata": {}}

        if field_label is not None:
            update_data["Metadata"]["label"] = field_label
        if description is not None:
            update_data["Metadata"]["inlineHelpText"] = description
        if required is not None:
            update_data["Metadata"]["required"] = required
        if picklist_values is not None:
            try:
                values = json.loads(picklist_values)
                update_data["Metadata"]["valueSet"] = {
                    "restricted": False,
                    "valueSetDefinition": {
                        "sorted": False,
                        "value": [
                            {"fullName": v, "label": v, "default": i == 0}
                            for i, v in enumerate(values)
                        ],
                    },
                }
            except json.JSONDecodeError:
                return "Error: 'picklist_values' must be a valid JSON array"

        if not update_data["Metadata"]:
            return "Error: At least one field must be provided to update."

        # Update via Tooling API
        sf.restful(f"tooling/sobjects/CustomField/{field_id}", method="PATCH", json=update_data)

        return f"Successfully updated field '{field_name}' on {object_name}"

    except Exception as e:
        error_str = str(e)
        _log_error(
            "salesforce_admin_update_field",
            {"object_name": object_name, "field_name": field_name},
            error_str,
        )
        return f"Error updating field: {error_str}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="salesforce")
def salesforce_admin_delete_field(object_name: str, field_name: str) -> str:
    """Delete a custom field.

    WARNING: This will delete the field and all its data!

    Note: Only custom fields (ending in __c) can be deleted.

    Args:
        object_name: The object API name (e.g., "Contact").
        field_name: The field API name (e.g., "Custom_Field__c").

    Returns:
        Success message confirming deletion.
    """
    sf = _get_admin_client()
    try:
        if not field_name.endswith("__c"):
            return "Error: Only custom fields (ending in __c) can be deleted."

        # Get the field ID from Tooling API
        query = (
            f"SELECT Id FROM CustomField "
            f"WHERE DeveloperName = '{field_name.replace('__c', '')}' "
            f"AND TableEnumOrId = '{object_name}'"
        )
        result = sf.restful(f"tooling/query/?q={query}")

        records = result.get("records", [])
        if not records:
            return f"Field '{field_name}' not found on {object_name}."

        field_id = records[0]["Id"]

        # Delete via Tooling API
        sf.restful(f"tooling/sobjects/CustomField/{field_id}", method="DELETE")

        return f"Successfully deleted field '{field_name}' from {object_name}"

    except Exception as e:
        error_str = str(e)
        _log_error(
            "salesforce_admin_delete_field",
            {"object_name": object_name, "field_name": field_name},
            error_str,
        )
        return f"Error deleting field: {error_str}"


# =============================================================================
# USERS - User management
# =============================================================================


@scoped_tool(scope=SCOPE_PRIVILEGED)
def salesforce_admin_list_users(active_only: bool = True) -> str:
    """List all users in Salesforce.

    Use this to discover team members for record assignment or to map
    users during CRM migration.

    Args:
        active_only: Whether to only show active users (default True).

    Returns:
        JSON list of users with their details.
    """
    sf = _get_admin_client()
    try:
        where_clause = "WHERE IsActive = true" if active_only else ""
        query = f"""
            SELECT Id, Username, Name, Email, Title, Department,
                   UserRole.Name, Profile.Name, IsActive
            FROM User
            {where_clause}
            ORDER BY Name
            LIMIT 200
        """

        result = sf.query(query)

        if not result.get("records"):
            return "No users found."

        users = []
        for u in result.get("records", []):
            users.append(
                {
                    "id": u.get("Id"),
                    "username": u.get("Username"),
                    "name": u.get("Name"),
                    "email": u.get("Email"),
                    "title": u.get("Title"),
                    "department": u.get("Department"),
                    "role": u.get("UserRole", {}).get("Name") if u.get("UserRole") else None,
                    "profile": u.get("Profile", {}).get("Name") if u.get("Profile") else None,
                    "isActive": u.get("IsActive"),
                }
            )

        return f"Found {len(users)} users:\n" + json.dumps(users, indent=2)
    except Exception as e:
        return f"Error listing users: {str(e)}"


# =============================================================================
# TOOL EXPORT
# =============================================================================


def get_admin_tools() -> list[BaseTool]:
    """Get all Salesforce admin tools.

    Returns:
        List of admin tools for schema and field operations.
    """
    return [
        # Objects
        salesforce_admin_list_objects,
        salesforce_admin_get_object,
        # Fields
        salesforce_admin_list_fields,
        salesforce_admin_get_field,
        salesforce_admin_create_field,
        salesforce_admin_update_field,
        salesforce_admin_delete_field,
        # Users
        salesforce_admin_list_users,
    ]
