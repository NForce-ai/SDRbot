"""Attio dynamic discovery tools."""

import json
from typing import Optional
from langchain_core.tools import tool
from sdrbot_cli.auth.attio import AttioClient
from sdrbot_cli.config import console, COLORS

# Shared client instance
_attio_client = None

def get_attio():
    global _attio_client
    if _attio_client is None:
        _attio_client = AttioClient()
    return _attio_client

@tool
def attio_list_objects() -> str:
    """
    List all available Attio objects (Standard and Custom).
    Use this to find the 'api_slug' of an object (e.g. 'people', 'companies', 'dealflow').
    """
    client = get_attio()
    try:
        data = client.request("GET", "/objects")
        objects = data.get("data", [])
        
        output = []
        for obj in objects:
            output.append(f"Name: {obj['singular_noun']} (Slug: {obj['api_slug']})")
            
        return "Available Attio Objects:\n" + "\n".join(output)
    except Exception as e:
        return f"Error listing objects: {str(e)}"

@tool
def attio_describe_object(object_slug: str) -> str:
    """
    Get the attributes (schema) for a specific Attio object.
    ALWAYS call this before creating/updating to know attribute slugs and types.
    
    Args:
        object_slug: The api_slug of the object (e.g. "people", "companies")
    """
    client = get_attio()
    try:
        data = client.request("GET", f"/objects/{object_slug}/attributes")
        attributes = data.get("data", [])
        
        output = []
        for attr in attributes:
            if attr['status'] == 'active':
                line = f"- {attr['api_slug']} ({attr['type']}): {attr['title']}"
                if attr['is_required']:
                    line += " [REQUIRED]"
                if attr['type'] == 'select':
                     options = [o['title'] for o in attr.get('config', {}).get('currency', {}).get('options', [])][:5] # Select config varies
                     # Actually select options are in 'config.select.options'
                     select_opts = attr.get('config', {}).get('select', {}).get('options', [])
                     if select_opts:
                         opts = [o['title'] for o in select_opts][:5]
                         line += f" Options: {opts}..."
                output.append(line)
            
        return f"Schema for {object_slug}:\n" + "\n".join(output)
    except Exception as e:
        return f"Error describing object: {str(e)}"

@tool
def attio_query_records(object_slug: str, filter_json: str = None, limit: int = 10) -> str:
    """
    Search/Filter records in Attio.
    
    Args:
        object_slug: e.g. "people"
        filter_json: Optional JSON string for filtering. 
                     Example: '{"$and": [{"email_addresses": {"$contains": "john"}}]}'
                     If None, returns recent records.
        limit: Max records to return (default 10).
    """
    client = get_attio()
    try:
        payload = {"limit": limit}
        if filter_json:
            payload["filter"] = json.loads(filter_json)
            
        # If no filter, we might just want to list, but the /query endpoint works for both?
        # V2 uses POST /objects/{slug}/records/query
        
        data = client.request("POST", f"/objects/{object_slug}/records/query", json=payload)
        records = data.get("data", [])
        
        if not records:
            return "No records found."
            
        # Clean up output
        clean_records = []
        for rec in records:
            # Flatten values for display
            simple_vals = {"id": rec["id"]["record_id"]}
            for slug, values in rec["values"].items():
                 # Attio values are lists of dicts usually
                 simple_vals[slug] = values
            clean_records.append(simple_vals)
            
        return f"Found {len(records)} records:\n{json.dumps(clean_records, indent=2)}"
    except Exception as e:
        return f"Error querying records: {str(e)}"

@tool
def attio_create_record(object_slug: str, values_json: str) -> str:
    """
    Create a new record in Attio.
    
    Args:
        object_slug: e.g. "people"
        values_json: JSON string of attribute values.
                     Attio expects specific formats per type.
                     Simple Text: {"name": "John"} -> automatic conversion? 
                     NO, Attio API requires strict value formats usually, but let's try to map simple ones if possible?
                     Actually, V2 API values are like:
                     "email_addresses": [{"email_address": "..."}]
                     The agent must infer this from `describe_object` or the user must provide correct JSON.
    """
    client = get_attio()
    try:
        values = json.loads(values_json)
        payload = {"data": {"values": values}}
        
        data = client.request("POST", f"/objects/{object_slug}/records", json=payload)
        rec = data.get("data", {})
        
        return f"Successfully created record ID: {rec.get('id', {}).get('record_id')}"
    except Exception as e:
        return f"Error creating record: {str(e)}"

@tool
def attio_update_record(object_slug: str, record_id: str, values_json: str) -> str:
    """
    Update a record in Attio.
    
    Args:
        object_slug: e.g. "people"
        record_id: The UUID of the record
        values_json: JSON string of values to update.
    """
    client = get_attio()
    try:
        values = json.loads(values_json)
        payload = {"data": {"values": values}}
        
        data = client.request("PATCH", f"/objects/{object_slug}/records/{record_id}", json=payload)
        rec = data.get("data", {})
        
        return f"Successfully updated record ID: {rec.get('id', {}).get('record_id')}"
    except Exception as e:
        return f"Error updating record: {str(e)}"
