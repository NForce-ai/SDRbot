"""MySQL Tools."""

import pymysql
from langchain_core.tools import BaseTool, tool

from sdrbot_cli.config import settings

# Shared connection instance (lazy loaded)
_mysql_conn = None


def get_mysql_connection():
    """Get or create MySQL connection.

    Returns fresh connection on each call if previous call returned None.
    """
    global _mysql_conn
    if _mysql_conn is None or not _mysql_conn.open:
        try:
            connect_kwargs = {
                "host": settings.mysql_host,
                "port": int(settings.mysql_port) if settings.mysql_port else 3306,
                "user": settings.mysql_user,
                "password": settings.mysql_password,
                "database": settings.mysql_db,
                "cursorclass": pymysql.cursors.DictCursor,
            }
            # Enable SSL if configured
            if settings.mysql_ssl:
                connect_kwargs["ssl"] = {"ssl": True}

            _mysql_conn = pymysql.connect(**connect_kwargs)
        except Exception as e:
            raise RuntimeError(f"MySQL connection failed: {e}") from e

    return _mysql_conn


def reset_client():
    """Reset the cached client (useful for testing)."""
    global _mysql_conn
    if _mysql_conn:
        try:
            _mysql_conn.close()
        except Exception:
            pass
    _mysql_conn = None


def _run_query(query: str) -> str:
    """Internal helper to run a query without going through tool invocation."""
    conn = get_mysql_connection()
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
            results = cursor.fetchall()

            if not results:
                return "Query returned no results."

            # Format as string (results are list of dicts)
            output = []
            if results:
                columns = list(results[0].keys())
                output.append(f"Columns: {', '.join(columns)}")
                for row in results:
                    output.append(str(list(row.values())))

            return "\n".join(output)

    except Exception as e:
        conn.rollback()
        return f"Error executing query: {str(e)}"


@tool
def mysql_run_query(query: str) -> str:
    """
    Execute a SQL query against the MySQL database.
    Can be used for both read (SELECT) and write (INSERT, UPDATE, DELETE) operations.

    Args:
        query: The SQL query to execute.
    """
    return _run_query(query)


@tool
def mysql_list_tables() -> str:
    """
    List all tables in the MySQL database.
    """
    query = "SHOW TABLES;"
    return _run_query(query)


@tool
def mysql_describe_table(table_name: str) -> str:
    """
    Get the schema information (columns, types) for a specific table.

    Args:
        table_name: The name of the table to describe.
    """
    query = f"DESCRIBE {table_name};"
    return _run_query(query)


def get_tools() -> list[BaseTool]:
    """Get all MySQL tools.

    Returns:
        List of MySQL tools.
    """
    return [
        mysql_run_query,
        mysql_list_tables,
        mysql_describe_table,
    ]
