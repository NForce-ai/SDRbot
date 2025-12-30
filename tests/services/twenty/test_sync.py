"""Tests for Twenty schema sync."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestTwentySyncUnit:
    """Unit tests for Twenty schema sync with mocked OpenAPI spec."""

    @pytest.fixture
    def mock_openapi_spec(self):
        """Create a mock OpenAPI spec response."""
        return {
            "paths": {
                "/rest/people": {"get": {}, "post": {}},
                "/rest/people/{id}": {"get": {}, "patch": {}, "delete": {}},
                "/rest/companies": {"get": {}, "post": {}},
                "/rest/companies/{id}": {"get": {}, "patch": {}, "delete": {}},
                "/rest/workspaceMembers": {"get": {}},  # System object - should be filtered
            },
            "components": {
                "schemas": {
                    "Person": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string", "format": "email"},
                            "jobTitle": {"type": "string"},
                            "city": {"type": "string"},
                            "id": {"type": "string", "format": "uuid"},  # System field
                            "createdAt": {"type": "string", "format": "date-time"},  # System field
                        },
                        "required": ["email"],
                    },
                    "Company": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "domainName": {"type": "string"},
                        },
                        "required": ["name"],
                    },
                }
            },
        }

    @pytest.fixture
    def mock_twenty_client(self):
        """Create a mock Twenty client."""
        mock = MagicMock()
        mock.base_url = "https://api.example.com/rest"
        mock.api_key = "test-api-key"
        return mock

    def test_parse_openapi_spec(self, mock_openapi_spec):
        """_parse_openapi_spec should extract objects from OpenAPI spec."""
        from sdrbot_cli.services.twenty.sync import _parse_openapi_spec

        result = _parse_openapi_spec(mock_openapi_spec)

        # Should include person and company
        assert "person" in result
        assert "company" in result
        # workspaceMember is in SYSTEM_OBJECTS - should be filtered
        assert "workspaceMember" not in result

    def test_parse_openapi_spec_extracts_fields(self, mock_openapi_spec):
        """_parse_openapi_spec should extract fields correctly."""
        from sdrbot_cli.services.twenty.sync import _parse_openapi_spec

        result = _parse_openapi_spec(mock_openapi_spec)

        # Check person fields
        person = result["person"]
        assert person["name_singular"] == "person"
        assert person["name_plural"] == "people"
        field_names = [f["name"] for f in person["fields"]]
        assert "email" in field_names
        assert "jobTitle" in field_names
        # System fields should be filtered
        assert "id" not in field_names
        assert "createdAt" not in field_names

    def test_extract_fields_from_schema(self):
        """_extract_fields_from_schema should convert OpenAPI properties to fields."""
        from sdrbot_cli.services.twenty.sync import _extract_fields_from_schema

        schema = {
            "type": "object",
            "properties": {
                "email": {"type": "string", "format": "email"},
                "name": {"type": "string"},
                "count": {"type": "integer"},
                "id": {"type": "string", "format": "uuid"},  # Should be in output only
            },
            "required": ["email"],
        }

        result = _extract_fields_from_schema(schema)

        # Should return dict with input and output keys
        assert "input" in result
        assert "output" in result

        # Input fields should exclude id
        input_names = [f["name"] for f in result["input"]]
        assert "email" in input_names
        assert "name" in input_names
        assert "id" not in input_names

        # Output fields should include id
        output_names = [f["name"] for f in result["output"]]
        assert "email" in output_names
        assert "name" in output_names
        assert "id" in output_names

        # Check required field
        email_field = next(f for f in result["input"] if f["name"] == "email")
        assert email_field["required"] is True

    def test_generate_tools_code_valid_python(self):
        """_generate_tools_code should produce valid Python."""
        from sdrbot_cli.services.twenty.sync import _generate_tools_code

        fields = [
            {
                "name": "email",
                "label": "Email",
                "type": "EMAIL",
                "required": True,
                "options": [],
            },
            {
                "name": "name",
                "label": "Name",
                "type": "TEXT",
                "required": False,
                "options": [],
            },
        ]
        output_fields = fields + [
            {
                "name": "id",
                "label": "Id",
                "type": "UUID",
                "required": False,
                "options": [],
            },
        ]
        schema = {
            "person": {
                "name_singular": "person",
                "name_plural": "people",
                "fields": fields,
                "output_fields": output_fields,
            }
        }
        code = _generate_tools_code(schema)

        # Verify code is valid Python
        compile(code, "<string>", "exec")

        # Verify expected tools are generated
        assert "twenty_create_person" in code
        assert "twenty_update_person" in code
        assert "twenty_search_people" in code
        assert "twenty_get_person" in code
        assert "twenty_delete_person" in code

        # Verify return docstrings include field info
        assert "- id: Record identifier" in code
        assert "- email: Email" in code

    def test_generate_tools_code_multiple_objects(self):
        """_generate_tools_code should handle multiple objects."""
        from sdrbot_cli.services.twenty.sync import _generate_tools_code

        person_fields = [
            {
                "name": "email",
                "label": "Email",
                "type": "EMAIL",
                "required": True,
                "options": [],
            },
        ]
        company_fields = [
            {
                "name": "name",
                "label": "Name",
                "type": "TEXT",
                "required": True,
                "options": [],
            },
        ]
        schema = {
            "person": {
                "name_singular": "person",
                "name_plural": "people",
                "fields": person_fields,
                "output_fields": person_fields + [{"name": "id", "label": "Id", "type": "UUID"}],
            },
            "company": {
                "name_singular": "company",
                "name_plural": "companies",
                "fields": company_fields,
                "output_fields": company_fields + [{"name": "id", "label": "Id", "type": "UUID"}],
            },
        }
        code = _generate_tools_code(schema)

        # Verify code is valid Python
        compile(code, "<string>", "exec")

        # Verify tools for both objects
        assert "twenty_create_person" in code
        assert "twenty_create_company" in code
        assert "twenty_search_people" in code
        assert "twenty_search_companies" in code

    def test_sync_schema_writes_file(self, mock_twenty_client, mock_openapi_spec):
        """sync_schema should write generated tools to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Mock the requests.get for OpenAPI spec fetch
            mock_response = MagicMock()
            mock_response.json.return_value = mock_openapi_spec
            mock_response.raise_for_status = MagicMock()

            with (
                patch(
                    "sdrbot_cli.services.twenty.sync.TwentyClient", return_value=mock_twenty_client
                ),
                patch("sdrbot_cli.services.twenty.sync.requests.get", return_value=mock_response),
                patch("sdrbot_cli.services.twenty.sync.settings") as mock_settings,
            ):
                mock_settings.ensure_generated_dir.return_value = tmp_path

                from sdrbot_cli.services.twenty.sync import sync_schema

                result = sync_schema()

                # Verify result structure
                assert "schema_hash" in result
                assert "objects" in result
                assert len(result["objects"]) == 2
                assert "person" in result["objects"]
                assert "company" in result["objects"]

                # Verify file was created
                generated_file = tmp_path / "twenty_tools.py"
                assert generated_file.exists()

                # Verify generated code is valid Python
                code = generated_file.read_text()
                compile(code, str(generated_file), "exec")


class TestTwentySyncHelpers:
    """Tests for sync helper functions."""

    def test_python_type_mapping(self):
        """_python_type should map Twenty types correctly."""
        from sdrbot_cli.services.twenty.sync import _python_type

        assert _python_type("TEXT") == "str"
        assert _python_type("NUMBER") == "float"
        assert _python_type("BOOLEAN") == "bool"
        assert _python_type("EMAIL") == "str"
        assert _python_type("DATE") == "str"
        assert _python_type("CURRENCY") == "float"
        assert _python_type("UNKNOWN_TYPE") == "str"  # Default

    def test_safe_param_name(self):
        """_safe_param_name should handle special characters."""
        from sdrbot_cli.services.twenty.sync import _safe_param_name

        assert _safe_param_name("email") == "email"
        assert _safe_param_name("first-name") == "first_name"
        assert _safe_param_name("my field") == "my_field"
        assert _safe_param_name("id") == "id_"  # Reserved word
        assert _safe_param_name("type") == "type_"  # Reserved word

    def test_prioritize_fields(self):
        """_prioritize_fields should sort by importance."""
        from sdrbot_cli.services.twenty.sync import _prioritize_fields

        fields = [
            {"name": "random", "required": False},
            {"name": "jobTitle", "required": False},
            {"name": "name", "required": False},
            {"name": "required_field", "required": True},
        ]

        sorted_fields = _prioritize_fields(fields, "person")

        # name and jobTitle should come first for person (priority map)
        assert sorted_fields[0]["name"] == "name"
        assert sorted_fields[1]["name"] == "jobTitle"
