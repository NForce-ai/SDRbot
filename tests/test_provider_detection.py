"""Tests for detect_provider() and validate_model_capabilities()."""

from __future__ import annotations

import pytest

from sdrbot_cli.config import detect_provider, validate_model_capabilities


class TestDetectProvider:
    @pytest.mark.parametrize(
        "model,expected",
        [
            ("claude-opus-4-6", "anthropic"),
            ("claude-sonnet-4-6", "anthropic"),
            ("claude-haiku-4-5-20251001", "anthropic"),
            ("gpt-5-mini", "openai"),
            ("gpt-4o", "openai"),
            ("o1-preview", "openai"),
            ("o3-mini", "openai"),
            ("o4-mini", "openai"),
            ("chatgpt-4o-latest", "openai"),
            ("gemini-2.5-pro", "google"),
            ("gemini-2.0-flash", "google"),
            ("anthropic.claude-v2", "bedrock"),
            ("llama3.2:latest", "unknown"),
            ("mistralai/mistral-7b", "ollama"),
        ],
    )
    def test_detection(self, model: str, expected: str) -> None:
        assert detect_provider(model) == expected

    def test_case_insensitive(self) -> None:
        assert detect_provider("Claude-Opus-4-6") == "anthropic"
        assert detect_provider("GPT-5-MINI") == "openai"


class TestValidateModelCapabilities:
    def test_no_warnings_for_capable_model(self) -> None:
        assert validate_model_capabilities("claude-opus-4-6", "anthropic") == []

    def test_warns_no_tool_calling(self) -> None:
        warnings = validate_model_capabilities("o1-preview", "openai")
        assert len(warnings) == 1
        assert "tool calling" in warnings[0].lower()

    def test_warns_small_context(self) -> None:
        warnings = validate_model_capabilities("gpt-4", "openai")
        assert len(warnings) == 1
        assert "8,192" in warnings[0]

    def test_gpt35_context_warning(self) -> None:
        warnings = validate_model_capabilities("gpt-3.5-turbo", "openai")
        assert any("context" in w.lower() for w in warnings)
