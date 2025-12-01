"""PostgreSQL Tools."""

import psycopg2
from langchain_core.tools import BaseTool, tool

from sdrbot_cli.config import settings

# Shared connection instance (lazy loaded)
_pg_conn = None


def get_pg_connection():
    """Get or create PostgreSQL connection.

    Returns fresh connection on each call if previous call returned None.
    """
    global _pg_conn
    if _pg_conn is None or _pg_conn.closed:
        try:
            connect_kwargs = {
                "host": settings.postgres_host,
                "port": settings.postgres_port or "5432",
                "user": settings.postgres_user,
                "password": settings.postgres_password,
                "dbname": settings.postgres_db,
            }
            # Add SSL mode if configured
            if settings.postgres_ssl_mode:
                connect_kwargs["sslmode"] = settings.postgres_ssl_mode

            _pg_conn = psycopg2.connect(**connect_kwargs)
        except Exception as e:
            raise RuntimeError(f"PostgreSQL connection failed: {e}") from e

    return _pg_conn


def reset_client():
    """Reset the cached client (useful for testing)."""
    global _pg_conn
    if _pg_conn:
        try:
            _pg_conn.close()
        except Exception:
            pass
    _pg_conn = None


def _run_query(query: str) -> str:
    """Internal helper to run a query without going through tool invocation."""
    conn = get_pg_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query)

            # Commit if it's a write operation
            if (
                query.strip()
                .upper()
                .startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"))
            ):
                conn.commit()
                return f"Query executed successfully. Rows affected: {cursor.rowcount}"

            # Fetch results for read operations
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                results = cursor.fetchall()

                if not results:
                    return "Query returned no results."

                # Format as string
                output = [f"Columns: {', '.join(columns)}"]
                for row in results:
                    output.append(str(row))

                return "\n".join(output)

            return "Query executed successfully."

    except Exception as e:
        conn.rollback()
        return f"Error executing query: {str(e)}"


@tool
def postgres_run_query(query: str) -> str:
    """
    Execute a SQL query against the PostgreSQL database.
    Can be used for both read (SELECT) and write (INSERT, UPDATE, DELETE) operations.

    Args:
        query: The SQL query to execute.
    """
    return _run_query(query)


@tool
def postgres_list_tables() -> str:
    """
    List all tables in the public schema of the PostgreSQL database.
    """
    query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """
    return _run_query(query)


@tool
def postgres_describe_table(table_name: str) -> str:
    """
    Get the schema information (columns, types) for a specific table.

    Args:
        table_name: The name of the table to describe.
    """
    query = f"""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = '{table_name}'
        ORDER BY ordinal_position;
    """
    return _run_query(query)


def get_tools() -> list[BaseTool]:
    """Get all PostgreSQL tools.

    Returns:
        List of PostgreSQL tools.
    """
    return [
        postgres_run_query,
        postgres_list_tables,
        postgres_describe_table,
    ]
