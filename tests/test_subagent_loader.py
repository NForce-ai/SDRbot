"""Tests for the subagent YAML frontmatter loader."""

from __future__ import annotations

from pathlib import Path

from sdrbot_cli.subagents.loader import (
    _parse_frontmatter,
    load_subagent_file,
    scan_subagent_dirs,
)


class TestParseFrontmatter:
    def test_basic_kv(self) -> None:
        text = "---\nname: test\ndescription: A test agent\n---\nBody here."
        meta, body = _parse_frontmatter(text)
        assert meta["name"] == "test"
        assert meta["description"] == "A test agent"
        assert body == "Body here."

    def test_list_values(self) -> None:
        text = "---\nname: test\ndescription: desc\ntools:\n  - shell\n  - write_file\n---\nBody."
        meta, body = _parse_frontmatter(text)
        assert meta["tools"] == ["shell", "write_file"]

    def test_no_frontmatter(self) -> None:
        text = "Just regular text without frontmatter."
        meta, body = _parse_frontmatter(text)
        assert meta == {}
        assert body == text


class TestLoadSubagentFile:
    def test_valid_file(self, tmp_path: Path) -> None:
        md = tmp_path / "agent.md"
        md.write_text(
            "---\nname: researcher\ndescription: Does research\n---\nYou are a research agent.\n"
        )
        result = load_subagent_file(md)
        assert result is not None
        assert result["name"] == "researcher"
        assert result["description"] == "Does research"
        assert "research agent" in result["system_prompt"]

    def test_missing_name(self, tmp_path: Path) -> None:
        md = tmp_path / "bad.md"
        md.write_text("---\ndescription: Missing name\n---\nBody.\n")
        assert load_subagent_file(md) is None

    def test_missing_file(self, tmp_path: Path) -> None:
        assert load_subagent_file(tmp_path / "nope.md") is None

    def test_with_tools(self, tmp_path: Path) -> None:
        md = tmp_path / "agent.md"
        md.write_text(
            "---\nname: coder\ndescription: Writes code\ntools:\n  - shell\n---\nPrompt.\n"
        )
        result = load_subagent_file(md)
        assert result is not None
        assert result["tools"] == ["shell"]


class TestScanSubagentDirs:
    def test_scans_directory(self, tmp_path: Path) -> None:
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        (builtin / "a.md").write_text("---\nname: agent-a\ndescription: Agent A\n---\nPrompt A.")
        (builtin / "b.md").write_text("---\nname: agent-b\ndescription: Agent B\n---\nPrompt B.")

        results = scan_subagent_dirs(builtin)
        names = {r["name"] for r in results}
        assert names == {"agent-a", "agent-b"}

    def test_project_overrides_builtin(self, tmp_path: Path) -> None:
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        project = tmp_path / "project"
        project.mkdir()

        (builtin / "a.md").write_text(
            "---\nname: shared\ndescription: Built-in\n---\nBuilt-in prompt."
        )
        (project / "a.md").write_text(
            "---\nname: shared\ndescription: Project override\n---\nCustom prompt."
        )

        results = scan_subagent_dirs(builtin, project)
        assert len(results) == 1
        assert results[0]["description"] == "Project override"

    def test_skips_missing_dir(self, tmp_path: Path) -> None:
        results = scan_subagent_dirs(tmp_path / "does-not-exist")
        assert results == []
