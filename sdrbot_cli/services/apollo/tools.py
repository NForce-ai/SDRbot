"""Apollo.io prospecting and enrichment tools.

Apollo does not have user-specific schemas - all tools are static.
"""

import json

from langchain_core.tools import BaseTool, tool

from sdrbot_cli.auth.apollo import ApolloClient

_apollo_client = None


def get_apollo():
    """Get or create Apollo client instance."""
    global _apollo_client
    if _apollo_client is None:
        _apollo_client = ApolloClient()
    return _apollo_client


def reset_client():
    """Reset the cached client (useful after env reload)."""
    global _apollo_client
    _apollo_client = None


@tool
def apollo_enrich_person(
    email: str | None = None,
    linkedin_url: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    organization_name: str | None = None,
    domain: str | None = None,
    reveal_personal_emails: bool = False,
) -> str:
    """
    Enrich a person's data using Apollo.io.

    Provide as much information as possible for best match accuracy.
    At minimum, provide email OR (first_name + last_name + organization/domain).

    Args:
        email: The person's email address (best identifier).
        linkedin_url: The person's LinkedIn profile URL.
        first_name: The person's first name.
        last_name: The person's last name.
        organization_name: The company name where the person works.
        domain: The company's website domain (e.g., 'apollo.io').
        reveal_personal_emails: Include personal email addresses (consumes extra credits).

    Returns:
        Enriched person data including name, title, company, emails, and social profiles.
    """
    client = get_apollo()
    try:
        # Build request payload
        # Note: reveal_phone_number is not supported without webhook configuration
        params = {
            "reveal_personal_emails": reveal_personal_emails,
        }

        if email:
            params["email"] = email
        if linkedin_url:
            params["linkedin_url"] = linkedin_url
        if first_name:
            params["first_name"] = first_name
        if last_name:
            params["last_name"] = last_name
        if organization_name:
            params["organization_name"] = organization_name
        if domain:
            params["domain"] = domain

        # Check we have enough info
        has_email = email is not None
        has_linkedin = linkedin_url is not None
        has_name_and_company = first_name and last_name and (organization_name or domain)

        if not (has_email or has_linkedin or has_name_and_company):
            return (
                "Error: Provide email, LinkedIn URL, or (first_name + last_name + organization/domain) "
                "for person enrichment."
            )

        response = client.post("/people/match", json=params)
        person = response.get("person", {})

        if not person:
            return "No matching person found in Apollo database."

        # Format the response
        info = []

        name = (
            person.get("name")
            or f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()
        )
        if name:
            info.append(f"Name: {name}")

        if person.get("title"):
            info.append(f"Title: {person.get('title')}")

        if person.get("organization", {}).get("name"):
            org = person["organization"]
            org_info = org.get("name")
            if org.get("website_url"):
                org_info += f" ({org.get('website_url')})"
            info.append(f"Company: {org_info}")

        if person.get("email"):
            info.append(f"Email: {person.get('email')}")

        if person.get("personal_emails"):
            info.append(f"Personal Emails: {', '.join(person['personal_emails'][:3])}")

        if person.get("phone_numbers"):
            phones = [
                p.get("sanitized_number") or p.get("raw_number")
                for p in person["phone_numbers"][:3]
            ]
            info.append(f"Phones: {', '.join(filter(None, phones))}")

        if person.get("linkedin_url"):
            info.append(f"LinkedIn: {person.get('linkedin_url')}")

        if person.get("twitter_url"):
            info.append(f"Twitter: {person.get('twitter_url')}")

        if person.get("city") or person.get("state") or person.get("country"):
            location_parts = filter(
                None, [person.get("city"), person.get("state"), person.get("country")]
            )
            info.append(f"Location: {', '.join(location_parts)}")

        if person.get("seniority"):
            info.append(f"Seniority: {person.get('seniority')}")

        if person.get("departments"):
            info.append(f"Departments: {', '.join(person['departments'][:3])}")

        return "Apollo Person Enrichment:\n" + "\n".join(info)

    except Exception as e:
        return f"Error enriching person: {str(e)}"


@tool
def apollo_enrich_company(domain: str) -> str:
    """
    Enrich a company's data using Apollo.io.

    Args:
        domain: The company's website domain (e.g., 'apollo.io', 'openai.com').

    Returns:
        Company data including name, industry, size, funding, location, and social profiles.
    """
    client = get_apollo()
    try:
        response = client.post("/organizations/enrich", json={"domain": domain})
        org = response.get("organization", {})

        if not org:
            return f"No company found for domain: {domain}"

        info = []

        if org.get("name"):
            info.append(f"Name: {org.get('name')}")

        if org.get("website_url"):
            info.append(f"Website: {org.get('website_url')}")

        if org.get("primary_domain"):
            info.append(f"Domain: {org.get('primary_domain')}")

        if org.get("industry"):
            info.append(f"Industry: {org.get('industry')}")

        if org.get("estimated_num_employees"):
            info.append(f"Employees: {org.get('estimated_num_employees')}")

        if org.get("annual_revenue_printed"):
            info.append(f"Revenue: {org.get('annual_revenue_printed')}")

        if org.get("total_funding_printed"):
            info.append(f"Total Funding: {org.get('total_funding_printed')}")

        if org.get("latest_funding_round_date"):
            info.append(f"Latest Funding: {org.get('latest_funding_round_date')}")

        if org.get("founded_year"):
            info.append(f"Founded: {org.get('founded_year')}")

        # Location
        location_parts = filter(
            None,
            [
                org.get("city"),
                org.get("state"),
                org.get("country"),
            ],
        )
        location = ", ".join(location_parts)
        if location:
            info.append(f"Location: {location}")

        if org.get("linkedin_url"):
            info.append(f"LinkedIn: {org.get('linkedin_url')}")

        if org.get("twitter_url"):
            info.append(f"Twitter: {org.get('twitter_url')}")

        if org.get("facebook_url"):
            info.append(f"Facebook: {org.get('facebook_url')}")

        if org.get("short_description"):
            desc = org["short_description"][:300]
            if len(org["short_description"]) > 300:
                desc += "..."
            info.append(f"Description: {desc}")

        # Technologies
        if org.get("technologies"):
            techs = org["technologies"][:10]
            info.append(f"Technologies: {', '.join(techs)}")

        return "Apollo Company Enrichment:\n" + "\n".join(info)

    except Exception as e:
        return f"Error enriching company: {str(e)}"


@tool
def apollo_search_people(
    person_titles: str | None = None,
    person_seniorities: str | None = None,
    organization_domains: str | None = None,
    organization_names: str | None = None,
    organization_locations: str | None = None,
    person_locations: str | None = None,
    organization_num_employees_ranges: str | None = None,
    organization_keywords: str | None = None,
    limit: int = 10,
) -> str:
    """
    Search for people/prospects in Apollo's database.

    Note: This endpoint finds prospects but does NOT return emails/phones directly.
    Use apollo_enrich_person on results to get contact details.

    Args:
        person_titles: Comma-separated job titles (e.g., "CEO,CTO,VP Sales").
        person_seniorities: Comma-separated seniority levels (e.g., "c_suite,vp,director,manager").
        organization_domains: Comma-separated company domains (e.g., "apollo.io,openai.com").
        organization_names: Comma-separated company names (e.g., "Apollo,OpenAI").
        organization_locations: Comma-separated company HQ locations (e.g., "San Francisco,New York").
        person_locations: Comma-separated person locations (e.g., "California,Texas").
        organization_num_employees_ranges: Comma-separated employee ranges (e.g., "1,10;11,50;51,200").
        organization_keywords: Comma-separated industry/business keywords (e.g., "insurance,fintech,healthcare").
        limit: Maximum results to return (default 10, max 100).

    Returns:
        List of matching people with names, titles, and companies.
    """
    client = get_apollo()
    try:
        params = {
            "page": 1,
            "per_page": min(limit, 100),
        }

        # Parse comma-separated values into arrays
        if person_titles:
            params["person_titles"] = [t.strip() for t in person_titles.split(",")]

        if person_seniorities:
            params["person_seniorities"] = [s.strip() for s in person_seniorities.split(",")]

        if organization_domains:
            params["q_organization_domains"] = organization_domains

        if organization_names:
            params["organization_names"] = [n.strip() for n in organization_names.split(",")]

        if organization_locations:
            params["organization_locations"] = [
                loc.strip() for loc in organization_locations.split(",")
            ]

        if person_locations:
            params["person_locations"] = [loc.strip() for loc in person_locations.split(",")]

        if organization_num_employees_ranges:
            # Parse ranges like "1,10;11,50" into [{"min":1,"max":10},...]
            ranges = []
            for range_str in organization_num_employees_ranges.split(";"):
                parts = range_str.split(",")
                if len(parts) == 2:
                    ranges.append({"min": int(parts[0].strip()), "max": int(parts[1].strip())})
            if ranges:
                params["organization_num_employees_ranges"] = ranges

        if organization_keywords:
            params["q_organization_keyword_tags"] = [
                k.strip() for k in organization_keywords.split(",")
            ]

        response = client.post("/mixed_people/search", json=params)
        people = response.get("people", [])

        if not people:
            return "No people found matching your criteria. Try broadening your search."

        results = []
        for p in people:
            person_info = {
                "name": p.get("name"),
                "title": p.get("title"),
                "company": p.get("organization", {}).get("name"),
                "linkedin_url": p.get("linkedin_url"),
                "location": ", ".join(
                    filter(None, [p.get("city"), p.get("state"), p.get("country")])
                ),
            }
            results.append(person_info)

        output = f"Found {len(results)} people:\n"
        output += json.dumps(results, indent=2)
        output += "\n\nNote: Use apollo_enrich_person with LinkedIn URL to get email/phone."

        return output

    except Exception as e:
        return f"Error searching people: {str(e)}"


@tool
def apollo_search_companies(
    organization_domains: str | None = None,
    organization_names: str | None = None,
    organization_locations: str | None = None,
    organization_num_employees_ranges: str | None = None,
    organization_keywords: str | None = None,
    limit: int = 10,
) -> str:
    """
    Search for companies in Apollo's database.

    Args:
        organization_domains: Comma-separated domains to search (e.g., "apollo.io,openai.com").
        organization_names: Comma-separated company names (e.g., "Apollo,OpenAI").
        organization_locations: Comma-separated HQ locations (e.g., "San Francisco,New York").
        organization_num_employees_ranges: Employee count ranges (e.g., "1,10;11,50;51,200").
        organization_keywords: Comma-separated industry/business keywords (e.g., "insurance,fintech,healthcare").
        limit: Maximum results to return (default 10, max 100).

    Returns:
        List of matching companies with basic info.
    """
    client = get_apollo()
    try:
        params = {
            "page": 1,
            "per_page": min(limit, 100),
        }

        if organization_domains:
            params["q_organization_domains"] = organization_domains

        if organization_names:
            params["organization_names"] = [n.strip() for n in organization_names.split(",")]

        if organization_locations:
            params["organization_locations"] = [
                loc.strip() for loc in organization_locations.split(",")
            ]

        if organization_num_employees_ranges:
            ranges = []
            for range_str in organization_num_employees_ranges.split(";"):
                parts = range_str.split(",")
                if len(parts) == 2:
                    ranges.append({"min": int(parts[0].strip()), "max": int(parts[1].strip())})
            if ranges:
                params["organization_num_employees_ranges"] = ranges

        if organization_keywords:
            params["q_organization_keyword_tags"] = [
                k.strip() for k in organization_keywords.split(",")
            ]

        response = client.post("/mixed_companies/search", json=params)
        organizations = response.get("organizations", [])

        if not organizations:
            return "No companies found matching your criteria. Try broadening your search."

        results = []
        for org in organizations:
            company_info = {
                "name": org.get("name"),
                "domain": org.get("primary_domain"),
                "industry": org.get("industry"),
                "employees": org.get("estimated_num_employees"),
                "location": ", ".join(
                    filter(None, [org.get("city"), org.get("state"), org.get("country")])
                ),
                "linkedin_url": org.get("linkedin_url"),
            }
            results.append(company_info)

        output = f"Found {len(results)} companies:\n"
        output += json.dumps(results, indent=2)

        return output

    except Exception as e:
        return f"Error searching companies: {str(e)}"


def get_static_tools() -> list[BaseTool]:
    """Get all Apollo tools.

    Returns:
        List of Apollo tools (all static, no generated tools).
    """
    return [
        apollo_enrich_person,
        apollo_enrich_company,
        apollo_search_people,
        apollo_search_companies,
    ]
