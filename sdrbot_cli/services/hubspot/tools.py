"""HubSpot static tools - schema-independent operations.

These tools work regardless of the user's HubSpot schema and don't require sync.
Schema-dependent CRUD tools are generated in tools.generated.py after sync.
"""

from typing import List

from langchain_core.tools import BaseTool, tool

from sdrbot_cli.auth.hubspot import get_client

# Shared client instance (lazy loaded)
_hs_client = None


def get_hs():
    """Get or create HubSpot client instance.

    Returns fresh client on each call if previous call returned None.
    """
    global _hs_client
    if _hs_client is None:
        _hs_client = get_client()
    # If still None, auth failed - don't cache the failure
    if _hs_client is None:
        raise RuntimeError("HubSpot authentication failed. Check HUBSPOT_ACCESS_TOKEN in .env")
    return _hs_client


def reset_client():
    """Reset the cached client (useful after env reload)."""
    global _hs_client
    _hs_client = None


@tool
def hubspot_list_pipelines(object_type: str = "deals") -> str:
    """
    List all pipelines for an object type.

    Args:
        object_type: Either "deals" or "tickets" (the objects that support pipelines)
    """
    hs = get_hs()
    try:
        response = hs.crm.pipelines.pipelines_api.get_all(object_type=object_type)

        output = [f"Pipelines for {object_type}:"]
        for pipeline in response.results:
            output.append(f"- {pipeline.label} (ID: {pipeline.id})")
            for stage in pipeline.stages:
                output.append(f"    Stage: {stage.label} (ID: {stage.id})")

        return "\n".join(output)
    except Exception as e:
        return f"Error listing pipelines: {str(e)}"


@tool
def hubspot_create_association(
    from_object_type: str,
    from_object_id: str,
    to_object_type: str,
    to_object_id: str,
) -> str:
    """
    Create an association between two HubSpot records.

    Args:
        from_object_type: Source object type (e.g., "contacts", "companies", "deals")
        from_object_id: Source record ID
        to_object_type: Target object type (e.g., "contacts", "companies", "deals")
        to_object_id: Target record ID
    """
    hs = get_hs()
    try:
        # Get association types between these objects
        types_response = hs.crm.associations.v4.schema.definitions_api.get_all(
            from_object_type=from_object_type,
            to_object_type=to_object_type,
        )

        if not types_response.results:
            return f"No association types found between {from_object_type} and {to_object_type}"

        # Use the first (default) association type
        assoc_type = types_response.results[0]

        # Create the association
        # Note: HubSpot SDK v4 uses object_type/object_id (not from_object_type/from_object_id)
        from hubspot.crm.associations.v4.models import AssociationSpec

        hs.crm.associations.v4.basic_api.create(
            object_type=from_object_type,
            object_id=from_object_id,
            to_object_type=to_object_type,
            to_object_id=to_object_id,
            association_spec=[
                AssociationSpec(
                    association_category=assoc_type.category,
                    association_type_id=assoc_type.type_id,
                )
            ],
        )

        return f"Successfully associated {from_object_type}/{from_object_id} with {to_object_type}/{to_object_id}"
    except Exception as e:
        return f"Error creating association: {str(e)}"


@tool
def hubspot_list_associations(
    from_object_type: str,
    from_object_id: str,
    to_object_type: str,
) -> str:
    """
    List all associations from a record to another object type.

    Args:
        from_object_type: Source object type (e.g., "contacts")
        from_object_id: Source record ID
        to_object_type: Target object type to find associations to (e.g., "companies")
    """
    hs = get_hs()
    try:
        # Note: HubSpot SDK v4 uses object_type/object_id (not from_object_type/from_object_id)
        response = hs.crm.associations.v4.basic_api.get_page(
            object_type=from_object_type,
            object_id=from_object_id,
            to_object_type=to_object_type,
        )

        if not response.results:
            return f"No {to_object_type} associated with {from_object_type}/{from_object_id}"

        output = [f"Associated {to_object_type} records:"]
        for assoc in response.results:
            output.append(f"- ID: {assoc.to_object_id}")

        return "\n".join(output)
    except Exception as e:
        return f"Error listing associations: {str(e)}"


@tool
def hubspot_delete_association(
    from_object_type: str,
    from_object_id: str,
    to_object_type: str,
    to_object_id: str,
) -> str:
    """
    Remove an association between two HubSpot records.

    Args:
        from_object_type: Source object type
        from_object_id: Source record ID
        to_object_type: Target object type
        to_object_id: Target record ID
    """
    hs = get_hs()
    try:
        # Note: HubSpot SDK v4 uses object_type/object_id (not from_object_type/from_object_id)
        hs.crm.associations.v4.basic_api.archive(
            object_type=from_object_type,
            object_id=from_object_id,
            to_object_type=to_object_type,
            to_object_id=to_object_id,
        )

        return f"Successfully removed association between {from_object_type}/{from_object_id} and {to_object_type}/{to_object_id}"
    except Exception as e:
        return f"Error deleting association: {str(e)}"


def get_static_tools() -> List[BaseTool]:
    """Get all static HubSpot tools.

    Returns:
        List of schema-independent HubSpot tools.
    """
    return [
        hubspot_list_pipelines,
        hubspot_create_association,
        hubspot_list_associations,
        hubspot_delete_association,
    ]
