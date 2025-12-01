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
