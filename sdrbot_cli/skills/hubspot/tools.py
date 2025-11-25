"""HubSpot dynamic discovery tools."""

import json
from typing import Optional, Dict, Any, List
from langchain_core.tools import tool
from hubspot.crm.objects import (
    PublicObjectSearchRequest, 
    SimplePublicObjectInput, 
    SimplePublicObjectInputForCreate
)
from hubspot.crm.schemas import ObjectSchema

from sdrbot_cli.auth.hubspot import get_client
from sdrbot_cli.config import console, COLORS

# Shared client instance (lazy loaded)
_hs_client = None

def get_hs():
    global _hs_client
    if _hs_client is None:
        _hs_client = get_client()
    return _hs_client


@tool
def hubspot_list_object_types() -> str:
    """
    List all available HubSpot object types (Standard and Custom).
    Use this to find the internal name of an object (e.g., 'contacts', 'companies', '2-12345').
    """
    hs = get_hs()
    try:
        # Get all schemas
        response = hs.crm.schemas.core_api.get_all()
        results = response.results
        
        output = []
        for schema in results:
            output.append(f"Name: {schema.name} (Object Type ID: {schema.object_type_id}) - Label: {schema.labels.singular}")
            
        return "Available HubSpot Objects:\n" + "\n".join(output)
    except Exception as e:
        return f"Error listing objects: {str(e)}"


@tool
def hubspot_describe_object(object_type: str) -> str:
    """
    Get the properties/fields for a specific HubSpot object.
    ALWAYS call this before creating or updating to know the correct property names (e.g. 'firstname' vs 'first_name').
    
    Args:
        object_type: The object type string (e.g., "contacts", "companies", or a custom object ID)
    """
    hs = get_hs()
    try:
        # We need to fetch properties for this object type.
        # The CRM Schemas API gives us the definition, but for the actual properties list 
        # (including default properties like email, firstname), we might need the Properties API.
        
        # Method 1: CRM Properties API
        response = hs.crm.properties.core_api.get_all(object_type=object_type)
        results = response.results
        
        props = []
        for p in results:
            # Filter for relevant properties to save tokens (not showing hidden/read-only system props if possible)
            if not p.hidden:
                props.append(f"- {p.name} ({p.type}): {p.label} {'[REQUIRED]' if p.form_field else ''}")
        
        # Truncate if too long (Contacts can have hundreds of props)
        if len(props) > 100:
             return f"Schema for {object_type} (First 100 properties):\n" + "\n".join(props[:100]) + "\n... (more properties exist)"
             
        return f"Schema for {object_type}:\n" + "\n".join(props)

    except Exception as e:
        return f"Error describing object {object_type}: {str(e)}"


@tool
def hubspot_search_objects(object_type: str, filter_groups_json: str = None, query_string: str = None) -> str:
    """
    Search for objects in HubSpot. 
    You can provide EITHER a simple `query_string` (fuzzy match) OR a `filter_groups_json` for precise filtering.
    
    Args:
        object_type: e.g., "contacts", "deals"
        query_string: Simple text search (e.g. "John Doe")
        filter_groups_json: Advanced JSON filter. 
           Example: '[{"filters": [{"propertyName": "email", "operator": "EQ", "value": "test@example.com"}]}]'
    """
    hs = get_hs()
    try:
        search_request = PublicObjectSearchRequest()
        
        if filter_groups_json:
            search_request.filter_groups = json.loads(filter_groups_json)
        elif query_string:
            search_request.query = query_string
        else:
             # Default to recent items if nothing provided? Or error?
             return "Error: Must provide either query_string or filter_groups_json"

        # Limit fields to save tokens, but ensure we get displayable info
        search_request.limit = 10
        # We generally want name, email, subject, amount depending on object, but we don't know the object.
        # We'll rely on default properties returned or ask for common ones.
        search_request.properties = ["firstname", "lastname", "email", "name", "subject", "amount", "dealstage"]

        response = hs.crm.objects.search_api.do_search(object_type=object_type, public_object_search_request=search_request)
        
        results = response.results
        if not results:
            return "No records found."
            
        clean_results = []
        for res in results:
            clean_results.append({
                "id": res.id,
                "properties": res.properties
            })
            
        return f"Found {response.total} records. Top 10:\n{json.dumps(clean_results, indent=2)}"
        
    except Exception as e:
        return f"Error searching objects: {str(e)}"


@tool
def hubspot_create_object(object_type: str, properties_json: str) -> str:
    """
    Create a new object in HubSpot.
    
    Args:
        object_type: e.g. "contacts", "companies"
        properties_json: JSON string of properties. e.g. '{"email": "john@doe.com", "firstname": "John"}'
    """
    hs = get_hs()
    try:
        props = json.loads(properties_json)
        # Fix: Use SimplePublicObjectInputForCreate and correct argument name
        simple_public_object_input_for_create = SimplePublicObjectInputForCreate(properties=props, associations=[])
        
        response = hs.crm.objects.basic_api.create(
            object_type=object_type,
            simple_public_object_input_for_create=simple_public_object_input_for_create
        )
        
        return f"Successfully created {object_type} with ID: {response.id}\nProperties: {response.properties}"
    except Exception as e:
        return f"Error creating object: {str(e)}"


@tool
def hubspot_update_object(object_type: str, object_id: str, properties_json: str) -> str:
    """
    Update an existing object in HubSpot.
    
    Args:
        object_type: e.g. "contacts"
        object_id: The ID of the record
        properties_json: JSON string of properties to update.
    """
    hs = get_hs()
    try:
        props = json.loads(properties_json)
        simple_public_object_input = SimplePublicObjectInput(properties=props)
        
        response = hs.crm.objects.basic_api.update(
            object_type=object_type,
            object_id=object_id,
            simple_public_object_input=simple_public_object_input
        )
        
        return f"Successfully updated {object_type} ({object_id}).\nNew Properties: {response.properties}"
    except Exception as e:
        return f"Error updating object: {str(e)}"
