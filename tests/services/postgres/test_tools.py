"""Tests for PostgreSQL tools."""

import os

import pytest

from sdrbot_cli.services.postgres.tools import (
    postgres_describe_table,
    postgres_list_tables,
    postgres_run_query,
    reset_client,
)


class TestPostgresToolsUnit:
    """Unit tests for PostgreSQL tools using mocked connection."""

    def setup_method(self):
        reset_client()

    def test_run_query_read(self, patch_postgres_conn):
        """Test executing a read query."""
        mock_conn, mock_cursor = patch_postgres_conn

        # Setup mock results
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "Alice"), (2, "Bob")]

        result = postgres_run_query.invoke({"query": "SELECT * FROM users"})

        assert "Columns: id, name" in result
        assert "(1, 'Alice')" in result
        assert "(2, 'Bob')" in result
        mock_cursor.execute.assert_called_with("SELECT * FROM users")

    def test_run_query_write(self, patch_postgres_conn):
        """Test executing a write query."""
        mock_conn, mock_cursor = patch_postgres_conn

        mock_cursor.rowcount = 1

        result = postgres_run_query.invoke({"query": "UPDATE users SET name='Charlie' WHERE id=1"})

        assert "Rows affected: 1" in result
        mock_conn.commit.assert_called_once()

    def test_list_tables(self, patch_postgres_conn):
        """Test listing tables."""
        mock_conn, mock_cursor = patch_postgres_conn

        mock_cursor.description = [("table_name",)]
        mock_cursor.fetchall.return_value = [("users",), ("products",)]

        result = postgres_list_tables.invoke({})

        assert "users" in result
        assert "products" in result
        assert "information_schema.tables" in mock_cursor.execute.call_args[0][0]

    def test_describe_table(self, patch_postgres_conn):
        """Test describing a table."""
        mock_conn, mock_cursor = patch_postgres_conn

        mock_cursor.description = [("column_name",), ("data_type",), ("is_nullable",)]
        mock_cursor.fetchall.return_value = [("id", "integer", "NO"), ("name", "text", "YES")]

        result = postgres_describe_table.invoke({"table_name": "users"})

        assert "id" in result
        assert "integer" in result
        assert "information_schema.columns" in mock_cursor.execute.call_args[0][0]


@pytest.mark.integration
class TestPostgresToolsIntegration:
    """Integration tests executing against a real database."""

    def setup_method(self):
        if not os.getenv("POSTGRES_HOST"):
            pytest.skip("POSTGRES_HOST not set")
        reset_client()

    def test_end_to_end_flow(self):
        """Create table, insert, select, and drop."""

        # 1. Create Table
        create_sql = "CREATE TABLE IF NOT EXISTS test_users (id SERIAL PRIMARY KEY, name TEXT);"
        postgres_run_query.invoke({"query": create_sql})

        # 2. Insert
        insert_sql = "INSERT INTO test_users (name) VALUES ('Integration Test');"
        postgres_run_query.invoke({"query": insert_sql})

        # 3. Select
        result = postgres_run_query.invoke(
            {"query": "SELECT * FROM test_users WHERE name='Integration Test'"}
        )
        assert "Integration Test" in result

        # 4. Cleanup
        postgres_run_query.invoke({"query": "DROP TABLE test_users;"})
