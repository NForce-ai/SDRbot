"""Tests for MongoDB tools."""

import os
from unittest.mock import MagicMock

import pytest

from sdrbot_cli.services.mongodb.tools import (
    mongodb_delete_many,
    mongodb_find,
    mongodb_insert_one,
    mongodb_list_collections,
    mongodb_update_many,
    reset_client,
)


class TestMongoDBToolsUnit:
    """Unit tests for MongoDB tools using mocked client."""

    def setup_method(self):
        reset_client()

    def test_list_collections(self, patch_mongo_db):
        """Test listing collections."""
        mock_db = patch_mongo_db
        mock_db.list_collection_names.return_value = ["users", "logs"]

        result = mongodb_list_collections.invoke({})

        assert "- users" in result
        assert "- logs" in result

    def test_find(self, patch_mongo_db):
        """Test finding documents."""
        mock_db = patch_mongo_db
        mock_db.list_collection_names.return_value = ["users"]

        # Mock cursor result
        mock_cursor = MagicMock()
        mock_cursor.limit.return_value = [{"name": "Alice"}, {"name": "Bob"}]
        mock_db.__getitem__.return_value.find.return_value = mock_cursor

        result = mongodb_find.invoke({"collection": "users", "query": '{"name": "Alice"}'})

        assert "Alice" in result
        assert "Bob" in result

    def test_insert_one(self, patch_mongo_db):
        """Test inserting a document."""
        mock_db = patch_mongo_db

        mock_result = MagicMock()
        mock_result.inserted_id = "12345"
        mock_db.__getitem__.return_value.insert_one.return_value = mock_result

        result = mongodb_insert_one.invoke(
            {"collection": "users", "document": '{"name": "Charlie"}'}
        )

        assert "12345" in result
        mock_db.__getitem__.return_value.insert_one.assert_called()

    def test_update_many(self, patch_mongo_db):
        """Test updating documents."""
        mock_db = patch_mongo_db

        mock_result = MagicMock()
        mock_result.matched_count = 5
        mock_result.modified_count = 3
        mock_db.__getitem__.return_value.update_many.return_value = mock_result

        result = mongodb_update_many.invoke(
            {
                "collection": "users",
                "filter": '{"active": false}',
                "update": '{"$set": {"active": true}}',
            }
        )

        assert "Matched: 5" in result

    def test_delete_many(self, patch_mongo_db):
        """Test deleting documents."""
        mock_db = patch_mongo_db

        mock_result = MagicMock()
        mock_result.deleted_count = 2
        mock_db.__getitem__.return_value.delete_many.return_value = mock_result

        result = mongodb_delete_many.invoke({"collection": "users", "filter": '{"name": "Old"}'})

        assert "Deleted count: 2" in result


@pytest.mark.integration
class TestMongoDBToolsIntegration:
    """Integration tests executing against a real database."""

    def setup_method(self):
        if not os.getenv("MONGODB_URI"):
            pytest.skip("MONGODB_URI not set")
        reset_client()

    def test_end_to_end_flow(self):
        """Insert, find, update, delete."""
        collection = "test_integration"

        # 1. Insert
        mongodb_insert_one.invoke(
            {
                "collection": collection,
                "document": '{"name": "Integration Test", "status": "pending"}',
            }
        )

        # 2. Find
        result = mongodb_find.invoke(
            {"collection": collection, "query": '{"name": "Integration Test"}'}
        )
        assert "Integration Test" in result

        # 3. Update
        mongodb_update_many.invoke(
            {
                "collection": collection,
                "filter": '{"name": "Integration Test"}',
                "update": '{"$set": {"status": "complete"}}',
            }
        )

        # 4. Verify Update
        result = mongodb_find.invoke(
            {"collection": collection, "query": '{"name": "Integration Test"}'}
        )
        assert "complete" in result

        # 5. Delete
        mongodb_delete_many.invoke(
            {"collection": collection, "filter": '{"name": "Integration Test"}'}
        )

        # 6. Verify Delete
        result = mongodb_find.invoke(
            {"collection": collection, "query": '{"name": "Integration Test"}'}
        )
        assert "No documents found" in result
