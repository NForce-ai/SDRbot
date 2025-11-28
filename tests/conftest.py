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
