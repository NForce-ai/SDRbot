"""HubSpot Admin Tools - Schema and property management operations.

These tools provide CRM configuration capabilities:
- Objects: List/get/create custom object schemas
- Properties: Create/modify custom properties on objects
- Owners: List workspace owners/users

These are privileged tools - they require Privileged Mode to be enabled
via /setup > Privileged Mode. When disabled, these tools are not available.
"""

import json
from datetime import datetime
from pathlib import Path

from langchain_core.tools import BaseTool

from sdrbot_cli.auth.hubspot import get_client
from sdrbot_cli.tools import SCOPE_PRIVILEGED, scoped_tool

# Shared client instance for admin operations
_admin_client = None

# Error log file
_ERROR_LOG = Path("files/hubspot_admin_errors.log")


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
    """Get or create HubSpot client for admin operations."""
    global _admin_client
    if _admin_client is None:
        _admin_client = get_client()
    if _admin_client is None:
        raise RuntimeError("HubSpot authentication failed. Check HUBSPOT_ACCESS_TOKEN in .env")
    return _admin_client


def reset_admin_client() -> None:
    """Reset the cached admin client."""
    global _admin_client
    _admin_client = None


# =============================================================================
# OBJECTS - Schema management
# =============================================================================


@scoped_tool(scope=SCOPE_PRIVILEGED)
def hubspot_admin_list_objects() -> str:
    """List all object schemas (standard and custom) in HubSpot.

    Use this to discover what object types exist in the CRM before
    creating properties or migrating data.

    Returns:
        JSON list of objects with their metadata.
    """
    hs = _get_admin_client()
    try:
        response = hs.crm.schemas.core_api.get_all()

        if not response.results:
            return "No object schemas found."

        results = []
        for schema in response.results:
            results.append(
                {
                    "name": schema.name,
                    "objectTypeId": schema.object_type_id,
                    "labels": {
                        "singular": schema.labels.singular if schema.labels else None,
                        "plural": schema.labels.plural if schema.labels else None,
                    },
                    "primaryDisplayProperty": schema.primary_display_property,
                    "fullyQualifiedName": schema.fully_qualified_name,
                }
            )

        return f"Found {len(results)} object schemas:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing objects: {str(e)}"


@scoped_tool(scope=SCOPE_PRIVILEGED)
def hubspot_admin_get_object(object_type: str) -> str:
    """Get details of a specific object schema.

    Args:
        object_type: The object type name (e.g., "contacts", "companies", "2-12345").

    Returns:
        JSON with object schema details including properties.
    """
    hs = _get_admin_client()
    try:
        schema = hs.crm.schemas.core_api.get_by_id(object_type=object_type)

        result = {
            "name": schema.name,
            "objectTypeId": schema.object_type_id,
            "labels": {
                "singular": schema.labels.singular if schema.labels else None,
                "plural": schema.labels.plural if schema.labels else None,
            },
            "primaryDisplayProperty": schema.primary_display_property,
            "secondaryDisplayProperties": schema.secondary_display_properties,
            "requiredProperties": schema.required_properties,
            "searchableProperties": schema.searchable_properties,
            "properties": [
                {"name": p.name, "label": p.label, "type": p.type}
                for p in (schema.properties or [])
            ],
        }

        return f"Object schema '{object_type}':\n" + json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting object schema: {str(e)}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="hubspot")
def hubspot_admin_create_object(
    name: str,
    label_singular: str,
    label_plural: str,
    primary_display_property: str = "name",
    description: str | None = None,
) -> str:
    """Create a new custom object schema in HubSpot.

    Args:
        name: API name for the object (e.g., "custom_lead"). Must be lowercase with underscores.
        label_singular: Display label in singular (e.g., "Custom Lead").
        label_plural: Display label in plural (e.g., "Custom Leads").
        primary_display_property: Property to use as the primary display (default: "name").
        description: Optional description of the object.

    Returns:
        Success message with the new object type ID.
    """
    hs = _get_admin_client()
    try:
        from hubspot.crm.schemas import ObjectSchemaEgg, ObjectTypePropertyCreate

        # Create with a default "name" property as primary display
        properties = [
            ObjectTypePropertyCreate(
                name=primary_display_property,
                label=primary_display_property.replace("_", " ").title(),
                type="string",
                field_type="text",
            )
        ]

        schema_egg = ObjectSchemaEgg(
            name=name,
            labels={"singular": label_singular, "plural": label_plural},
            primary_display_property=primary_display_property,
            required_properties=[primary_display_property],
            properties=properties,
        )

        if description:
            schema_egg.description = description

        response = hs.crm.schemas.core_api.create(object_schema_egg=schema_egg)

        return f"Successfully created object '{label_singular}' (objectTypeId: {response.object_type_id})"
    except Exception as e:
        error_str = str(e)
        _log_error(
            "hubspot_admin_create_object",
            {
                "name": name,
                "label_singular": label_singular,
                "label_plural": label_plural,
            },
            error_str,
        )
        return f"Error creating object: {error_str}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="hubspot")
def hubspot_admin_update_object(
    object_type: str,
    label_singular: str | None = None,
    label_plural: str | None = None,
    description: str | None = None,
) -> str:
    """Update a custom object schema's configuration.

    Note: Only custom objects can be updated. Standard HubSpot objects
    (contacts, companies, deals, tickets) cannot be modified.

    Args:
        object_type: The object type ID (e.g., "2-12345" for custom objects).
        label_singular: New display label in singular.
        label_plural: New display label in plural.
        description: New description.

    Returns:
        Success message confirming the update.
    """
    hs = _get_admin_client()
    try:
        from hubspot.crm.schemas import ObjectTypeDefinitionPatch

        update_data = {}

        if label_singular is not None or label_plural is not None:
            update_data["labels"] = {}
            if label_singular is not None:
                update_data["labels"]["singular"] = label_singular
            if label_plural is not None:
                update_data["labels"]["plural"] = label_plural

        if description is not None:
            update_data["description"] = description

        if not update_data:
            return "Error: At least one field must be provided to update."

        patch = ObjectTypeDefinitionPatch(**update_data)

        hs.crm.schemas.core_api.update(object_type=object_type, object_type_definition_patch=patch)

        return f"Successfully updated object '{object_type}'"
    except Exception as e:
        error_str = str(e)
        _log_error(
            "hubspot_admin_update_object",
            {"object_type": object_type},
            error_str,
        )
        return f"Error updating object: {error_str}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="hubspot")
def hubspot_admin_delete_object(object_type: str) -> str:
    """Delete a custom object schema.

    WARNING: This will delete the object schema and ALL its records!

    Note: Only custom objects can be deleted. Standard HubSpot objects
    (contacts, companies, deals, tickets) cannot be deleted. The object
    must have no records before it can be deleted.

    Args:
        object_type: The object type ID (e.g., "2-12345" for custom objects).

    Returns:
        Success message confirming deletion.
    """
    hs = _get_admin_client()
    try:
        hs.crm.schemas.core_api.archive(object_type=object_type)

        return f"Successfully deleted object '{object_type}'"
    except Exception as e:
        error_str = str(e)
        if "records" in error_str.lower() or "not empty" in error_str.lower():
            return (
                f"Error: Cannot delete object '{object_type}'. "
                "Delete all records first before deleting the schema."
            )
        _log_error(
            "hubspot_admin_delete_object",
            {"object_type": object_type},
            error_str,
        )
        return f"Error deleting object: {error_str}"


# =============================================================================
# PROPERTIES - Field management
# =============================================================================


@scoped_tool(scope=SCOPE_PRIVILEGED)
def hubspot_admin_list_properties(object_type: str, include_hidden: bool = False) -> str:
    """List all properties for an object type.

    Args:
        object_type: The object type (e.g., "contacts", "companies", "deals").
        include_hidden: Whether to include hidden properties (default False).

    Returns:
        JSON list of properties with their metadata.
    """
    hs = _get_admin_client()
    try:
        response = hs.crm.properties.core_api.get_all(object_type=object_type)

        if not response.results:
            return f"No properties found for {object_type}."

        results = []
        for p in response.results:
            # Skip hidden unless requested
            if p.hidden and not include_hidden:
                continue

            prop_info = {
                "name": p.name,
                "label": p.label,
                "type": p.type,
                "fieldType": p.field_type,
                "groupName": p.group_name,
                "hidden": p.hidden,
            }

            # Include read-only status
            if p.modification_metadata:
                prop_info["readOnly"] = p.modification_metadata.read_only_value

            # Include options for enumeration types
            if p.options:
                prop_info["options"] = [
                    {"value": o.value, "label": o.label}
                    for o in p.options[:10]  # Limit to first 10
                ]
                if len(p.options) > 10:
                    prop_info["optionsCount"] = len(p.options)

            results.append(prop_info)

        return f"Found {len(results)} properties for {object_type}:\n" + json.dumps(
            results, indent=2
        )
    except Exception as e:
        return f"Error listing properties: {str(e)}"


@scoped_tool(scope=SCOPE_PRIVILEGED)
def hubspot_admin_get_property(object_type: str, property_name: str) -> str:
    """Get details of a specific property.

    Args:
        object_type: The object type (e.g., "contacts").
        property_name: The property's internal name.

    Returns:
        JSON with property details.
    """
    hs = _get_admin_client()
    try:
        p = hs.crm.properties.core_api.get_by_name(
            object_type=object_type, property_name=property_name
        )

        result = {
            "name": p.name,
            "label": p.label,
            "type": p.type,
            "fieldType": p.field_type,
            "description": p.description,
            "groupName": p.group_name,
            "hidden": p.hidden,
            "displayOrder": p.display_order,
            "hasUniqueValue": p.has_unique_value,
            "formField": p.form_field,
        }

        if p.modification_metadata:
            result["readOnly"] = p.modification_metadata.read_only_value

        if p.options:
            result["options"] = [
                {"value": o.value, "label": o.label, "hidden": o.hidden} for o in p.options
            ]

        return f"Property '{property_name}' on {object_type}:\n" + json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting property: {str(e)}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="hubspot")
def hubspot_admin_create_property(
    object_type: str,
    name: str,
    label: str,
    property_type: str,
    field_type: str,
    group_name: str = "contactinformation",
    description: str | None = None,
    options: str | None = None,
) -> str:
    """Create a custom property on an object.

    Args:
        object_type: The object type to add the property to (e.g., "contacts").
        name: API name for the property (lowercase with underscores, e.g., "lead_score").
        label: Display label (e.g., "Lead Score").
        property_type: Property type. Options:
                       - string: Text values
                       - number: Numeric values
                       - date: Date values
                       - datetime: Date and time values
                       - enumeration: Dropdown/checkbox (requires options)
                       - bool: Boolean true/false
        field_type: Field type (UI control). Options:
                    - text: Single-line text
                    - textarea: Multi-line text
                    - number: Number input
                    - date: Date picker
                    - select: Dropdown (for enumeration)
                    - checkbox: Multiple checkboxes (for enumeration)
                    - radio: Radio buttons (for enumeration)
                    - booleancheckbox: Single checkbox (for bool)
        group_name: Property group (default "contactinformation").
                    Common groups: contactinformation, companyinformation, dealinformation
        description: Optional description.
        options: For enumeration type: JSON array of options.
                 Example: '[{"value": "hot", "label": "Hot Lead"}, {"value": "warm", "label": "Warm Lead"}]'

    Returns:
        Success message with the new property name.
    """
    hs = _get_admin_client()
    try:
        from hubspot.crm.properties import OptionInput, PropertyCreate

        prop_create = PropertyCreate(
            name=name,
            label=label,
            type=property_type,
            field_type=field_type,
            group_name=group_name,
        )

        if description:
            prop_create.description = description

        if options:
            try:
                parsed_options = json.loads(options)
                prop_create.options = [
                    OptionInput(
                        value=opt["value"],
                        label=opt["label"],
                        hidden=opt.get("hidden", False),
                        display_order=idx,
                    )
                    for idx, opt in enumerate(parsed_options)
                ]
            except json.JSONDecodeError:
                return "Error: 'options' must be a valid JSON array"

        response = hs.crm.properties.core_api.create(
            object_type=object_type, property_create=prop_create
        )

        return f"Successfully created property '{label}' (name: {response.name}) on {object_type}"
    except Exception as e:
        error_str = str(e)
        _log_error(
            "hubspot_admin_create_property",
            {
                "object_type": object_type,
                "name": name,
                "label": label,
                "property_type": property_type,
                "field_type": field_type,
                "options": options,
            },
            error_str,
        )
        return f"Error creating property: {error_str}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="hubspot")
def hubspot_admin_update_property(
    object_type: str,
    property_name: str,
    label: str | None = None,
    description: str | None = None,
    group_name: str | None = None,
    display_order: int | None = None,
    hidden: bool | None = None,
    options: str | None = None,
) -> str:
    """Update a property's configuration.

    Args:
        object_type: The object type (e.g., "contacts").
        property_name: The property's internal name.
        label: New display label.
        description: New description.
        group_name: New property group.
        display_order: New display order.
        hidden: Whether to hide the property.
        options: For enumeration type: JSON array of options to replace existing.
                 Example: '[{"value": "hot", "label": "Hot Lead"}]'

    Returns:
        Success message confirming the update.
    """
    hs = _get_admin_client()
    try:
        from hubspot.crm.properties import OptionInput, PropertyUpdate

        update_data = {}
        if label is not None:
            update_data["label"] = label
        if description is not None:
            update_data["description"] = description
        if group_name is not None:
            update_data["group_name"] = group_name
        if display_order is not None:
            update_data["display_order"] = display_order
        if hidden is not None:
            update_data["hidden"] = hidden

        if options:
            try:
                parsed_options = json.loads(options)
                update_data["options"] = [
                    OptionInput(
                        value=opt["value"],
                        label=opt["label"],
                        hidden=opt.get("hidden", False),
                        display_order=idx,
                    )
                    for idx, opt in enumerate(parsed_options)
                ]
            except json.JSONDecodeError:
                return "Error: 'options' must be a valid JSON array"

        if not update_data:
            return "Error: At least one field must be provided to update."

        prop_update = PropertyUpdate(**update_data)

        hs.crm.properties.core_api.update(
            object_type=object_type,
            property_name=property_name,
            property_update=prop_update,
        )

        return f"Successfully updated property '{property_name}' on {object_type}"
    except Exception as e:
        error_str = str(e)
        _log_error(
            "hubspot_admin_update_property",
            {
                "object_type": object_type,
                "property_name": property_name,
                "label": label,
                "options": options,
            },
            error_str,
        )
        return f"Error updating property: {error_str}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="hubspot")
def hubspot_admin_delete_property(object_type: str, property_name: str) -> str:
    """Delete a custom property.

    WARNING: This will delete the property and all its data!

    Note: Only custom properties can be deleted. Standard HubSpot properties
    cannot be deleted.

    Args:
        object_type: The object type (e.g., "contacts").
        property_name: The property's internal name.

    Returns:
        Success message confirming deletion.
    """
    hs = _get_admin_client()
    try:
        hs.crm.properties.core_api.archive(object_type=object_type, property_name=property_name)

        return f"Successfully deleted property '{property_name}' from {object_type}"
    except Exception as e:
        error_str = str(e)
        if "cannot be deleted" in error_str.lower() or "standard" in error_str.lower():
            return (
                f"Error: Cannot delete property '{property_name}'. "
                "Standard HubSpot properties cannot be deleted, only custom properties."
            )
        return f"Error deleting property: {error_str}"


# =============================================================================
# OWNERS - User management
# =============================================================================


@scoped_tool(scope=SCOPE_PRIVILEGED)
def hubspot_admin_list_owners(include_archived: bool = False) -> str:
    """List all owners (users) in HubSpot.

    Use this to discover team members for record assignment or to map
    owners during CRM migration.

    Args:
        include_archived: Whether to include archived/inactive owners (default False).

    Returns:
        JSON list of owners with their details.
    """
    hs = _get_admin_client()
    try:
        response = hs.crm.owners.owners_api.get_page(limit=100, archived=include_archived)

        if not response.results:
            return "No owners found."

        results = []
        for owner in response.results:
            results.append(
                {
                    "id": owner.id,
                    "userId": owner.user_id,
                    "email": owner.email,
                    "firstName": owner.first_name,
                    "lastName": owner.last_name,
                    "teams": [{"id": t.id, "name": t.name} for t in (owner.teams or [])],
                }
            )

        return f"Found {len(results)} owners:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing owners: {str(e)}"


# =============================================================================
# TOOL EXPORT
# =============================================================================


def get_admin_tools() -> list[BaseTool]:
    """Get all HubSpot admin tools.

    Returns:
        List of admin tools for schema and property operations.
    """
    return [
        # Objects
        hubspot_admin_list_objects,
        hubspot_admin_get_object,
        hubspot_admin_create_object,
        hubspot_admin_update_object,
        hubspot_admin_delete_object,
        # Properties
        hubspot_admin_list_properties,
        hubspot_admin_get_property,
        hubspot_admin_create_property,
        hubspot_admin_update_property,
        hubspot_admin_delete_property,
        # Owners
        hubspot_admin_list_owners,
    ]
