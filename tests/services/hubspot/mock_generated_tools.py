from langchain_core.tools import StructuredTool


def mock_get_client():
    from hubspot import HubSpot

    return HubSpot()


def mock_search_contacts(limit: int = 10, **kwargs):
    return f"Found {limit} contacts"


def mock_create_contact(email: str = None, firstname: str = None, lastname: str = None, **kwargs):
    if not any([email, firstname, lastname]):
        return "Error: At least one property must be provided"
    return "Successfully created contact with ID: 456"


hubspot_search_contacts = StructuredTool.from_function(
    func=mock_search_contacts, name="hubspot_search_contacts", description="Search contacts"
)

hubspot_create_contact = StructuredTool.from_function(
    func=mock_create_contact, name="hubspot_create_contact", description="Create contact"
)
