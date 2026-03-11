# Upstream Tracking Guide

SDRBot was forked from [langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) at version `deepagents-cli==0.0.9`. We maintain this as a **hard fork** with substantial customizations for RevOps use cases.

## Our Customizations

The following are SDRBot-specific additions not present in upstream:

| Directory/File | Purpose |
|----------------|---------|
| `sdrbot_cli/services/` | CRM integrations (HubSpot, Salesforce, Attio, Hunter, Lusha) |
| `sdrbot_cli/auth/` | OAuth and API key authentication handlers |
| `sdrbot_cli/setup_wizard.py` | Interactive first-run configuration |
| `sdrbot_cli/shell.py` | Shell middleware |
| `sdrbot_cli/clipboard.py` | Clipboard copy with OSC52 fallback |
| `sdrbot_cli/sessions.py` | SQLite-backed session persistence |
| `sdrbot_cli/non_interactive.py` | Headless execution mode |
| `sdrbot_cli/subagents/loader.py` | YAML frontmatter subagent loader |
| `sdrbot_cli/system_prompt.md` | Templated system prompt |
| `agents/` | User-defined agent personas |

Additionally, most core files (`config.py`, `main.py`, `agent.py`, `execution.py`) have been substantially modified to support these features.

We have also changed the entire UI stack to TerminalUI library (TUI)

## Tracking Upstream Changes

### Setup (one-time)

The upstream remote should already be configured:

```bash
git remote -v
# Should show:
# upstream    https://github.com/langchain-ai/deepagents.git (fetch)
```

If not, add it:

```bash
git remote add upstream https://github.com/langchain-ai/deepagents.git
```

### Workflow: Reviewing New Releases

1. **Watch for releases**: Subscribe to upstream releases at https://github.com/langchain-ai/deepagents/releases (Watch → Custom → Releases)

2. **Fetch new tags**:
   ```bash
   make upstream_fetch
   # or: git fetch upstream --tags
   ```

3. **List available versions**:
   ```bash
   make upstream_versions
   ```

4. **Generate diff report**:
   ```bash
   make upstream_diff
   # or for specific version:
   make upstream_diff_version V=0.0.11
   ```

5. **Review the report** and categorize each change:
   - **[PORT]** - Bug fixes or improvements we need → port directly
   - **[ADAPT]** - Good ideas that need modification → adapt to our architecture
   - **[SKIP]** - Not relevant or conflicts with our design → skip

6. **For each file with changes**, compare upstream's new version to our current code:
   ```bash
   # The script outputs the temp directory path, e.g. /tmp/upstream-diff-12345
   # Compare what upstream changed to what we have:
   diff -u /tmp/upstream-diff-*/new/<file>.py sdrbot_cli/<file>.py
   ```

7. **Port changes manually** by editing the corresponding `sdrbot_cli/` files
   - Remember to change `deepagents_cli` imports to `sdrbot_cli`
   - Adapt paths like `~/.deepagents/` to our conventions (e.g., `./agents/`)

8. **Update this document** with your review notes in the Version History section

### Manual Comparison Commands

The diff script extracts versions to `/tmp/upstream-diff-*/`. Useful commands:

```bash
# See what changed in upstream between versions
diff -u /tmp/upstream-diff-*/old/config.py /tmp/upstream-diff-*/new/config.py

# Compare upstream's new version to our current code (most important!)
diff -u /tmp/upstream-diff-*/new/config.py sdrbot_cli/config.py

# Check if we already have a feature
grep -n "some_function_name" sdrbot_cli/*.py

# Read upstream's new file to understand it
cat /tmp/upstream-diff-*/new/new_file.py
```

## File Mapping

Upstream uses `deepagents_cli/`, we use `sdrbot_cli/`. The structure is similar:

| Upstream | SDRBot |
|----------|--------|
| `libs/deepagents-cli/deepagents_cli/` | `sdrbot_cli/` |
| `deepagents_cli.xxx` imports | `sdrbot_cli.xxx` imports |
| `~/.deepagents/{agent}/` | `./agents/{agent}.md` |
| `~/.deepagents/{agent}/agent.md` | `./agents/{agent}.md` |

### Key Files to Review

These files contain the core logic and are most likely to have important changes:

| File | What it does | Priority |
|------|--------------|----------|
| `execution.py` | HITL approval, streaming, tool execution | HIGH |
| `config.py` | Settings, model creation, API keys | HIGH |
| `agent.py` | Agent creation, system prompt, middleware | HIGH |
| `main.py` | CLI entry, argument parsing, main loop | MEDIUM |
| `ui.py` | Display formatting, diffs, help text | MEDIUM |
| `file_ops.py` | File operation tracking, diff preview | MEDIUM |
| `input.py` | User input, completions | LOW |
| `token_utils.py` | Token counting | LOW |
| `integrations/*.py` | Sandbox backends (Modal, Daytona, RunLoop) | LOW |

## Version History

| Date | Upstream Version | Action Taken |
|------|------------------|--------------|
| Initial | `deepagents-cli==0.0.9` | Forked as baseline |
| 2025-11-27 | `deepagents-cli==0.0.10` | Reviewed - all relevant changes already ported (see below) |
| 2025-12-27 | `deepagents-cli==0.0.11` | Ported image paste support, shell.py already existed (see below) |
| 2025-12-27 | `deepagents-cli==0.0.12` | Reviewed - `--model` CLI arg not relevant (we use TUI), skills spec skipped (see below) |
| 2026-03-02 | `deepagents-cli==0.0.13–0.0.25` | Bulk port: bug fixes, security hardening, clipboard, provider detection, sessions, shell allow-list, subagent loader, non-interactive mode (see below) |

### 0.0.10 Review Notes (2025-11-27)

**Summary**: No action needed - all relevant features were already implemented in SDRBot.

| Change | Status | Notes |
|--------|--------|-------|
| `skills/` directory added | SKIP | We have our own implementation |
| `project_utils.py` added | SKIP | We already have this |
| `config.py` - Settings class, Gemini support | ALREADY HAVE | Our version is more advanced (service credentials, reload(), custom endpoints) |
| `execution.py` - auto-approve all option | ALREADY HAVE | `auto-accept all going forward` option in HITL prompt |
| `execution.py` - Gemini tool_call streaming | ALREADY HAVE | `block_type in ("tool_call_chunk", "tool_call")` |
| `execution.py` - mark_hitl_approved | ALREADY HAVE | Skips duplicate diff display after approval |
| `file_ops.py` - backend download improvements | ALREADY HAVE | Identical implementation |
| `file_ops.py` - update_args for incremental streaming | ALREADY HAVE | Retries before_content capture |
| `agent_memory.py` - user/project memory split | ALREADY HAVE | Our version uses project-local paths (./agents/) vs upstream's global (~/.deepagents/) |
| `main.py` - --no-splash flag | ALREADY HAVE | Skip ASCII art on startup |
| `main.py` - platform-specific tips (macOS symbols) | ALREADY HAVE | ⌥⌃ on macOS, Ctrl/Alt on others |
| `main.py` - CompositeBackend sandbox ID extraction | ALREADY HAVE | Proper handling of nested backends |
| `token_utils.py` - expansion | ALREADY HAVE | Functionally identical |
| `integrations/*.py` - upload/download_files | ALREADY HAVE | Modal, Daytona, RunLoop all have these |
| Various linting fixes (`_unused` prefixes) | SKIP | Style only, no functional change |

---

### 0.0.11 Review Notes (2025-12-27)

**Summary**: Ported image paste support for multimodal messages. Shell middleware already existed.

| Change | Status | Notes |
|--------|--------|-------|
| `image_utils.py` (NEW) - Clipboard image paste | **PORTED** | Adapted for cross-platform (macOS/Linux), uses Pillow |
| `shell.py` (NEW) - ShellMiddleware | ALREADY HAVE | Our version is identical + includes OS detection |
| `agent.py` - `create_cli_agent` with more options | SKIP | We have custom TUI-based agent creation |
| `config.py` - LangSmith project routing | SKIP | We already have `langsmith_project` in Settings |
| `execution.py` - Image support in messages | **PORTED** | Added `images` param and multimodal content |
| `input.py` - ImageTracker for prompt_toolkit | **ADAPTED** | Ported to Textual TUI (app.py) |
| `main.py` - Image integration | **ADAPTED** | Integrated in agent_worker.py instead |

**Ported changes**:
- [x] `sdrbot_cli/image_utils.py` - New file with ImageData, ImageTracker, get_clipboard_image
- [x] `sdrbot_cli/execution.py` - Added `images` parameter for multimodal messages
- [x] `sdrbot_cli/tui/app.py` - Modified action_paste() to detect images
- [x] `sdrbot_cli/tui/agent_worker.py` - Pass images to execute_task

**Dependencies added**:
- Pillow>=10.0.0 (for image processing)

---

### 0.0.12 Review Notes (2025-12-27)

**Summary**: No action needed - CLI `--model` arg not relevant (we use TUI with model.json). Skills spec improvements deferred.

| Change | Status | Notes |
|--------|--------|-------|
| `config.py` - `--model` CLI arg, auto-detect provider | SKIP | We have TUI model selector + model.json + more providers (Ollama, vLLM, Bedrock, etc.) |
| `main.py` - `--model` argument | SKIP | We use TUI |
| `skills/commands.py` - Agent Skills spec validation | CONSIDER | Good improvement, could port later |
| `skills/load.py` - Agent Skills spec compliance | CONSIDER | Proper YAML parsing, additional metadata fields |
| `ui.py` - Help text for --model | SKIP | We use TUI |

**Skipped** (with reason):
- `--model` CLI arg: We use TUI with interactive model selection + model.json configuration
- Skills spec improvements: Deferred - our skills work fine, could consider for future alignment

---

### 0.0.13–0.0.25 Review Notes (2026-03-02)

**Summary**: Bulk port of 13 upstream releases. Ported bug fixes, security hardening, clipboard copy, provider detection, model validation, session persistence, system prompt templating, shell allow-list, subagent loader, and non-interactive mode.

| Change | Status | Notes |
|--------|--------|-------|
| `file_ops.py` - `encoding="utf-8"` in `_safe_read()` | **PORTED** | Prevents encoding errors on non-ASCII files |
| `file_ops.py` - offset bounds check | **PORTED** | Clamps offset to 0 when > lines |
| `file_ops.py` - narrow `except Exception` | **PORTED** | → `(OSError, UnicodeDecodeError, AttributeError)` in 3 locations |
| `image_utils.py` - `_get_executable()` helper | **PORTED** | `shutil.which()` validates executables before `subprocess.run()` |
| `image_utils.py` - narrow `except Exception` | **PORTED** | 5 bare excepts → specific types |
| `config.py` - OSError guard in `_find_project_root()` | **PORTED** | Wraps `git_dir.exists()` |
| `clipboard.py` (NEW) - `copy_to_clipboard()` | **PORTED** | pyperclip + OSC52 fallback for SSH/tmux |
| `config.py` - `detect_provider()` | **PORTED** | Prefix-based matching for 6 providers incl. `o1-/o3-/o4-/chatgpt-` |
| `config.py` - `validate_model_capabilities()` | **PORTED** | Warns about no tool_calling or small context windows |
| `sessions.py` (NEW) - SQLite session persistence | **PORTED** | `AsyncSqliteSaver` checkpointer, CRUD helpers |
| `agent.py` - widen checkpointer type | **PORTED** | `InMemorySaver | None` → `BaseCheckpointSaver | None` |
| `tui/sessions_screen.py` (NEW) - thread list UI | **PORTED** | Resume/delete past conversations |
| `system_prompt.md` (NEW) - template extraction | **PORTED** | Static boilerplate → Markdown with `{variable}` placeholders |
| `agent.py` - model identity injection | **PORTED** | `"You are powered by {model_name} via {provider}."` |
| `agent.py` - `/tmp` virtual routing | **PORTED** | `FilesystemBackend(virtual_mode=True)` route for large results |
| `config.py` - shell allow-list | **PORTED** | `DEFAULT_SHELL_ALLOW_LIST` + `is_command_allowed()` + custom `.sdrbot/shell_allowlist.json` |
| `execution.py` - auto-approve safe commands | **PORTED** | Allow-listed shell commands skip HITL prompt |
| `subagents/loader.py` (NEW) - YAML frontmatter parser | **PORTED** | Regex-based, scans built-in + project-level `.md` definitions |
| `deep_agent.py` - auto-discover subagents | **PORTED** | Scans `sdrbot_cli/subagents/*.md` and `.sdrbot/subagents/*.md` |
| `non_interactive.py` (NEW) - headless mode | **PORTED** | `run_non_interactive()` with text/JSON output, stdin piping |
| `main.py` - `--non-interactive/-n`, `--prompt/-p` flags | **PORTED** | + `--output-format`, `--max-turns` |
| Upstream TUI migration (Textual) | ALREADY HAVE | We did this independently |
| Various upstream CLI-only features (`--model` flag etc.) | SKIP | We use TUI with model.json |

**New files**:
- [x] `sdrbot_cli/clipboard.py`
- [x] `sdrbot_cli/sessions.py`
- [x] `sdrbot_cli/system_prompt.md`
- [x] `sdrbot_cli/non_interactive.py`
- [x] `sdrbot_cli/subagents/loader.py`
- [x] `sdrbot_cli/tui/sessions_screen.py`

**New test files**:
- [x] `tests/test_file_ops.py` (11 tests)
- [x] `tests/test_image_utils.py` (3 tests)
- [x] `tests/test_provider_detection.py` (19 tests)
- [x] `tests/test_clipboard.py` (2 tests)
- [x] `tests/test_sessions.py` (4 tests)
- [x] `tests/test_system_prompt.py` (5 tests)
- [x] `tests/test_shell_allowlist.py` (26 tests)
- [x] `tests/test_subagent_loader.py` (10 tests)
- [x] `tests/test_non_interactive.py` (2 tests)

**Dependencies added**:
- `aiosqlite>=0.19.0`
- `langgraph-checkpoint-sqlite>=1.0.0`

**Test results**: 141 tests pass (79 new + 62 existing), 0 regressions.

---

<!-- Template for future reviews:

### X.X.X Review Notes (YYYY-MM-DD)

**Summary**: [One sentence summary of action taken]

| Change | Status | Notes |
|--------|--------|-------|
| `file.py` - feature name | PORT/ADAPT/SKIP/ALREADY HAVE | Details |

**Ported changes**:
- [ ] Change 1
- [ ] Change 2

**Skipped** (with reason):
- Change X: reason

-->

## Important Notes

1. **Never merge upstream directly** - The import renaming and architectural differences make git merge useless

2. **Focus on the `deepagents` library** - The core `deepagents` package (not `deepagents-cli`) is a pip dependency. Library updates come through normal dependency updates.

3. **Test after porting** - Always run `make test` after porting changes

4. **Document what you port** - Update the Version History table above when porting changes
