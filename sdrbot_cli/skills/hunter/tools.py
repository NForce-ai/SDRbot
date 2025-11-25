"""Hunter.io prospecting and verification tools."""

import json
from langchain_core.tools import tool
from sdrbot_cli.auth.hunter import HunterClient

_hunter_client = None

def get_hunter():
    global _hunter_client
    if _hunter_client is None:
        _hunter_client = HunterClient()
    return _hunter_client

@tool
def hunter_domain_search(domain: str, limit: int = 10, department: str = None) -> str:
    """
    Search for email addresses found on the internet for a given domain.
    
    Args:
        domain: The domain name to search (e.g., 'stripe.com').
        limit: The maximum number of emails to return (default 10).
        department: Optional. Filter by department (e.g., 'executive', 'it', 'sales', 'marketing', 'support', 'communication', 'finance', 'hr', 'legal').
    """
    client = get_hunter()
    try:
        params = {"domain": domain, "limit": limit}
        if department:
            params["department"] = department
            
        data = client.request("GET", "/domain-search", params=params)
        
        if not data.get("data"):
             return f"No data returned for domain: {domain}"

        res = data["data"]
        
        emails = res.get("emails", [])
        if not emails:
            return f"No emails found for {domain}."
            
        output = [f"Domain Search Results for {domain} ({len(emails)} found):"]
        for e in emails:
            output.append(f"- {e.get('value')} ({e.get('type')}) - {e.get('first_name')} {e.get('last_name')} - {e.get('position')}")
            
        return "\n".join(output)
        
    except Exception as e:
        return f"Error searching domain: {str(e)}"

@tool
def hunter_email_finder(domain: str, first_name: str, last_name: str) -> str:
    """
    Find the email address of a person by their name and company domain.
    
    Args:
        domain: The company domain (e.g., 'openai.com').
        first_name: The person's first name.
        last_name: The person's last name.
    """
    client = get_hunter()
    try:
        params = {
            "domain": domain,
            "first_name": first_name,
            "last_name": last_name
        }
        
        data = client.request("GET", "/email-finder", params=params)
        
        if not data.get("data"):
            return "No email found."
            
        res = data["data"]
        email = res.get("email")
        score = res.get("score")
        
        if email:
            return f"Found email: {email} (Confidence: {score}%)"
        else:
            return "Email not found."

    except Exception as e:
        return f"Error finding email: {str(e)}"

@tool
def hunter_email_verifier(email: str) -> str:
    """
    Verify the deliverability of an email address.
    
    Args:
        email: The email address to verify.
    """
    client = get_hunter()
    try:
        params = {"email": email}
        data = client.request("GET", "/email-verifier", params=params)
        
        if not data.get("data"):
             return "No verification data returned."
             
        res = data["data"]
        status = res.get("status") # 'valid', 'invalid', 'accept_all', 'webmail', 'disposable', 'unknown'
        score = res.get("score")
        
        return f"Verification Result for {email}:\nStatus: {status}\nScore: {score}%"
        
    except Exception as e:
        return f"Error verifying email: {str(e)}"
