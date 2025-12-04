"""Tests for connection testing functions."""

from unittest.mock import MagicMock, patch

import httpx

# Rename imports to avoid pytest picking them up as test functions
from sdrbot_cli.tui.setup_screens import (
    test_azure_endpoint as _test_azure_endpoint,
)
from sdrbot_cli.tui.setup_screens import (
    test_bedrock_credentials as _test_bedrock_credentials,
)
from sdrbot_cli.tui.setup_screens import (
    test_openai_compatible_endpoint as _test_openai_compatible_endpoint,
)


class TestOpenAICompatibleEndpoint:
    """Tests for test_openai_compatible_endpoint function."""

    def test_success_returns_none(self):
        """Test that successful connection returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.get", return_value=mock_response):
            result = _test_openai_compatible_endpoint("http://localhost:11434/v1", "test-key")
            assert result is None

    def test_401_returns_auth_error(self):
        """Test that 401 returns authentication error message."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("httpx.get", return_value=mock_response):
            result = _test_openai_compatible_endpoint("http://localhost:11434/v1", "bad-key")
            assert result == "Authentication failed - check your API key"

    def test_404_accepted_as_success(self):
        """Test that 404 is accepted (some servers don't implement /models)."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.get", return_value=mock_response):
            result = _test_openai_compatible_endpoint("http://localhost:11434/v1", "test-key")
            assert result is None

    def test_500_returns_error_message(self):
        """Test that server errors return error message."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("httpx.get", return_value=mock_response):
            result = _test_openai_compatible_endpoint("http://localhost:11434/v1", "test-key")
            assert result == "Server returned error 500"

    def test_connect_error_returns_message(self):
        """Test that connection errors return helpful message."""
        with patch("httpx.get", side_effect=httpx.ConnectError("Connection refused")):
            result = _test_openai_compatible_endpoint("http://localhost:11434/v1", "test-key")
            assert result == "Cannot connect to server - is it running?"

    def test_timeout_returns_message(self):
        """Test that timeout returns helpful message."""
        with patch("httpx.get", side_effect=httpx.TimeoutException("Timeout")):
            result = _test_openai_compatible_endpoint("http://localhost:11434/v1", "test-key")
            assert result == "Connection timed out"

    def test_generic_exception_returns_message(self):
        """Test that generic exceptions return error message."""
        with patch("httpx.get", side_effect=Exception("Something went wrong")):
            result = _test_openai_compatible_endpoint("http://localhost:11434/v1", "test-key")
            assert "Connection error" in result
            assert "Something went wrong" in result

    def test_url_trailing_slash_handled(self):
        """Test that trailing slashes in URL are handled correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.get", return_value=mock_response) as mock_get:
            _test_openai_compatible_endpoint("http://localhost:11434/v1/", "test-key")
            # Should not have double slashes
            call_url = mock_get.call_args[0][0]
            assert "//" not in call_url.replace("http://", "")


class TestAzureEndpoint:
    """Tests for test_azure_endpoint function."""

    def test_success_returns_none(self):
        """Test that successful connection returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.get", return_value=mock_response):
            result = _test_azure_endpoint(
                "https://myresource.openai.azure.com",
                "my-deployment",
                "2024-02-01",
                "test-key",
            )
            assert result is None

    def test_401_returns_auth_error(self):
        """Test that 401 returns authentication error message."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("httpx.get", return_value=mock_response):
            result = _test_azure_endpoint(
                "https://myresource.openai.azure.com",
                "my-deployment",
                "2024-02-01",
                "bad-key",
            )
            assert result == "Authentication failed - check your API key"

    def test_404_returns_deployment_error(self):
        """Test that 404 returns deployment not found message."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.get", return_value=mock_response):
            result = _test_azure_endpoint(
                "https://myresource.openai.azure.com",
                "wrong-deployment",
                "2024-02-01",
                "test-key",
            )
            assert result == "Deployment not found - check deployment name"

    def test_other_status_codes_accepted(self):
        """Test that other status codes are accepted (Azure endpoints vary)."""
        mock_response = MagicMock()
        mock_response.status_code = 403  # Some Azure configs return this

        with patch("httpx.get", return_value=mock_response):
            result = _test_azure_endpoint(
                "https://myresource.openai.azure.com",
                "my-deployment",
                "2024-02-01",
                "test-key",
            )
            assert result is None

    def test_connect_error_returns_message(self):
        """Test that connection errors return helpful message."""
        with patch("httpx.get", side_effect=httpx.ConnectError("Connection refused")):
            result = _test_azure_endpoint(
                "https://myresource.openai.azure.com",
                "my-deployment",
                "2024-02-01",
                "test-key",
            )
            assert result == "Cannot connect to Azure endpoint"

    def test_timeout_returns_message(self):
        """Test that timeout returns helpful message."""
        with patch("httpx.get", side_effect=httpx.TimeoutException("Timeout")):
            result = _test_azure_endpoint(
                "https://myresource.openai.azure.com",
                "my-deployment",
                "2024-02-01",
                "test-key",
            )
            assert result == "Connection timed out"

    def test_correct_url_format(self):
        """Test that the URL is constructed correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.get", return_value=mock_response) as mock_get:
            _test_azure_endpoint(
                "https://myresource.openai.azure.com",
                "my-deployment",
                "2024-02-01",
                "test-key",
            )
            call_url = mock_get.call_args[0][0]
            assert "openai/deployments/my-deployment/models" in call_url
            assert "api-version=2024-02-01" in call_url

    def test_api_key_header(self):
        """Test that api-key header is set correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.get", return_value=mock_response) as mock_get:
            _test_azure_endpoint(
                "https://myresource.openai.azure.com",
                "my-deployment",
                "2024-02-01",
                "my-secret-key",
            )
            headers = mock_get.call_args[1]["headers"]
            assert headers["api-key"] == "my-secret-key"


class TestBedrockCredentials:
    """Tests for test_bedrock_credentials function."""

    def test_success_returns_none(self):
        """Test that successful connection returns None."""
        mock_client = MagicMock()
        mock_client.list_foundation_models.return_value = {"modelSummaries": []}

        with patch("boto3.client", return_value=mock_client):
            result = _test_bedrock_credentials("us-east-1")
            assert result is None

    def test_no_credentials_error(self):
        """Test that missing credentials return helpful message."""
        from botocore.exceptions import NoCredentialsError

        with patch("boto3.client", side_effect=NoCredentialsError()):
            result = _test_bedrock_credentials("us-east-1")
            assert result == "AWS credentials not found or invalid"

    def test_access_denied_error(self):
        """Test that access denied returns IAM permissions message."""
        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}}
        with patch(
            "boto3.client",
            side_effect=ClientError(error_response, "ListFoundationModels"),
        ):
            result = _test_bedrock_credentials("us-east-1")
            assert result == "Access denied - check IAM permissions for Bedrock"

    def test_unrecognized_client_error(self):
        """Test that invalid credentials return appropriate message."""
        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "UnrecognizedClientException", "Message": "Bad creds"}}
        with patch(
            "boto3.client",
            side_effect=ClientError(error_response, "ListFoundationModels"),
        ):
            result = _test_bedrock_credentials("us-east-1")
            assert result == "Invalid AWS credentials"

    def test_other_client_error(self):
        """Test that other AWS errors return the error code."""
        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "ThrottlingException", "Message": "Too many requests"}}
        with patch(
            "boto3.client",
            side_effect=ClientError(error_response, "ListFoundationModels"),
        ):
            result = _test_bedrock_credentials("us-east-1")
            assert result == "AWS error: ThrottlingException"

    def test_region_passed_to_client(self):
        """Test that region is passed to boto3 client."""
        mock_client = MagicMock()
        mock_client.list_foundation_models.return_value = {}

        with patch("boto3.client", return_value=mock_client) as mock_boto:
            _test_bedrock_credentials("eu-west-1")
            mock_boto.assert_called_once_with("bedrock", region_name="eu-west-1")
