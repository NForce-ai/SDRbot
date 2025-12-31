"""Attio Admin Tools - Schema and attribute management operations.

These tools provide CRM configuration capabilities:
- Objects: List/get/create/update custom object schemas
- Attributes: List/get/create/update custom attributes on objects
- Members: List workspace members/users

These are privileged tools - they require Privileged Mode to be enabled
via /setup > Privileged Mode. When disabled, these tools are not available.

Note: Attio API does not support deleting objects or attributes.
"""

import json
from datetime import datetime
from pathlib import Path

from langchain_core.tools import BaseTool

from sdrbot_cli.auth.attio import AttioClient
from sdrbot_cli.tools import SCOPE_PRIVILEGED, scoped_tool

# Shared client instance for admin operations
_admin_client = None

# Error log file
_ERROR_LOG = Path("files/attio_admin_errors.log")


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
    """Get or create Attio client for admin operations."""
    global _admin_client
    if _admin_client is None:
        _admin_client = AttioClient()
    return _admin_client


def reset_admin_client() -> None:
    """Reset the cached admin client."""
    global _admin_client
    _admin_client = None


# =============================================================================
# OBJECTS - Schema management
# =============================================================================


@scoped_tool(scope=SCOPE_PRIVILEGED)
def attio_admin_list_objects() -> str:
    """List all object types in Attio.

    Use this to discover what object types exist in the CRM before
    creating attributes or migrating data.

    Returns:
        JSON list of objects with their metadata.
    """
    client = _get_admin_client()
    try:
        response = client.request("GET", "/objects")
        objects = response.get("data", [])

        if not objects:
            return "No objects found."

        results = []
        for obj in objects:
            results.append(
                {
                    "object_id": obj.get("id", {}).get("object_id"),
                    "api_slug": obj.get("api_slug"),
                    "singular_noun": obj.get("singular_noun"),
                    "plural_noun": obj.get("plural_noun"),
                    "created_at": obj.get("created_at"),
                }
            )

        return f"Found {len(results)} objects:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing objects: {str(e)}"


@scoped_tool(scope=SCOPE_PRIVILEGED)
def attio_admin_get_object(object_slug: str) -> str:
    """Get details of a specific object type including its attributes.

    Args:
        object_slug: The object's API slug (e.g., "people", "companies").

    Returns:
        JSON with object details and its attributes.
    """
    client = _get_admin_client()
    try:
        # Get object details
        response = client.request("GET", f"/objects/{object_slug}")
        obj = response.get("data", {})

        if not obj:
            return f"Object not found: {object_slug}"

        # Get attributes for this object
        attrs_response = client.request("GET", f"/objects/{object_slug}/attributes")
        attributes = attrs_response.get("data", [])

        result = {
            "object_id": obj.get("id", {}).get("object_id"),
            "api_slug": obj.get("api_slug"),
            "singular_noun": obj.get("singular_noun"),
            "plural_noun": obj.get("plural_noun"),
            "created_at": obj.get("created_at"),
            "attributes": [
                {
                    "api_slug": a.get("api_slug"),
                    "title": a.get("title"),
                    "type": a.get("type"),
                    "is_required": a.get("is_required", False),
                    "is_unique": a.get("is_unique", False),
                    "is_multiselect": a.get("is_multiselect", False),
                    "is_writable": a.get("is_writable", True),
                    "is_archived": a.get("is_archived", False),
                }
                for a in attributes[:30]  # Limit to first 30
            ],
        }

        if len(attributes) > 30:
            result["total_attributes"] = len(attributes)

        return f"Object '{object_slug}':\n" + json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting object: {str(e)}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="attio")
def attio_admin_create_object(
    api_slug: str,
    singular_noun: str,
    plural_noun: str,
) -> str:
    """Create a new custom object type in Attio.

    Args:
        api_slug: Machine-readable identifier (e.g., "projects"). Must be lowercase
                  with underscores or hyphens, no spaces.
        singular_noun: Display label in singular (e.g., "Project").
        plural_noun: Display label in plural (e.g., "Projects").

    Returns:
        Success message with the new object ID.
    """
    client = _get_admin_client()
    try:
        payload = {
            "data": {
                "api_slug": api_slug,
                "singular_noun": singular_noun,
                "plural_noun": plural_noun,
            }
        }

        response = client.request("POST", "/objects", json=payload)
        obj = response.get("data", {})
        object_id = obj.get("id", {}).get("object_id")

        return f"Successfully created object '{singular_noun}' (object_id: {object_id}, api_slug: {api_slug})"
    except Exception as e:
        error_str = str(e)
        _log_error(
            "attio_admin_create_object",
            {
                "api_slug": api_slug,
                "singular_noun": singular_noun,
                "plural_noun": plural_noun,
            },
            error_str,
        )
        return f"Error creating object: {error_str}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="attio")
def attio_admin_update_object(
    object_slug: str,
    api_slug: str | None = None,
    singular_noun: str | None = None,
    plural_noun: str | None = None,
) -> str:
    """Update an object type's configuration.

    Args:
        object_slug: The object's current API slug (e.g., "people").
        api_slug: New API slug (optional).
        singular_noun: New singular display name (optional).
        plural_noun: New plural display name (optional).

    Returns:
        Success message confirming the update.
    """
    client = _get_admin_client()
    try:
        update_data = {}
        if api_slug is not None:
            update_data["api_slug"] = api_slug
        if singular_noun is not None:
            update_data["singular_noun"] = singular_noun
        if plural_noun is not None:
            update_data["plural_noun"] = plural_noun

        if not update_data:
            return "Error: At least one field must be provided to update."

        payload = {"data": update_data}

        client.request("PATCH", f"/objects/{object_slug}", json=payload)

        return f"Successfully updated object '{object_slug}'"
    except Exception as e:
        error_str = str(e)
        _log_error(
            "attio_admin_update_object",
            {"object_slug": object_slug, **update_data},
            error_str,
        )
        return f"Error updating object: {error_str}"


# =============================================================================
# ATTRIBUTES - Field management
# =============================================================================


@scoped_tool(scope=SCOPE_PRIVILEGED)
def attio_admin_list_attributes(object_slug: str, include_archived: bool = False) -> str:
    """List all attributes for an object type.

    Args:
        object_slug: The object's API slug (e.g., "people", "companies").
        include_archived: Whether to include archived attributes (default False).

    Returns:
        JSON list of attributes with their metadata.
    """
    client = _get_admin_client()
    try:
        response = client.request("GET", f"/objects/{object_slug}/attributes")
        attributes = response.get("data", [])

        if not attributes:
            return f"No attributes found for {object_slug}."

        results = []
        for a in attributes:
            # Skip archived unless requested
            if a.get("is_archived", False) and not include_archived:
                continue

            attr_info = {
                "attribute_id": a.get("id", {}).get("attribute_id"),
                "api_slug": a.get("api_slug"),
                "title": a.get("title"),
                "type": a.get("type"),
                "is_required": a.get("is_required", False),
                "is_unique": a.get("is_unique", False),
                "is_multiselect": a.get("is_multiselect", False),
                "is_writable": a.get("is_writable", True),
                "is_system_attribute": a.get("is_system_attribute", False),
                "is_archived": a.get("is_archived", False),
            }

            # Include description if present
            if a.get("description"):
                attr_info["description"] = a["description"]

            # Include options for select types
            config = a.get("config", {})
            select_config = config.get("select", {})
            if select_config.get("options"):
                attr_info["options"] = [
                    {"value": o.get("value"), "title": o.get("title")}
                    for o in select_config["options"][:10]
                ]
                if len(select_config["options"]) > 10:
                    attr_info["options_count"] = len(select_config["options"])

            results.append(attr_info)

        return f"Found {len(results)} attributes for {object_slug}:\n" + json.dumps(
            results, indent=2
        )
    except Exception as e:
        return f"Error listing attributes: {str(e)}"


@scoped_tool(scope=SCOPE_PRIVILEGED)
def attio_admin_get_attribute(object_slug: str, attribute_slug: str) -> str:
    """Get details of a specific attribute.

    Args:
        object_slug: The object's API slug (e.g., "people").
        attribute_slug: The attribute's API slug.

    Returns:
        JSON with attribute details.
    """
    client = _get_admin_client()
    try:
        response = client.request("GET", f"/objects/{object_slug}/attributes/{attribute_slug}")
        a = response.get("data", {})

        if not a:
            return f"Attribute not found: {attribute_slug}"

        result = {
            "attribute_id": a.get("id", {}).get("attribute_id"),
            "api_slug": a.get("api_slug"),
            "title": a.get("title"),
            "description": a.get("description"),
            "type": a.get("type"),
            "is_required": a.get("is_required", False),
            "is_unique": a.get("is_unique", False),
            "is_multiselect": a.get("is_multiselect", False),
            "is_writable": a.get("is_writable", True),
            "is_system_attribute": a.get("is_system_attribute", False),
            "is_archived": a.get("is_archived", False),
            "is_default_value_enabled": a.get("is_default_value_enabled", False),
            "created_at": a.get("created_at"),
        }

        # Include config details
        config = a.get("config", {})
        if config:
            result["config"] = config

        # Include default value if present
        if a.get("default_value"):
            result["default_value"] = a["default_value"]

        # Include relationship info for record-reference types
        if a.get("relationship"):
            result["relationship"] = a["relationship"]

        return f"Attribute '{attribute_slug}' on {object_slug}:\n" + json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting attribute: {str(e)}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="attio")
def attio_admin_create_attribute(
    object_slug: str,
    api_slug: str,
    title: str,
    attribute_type: str,
    description: str | None = None,
    is_required: bool = False,
    is_unique: bool = False,
    is_multiselect: bool = False,
    type_config: str | None = None,
    relationship_object: str | None = None,
) -> str:
    """Create a custom attribute on an object.

    Args:
        object_slug: The object to add the attribute to (e.g., "people").
        api_slug: Machine-readable identifier (e.g., "lead_score"). Must be lowercase
                  with underscores or hyphens.
        title: Display title (e.g., "Lead Score").
        attribute_type: Attribute type. Options:
                        - text: Text values
                        - number: Numeric values
                        - checkbox: Boolean true/false
                        - currency: Money values
                        - date: Date values
                        - timestamp: Date and time values
                        - select: Dropdown (use type_config for options)
                        - record-reference: Link to another object (use relationship_object)
                        - email: Email addresses
                        - phone: Phone numbers
                        - domain: Website domains
                        - location: Address/location
        description: Optional description of the attribute.
        is_required: Whether the attribute must have a value (default False).
        is_unique: Whether values must be unique across records (default False).
        is_multiselect: Whether multiple values are allowed (default False).
        type_config: JSON string for type-specific configuration.
                     For select type: '{"select": {"options": [{"value": "v1", "title": "Option 1"}]}}'
                     For currency type: '{"currency": {"currency_code": "USD"}}'
        relationship_object: For record-reference type: the target object slug (e.g., "companies").

    Returns:
        Success message with the new attribute ID.
    """
    client = _get_admin_client()
    try:
        payload_data = {
            "api_slug": api_slug,
            "title": title,
            "type": attribute_type,
            "is_required": is_required,
            "is_unique": is_unique,
            "is_multiselect": is_multiselect,
        }

        # Attio API requires description (use empty string if not provided)
        payload_data["description"] = description or ""

        # Attio API requires a config object (can be empty for simple types)
        if type_config:
            try:
                payload_data["config"] = json.loads(type_config)
            except json.JSONDecodeError:
                return "Error: 'type_config' must be a valid JSON string"
        else:
            payload_data["config"] = {}

        # For record-reference type, set up the relationship
        if attribute_type == "record-reference" and relationship_object:
            payload_data["config"] = {
                "record_reference": {"allowed_objects": [relationship_object]}
            }

        payload = {"data": payload_data}

        response = client.request("POST", f"/objects/{object_slug}/attributes", json=payload)
        attr = response.get("data", {})
        attribute_id = attr.get("id", {}).get("attribute_id")

        return f"Successfully created attribute '{title}' (attribute_id: {attribute_id}, api_slug: {api_slug}) on {object_slug}"
    except Exception as e:
        error_str = str(e)
        _log_error(
            "attio_admin_create_attribute",
            {
                "object_slug": object_slug,
                "api_slug": api_slug,
                "title": title,
                "type": attribute_type,
            },
            error_str,
        )
        return f"Error creating attribute: {error_str}"


@scoped_tool(scope=SCOPE_PRIVILEGED, schema_modifying="attio")
def attio_admin_update_attribute(
    object_slug: str,
    attribute_slug: str,
    title: str | None = None,
    description: str | None = None,
    api_slug: str | None = None,
    is_required: bool | None = None,
    is_unique: bool | None = None,
    is_archived: bool | None = None,
    type_config: str | None = None,
) -> str:
    """Update an attribute's configuration.

    Args:
        object_slug: The object's API slug (e.g., "people").
        attribute_slug: The attribute's current API slug.
        title: New display title.
        description: New description.
        api_slug: New API slug.
        is_required: Whether the attribute is required.
        is_unique: Whether values must be unique.
        is_archived: Whether to archive/hide the attribute.
        type_config: JSON string for type-specific configuration.

    Returns:
        Success message confirming the update.
    """
    client = _get_admin_client()
    try:
        update_data = {}
        if title is not None:
            update_data["title"] = title
        if description is not None:
            update_data["description"] = description
        if api_slug is not None:
            update_data["api_slug"] = api_slug
        if is_required is not None:
            update_data["is_required"] = is_required
        if is_unique is not None:
            update_data["is_unique"] = is_unique
        if is_archived is not None:
            update_data["is_archived"] = is_archived

        if type_config:
            try:
                update_data["config"] = json.loads(type_config)
            except json.JSONDecodeError:
                return "Error: 'type_config' must be a valid JSON string"

        if not update_data:
            return "Error: At least one field must be provided to update."

        payload = {"data": update_data}

        client.request("PATCH", f"/objects/{object_slug}/attributes/{attribute_slug}", json=payload)

        return f"Successfully updated attribute '{attribute_slug}' on {object_slug}"
    except Exception as e:
        error_str = str(e)
        _log_error(
            "attio_admin_update_attribute",
            {
                "object_slug": object_slug,
                "attribute_slug": attribute_slug,
                **update_data,
            },
            error_str,
        )
        return f"Error updating attribute: {error_str}"


# =============================================================================
# WORKSPACE MEMBERS - User management
# =============================================================================


@scoped_tool(scope=SCOPE_PRIVILEGED)
def attio_admin_list_members() -> str:
    """List all workspace members (users) in Attio.

    Use this to discover team members for record assignment or to map
    users during CRM migration.

    Returns:
        JSON list of workspace members with their details.
    """
    client = _get_admin_client()
    try:
        response = client.request("GET", "/workspace_members")
        members = response.get("data", [])

        if not members:
            return "No workspace members found."

        results = []
        for m in members:
            results.append(
                {
                    "workspace_member_id": m.get("id", {}).get("workspace_member_id"),
                    "email_address": m.get("email_address"),
                    "first_name": m.get("first_name"),
                    "last_name": m.get("last_name"),
                    "access_level": m.get("access_level"),
                    "avatar_url": m.get("avatar_url"),
                    "created_at": m.get("created_at"),
                }
            )

        return f"Found {len(results)} workspace members:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing workspace members: {str(e)}"


# =============================================================================
# TOOL EXPORT
# =============================================================================


def get_admin_tools() -> list[BaseTool]:
    """Get all Attio admin tools.

    Returns:
        List of admin tools for schema and attribute operations.
    """
    return [
        # Objects
        attio_admin_list_objects,
        attio_admin_get_object,
        attio_admin_create_object,
        attio_admin_update_object,
        # Attributes
        attio_admin_list_attributes,
        attio_admin_get_attribute,
        attio_admin_create_attribute,
        attio_admin_update_attribute,
        # Members
        attio_admin_list_members,
    ]
