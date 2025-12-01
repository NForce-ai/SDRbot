"""Tests for MySQL tools."""

import os

import pytest

from sdrbot_cli.services.mysql.tools import (
    mysql_describe_table,
    mysql_list_tables,
    mysql_run_query,
    reset_client,
)


class TestMySQLToolsUnit:
    """Unit tests for MySQL tools using mocked connection."""

    def setup_method(self):
        reset_client()

    def test_run_query_read(self, patch_mysql_conn):
        """Test executing a read query."""
        mock_conn, mock_cursor = patch_mysql_conn

        # MySQL cursor returns list of dicts with DictCursor
        mock_cursor.fetchall.return_value = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

        result = mysql_run_query.invoke({"query": "SELECT * FROM users"})

        assert "Columns: id, name" in result
        assert "[1, 'Alice']" in result
        mock_cursor.execute.assert_called_with("SELECT * FROM users")

    def test_run_query_write(self, patch_mysql_conn):
        """Test executing a write query."""
        mock_conn, mock_cursor = patch_mysql_conn

        mock_cursor.rowcount = 1

        result = mysql_run_query.invoke({"query": "UPDATE users SET name='Charlie' WHERE id=1"})

        assert "Rows affected: 1" in result
        mock_conn.commit.assert_called_once()

    def test_list_tables(self, patch_mysql_conn):
        """Test listing tables."""
        mock_conn, mock_cursor = patch_mysql_conn

        mock_cursor.fetchall.return_value = [
            {"Tables_in_db": "users"},
            {"Tables_in_db": "products"},
        ]

        result = mysql_list_tables.invoke({})

        assert "users" in result
        assert "products" in result
        mock_cursor.execute.assert_called_with("SHOW TABLES;")

    def test_describe_table(self, patch_mysql_conn):
        """Test describing a table."""
        mock_conn, mock_cursor = patch_mysql_conn

        mock_cursor.fetchall.return_value = [
            {"Field": "id", "Type": "int", "Null": "NO"},
            {"Field": "name", "Type": "varchar(255)", "Null": "YES"},
        ]

        result = mysql_describe_table.invoke({"table_name": "users"})

        assert "id" in result
        assert "int" in result
        mock_cursor.execute.assert_called_with("DESCRIBE users;")


@pytest.mark.integration
class TestMySQLToolsIntegration:
    """Integration tests executing against a real database."""

    def setup_method(self):
        if not os.getenv("MYSQL_HOST"):
            pytest.skip("MYSQL_HOST not set")
        reset_client()

    def test_end_to_end_flow(self):
        """Create table, insert, select, and drop."""

        # 1. Create Table
        create_sql = (
            "CREATE TABLE IF NOT EXISTS test_users (id INT AUTO_INCREMENT PRIMARY KEY, name TEXT);"
        )
        mysql_run_query.invoke({"query": create_sql})

        # 2. Insert
        insert_sql = "INSERT INTO test_users (name) VALUES ('Integration Test');"
        mysql_run_query.invoke({"query": insert_sql})

        # 3. Select
        result = mysql_run_query.invoke(
            {"query": "SELECT * FROM test_users WHERE name='Integration Test'"}
        )
        assert "Integration Test" in result

        # 4. Cleanup
        mysql_run_query.invoke({"query": "DROP TABLE test_users;"})
