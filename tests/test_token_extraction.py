"""Tests for token extraction from different LLM response formats."""


def extract_tokens_from_message(message, token_tracker=True):
    """Extract tokens from a message using the same logic as execute_task.

    This is a standalone version of the token extraction logic from execution.py
    for testing purposes.
    """
    if not token_tracker:
        return 0, 0

    input_toks = 0
    output_toks = 0

    # Try usage_metadata first (LangChain standard)
    if hasattr(message, "usage_metadata") and message.usage_metadata:
        usage = message.usage_metadata
        input_toks = usage.get("input_tokens", 0)
        output_toks = usage.get("output_tokens", 0)

    # Fallback: check response_metadata for OpenAI-compatible endpoints
    if not (input_toks or output_toks):
        if hasattr(message, "response_metadata") and message.response_metadata:
            resp_meta = message.response_metadata
            # Try common usage locations
            usage = resp_meta.get("usage") or resp_meta.get("token_usage") or {}
            # OpenAI format uses prompt_tokens/completion_tokens
            input_toks = usage.get("input_tokens") or usage.get("prompt_tokens", 0)
            output_toks = usage.get("output_tokens") or usage.get("completion_tokens", 0)

    return input_toks, output_toks


class MockMessage:
    """Mock message class for testing token extraction."""

    def __init__(self, usage_metadata=None, response_metadata=None):
        self.usage_metadata = usage_metadata
        self.response_metadata = response_metadata


class TestTokenExtraction:
    """Tests for token extraction logic."""

    def test_langchain_standard_format(self):
        """Test extraction from LangChain usage_metadata format."""
        message = MockMessage(usage_metadata={"input_tokens": 100, "output_tokens": 50})
        input_toks, output_toks = extract_tokens_from_message(message)
        assert input_toks == 100
        assert output_toks == 50

    def test_openai_format_in_response_metadata(self):
        """Test extraction from OpenAI prompt_tokens/completion_tokens format."""
        message = MockMessage(
            response_metadata={"usage": {"prompt_tokens": 150, "completion_tokens": 75}}
        )
        input_toks, output_toks = extract_tokens_from_message(message)
        assert input_toks == 150
        assert output_toks == 75

    def test_token_usage_key_in_response_metadata(self):
        """Test extraction from token_usage key (some providers use this)."""
        message = MockMessage(
            response_metadata={"token_usage": {"input_tokens": 200, "output_tokens": 100}}
        )
        input_toks, output_toks = extract_tokens_from_message(message)
        assert input_toks == 200
        assert output_toks == 100

    def test_langchain_format_takes_priority(self):
        """Test that usage_metadata is preferred over response_metadata."""
        message = MockMessage(
            usage_metadata={"input_tokens": 100, "output_tokens": 50},
            response_metadata={"usage": {"prompt_tokens": 999, "completion_tokens": 888}},
        )
        input_toks, output_toks = extract_tokens_from_message(message)
        # Should use usage_metadata values, not response_metadata
        assert input_toks == 100
        assert output_toks == 50

    def test_fallback_when_usage_metadata_empty(self):
        """Test fallback to response_metadata when usage_metadata is empty."""
        message = MockMessage(
            usage_metadata={},  # Empty but truthy
            response_metadata={"usage": {"prompt_tokens": 150, "completion_tokens": 75}},
        )
        # Empty dict is truthy but has no tokens, should fallback
        input_toks, output_toks = extract_tokens_from_message(message)
        assert input_toks == 150
        assert output_toks == 75

    def test_fallback_when_usage_metadata_none(self):
        """Test fallback to response_metadata when usage_metadata is None."""
        message = MockMessage(
            usage_metadata=None,
            response_metadata={"usage": {"input_tokens": 200, "output_tokens": 100}},
        )
        input_toks, output_toks = extract_tokens_from_message(message)
        assert input_toks == 200
        assert output_toks == 100

    def test_no_usage_data_returns_zeros(self):
        """Test that missing usage data returns zeros."""
        message = MockMessage()
        input_toks, output_toks = extract_tokens_from_message(message)
        assert input_toks == 0
        assert output_toks == 0

    def test_partial_usage_metadata(self):
        """Test extraction when only some fields are present."""
        message = MockMessage(
            usage_metadata={"input_tokens": 100}  # Missing output_tokens
        )
        input_toks, output_toks = extract_tokens_from_message(message)
        assert input_toks == 100
        assert output_toks == 0

    def test_mixed_format_in_response_metadata(self):
        """Test extraction with input_tokens key (not prompt_tokens)."""
        message = MockMessage(
            response_metadata={"usage": {"input_tokens": 120, "output_tokens": 60}}
        )
        input_toks, output_toks = extract_tokens_from_message(message)
        assert input_toks == 120
        assert output_toks == 60

    def test_tracker_disabled_returns_zeros(self):
        """Test that disabled tracker returns zeros."""
        message = MockMessage(usage_metadata={"input_tokens": 100, "output_tokens": 50})
        input_toks, output_toks = extract_tokens_from_message(message, token_tracker=False)
        assert input_toks == 0
        assert output_toks == 0

    def test_empty_response_metadata(self):
        """Test handling of empty response_metadata."""
        message = MockMessage(
            usage_metadata=None,
            response_metadata={},
        )
        input_toks, output_toks = extract_tokens_from_message(message)
        assert input_toks == 0
        assert output_toks == 0

    def test_missing_usage_in_response_metadata(self):
        """Test handling when response_metadata exists but no usage key."""
        message = MockMessage(
            usage_metadata=None,
            response_metadata={"model": "gpt-4", "finish_reason": "stop"},
        )
        input_toks, output_toks = extract_tokens_from_message(message)
        assert input_toks == 0
        assert output_toks == 0

    def test_zero_tokens_triggers_fallback(self):
        """Test that zero tokens in usage_metadata triggers fallback."""
        message = MockMessage(
            usage_metadata={"input_tokens": 0, "output_tokens": 0},
            response_metadata={"usage": {"prompt_tokens": 100, "completion_tokens": 50}},
        )
        input_toks, output_toks = extract_tokens_from_message(message)
        # Zero values should trigger fallback
        assert input_toks == 100
        assert output_toks == 50
