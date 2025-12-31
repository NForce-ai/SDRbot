"""Shared pytest fixtures and configuration."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def load_env():
    """Load .env file for tests that need real credentials."""
    import dotenv

    dotenv.load_dotenv(Path(__file__).parent.parent / ".env")


@pytest.fixture
def mock_hubspot_client():
    """Create a mock HubSpot client for unit tests."""
    mock_client = MagicMock()

    # Mock common API responses
    mock_client.crm.contacts.basic_api.get_page.return_value = MagicMock(
        results=[MagicMock(id="123", properties={"email": "test@example.com", "firstname": "Test"})]
    )

    mock_client.crm.pipelines.pipelines_api.get_all.return_value = MagicMock(
        results=[
            MagicMock(
                id="default",
                label="Sales Pipeline",
                stages=[MagicMock(id="stage1", label="Prospecting")],
            )
        ]
    )

    # Mock association schema
    mock_client.crm.associations.v4.schema.definitions_api.get_all.return_value = MagicMock(
        results=[MagicMock(category="HUBSPOT_DEFINED", type_id=1)]
    )

    return mock_client


@pytest.fixture
def patch_hubspot_client(mock_hubspot_client):
    """Patch get_client to return mock."""
    import sdrbot_cli.services.hubspot.tools as tools_module

    # Reset cached client before test
    original_client = tools_module._hs_client
    tools_module._hs_client = None

    with patch("sdrbot_cli.services.hubspot.tools.get_client", return_value=mock_hubspot_client):
        yield mock_hubspot_client

    # Restore after test
    tools_module._hs_client = original_client


@pytest.fixture
def real_hubspot_client():
    """Get real HubSpot client for integration tests.

    Skip if credentials not available.
    """
    pat = os.getenv("HUBSPOT_ACCESS_TOKEN")
    if not pat:
        pytest.skip("HUBSPOT_ACCESS_TOKEN not set - skipping integration test")

    from hubspot import HubSpot

    return HubSpot(access_token=pat)


class SimpleNamespace:
    """Simple object with attributes set from kwargs (JSON-serializable compatible)."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def mock_hubspot_admin_client():
    """Create a mock HubSpot client for admin tool unit tests."""
    mock_client = MagicMock()

    # Mock schemas API - use SimpleNamespace for JSON-serializable attributes
    schema_labels = SimpleNamespace(singular="Contact", plural="Contacts")
    schema_obj = SimpleNamespace(
        name="contacts",
        object_type_id="0-1",
        labels=schema_labels,
        primary_display_property="email",
        fully_qualified_name="contacts",
    )
    mock_client.crm.schemas.core_api.get_all.return_value = SimpleNamespace(results=[schema_obj])

    schema_detail = SimpleNamespace(
        name="contacts",
        object_type_id="0-1",
        labels=schema_labels,
        primary_display_property="email",
        secondary_display_properties=["firstname", "lastname"],
        required_properties=["email"],
        searchable_properties=["email", "firstname"],
        properties=[],
    )
    mock_client.crm.schemas.core_api.get_by_id.return_value = schema_detail
    mock_client.crm.schemas.core_api.create.return_value = SimpleNamespace(object_type_id="2-12345")

    # Mock properties API - use SimpleNamespace for JSON-serializable attributes
    email_mod_meta = SimpleNamespace(read_only_value=False)
    email_prop = SimpleNamespace(
        name="email",
        label="Email",
        type="string",
        field_type="text",
        group_name="contactinformation",
        hidden=False,
        modification_metadata=email_mod_meta,
        options=None,
        description="Contact email",
    )

    lead_status_options = [
        SimpleNamespace(value="new", label="New", hidden=False),
        SimpleNamespace(value="open", label="Open", hidden=False),
    ]
    lead_status_prop = SimpleNamespace(
        name="lead_status",
        label="Lead Status",
        type="enumeration",
        field_type="select",
        group_name="contactinformation",
        hidden=False,
        modification_metadata=email_mod_meta,
        options=lead_status_options,
        description="Lead status",
    )

    mock_client.crm.properties.core_api.get_all.return_value = SimpleNamespace(
        results=[email_prop, lead_status_prop]
    )

    email_prop_detail = SimpleNamespace(
        name="email",
        label="Email",
        type="string",
        field_type="text",
        description="Contact email",
        group_name="contactinformation",
        hidden=False,
        display_order=1,
        has_unique_value=True,
        form_field=True,
        modification_metadata=email_mod_meta,
        options=None,
    )
    mock_client.crm.properties.core_api.get_by_name.return_value = email_prop_detail
    mock_client.crm.properties.core_api.create.return_value = SimpleNamespace(name="custom_field")

    # Mock owners API - use SimpleNamespace for JSON-serializable attributes
    owner_teams = [SimpleNamespace(id="team1", name="Sales")]
    owner_obj = SimpleNamespace(
        id="123",
        user_id=123,
        email="owner@example.com",
        first_name="Test",
        last_name="Owner",
        teams=owner_teams,
    )
    mock_client.crm.owners.owners_api.get_page.return_value = SimpleNamespace(results=[owner_obj])

    # Mock notes API
    mock_client.crm.objects.notes.basic_api.create.return_value = MagicMock(id="note123")
    mock_client.crm.objects.notes.basic_api.get_by_id.return_value = MagicMock(
        id="note123",
        properties={
            "hs_note_body": "Test note",
            "hs_timestamp": "2024-01-01T00:00:00Z",
            "hubspot_owner_id": "123",
        },
    )

    # Mock tasks API
    mock_client.crm.objects.tasks.basic_api.create.return_value = MagicMock(id="task123")
    mock_client.crm.objects.tasks.basic_api.get_by_id.return_value = MagicMock(
        id="task123",
        properties={
            "hs_task_subject": "Test task",
            "hs_task_body": "Task body",
            "hs_task_status": "NOT_STARTED",
            "hs_task_priority": "HIGH",
            "hs_timestamp": "2024-01-01T00:00:00Z",
            "hubspot_owner_id": "123",
        },
    )

    # Mock generic objects API
    mock_client.crm.objects.basic_api.get_by_id.return_value = MagicMock(
        id="record123",
        properties={"name": "Test Record", "email": "test@example.com"},
    )
    mock_client.crm.objects.search_api.do_search.return_value = MagicMock(
        total=1,
        results=[MagicMock(id="record123", properties={"name": "Test Record"})],
    )

    # Mock associations API for notes/tasks listing
    mock_client.crm.associations.v4.basic_api.get_page.return_value = MagicMock(
        results=[MagicMock(to_object_id="note123")]
    )

    return mock_client


@pytest.fixture
def patch_hubspot_admin_client(mock_hubspot_admin_client):
    """Patch get_client for admin tools to return mock."""
    import sdrbot_cli.services.hubspot.admin_tools as admin_module

    original_client = admin_module._admin_client
    admin_module._admin_client = None

    with patch(
        "sdrbot_cli.services.hubspot.admin_tools.get_client",
        return_value=mock_hubspot_admin_client,
    ):
        yield mock_hubspot_admin_client

    admin_module._admin_client = original_client


@pytest.fixture
def mock_postgres_conn():
    """Create a mock PostgreSQL connection and cursor."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    return mock_conn, mock_cursor


@pytest.fixture
def patch_postgres_conn(mock_postgres_conn):
    """Patch psycopg2.connect to return mock."""
    mock_conn, _ = mock_postgres_conn
    with patch("psycopg2.connect", return_value=mock_conn):
        yield mock_postgres_conn


@pytest.fixture
def mock_mysql_conn():
    """Create a mock MySQL connection and cursor."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    # Mock 'open' property
    mock_conn.open = True
    return mock_conn, mock_cursor


@pytest.fixture
def patch_mysql_conn(mock_mysql_conn):
    """Patch pymysql.connect to return mock."""
    mock_conn, _ = mock_mysql_conn
    with patch("pymysql.connect", return_value=mock_conn):
        yield mock_mysql_conn


@pytest.fixture
def mock_twenty_client():
    """Create a mock Twenty client for unit tests."""
    mock_client = MagicMock()

    # Mock common API responses
    mock_client.get.return_value = {"data": []}
    mock_client.post.return_value = {"data": {"id": "mock-id"}}
    mock_client.patch.return_value = {"data": {}}
    mock_client.delete.return_value = {}

    return mock_client


@pytest.fixture
def patch_twenty_client(mock_twenty_client):
    """Patch TwentyClient to return mock."""
    import sdrbot_cli.services.twenty.tools as tools_module

    original_client = getattr(tools_module, "_twenty_client", None)
    tools_module._twenty_client = None

    with patch("sdrbot_cli.services.twenty.tools.TwentyClient", return_value=mock_twenty_client):
        yield mock_twenty_client

    tools_module._twenty_client = original_client


@pytest.fixture
def real_twenty_client():
    """Get real Twenty client for integration tests.

    Skip if credentials not available.
    """
    api_key = os.getenv("TWENTY_API_KEY")
    if not api_key:
        pytest.skip("TWENTY_API_KEY not set - skipping integration test")

    from sdrbot_cli.auth.twenty import TwentyClient

    return TwentyClient(api_key=api_key)


@pytest.fixture
def patch_mongo_db():
    """Patch get_mongo_db to return a mock database object."""
    mock_db = MagicMock()

    # Mock common MongoDB operations
    mock_db.list_collection_names.return_value = ["test_collection"]

    # Mock find().limit() chain
    mock_cursor = MagicMock()
    mock_cursor.limit.return_value = []  # Default to no results
    mock_db.__getitem__.return_value.find.return_value = mock_cursor

    mock_insert_result = MagicMock()
    mock_insert_result.inserted_id = "mock_insert_id"
    mock_db.__getitem__.return_value.insert_one.return_value = mock_insert_result

    mock_update_result = MagicMock()
    mock_update_result.matched_count = 0
    mock_update_result.modified_count = 0
    mock_db.__getitem__.return_value.update_many.return_value = mock_update_result

    mock_delete_result = MagicMock()
    mock_delete_result.deleted_count = 0
    mock_db.__getitem__.return_value.delete_many.return_value = mock_delete_result

    with patch("sdrbot_cli.services.mongodb.tools.get_mongo_db", return_value=mock_db):
        yield mock_db


@pytest.fixture
def mock_salesforce_admin_client():
    """Create a mock Salesforce client for admin tool unit tests."""
    mock_client = MagicMock()

    # Mock describe() for list_objects
    mock_client.describe.return_value = {
        "sobjects": [
            {
                "name": "Contact",
                "label": "Contact",
                "labelPlural": "Contacts",
                "keyPrefix": "003",
                "custom": False,
                "createable": True,
                "updateable": True,
                "queryable": True,
            },
            {
                "name": "Account",
                "label": "Account",
                "labelPlural": "Accounts",
                "keyPrefix": "001",
                "custom": False,
                "createable": True,
                "updateable": True,
                "queryable": True,
            },
            {
                "name": "Custom_Object__c",
                "label": "Custom Object",
                "labelPlural": "Custom Objects",
                "keyPrefix": "a01",
                "custom": True,
                "createable": True,
                "updateable": True,
                "queryable": True,
            },
        ]
    }

    # Mock restful() for get_object/get_field
    def mock_restful(path, method="GET", json=None):
        if "describe" in path:
            # Object describe
            return {
                "name": "Contact",
                "label": "Contact",
                "labelPlural": "Contacts",
                "keyPrefix": "003",
                "custom": False,
                "createable": True,
                "updateable": True,
                "queryable": True,
                "fields": [
                    {
                        "name": "Id",
                        "label": "Contact ID",
                        "type": "id",
                        "nillable": False,
                        "createable": False,
                        "updateable": False,
                        "custom": False,
                    },
                    {
                        "name": "FirstName",
                        "label": "First Name",
                        "type": "string",
                        "length": 40,
                        "nillable": True,
                        "createable": True,
                        "updateable": True,
                        "custom": False,
                    },
                    {
                        "name": "LastName",
                        "label": "Last Name",
                        "type": "string",
                        "length": 80,
                        "nillable": False,
                        "createable": True,
                        "updateable": True,
                        "custom": False,
                    },
                    {
                        "name": "Email",
                        "label": "Email",
                        "type": "email",
                        "nillable": True,
                        "createable": True,
                        "updateable": True,
                        "custom": False,
                    },
                    {
                        "name": "LeadSource",
                        "label": "Lead Source",
                        "type": "picklist",
                        "nillable": True,
                        "createable": True,
                        "updateable": True,
                        "custom": False,
                        "picklistValues": [
                            {"value": "Web", "label": "Web", "active": True},
                            {"value": "Phone", "label": "Phone Inquiry", "active": True},
                            {"value": "Referral", "label": "Partner Referral", "active": True},
                        ],
                    },
                    {
                        "name": "Custom_Field__c",
                        "label": "Custom Field",
                        "type": "string",
                        "length": 255,
                        "nillable": True,
                        "createable": True,
                        "updateable": True,
                        "custom": True,
                    },
                ],
                "recordTypeInfos": [],
            }
        elif "tooling/query" in path:
            # Tooling API query for field ID
            return {
                "records": [{"Id": "00N000000000001"}],
            }
        elif "tooling/sobjects/CustomField" in path:
            if method == "POST":
                return {"success": True, "id": "00N000000000002"}
            elif method == "PATCH":
                return None
            elif method == "DELETE":
                return None
        elif "sobjects/Note" in path:
            if method == "POST":
                return {"success": True, "id": "002000000000001"}
        elif "sobjects/Task" in path:
            if method == "POST":
                return {"success": True, "id": "00T000000000001"}
        elif "sobjects/" in path:
            # Get record
            return {
                "Id": "003000000000001",
                "Name": "Test Contact",
                "Email": "test@example.com",
                "attributes": {"type": "Contact"},
            }
        return {}

    mock_client.restful = MagicMock(side_effect=mock_restful)

    # Mock query() for users/notes/tasks
    def mock_query(soql):
        if "FROM User" in soql:
            return {
                "records": [
                    {
                        "Id": "005000000000001",
                        "Username": "user@example.com",
                        "Name": "Test User",
                        "Email": "user@example.com",
                        "Title": "Sales Rep",
                        "Department": "Sales",
                        "UserRole": {"Name": "Sales Manager"},
                        "Profile": {"Name": "Standard User"},
                        "IsActive": True,
                    }
                ]
            }
        elif "FROM Note" in soql:
            return {
                "records": [
                    {
                        "Id": "002000000000001",
                        "Title": "Test Note",
                        "Body": "Note body",
                        "CreatedDate": "2024-01-01T00:00:00.000Z",
                        "CreatedBy": {"Name": "Test User"},
                        "attributes": {"type": "Note"},
                    }
                ]
            }
        elif "FROM Task" in soql:
            return {
                "records": [
                    {
                        "Id": "00T000000000001",
                        "Subject": "Follow up",
                        "Description": "Call customer",
                        "Status": "Not Started",
                        "Priority": "Normal",
                        "ActivityDate": "2024-12-31",
                        "Owner": {"Name": "Test User"},
                        "CreatedDate": "2024-01-01T00:00:00.000Z",
                        "attributes": {"type": "Task"},
                    }
                ]
            }
        elif "FROM Contact" in soql or "FROM Account" in soql:
            return {
                "totalSize": 1,
                "records": [
                    {
                        "Id": "003000000000001",
                        "Name": "Test Record",
                        "CreatedDate": "2024-01-01T00:00:00.000Z",
                        "LastModifiedDate": "2024-01-01T00:00:00.000Z",
                        "attributes": {"type": "Contact"},
                    }
                ],
            }
        return {"records": []}

    mock_client.query = MagicMock(side_effect=mock_query)

    return mock_client


@pytest.fixture
def patch_salesforce_admin_client(mock_salesforce_admin_client):
    """Patch get_client for Salesforce admin tools to return mock."""
    import sdrbot_cli.services.salesforce.admin_tools as admin_module
    import sdrbot_cli.services.salesforce.tools as tools_module

    original_admin_client = admin_module._admin_client
    original_tools_client = tools_module._sf_client
    admin_module._admin_client = None
    tools_module._sf_client = None

    with (
        patch(
            "sdrbot_cli.services.salesforce.admin_tools.get_client",
            return_value=mock_salesforce_admin_client,
        ),
        patch(
            "sdrbot_cli.services.salesforce.tools.get_client",
            return_value=mock_salesforce_admin_client,
        ),
    ):
        yield mock_salesforce_admin_client

    admin_module._admin_client = original_admin_client
    tools_module._sf_client = original_tools_client
