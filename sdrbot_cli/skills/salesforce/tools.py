"""Salesforce dynamic discovery tools."""

from typing import Optional, List, Dict, Any
from langchain_core.tools import tool
from sdrbot_cli.auth.salesforce import get_client
from sdrbot_cli.config import console, COLORS

# Shared client instance (lazy loaded)
_sf_client = None

def get_sf():
    global _sf_client
    if _sf_client is None:
        _sf_client = get_client()
    return _sf_client


@tool
def list_objects(query: str) -> str:
    """
    Search for available Salesforce objects by name. 
    Use this to find the correct API name for an object (e.g., finding that 'Commission' is 'Commission__c').
    
    Args:
        query: Search string (e.g., "commission", "user", "opportunity")
    """
    sf = get_sf()
    # describeGlobal returns a list of all objects
    desc = sf.describe()
    
    matches = []
    query_lower = query.lower()
    
    for obj in desc['sobjects']:
        if query_lower in obj['name'].lower() or query_lower in obj['label'].lower():
            matches.append(f"{obj['name']} (Label: {obj['label']})")
            
    if not matches:
        return f"No objects found matching '{query}'."
    
    # Limit results to avoid token overflow
    return "Found Objects:\n" + "\n".join(matches[:20])


@tool
def describe_object(object_name: str) -> str:
    """
    Get the schema definition for a specific Salesforce object.
    ALWAYS call this before creating or updating records to ensure you have the correct field names and types.
    
    Args:
        object_name: The API name of the object (e.g., "Account", "Commission__c")
    """
    sf = get_sf()
    try:
        desc = sf.restful(f"sobjects/{object_name}/describe")
        
        fields_info = []
        for field in desc['fields']:
            field_str = f"- {field['name']} ({field['type']})"
            if field['label'] != field['name']:
                field_str += f" Label: '{field['label']}'"
            if not field['nillable'] and not field['defaultedOnCreate']:
                field_str += " [REQUIRED]"
            if field['type'] == 'reference':
                field_str += f" -> References: {field['referenceTo']}"
            if field['type'] == 'picklist':
                values = [p['value'] for p in field['picklistValues'] if p['active']][:5]
                field_str += f" Values: {values}..."
                
            fields_info.append(field_str)
            
        return f"Schema for {object_name}:\n" + "\n".join(fields_info)
    except Exception as e:
        return f"Error describing object {object_name}: {str(e)}"


@tool
def soql_query(query: str) -> str:
    """
    Execute a SOQL query against Salesforce.
    Use this to find records, IDs, or check existence.
    Example: "SELECT Id, Name, Email FROM Contact WHERE Name LIKE 'John%'"
    """
    sf = get_sf()
    try:
        # Sanity check: prevent destructive queries if model hallucinates SOSL or something
        if not query.strip().upper().startswith("SELECT"):
            return "Error: Only SELECT queries are allowed via this tool."
            
        results = sf.query(query)
        
        records = results.get('records', [])
        if not records:
            return "Query returned 0 records."
            
        # Clean up attributes metadata to save tokens
        clean_records = []
        for rec in records:
            if 'attributes' in rec:
                del rec['attributes']
            clean_records.append(rec)
            
        return f"Query returned {results['totalSize']} records. First {len(clean_records)}:\n{json.dumps(clean_records, indent=2)}"
    except Exception as e:
        return f"SOQL Error: {str(e)}"


import json

@tool
def create_record(object_name: str, data: str) -> str:
    """
    Create a new record in Salesforce.
    
    Args:
        object_name: API name of the object (e.g., "Lead", "Commission__c")
        data: JSON string of field-value pairs (e.g., '{"FirstName": "John", "LastName": "Doe"}')
    """
    sf = get_sf()
    try:
        record_data = json.loads(data)
        result = sf.restful(f"sobjects/{object_name}", method='POST', json=record_data)
        
        if result.get('success'):
            return f"Successfully created {object_name} with ID: {result['id']}"
        else:
            return f"Failed to create record. Response: {result}"
    except Exception as e:
        return f"Error creating record: {str(e)}"

@tool
def update_record(object_name: str, record_id: str, data: str) -> str:
    """
    Update an existing Salesforce record.
    
    Args:
        object_name: API name (e.g. "Account")
        record_id: The Salesforce ID (15 or 18 char)
        data: JSON string of fields to update
    """
    sf = get_sf()
    try:
        record_data = json.loads(data)
        # simple-salesforce update method returns status code 204 on success
        sf.restful(f"sobjects/{object_name}/{record_id}", method='PATCH', json=record_data)
        return f"Successfully updated {object_name} ({record_id})"
    except Exception as e:
        return f"Error updating record: {str(e)}"
