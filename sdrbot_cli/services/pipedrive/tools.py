"""Pipedrive static tools - schema-independent operations.

These tools work regardless of the user's Pipedrive schema and don't require sync.
Schema-dependent CRUD tools are generated in pipedrive_tools.py after sync.
"""

import json

from langchain_core.tools import BaseTool, tool

from sdrbot_cli.auth.pipedrive import get_pipedrive_client

# Shared client instance (lazy loaded)
_pipedrive_client = None


def get_pipedrive():
    """Get or create Pipedrive client instance.

    Returns fresh client on each call if previous call returned None.
    """
    global _pipedrive_client
    if _pipedrive_client is None:
        _pipedrive_client = get_pipedrive_client()
    # If still None, auth failed - don't cache the failure
    if _pipedrive_client is None:
        raise RuntimeError(
            "Pipedrive authentication failed. Check PIPEDRIVE_API_TOKEN or "
            "PIPEDRIVE_CLIENT_ID/SECRET in .env"
        )
    return _pipedrive_client


def reset_client():
    """Reset the cached client (useful after env reload)."""
    global _pipedrive_client
    _pipedrive_client = None


@tool
def pipedrive_search(term: str, item_types: str | None = None, limit: int = 10) -> str:
    """
    Search across all Pipedrive entities (deals, persons, organizations, etc.).

    Args:
        term: Search term to look for.
        item_types: Comma-separated entity types to search (e.g., "deal,person,organization").
                    If not specified, searches all types.
        limit: Maximum results to return (default 10).

    Returns:
        JSON string with search results grouped by type.
    """
    client = get_pipedrive()
    try:
        params = {"term": term, "limit": limit}
        if item_types:
            params["item_types"] = item_types

        response = client.get("/itemSearch", params=params)
        items = response.get("data", {}).get("items", [])

        if not items:
            return f'No results found for "{term}"'

        # Group by type
        results_by_type = {}
        for item in items:
            item_type = item.get("item", {}).get("type", "unknown")
            if item_type not in results_by_type:
                results_by_type[item_type] = []

            result_item = item.get("item", {})
            results_by_type[item_type].append(
                {
                    "id": result_item.get("id"),
                    "title": result_item.get("title"),
                    "type": item_type,
                }
            )

        return f"Found {len(items)} results:\n" + json.dumps(results_by_type, indent=2)
    except Exception as e:
        return f"Error searching Pipedrive: {str(e)}"


@tool
def pipedrive_add_note(
    content: str,
    deal_id: int | None = None,
    person_id: int | None = None,
    org_id: int | None = None,
) -> str:
    """
    Add a note to a deal, person, or organization in Pipedrive.

    Args:
        content: The content/body of the note.
        deal_id: ID of the deal to attach the note to.
        person_id: ID of the person to attach the note to.
        org_id: ID of the organization to attach the note to.

    Returns:
        Success message with the note ID.
    """
    client = get_pipedrive()
    try:
        data = {"content": content}

        if deal_id:
            data["deal_id"] = deal_id
        if person_id:
            data["person_id"] = person_id
        if org_id:
            data["org_id"] = org_id

        if not any([deal_id, person_id, org_id]):
            return "Error: Must specify at least one of deal_id, person_id, or org_id"

        response = client.post("/notes", json=data)
        result = response.get("data", {})
        note_id = result.get("id", "unknown")

        target = []
        if deal_id:
            target.append(f"Deal {deal_id}")
        if person_id:
            target.append(f"Person {person_id}")
        if org_id:
            target.append(f"Organization {org_id}")

        return f"Successfully added note (ID: {note_id}) to {', '.join(target)}"
    except Exception as e:
        return f"Error adding note: {str(e)}"


@tool
def pipedrive_list_notes(
    deal_id: int | None = None,
    person_id: int | None = None,
    org_id: int | None = None,
    limit: int = 10,
) -> str:
    """
    List notes attached to a deal, person, or organization in Pipedrive.

    Args:
        deal_id: ID of the deal to get notes for.
        person_id: ID of the person to get notes for.
        org_id: ID of the organization to get notes for.
        limit: Maximum number of notes to return (default 10).

    Returns:
        JSON string with notes data.
    """
    client = get_pipedrive()
    try:
        params = {"limit": limit}

        # Determine endpoint based on what ID was provided
        if deal_id:
            endpoint = f"/deals/{deal_id}/notes"
        elif person_id:
            endpoint = f"/persons/{person_id}/notes"
        elif org_id:
            endpoint = f"/organizations/{org_id}/notes"
        else:
            # Get all recent notes
            endpoint = "/notes"

        response = client.get(endpoint, params=params)
        notes = response.get("data", [])

        if not notes:
            return "No notes found"

        results = [
            {
                "id": note.get("id"),
                "content": note.get("content", "")[:200],  # Truncate long content
                "add_time": note.get("add_time"),
                "update_time": note.get("update_time"),
            }
            for note in notes
        ]

        return f"Found {len(results)} notes:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing notes: {str(e)}"


@tool
def pipedrive_list_pipelines() -> str:
    """
    List all sales pipelines in Pipedrive.

    Returns:
        JSON string with pipelines and their stages.
    """
    client = get_pipedrive()
    try:
        response = client.get("/pipelines")
        pipelines = response.get("data", [])

        if not pipelines:
            return "No pipelines found"

        results = []
        for pipeline in pipelines:
            pipeline_id = pipeline.get("id")

            # Get stages for this pipeline
            stages_response = client.get("/stages", params={"pipeline_id": pipeline_id})
            stages = stages_response.get("data", [])

            results.append(
                {
                    "id": pipeline_id,
                    "name": pipeline.get("name"),
                    "active": pipeline.get("active"),
                    "deal_probability": pipeline.get("deal_probability"),
                    "stages": [
                        {
                            "id": s.get("id"),
                            "name": s.get("name"),
                            "order_nr": s.get("order_nr"),
                        }
                        for s in stages
                    ],
                }
            )

        return f"Found {len(results)} pipelines:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing pipelines: {str(e)}"


@tool
def pipedrive_list_users(limit: int = 50) -> str:
    """
    List users in the Pipedrive account.

    Args:
        limit: Maximum number of users to return (default 50).

    Returns:
        JSON string with user data.
    """
    client = get_pipedrive()
    try:
        response = client.get("/users", params={"limit": limit})
        users = response.get("data", [])

        if not users:
            return "No users found."

        results = [
            {
                "id": user.get("id"),
                "name": user.get("name"),
                "email": user.get("email"),
                "active_flag": user.get("active_flag"),
                "role_id": user.get("role_id"),
            }
            for user in users
        ]

        return f"Found {len(results)} users:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing users: {str(e)}"


@tool
def pipedrive_get_deal_activities(deal_id: int, limit: int = 10) -> str:
    """
    Get activities (calls, meetings, tasks) associated with a deal.

    Args:
        deal_id: ID of the deal.
        limit: Maximum number of activities to return (default 10).

    Returns:
        JSON string with activities data.
    """
    client = get_pipedrive()
    try:
        response = client.get(f"/deals/{deal_id}/activities", params={"limit": limit})
        activities = response.get("data", [])

        if not activities:
            return f"No activities found for deal {deal_id}"

        results = [
            {
                "id": act.get("id"),
                "type": act.get("type"),
                "subject": act.get("subject"),
                "due_date": act.get("due_date"),
                "due_time": act.get("due_time"),
                "done": act.get("done"),
                "marked_as_done_time": act.get("marked_as_done_time"),
            }
            for act in activities
        ]

        return f"Found {len(results)} activities for deal {deal_id}:\n" + json.dumps(
            results, indent=2
        )
    except Exception as e:
        return f"Error getting activities: {str(e)}"


def get_static_tools() -> list[BaseTool]:
    """Get all static Pipedrive tools.

    Returns:
        List of schema-independent Pipedrive tools.
    """
    return [
        pipedrive_search,
        pipedrive_add_note,
        pipedrive_list_notes,
        pipedrive_list_pipelines,
        pipedrive_list_users,
        pipedrive_get_deal_activities,
    ]
