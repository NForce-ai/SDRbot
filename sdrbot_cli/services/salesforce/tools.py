"""Salesforce static tools - schema-independent operations.

These tools work regardless of the user's Salesforce schema and don't require sync.
Schema-dependent CRUD tools are generated in tools.generated.py after sync.
"""

import json

from langchain_core.tools import BaseTool, tool

from sdrbot_cli.auth.salesforce import get_client

# Shared client instance (lazy loaded)
_sf_client = None


def get_sf():
    """Get or create Salesforce client instance."""
    global _sf_client
    if _sf_client is None:
        _sf_client = get_client()
    return _sf_client


@tool
def salesforce_soql_query(query: str) -> str:
    """
    Execute a SOQL query against Salesforce.
    Use this for complex queries, reporting, or when you need to join data across objects.

    Args:
        query: SOQL query string (e.g., "SELECT Id, Name, Email FROM Contact WHERE Name LIKE 'John%' LIMIT 10")

    Note: Only SELECT queries are allowed for safety.
    """
    sf = get_sf()
    try:
        # Sanity check: prevent destructive queries
        if not query.strip().upper().startswith("SELECT"):
            return "Error: Only SELECT queries are allowed via this tool."

        results = sf.query(query)

        records = results.get("records", [])
        if not records:
            return "Query returned 0 records."

        # Clean up attributes metadata to save tokens
        clean_records = []
        for rec in records:
            if "attributes" in rec:
                del rec["attributes"]
            clean_records.append(rec)

        return (
            f"Query returned {results['totalSize']} records:\n{json.dumps(clean_records, indent=2)}"
        )
    except Exception as e:
        return f"SOQL Error: {str(e)}"


@tool
def salesforce_sosl_search(search: str) -> str:
    """
    Execute a SOSL search across Salesforce objects.
    Use this for full-text search across multiple object types.

    Args:
        search: SOSL search string (e.g., "FIND {John Smith} IN ALL FIELDS RETURNING Contact(Id, Name), Lead(Id, Name)")
    """
    sf = get_sf()
    try:
        results = sf.search(search)

        if not results.get("searchRecords"):
            return "No records found."

        # Format results
        output = []
        for rec in results["searchRecords"]:
            obj_type = rec.get("attributes", {}).get("type", "Unknown")
            output.append(f"- [{obj_type}] {rec.get('Name', rec.get('Id'))} (ID: {rec.get('Id')})")

        return f"Found {len(results['searchRecords'])} records:\n" + "\n".join(output)
    except Exception as e:
        return f"SOSL Error: {str(e)}"


def get_static_tools() -> list[BaseTool]:
    """Get all static Salesforce tools.

    Returns:
        List of schema-independent Salesforce tools.
    """
    return [
        salesforce_soql_query,
        salesforce_sosl_search,
    ]
