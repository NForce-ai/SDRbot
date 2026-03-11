"""Tests for system prompt template rendering and model identity injection."""

from __future__ import annotations

from unittest.mock import patch

from sdrbot_cli.agent import get_system_prompt


def _stub_services_prompt() -> str:
    return ""


def _stub_privileged_prompt() -> str:
    return ""


class TestSystemPromptTemplate:
    @patch("sdrbot_cli.agent._get_privileged_mode_prompt", _stub_privileged_prompt)
    @patch("sdrbot_cli.agent._get_enabled_services_prompt", _stub_services_prompt)
    def test_contains_skills_dir(self) -> None:
        prompt = get_system_prompt("test-agent")
        assert "Skills Directory" in prompt

    @patch("sdrbot_cli.agent._get_privileged_mode_prompt", _stub_privileged_prompt)
    @patch("sdrbot_cli.agent._get_enabled_services_prompt", _stub_services_prompt)
    def test_model_identity_injected(self) -> None:
        prompt = get_system_prompt(
            "test-agent",
            model_name="claude-opus-4-6",
            provider="anthropic",
        )
        assert "claude-opus-4-6" in prompt
        assert "anthropic" in prompt

    @patch("sdrbot_cli.agent._get_privileged_mode_prompt", _stub_privileged_prompt)
    @patch("sdrbot_cli.agent._get_enabled_services_prompt", _stub_services_prompt)
    def test_no_model_identity_when_omitted(self) -> None:
        prompt = get_system_prompt("test-agent")
        assert "You are powered by" not in prompt

    @patch("sdrbot_cli.agent._get_privileged_mode_prompt", _stub_privileged_prompt)
    @patch("sdrbot_cli.agent._get_enabled_services_prompt", _stub_services_prompt)
    def test_contains_working_directory(self) -> None:
        prompt = get_system_prompt("test-agent")
        assert "Working directory" in prompt

    @patch("sdrbot_cli.agent._get_privileged_mode_prompt", _stub_privileged_prompt)
    @patch("sdrbot_cli.agent._get_enabled_services_prompt", _stub_services_prompt)
    def test_sandbox_mode(self) -> None:
        prompt = get_system_prompt("test-agent", sandbox_type="modal")
        assert "remote Linux sandbox" in prompt
