"""Twenty Admin Tools - Metadata API operations for schema management.

These tools provide CRM configuration capabilities:
- Objects: Create/modify custom object types
- Fields: Create/modify custom fields on objects
- Views: Configure table/kanban views
- View Fields/Filters/Sorts/Groups: Fine-tune view configuration

These are privileged tools - they require Privileged Mode to be enabled
via /setup > Privileged Mode. When disabled, these tools are not available.
"""

import json

from langchain_core.tools import BaseTool

from sdrbot_cli.auth.twenty import TwentyClient
from sdrbot_cli.tools import privileged_tool

# Shared client instance for admin operations
_admin_client = None


def _get_admin_client() -> TwentyClient:
    """Get or create Twenty client for admin operations."""
    global _admin_client
    if _admin_client is None:
        _admin_client = TwentyClient()
    return _admin_client


def reset_admin_client() -> None:
    """Reset the cached admin client."""
    global _admin_client
    _admin_client = None


# =============================================================================
# OBJECTS - Custom object type management
# =============================================================================


@privileged_tool
def twenty_admin_list_objects(limit: int = 50) -> str:
    """List all objects (standard and custom) in Twenty.

    Use this to discover what object types exist in the CRM before
    creating fields or migrating data.

    Args:
        limit: Maximum objects to return (default 50).

    Returns:
        JSON list of objects with their metadata.
    """
    client = _get_admin_client()
    try:
        # Metadata endpoints are at /rest/objects, /rest/fields, etc.
        data = client.get("/metadata/objects")

        objects = data.get("data", {}).get("objects", []) if isinstance(data, dict) else data
        if not objects:
            return "No objects found."

        results = []
        for obj in objects:
            results.append(
                {
                    "id": obj.get("id"),
                    "nameSingular": obj.get("nameSingular"),
                    "namePlural": obj.get("namePlural"),
                    "labelSingular": obj.get("labelSingular"),
                    "labelPlural": obj.get("labelPlural"),
                    "isCustom": obj.get("isCustom", False),
                    "isActive": obj.get("isActive", True),
                }
            )

        return f"Found {len(results)} objects:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing objects: {str(e)}"


@privileged_tool
def twenty_admin_get_object(object_id: str) -> str:
    """Get details of a specific object by ID.

    Args:
        object_id: The object's metadata ID.

    Returns:
        JSON with object details including fields.
    """
    client = _get_admin_client()
    try:
        data = client.get(f"/metadata/objects/{object_id}")

        obj = (
            data.get("data", {}).get("object", {})
            if isinstance(data, dict) and "data" in data
            else data
        )
        return f"Object {object_id}:\n" + json.dumps(obj, indent=2)
    except Exception as e:
        return f"Error getting object: {str(e)}"


@privileged_tool
def twenty_admin_create_object(
    name_singular: str,
    name_plural: str,
    label_singular: str,
    label_plural: str,
    description: str | None = None,
    icon: str | None = None,
) -> str:
    """Create a new custom object type in Twenty.

    Args:
        name_singular: API name in singular (e.g., "customLead"). Must be camelCase.
        name_plural: API name in plural (e.g., "customLeads"). Must be camelCase.
        label_singular: Display label in singular (e.g., "Custom Lead").
        label_plural: Display label in plural (e.g., "Custom Leads").
        description: Optional description of the object.
        icon: Optional icon name (e.g., "IconUser").

    Returns:
        Success message with the new object ID.
    """
    client = _get_admin_client()
    try:
        payload = {
            "nameSingular": name_singular,
            "namePlural": name_plural,
            "labelSingular": label_singular,
            "labelPlural": label_plural,
        }
        if description:
            payload["description"] = description
        if icon:
            payload["icon"] = icon

        data = client.post("/metadata/objects", json=payload)

        obj = (
            data.get("data", {}).get("object", {})
            if isinstance(data, dict) and "data" in data
            else data
        )
        obj_id = obj.get("id", "unknown")

        return f"Successfully created object '{label_singular}' (ID: {obj_id})"
    except Exception as e:
        return f"Error creating object: {str(e)}"


@privileged_tool
def twenty_admin_update_object(
    object_id: str,
    is_active: bool | None = None,
    label_singular: str | None = None,
    label_plural: str | None = None,
    description: str | None = None,
    icon: str | None = None,
) -> str:
    """Update an existing object's properties.

    Args:
        object_id: The object's metadata ID.
        is_active: Set to False to deactivate the object.
        label_singular: New singular display label.
        label_plural: New plural display label.
        description: New description.
        icon: New icon name.

    Returns:
        Success message confirming the update.
    """
    client = _get_admin_client()
    try:
        payload = {}
        if is_active is not None:
            payload["isActive"] = is_active
        if label_singular:
            payload["labelSingular"] = label_singular
        if label_plural:
            payload["labelPlural"] = label_plural
        if description:
            payload["description"] = description
        if icon:
            payload["icon"] = icon

        if not payload:
            return "Error: At least one field must be provided to update."

        client.patch(f"/metadata/objects/{object_id}", json=payload)
        return f"Successfully updated object {object_id}"
    except Exception as e:
        return f"Error updating object: {str(e)}"


@privileged_tool
def twenty_admin_delete_object(object_id: str) -> str:
    """Delete a custom object type.

    WARNING: This will delete the object and all its records!

    Args:
        object_id: The object's metadata ID.

    Returns:
        Success message confirming deletion.
    """
    client = _get_admin_client()
    try:
        client.delete(f"/metadata/objects/{object_id}")

        return f"Successfully deleted object {object_id}"
    except Exception as e:
        return f"Error deleting object: {str(e)}"


# =============================================================================
# FIELDS - Custom field management
# =============================================================================


@privileged_tool
def twenty_admin_list_fields(object_id: str | None = None, limit: int = 100) -> str:
    """List fields, optionally filtered by object.

    Args:
        object_id: Filter by object metadata ID (optional).
        limit: Maximum fields to return (default 100).

    Returns:
        JSON list of fields with their metadata.
    """
    client = _get_admin_client()
    try:
        params = {"limit": limit}
        if object_id:
            params["filter"] = f'objectMetadataId[eq]:"{object_id}"'

        data = client.get("/metadata/fields")

        fields = data.get("data", {}).get("fields", []) if isinstance(data, dict) else data
        if not fields:
            return "No fields found."

        results = []
        for field in fields:
            results.append(
                {
                    "id": field.get("id"),
                    "name": field.get("name"),
                    "label": field.get("label"),
                    "type": field.get("type"),
                    "objectMetadataId": field.get("objectMetadataId"),
                    "isCustom": field.get("isCustom", False),
                    "isNullable": field.get("isNullable", True),
                }
            )

        return f"Found {len(results)} fields:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing fields: {str(e)}"


@privileged_tool
def twenty_admin_get_field(field_id: str) -> str:
    """Get details of a specific field.

    Args:
        field_id: The field's metadata ID.

    Returns:
        JSON with field details.
    """
    client = _get_admin_client()
    try:
        data = client.get(f"/metadata/fields/{field_id}")

        field = (
            data.get("data", {}).get("field", {})
            if isinstance(data, dict) and "data" in data
            else data
        )
        return f"Field {field_id}:\n" + json.dumps(field, indent=2)
    except Exception as e:
        return f"Error getting field: {str(e)}"


@privileged_tool
def twenty_admin_create_field(
    object_id: str,
    name: str,
    label: str,
    field_type: str,
    description: str | None = None,
    icon: str | None = None,
    is_nullable: bool = True,
    default_value: str | None = None,
    options: str | None = None,
) -> str:
    """Create a custom field on an object.

    Args:
        object_id: The object metadata ID to add the field to.
        name: API name for the field (camelCase, e.g., "leadScore").
        label: Display label (e.g., "Lead Score").
        field_type: Field type. Valid types:
                    - Basic: UUID, TEXT, BOOLEAN, NUMBER, NUMERIC, POSITION
                    - Date/Time: DATE, DATE_TIME
                    - Contact: PHONES, EMAILS, LINKS (note: plural forms!)
                    - Monetary: CURRENCY
                    - Name: FULL_NAME
                    - Rating: RATING (1-5 scale)
                    - Selection: SELECT, MULTI_SELECT (require options)
                    - Complex: ADDRESS, ACTOR, ARRAY, RAW_JSON, RICH_TEXT, TS_VECTOR
                    - Relations: RELATION
        description: Optional field description.
        icon: Optional icon name.
        is_nullable: Whether field can be empty (default True).
        default_value: Default value as JSON string.
        options: For SELECT/MULTI_SELECT: JSON array of options.
                 IMPORTANT: option "value" must be SCREAMING_SNAKE_CASE matching
                 pattern ^[A-Z0-9]+_[A-Z0-9]+$. Example:
                 '[{"value": "HOT_LEAD", "label": "Hot Lead", "color": "green"}]'
                 Valid colors: green, turquoise, sky, blue, purple, pink, red,
                 orange, yellow, gray.

    Returns:
        Success message with the new field ID.
    """
    client = _get_admin_client()
    try:
        payload = {
            "objectMetadataId": object_id,
            "name": name,
            "label": label,
            "type": field_type,
            "isNullable": is_nullable,
        }
        if description:
            payload["description"] = description
        if icon:
            payload["icon"] = icon
        if default_value:
            try:
                payload["defaultValue"] = json.loads(default_value)
            except json.JSONDecodeError:
                payload["defaultValue"] = default_value
        if options:
            try:
                payload["options"] = json.loads(options)
            except json.JSONDecodeError:
                return "Error: 'options' must be a valid JSON array"

        data = client.post("/metadata/fields", json=payload)

        field = (
            data.get("data", {}).get("field", {})
            if isinstance(data, dict) and "data" in data
            else data
        )
        field_id = field.get("id", "unknown")

        return f"Successfully created field '{label}' (ID: {field_id})"
    except Exception as e:
        return f"Error creating field: {str(e)}"


@privileged_tool
def twenty_admin_update_field(
    field_id: str,
    label: str | None = None,
    description: str | None = None,
    icon: str | None = None,
    is_nullable: bool | None = None,
    default_value: str | None = None,
    options: str | None = None,
) -> str:
    """Update a field's properties.

    Args:
        field_id: The field's metadata ID.
        label: New display label.
        description: New description.
        icon: New icon name.
        is_nullable: Whether field can be empty.
        default_value: New default value as JSON string.
        options: For SELECT/MULTI_SELECT: JSON array of options.
                 Option "value" must be SCREAMING_SNAKE_CASE matching
                 pattern ^[A-Z0-9]+_[A-Z0-9]+$. Example:
                 '[{"value": "HOT_LEAD", "label": "Hot Lead", "color": "green"}]'

    Returns:
        Success message confirming the update.
    """
    client = _get_admin_client()
    try:
        payload = {}
        if label:
            payload["label"] = label
        if description:
            payload["description"] = description
        if icon:
            payload["icon"] = icon
        if is_nullable is not None:
            payload["isNullable"] = is_nullable
        if default_value:
            try:
                payload["defaultValue"] = json.loads(default_value)
            except json.JSONDecodeError:
                payload["defaultValue"] = default_value
        if options:
            try:
                payload["options"] = json.loads(options)
            except json.JSONDecodeError:
                return "Error: 'options' must be a valid JSON array"

        if not payload:
            return "Error: At least one field must be provided to update."

        client.patch(f"/metadata/fields/{field_id}", json=payload)
        return f"Successfully updated field {field_id}"
    except Exception as e:
        return f"Error updating field: {str(e)}"


@privileged_tool
def twenty_admin_delete_field(field_id: str) -> str:
    """Delete a custom field.

    WARNING: This will delete the field and all its data!

    Args:
        field_id: The field's metadata ID.

    Returns:
        Success message confirming deletion.
    """
    client = _get_admin_client()
    try:
        client.delete(f"/metadata/fields/{field_id}")

        return f"Successfully deleted field {field_id}"
    except Exception as e:
        return f"Error deleting field: {str(e)}"


# =============================================================================
# VIEWS - Table/Kanban view configuration
# =============================================================================


@privileged_tool
def twenty_admin_list_views(object_id: str | None = None, limit: int = 50) -> str:
    """List views, optionally filtered by object.

    Args:
        object_id: Filter by object metadata ID (optional).
        limit: Maximum views to return (default 50).

    Returns:
        JSON list of views.
    """
    client = _get_admin_client()
    try:
        params = {"limit": limit}
        if object_id:
            params["filter"] = f'objectMetadataId[eq]:"{object_id}"'

        data = client.get("/metadata/views")

        views = data.get("data", {}).get("views", []) if isinstance(data, dict) else data
        if not views:
            return "No views found."

        results = []
        for view in views:
            results.append(
                {
                    "id": view.get("id"),
                    "name": view.get("name"),
                    "type": view.get("type"),
                    "objectMetadataId": view.get("objectMetadataId"),
                    "isCompact": view.get("isCompact", False),
                }
            )

        return f"Found {len(results)} views:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing views: {str(e)}"


@privileged_tool
def twenty_admin_get_view(view_id: str) -> str:
    """Get details of a specific view.

    Args:
        view_id: The view's ID.

    Returns:
        JSON with view details.
    """
    client = _get_admin_client()
    try:
        data = client.get(f"/metadata/views/{view_id}")

        view = (
            data.get("data", {}).get("view", {})
            if isinstance(data, dict) and "data" in data
            else data
        )
        return f"View {view_id}:\n" + json.dumps(view, indent=2)
    except Exception as e:
        return f"Error getting view: {str(e)}"


@privileged_tool
def twenty_admin_create_view(
    object_id: str,
    name: str,
    view_type: str = "table",
    icon: str | None = None,
    is_compact: bool = False,
) -> str:
    """Create a new view for an object.

    Args:
        object_id: The object metadata ID.
        name: View name (e.g., "My Custom View").
        view_type: View type - "table" or "kanban" (default "table").
        icon: Optional icon name.
        is_compact: Whether to use compact display (default False).

    Returns:
        Success message with the new view ID.
    """
    client = _get_admin_client()
    try:
        payload = {
            "objectMetadataId": object_id,
            "name": name,
            "type": view_type.upper(),
            "isCompact": is_compact,
        }
        if icon:
            payload["icon"] = icon

        data = client.post("/metadata/views", json=payload)

        view = (
            data.get("data", {}).get("view", {})
            if isinstance(data, dict) and "data" in data
            else data
        )
        view_id = view.get("id", "unknown")

        return f"Successfully created view '{name}' (ID: {view_id})"
    except Exception as e:
        return f"Error creating view: {str(e)}"


@privileged_tool
def twenty_admin_update_view(
    view_id: str,
    name: str | None = None,
    view_type: str | None = None,
    icon: str | None = None,
    is_compact: bool | None = None,
) -> str:
    """Update a view's properties.

    Args:
        view_id: The view's ID.
        name: New view name.
        view_type: New view type - "table" or "kanban".
        icon: New icon name.
        is_compact: Whether to use compact display.

    Returns:
        Success message confirming the update.
    """
    client = _get_admin_client()
    try:
        payload = {}
        if name:
            payload["name"] = name
        if view_type:
            payload["type"] = view_type.upper()
        if icon:
            payload["icon"] = icon
        if is_compact is not None:
            payload["isCompact"] = is_compact

        if not payload:
            return "Error: At least one field must be provided to update."

        client.patch(f"/metadata/views/{view_id}", json=payload)
        return f"Successfully updated view {view_id}"
    except Exception as e:
        return f"Error updating view: {str(e)}"


@privileged_tool
def twenty_admin_delete_view(view_id: str) -> str:
    """Delete a view.

    Args:
        view_id: The view's ID.

    Returns:
        Success message confirming deletion.
    """
    client = _get_admin_client()
    try:
        client.delete(f"/metadata/views/{view_id}")

        return f"Successfully deleted view {view_id}"
    except Exception as e:
        return f"Error deleting view: {str(e)}"


# =============================================================================
# VIEW FIELDS - Configure which fields appear in views
# =============================================================================


@privileged_tool
def twenty_admin_list_view_fields(view_id: str, limit: int = 50) -> str:
    """List fields configured for a view.

    Args:
        view_id: The view's ID.
        limit: Maximum fields to return (default 50).

    Returns:
        JSON list of view field configurations.
    """
    client = _get_admin_client()
    try:
        data = client.get("/metadata/viewFields")

        fields = data.get("data", {}).get("viewFields", [])
        if not fields:
            return "No view fields found."

        results = []
        for field in fields:
            results.append(
                {
                    "id": field.get("id"),
                    "fieldMetadataId": field.get("fieldMetadataId"),
                    "isVisible": field.get("isVisible", True),
                    "position": field.get("position"),
                    "size": field.get("size"),
                }
            )

        return f"Found {len(results)} view fields:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing view fields: {str(e)}"


@privileged_tool
def twenty_admin_create_view_field(
    view_id: str,
    field_metadata_id: str,
    is_visible: bool = True,
    position: int | None = None,
    size: int | None = None,
) -> str:
    """Add a field to a view.

    Args:
        view_id: The view's ID.
        field_metadata_id: The field's metadata ID.
        is_visible: Whether the field is visible (default True).
        position: Field position in the view (0-indexed).
        size: Field column width.

    Returns:
        Success message with the new view field ID.
    """
    client = _get_admin_client()
    try:
        payload = {
            "viewId": view_id,
            "fieldMetadataId": field_metadata_id,
            "isVisible": is_visible,
        }
        if position is not None:
            payload["position"] = position
        if size is not None:
            payload["size"] = size

        data = client.post("/metadata/viewFields", json=payload)

        vf = data.get("data", {}).get("viewField", {})
        vf_id = vf.get("id", "unknown")

        return f"Successfully added field to view (ID: {vf_id})"
    except Exception as e:
        return f"Error creating view field: {str(e)}"


@privileged_tool
def twenty_admin_update_view_field(
    view_field_id: str,
    is_visible: bool | None = None,
    position: int | None = None,
    size: int | None = None,
) -> str:
    """Update a view field's configuration.

    Args:
        view_field_id: The view field's ID.
        is_visible: Whether the field is visible.
        position: Field position in the view.
        size: Field column width.

    Returns:
        Success message confirming the update.
    """
    client = _get_admin_client()
    try:
        payload = {}
        if is_visible is not None:
            payload["isVisible"] = is_visible
        if position is not None:
            payload["position"] = position
        if size is not None:
            payload["size"] = size

        if not payload:
            return "Error: At least one field must be provided to update."

        client.patch(f"/metadata/viewFields/{view_field_id}", json=payload)
        return f"Successfully updated view field {view_field_id}"
    except Exception as e:
        return f"Error updating view field: {str(e)}"


@privileged_tool
def twenty_admin_delete_view_field(view_field_id: str) -> str:
    """Remove a field from a view.

    Args:
        view_field_id: The view field's ID.

    Returns:
        Success message confirming deletion.
    """
    client = _get_admin_client()
    try:
        client.delete(f"/metadata/viewFields/{view_field_id}")

        return f"Successfully removed field from view {view_field_id}"
    except Exception as e:
        return f"Error deleting view field: {str(e)}"


# =============================================================================
# VIEW FILTERS - Configure filter rules on views
# =============================================================================


@privileged_tool
def twenty_admin_list_view_filters(view_id: str, limit: int = 50) -> str:
    """List filters configured for a view.

    Args:
        view_id: The view's ID.
        limit: Maximum filters to return (default 50).

    Returns:
        JSON list of view filter configurations.
    """
    client = _get_admin_client()
    try:
        data = client.get("/metadata/viewFilters")

        filters = data.get("data", {}).get("viewFilters", [])
        if not filters:
            return "No view filters found."

        return f"Found {len(filters)} view filters:\n" + json.dumps(filters, indent=2)
    except Exception as e:
        return f"Error listing view filters: {str(e)}"


@privileged_tool
def twenty_admin_create_view_filter(
    view_id: str,
    field_metadata_id: str,
    operand: str,
    value: str,
) -> str:
    """Add a filter to a view.

    Args:
        view_id: The view's ID.
        field_metadata_id: The field to filter on.
        operand: Filter operator. Options: IS, IS_NOT, CONTAINS, DOES_NOT_CONTAIN,
                 GREATER_THAN, LESS_THAN, IS_EMPTY, IS_NOT_EMPTY.
        value: Filter value.

    Returns:
        Success message with the new filter ID.
    """
    client = _get_admin_client()
    try:
        payload = {
            "viewId": view_id,
            "fieldMetadataId": field_metadata_id,
            "operand": operand,
            "value": value,
        }

        data = client.post("/metadata/viewFilters", json=payload)

        vf = data.get("data", {}).get("viewFilter", {})
        vf_id = vf.get("id", "unknown")

        return f"Successfully created view filter (ID: {vf_id})"
    except Exception as e:
        return f"Error creating view filter: {str(e)}"


@privileged_tool
def twenty_admin_update_view_filter(
    view_filter_id: str,
    operand: str | None = None,
    value: str | None = None,
) -> str:
    """Update a view filter.

    Args:
        view_filter_id: The view filter's ID.
        operand: New filter operator.
        value: New filter value.

    Returns:
        Success message confirming the update.
    """
    client = _get_admin_client()
    try:
        payload = {}
        if operand:
            payload["operand"] = operand
        if value:
            payload["value"] = value

        if not payload:
            return "Error: At least one field must be provided to update."

        client.patch(f"/metadata/viewFilters/{view_filter_id}", json=payload)
        return f"Successfully updated view filter {view_filter_id}"
    except Exception as e:
        return f"Error updating view filter: {str(e)}"


@privileged_tool
def twenty_admin_delete_view_filter(view_filter_id: str) -> str:
    """Remove a filter from a view.

    Args:
        view_filter_id: The view filter's ID.

    Returns:
        Success message confirming deletion.
    """
    client = _get_admin_client()
    try:
        client.delete(f"/metadata/viewFilters/{view_filter_id}")

        return f"Successfully deleted view filter {view_filter_id}"
    except Exception as e:
        return f"Error deleting view filter: {str(e)}"


# =============================================================================
# VIEW SORTS - Configure sort order on views
# =============================================================================


@privileged_tool
def twenty_admin_list_view_sorts(view_id: str, limit: int = 50) -> str:
    """List sort configurations for a view.

    Args:
        view_id: The view's ID.
        limit: Maximum sorts to return (default 50).

    Returns:
        JSON list of view sort configurations.
    """
    client = _get_admin_client()
    try:
        data = client.get("/metadata/viewSorts")

        sorts = data.get("data", {}).get("viewSorts", [])
        if not sorts:
            return "No view sorts found."

        return f"Found {len(sorts)} view sorts:\n" + json.dumps(sorts, indent=2)
    except Exception as e:
        return f"Error listing view sorts: {str(e)}"


@privileged_tool
def twenty_admin_create_view_sort(
    view_id: str,
    field_metadata_id: str,
    direction: str = "AscNullsLast",
) -> str:
    """Add a sort to a view.

    Args:
        view_id: The view's ID.
        field_metadata_id: The field to sort by.
        direction: Sort direction. Options: AscNullsFirst, AscNullsLast,
                   DescNullsFirst, DescNullsLast (default: AscNullsLast).

    Returns:
        Success message with the new sort ID.
    """
    client = _get_admin_client()
    try:
        payload = {
            "viewId": view_id,
            "fieldMetadataId": field_metadata_id,
            "direction": direction,
        }

        data = client.post("/metadata/viewSorts", json=payload)

        vs = data.get("data", {}).get("viewSort", {})
        vs_id = vs.get("id", "unknown")

        return f"Successfully created view sort (ID: {vs_id})"
    except Exception as e:
        return f"Error creating view sort: {str(e)}"


@privileged_tool
def twenty_admin_update_view_sort(
    view_sort_id: str,
    direction: str | None = None,
) -> str:
    """Update a view sort.

    Args:
        view_sort_id: The view sort's ID.
        direction: New sort direction.

    Returns:
        Success message confirming the update.
    """
    client = _get_admin_client()
    try:
        if not direction:
            return "Error: direction must be provided to update."

        client.patch(f"/metadata/viewSorts/{view_sort_id}", json={"direction": direction})

        return f"Successfully updated view sort {view_sort_id}"
    except Exception as e:
        return f"Error updating view sort: {str(e)}"


@privileged_tool
def twenty_admin_delete_view_sort(view_sort_id: str) -> str:
    """Remove a sort from a view.

    Args:
        view_sort_id: The view sort's ID.

    Returns:
        Success message confirming deletion.
    """
    client = _get_admin_client()
    try:
        client.delete(f"/metadata/viewSorts/{view_sort_id}")

        return f"Successfully deleted view sort {view_sort_id}"
    except Exception as e:
        return f"Error deleting view sort: {str(e)}"


# =============================================================================
# VIEW GROUPS - Configure grouping on views
# =============================================================================


@privileged_tool
def twenty_admin_list_view_groups(view_id: str, limit: int = 50) -> str:
    """List group configurations for a view.

    Args:
        view_id: The view's ID.
        limit: Maximum groups to return (default 50).

    Returns:
        JSON list of view group configurations.
    """
    client = _get_admin_client()
    try:
        data = client.get("/metadata/viewGroups")

        groups = data.get("data", {}).get("viewGroups", [])
        if not groups:
            return "No view groups found."

        return f"Found {len(groups)} view groups:\n" + json.dumps(groups, indent=2)
    except Exception as e:
        return f"Error listing view groups: {str(e)}"


@privileged_tool
def twenty_admin_create_view_group(
    view_id: str,
    field_metadata_id: str,
    is_visible: bool = True,
    position: int = 0,
) -> str:
    """Add a grouping to a view.

    Args:
        view_id: The view's ID.
        field_metadata_id: The field to group by.
        is_visible: Whether the group is visible (default True).
        position: Group position (default 0).

    Returns:
        Success message with the new group ID.
    """
    client = _get_admin_client()
    try:
        payload = {
            "viewId": view_id,
            "fieldMetadataId": field_metadata_id,
            "isVisible": is_visible,
            "position": position,
        }

        data = client.post("/metadata/viewGroups", json=payload)

        vg = data.get("data", {}).get("viewGroup", {})
        vg_id = vg.get("id", "unknown")

        return f"Successfully created view group (ID: {vg_id})"
    except Exception as e:
        return f"Error creating view group: {str(e)}"


@privileged_tool
def twenty_admin_update_view_group(
    view_group_id: str,
    is_visible: bool | None = None,
    position: int | None = None,
) -> str:
    """Update a view group.

    Args:
        view_group_id: The view group's ID.
        is_visible: Whether the group is visible.
        position: Group position.

    Returns:
        Success message confirming the update.
    """
    client = _get_admin_client()
    try:
        payload = {}
        if is_visible is not None:
            payload["isVisible"] = is_visible
        if position is not None:
            payload["position"] = position

        if not payload:
            return "Error: At least one field must be provided to update."

        client.patch(f"/metadata/viewGroups/{view_group_id}", json=payload)
        return f"Successfully updated view group {view_group_id}"
    except Exception as e:
        return f"Error updating view group: {str(e)}"


@privileged_tool
def twenty_admin_delete_view_group(view_group_id: str) -> str:
    """Remove a grouping from a view.

    Args:
        view_group_id: The view group's ID.

    Returns:
        Success message confirming deletion.
    """
    client = _get_admin_client()
    try:
        client.delete(f"/metadata/viewGroups/{view_group_id}")

        return f"Successfully deleted view group {view_group_id}"
    except Exception as e:
        return f"Error deleting view group: {str(e)}"


# =============================================================================
# TOOL EXPORT
# =============================================================================


def get_admin_tools() -> list[BaseTool]:
    """Get all Twenty admin tools.

    Returns:
        List of admin tools for metadata operations.
    """
    return [
        # Objects
        twenty_admin_list_objects,
        twenty_admin_get_object,
        twenty_admin_create_object,
        twenty_admin_update_object,
        twenty_admin_delete_object,
        # Fields
        twenty_admin_list_fields,
        twenty_admin_get_field,
        twenty_admin_create_field,
        twenty_admin_update_field,
        twenty_admin_delete_field,
        # Views
        twenty_admin_list_views,
        twenty_admin_get_view,
        twenty_admin_create_view,
        twenty_admin_update_view,
        twenty_admin_delete_view,
        # View Fields
        twenty_admin_list_view_fields,
        twenty_admin_create_view_field,
        twenty_admin_update_view_field,
        twenty_admin_delete_view_field,
        # View Filters
        twenty_admin_list_view_filters,
        twenty_admin_create_view_filter,
        twenty_admin_update_view_filter,
        twenty_admin_delete_view_filter,
        # View Sorts
        twenty_admin_list_view_sorts,
        twenty_admin_create_view_sort,
        twenty_admin_update_view_sort,
        twenty_admin_delete_view_sort,
        # View Groups
        twenty_admin_list_view_groups,
        twenty_admin_create_view_group,
        twenty_admin_update_view_group,
        twenty_admin_delete_view_group,
    ]
