"""MongoDB Tools."""

import json

from langchain_core.tools import BaseTool, tool
from pymongo import MongoClient
from pymongo.database import Database

from sdrbot_cli.config import settings

# Shared connection instance (lazy loaded)
_mongo_client: MongoClient | None = None


def get_mongo_db() -> Database:
    """Get or create MongoDB database connection.

    Returns fresh database connection on each call if previous call returned None.
    """
    global _mongo_client
    if _mongo_client is None:
        try:
            connect_kwargs = {}
            # Enable TLS if configured
            if settings.mongodb_tls:
                connect_kwargs["tls"] = True

            _mongo_client = MongoClient(settings.mongodb_uri, **connect_kwargs)
            # Force connection verification
            _mongo_client.admin.command("ping")
        except Exception as e:
            raise RuntimeError(f"MongoDB connection failed: {e}") from e

    if settings.mongodb_db is None:
        raise RuntimeError("MongoDB database name not configured (MONGODB_DB).")

    db_name = settings.mongodb_db
    return _mongo_client[db_name]


def reset_client():
    """Reset the cached client (useful for testing)."""
    global _mongo_client
    if _mongo_client:
        try:
            _mongo_client.close()
        except Exception:
            pass
    _mongo_client = None


@tool
def mongodb_list_collections() -> str:
    """
    List all collections in the MongoDB database.
    """
    try:
        db = get_mongo_db()
        collections = db.list_collection_names()
        if not collections:
            return "No collections found."
        return "Collections:\n" + "\n".join(f"- {c}" for c in sorted(collections))
    except Exception as e:
        return f"Error listing collections: {str(e)}"


@tool
def mongodb_find(collection: str, query: str = "{}", limit: int = 10) -> str:
    """
    Find documents in a MongoDB collection.

    Args:
        collection: The name of the collection to search.
        query: A JSON string representing the query filter (e.g., '{"name": "John"}'). Defaults to "{}".
        limit: Maximum number of documents to return. Defaults to 10.
    """
    try:
        db = get_mongo_db()
        if collection not in db.list_collection_names():
            return f"Error: Collection '{collection}' does not exist."

        # Parse query string to dict
        try:
            query_dict = json.loads(query)
        except json.JSONDecodeError as e:
            return f"Error parsing query JSON: {e}"

        cursor = db[collection].find(query_dict).limit(limit)
        results = list(cursor)

        if not results:
            return "No documents found."

        # Convert ObjectId and other non-serializable types to string for display
        return json.dumps(results, default=str, indent=2)

    except Exception as e:
        return f"Error executing find: {str(e)}"


@tool
def mongodb_insert_one(collection: str, document: str) -> str:
    """
    Insert a single document into a MongoDB collection.

    Args:
        collection: The name of the collection.
        document: A JSON string representing the document to insert.
    """
    try:
        db = get_mongo_db()

        # Parse document string to dict
        try:
            doc_dict = json.loads(document)
        except json.JSONDecodeError as e:
            return f"Error parsing document JSON: {e}"

        result = db[collection].insert_one(doc_dict)
        return f"Document inserted successfully. ID: {result.inserted_id}"

    except Exception as e:
        return f"Error inserting document: {str(e)}"


@tool
def mongodb_update_many(collection: str, filter: str, update: str) -> str:
    """
    Update documents in a MongoDB collection.

    Args:
        collection: The name of the collection.
        filter: A JSON string representing the filter to match documents.
        update: A JSON string representing the update operations (e.g., '{"name": "active"}}').
    """
    try:
        db = get_mongo_db()

        try:
            filter_dict = json.loads(filter)
            update_dict = json.loads(update)
        except json.JSONDecodeError as e:
            return f"Error parsing JSON: {e}"

        result = db[collection].update_many(filter_dict, update_dict)
        return (
            f"Update successful. Matched: {result.matched_count}, Modified: {result.modified_count}"
        )

    except Exception as e:
        return f"Error updating documents: {str(e)}"


@tool
def mongodb_delete_many(collection: str, filter: str) -> str:
    """
    Delete documents from a MongoDB collection.

    Args:
        collection: The name of the collection.
        filter: A JSON string representing the filter to match documents.
    """
    try:
        db = get_mongo_db()

        try:
            filter_dict = json.loads(filter)
        except json.JSONDecodeError as e:
            return f"Error parsing filter JSON: {e}"

        result = db[collection].delete_many(filter_dict)
        return f"Delete successful. Deleted count: {result.deleted_count}"

    except Exception as e:
        return f"Error deleting documents: {str(e)}"


def get_tools() -> list[BaseTool]:
    """Get all MongoDB tools.

    Returns:
        List of MongoDB tools.
    """
    return [
        mongodb_list_collections,
        mongodb_find,
        mongodb_insert_one,
        mongodb_update_many,
        mongodb_delete_many,
    ]
