"""Zoho CRM static tools - schema-independent operations.

These tools work regardless of the user's Zoho CRM schema and don't require sync.
Schema-dependent CRUD tools are generated in zohocrm_tools.py after sync.
"""

from langchain_core.tools import BaseTool, tool

from sdrbot_cli.auth.zohocrm import get_zoho_client

# Shared client instance (lazy loaded)
_zoho_client = None


def get_zoho():
    """Get or create Zoho CRM client instance.

    Returns fresh client on each call if previous call returned None.
    """
    global _zoho_client
    if _zoho_client is None:
        _zoho_client = get_zoho_client()
    # If still None, auth failed - don't cache the failure
    if _zoho_client is None:
        raise RuntimeError(
            "Zoho CRM authentication failed. Check ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, and ZOHO_REGION in .env"
        )
    return _zoho_client


def reset_client():
    """Reset the cached client (useful after env reload)."""
    global _zoho_client
    _zoho_client = None


@tool
def zohocrm_coql_query(query: str) -> str:
    """
    Execute a COQL (CRM Object Query Language) query against Zoho CRM.

    COQL is similar to SQL and allows complex queries across modules.

    Args:
        query: The COQL SELECT query string.
               Example: "SELECT Last_Name, First_Name, Email FROM Contacts WHERE Lead_Source = 'Web'"

    Returns:
        JSON string with query results.
    """
    import json

    zoho = get_zoho()
    try:
        response = zoho.post("/coql", json={"select_query": query})
        records = response.get("data", [])

        if not records:
            return "No records found matching the query."

        # Filter out internal fields
        results = [{k: v for k, v in record.items() if not k.startswith("$")} for record in records]

        return f"Found {len(results)} records:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error executing COQL query: {str(e)}"


@tool
def zohocrm_convert_lead(
    lead_id: str,
    create_account: bool = True,
    create_contact: bool = True,
    create_deal: bool = False,
    deal_name: str | None = None,
) -> str:
    """
    Convert a Lead to Contact, Account, and optionally a Deal.

    Args:
        lead_id: The Zoho CRM ID of the Lead to convert.
        create_account: Whether to create an Account (default True).
        create_contact: Whether to create a Contact (default True).
        create_deal: Whether to create a Deal (default False).
        deal_name: Name for the Deal if create_deal is True.

    Returns:
        Success message with created record IDs.
    """
    zoho = get_zoho()
    try:
        data = {
            "data": [
                {
                    "overwrite": True,
                    "notify_lead_owner": False,
                    "notify_new_entity_owner": False,
                    "Accounts": str(create_account).lower(),
                    "Contacts": str(create_contact).lower(),
                    "Deals": str(create_deal).lower(),
                }
            ]
        }

        if create_deal and deal_name:
            data["data"][0]["Deals"] = {"Deal_Name": deal_name}

        response = zoho.post(f"/Leads/{lead_id}/actions/convert", json=data)
        result = response.get("data", [{}])[0]

        output = [f"Successfully converted Lead {lead_id}:"]
        if result.get("Contacts"):
            output.append(f"  - Contact ID: {result['Contacts']}")
        if result.get("Accounts"):
            output.append(f"  - Account ID: {result['Accounts']}")
        if result.get("Deals"):
            output.append(f"  - Deal ID: {result['Deals']}")

        return "\n".join(output)
    except Exception as e:
        return f"Error converting lead: {str(e)}"


@tool
def zohocrm_add_note(
    module: str,
    record_id: str,
    note_title: str,
    note_content: str,
) -> str:
    """
    Add a note to a record in Zoho CRM.

    Args:
        module: The module name (e.g., "Leads", "Contacts", "Accounts", "Deals").
        record_id: The Zoho CRM ID of the record to add a note to.
        note_title: Title of the note.
        note_content: Content/body of the note.

    Returns:
        Success message with the note ID.
    """
    zoho = get_zoho()
    try:
        data = {
            "data": [
                {
                    "Note_Title": note_title,
                    "Note_Content": note_content,
                    "Parent_Id": record_id,
                    "$se_module": module,
                }
            ]
        }

        response = zoho.post("/Notes", json=data)
        result = response.get("data", [{}])[0]
        note_id = result.get("details", {}).get("id", "unknown")

        return f"Successfully added note (ID: {note_id}) to {module}/{record_id}"
    except Exception as e:
        return f"Error adding note: {str(e)}"


@tool
def zohocrm_list_notes(
    module: str,
    record_id: str,
    limit: int = 10,
) -> str:
    """
    List notes attached to a record in Zoho CRM.

    Args:
        module: The module name (e.g., "Leads", "Contacts", "Accounts", "Deals").
        record_id: The Zoho CRM ID of the record.
        limit: Maximum number of notes to return (default 10).

    Returns:
        JSON string with notes data.
    """
    import json

    zoho = get_zoho()
    try:
        response = zoho.get(f"/{module}/{record_id}/Notes?per_page={limit}")
        notes = response.get("data", [])

        if not notes:
            return f"No notes found for {module}/{record_id}"

        results = [
            {
                "id": note.get("id"),
                "title": note.get("Note_Title"),
                "content": note.get("Note_Content"),
                "created_time": note.get("Created_Time"),
            }
            for note in notes
        ]

        return f"Found {len(results)} notes:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing notes: {str(e)}"


@tool
def zohocrm_get_related_records(
    module: str,
    record_id: str,
    related_module: str,
    limit: int = 10,
) -> str:
    """
    Get related records for a record in Zoho CRM.

    Args:
        module: The parent module name (e.g., "Accounts").
        record_id: The Zoho CRM ID of the parent record.
        related_module: The related module name (e.g., "Contacts", "Deals").
        limit: Maximum number of related records to return (default 10).

    Returns:
        JSON string with related records data.
    """
    import json

    zoho = get_zoho()
    try:
        response = zoho.get(f"/{module}/{record_id}/{related_module}?per_page={limit}")
        records = response.get("data", [])

        if not records:
            return f"No {related_module} found related to {module}/{record_id}"

        # Filter out internal fields
        results = [
            {
                "id": r.get("id"),
                **{k: v for k, v in r.items() if not k.startswith("$") and k != "id"},
            }
            for r in records
        ]

        return f"Found {len(results)} related {related_module}:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error getting related records: {str(e)}"


@tool
def zohocrm_list_users(limit: int = 50) -> str:
    """
    List users in the Zoho CRM organization.

    Args:
        limit: Maximum number of users to return (default 50).

    Returns:
        JSON string with user data.
    """
    import json

    zoho = get_zoho()
    try:
        response = zoho.get(f"/users?per_page={limit}")
        users = response.get("users", [])

        if not users:
            return "No users found."

        results = [
            {
                "id": user.get("id"),
                "name": user.get("full_name"),
                "email": user.get("email"),
                "role": user.get("role", {}).get("name"),
                "profile": user.get("profile", {}).get("name"),
                "status": user.get("status"),
            }
            for user in users
        ]

        return f"Found {len(results)} users:\n" + json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing users: {str(e)}"


def get_static_tools() -> list[BaseTool]:
    """Get all static Zoho CRM tools.

    Returns:
        List of schema-independent Zoho CRM tools.
    """
    return [
        zohocrm_coql_query,
        zohocrm_convert_lead,
        zohocrm_add_note,
        zohocrm_list_notes,
        zohocrm_get_related_records,
        zohocrm_list_users,
    ]
