"""Lusha prospecting and enrichment tools.

Lusha does not have user-specific schemas - all tools are static.
"""

import json

from langchain_core.tools import BaseTool, tool

from sdrbot_cli.auth.lusha import LushaClient

_lusha_client = None


def get_lusha():
    """Get or create Lusha client instance."""
    global _lusha_client
    if _lusha_client is None:
        _lusha_client = LushaClient()
    return _lusha_client


@tool
def lusha_enrich_person(linkedin_url: str = None, email: str = None) -> str:
    """
    Get contact details (email, phone) for a person using Lusha.
    Provide EITHER a LinkedIn URL OR an Email address.

    Args:
        linkedin_url: The person's LinkedIn profile URL.
        email: The person's business email.
    """
    client = get_lusha()
    try:
        params = {}
        if linkedin_url:
            params["linkedinUrl"] = linkedin_url
        elif email:
            params["email"] = email
        else:
            return "Error: Must provide either linkedin_url or email."

        data = client.request("GET", "/person/enrich", params=params)

        if not data.get("data"):
            return "No data found for this person."

        p = data["data"]

        # Format key info
        info = [f"Name: {p.get('fullName')}"]

        emails = p.get("emailAddresses", [])
        if emails:
            info.append(f"Emails: {', '.join([e['email'] for e in emails[:3]])}")

        phones = p.get("phoneNumbers", [])
        if phones:
            info.append(f"Phones: {', '.join([ph['internationalNumber'] for ph in phones[:3]])}")

        job = p.get("jobTitle")
        company = p.get("company", {}).get("name")
        if job and company:
            info.append(f"Role: {job} at {company}")

        return "Lusha Enrichment Result:\n" + "\n".join(info)

    except Exception as e:
        return f"Error enriching person: {str(e)}"


@tool
def lusha_enrich_company(domain: str) -> str:
    """
    Get firmographic data for a company using Lusha.

    Args:
        domain: Company website domain (e.g. 'openai.com')
    """
    client = get_lusha()
    try:
        params = {"domain": domain}
        data = client.request("GET", "/company/enrich", params=params)

        if not data.get("data"):
            return "No data found for this company."

        c = data["data"]

        info = [
            f"Name: {c.get('name')}",
            f"Industry: {c.get('industryPrimaryGroup')}",
            f"Employees: {c.get('employeesSize')}",
            f"Revenue: {c.get('revenueRange')}",
            f"LinkedIn: {c.get('social', {}).get('linkedin')}",
        ]

        description = c.get("description", "")
        if description:
            info.append(f"Description: {description[:200]}...")

        return "Lusha Company Profile:\n" + "\n".join(info)

    except Exception as e:
        return f"Error enriching company: {str(e)}"


@tool
def lusha_prospect(filters_json: str) -> str:
    """
    Find prospects (people) based on criteria.

    Args:
        filters_json: JSON string of filters.
        Available filters:
        - jobTitle (list): e.g. ["CEO", "VP Sales"]
        - companyName (str)
        - country (str): e.g. "US"
        - industry (str)

        Example: '{"jobTitle": ["CTO"], "companyName": "Google"}'
    """
    client = get_lusha()
    try:
        filters = json.loads(filters_json)
        payload = {"filters": filters, "limit": 10}

        data = client.request("POST", "/prospecting/search", json=payload)

        contacts = data.get("data", {}).get("contacts", [])
        if not contacts:
            return "No prospects found matching criteria."

        results = []
        for c in contacts:
            results.append(
                {
                    "name": c.get("fullName"),
                    "title": c.get("jobTitle"),
                    "company": c.get("company", {}).get("name"),
                    "linkedin": c.get("social", {}).get("linkedin"),
                }
            )

        return f"Found {len(results)} prospects:\n{json.dumps(results, indent=2)}"

    except Exception as e:
        return f"Error searching prospects: {str(e)}"


def get_static_tools() -> list[BaseTool]:
    """Get all Lusha tools.

    Returns:
        List of Lusha tools (all static, no generated tools).
    """
    return [
        lusha_enrich_person,
        lusha_enrich_company,
        lusha_prospect,
    ]
