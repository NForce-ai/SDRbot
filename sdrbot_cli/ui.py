"""UI rendering and display utilities for the CLI."""

import json
import re
import shutil
from pathlib import Path
from typing import Any

from rich.console import RenderableType
from rich.markup import escape
from rich.text import Text

from .config import COLORS, COMMANDS, DEEP_AGENTS_ASCII, MAX_ARG_LENGTH
from .file_ops import FileOperationRecord


def truncate_value(value: str, max_length: int = MAX_ARG_LENGTH) -> str:
    """Truncate a string value if it exceeds max_length."""
    if len(value) > max_length:
        return value[:max_length] + "..."
    return value


def format_tool_display(tool_name: str, tool_args: dict) -> str:
    """Format tool calls for display with tool-specific smart formatting.

    Shows the most relevant information for each tool type rather than all arguments.

    Args:
        tool_name: Name of the tool being called
        tool_args: Dictionary of tool arguments

    Returns:
        Formatted string for display (e.g., "read_file(config.py)")

    Examples:
        read_file(path="/long/path/file.py") → "read_file(file.py)"
        shell(command="pip install foo") → 'shell("pip install foo")'
    """

    def abbreviate_path(path_str: str, max_length: int = 60) -> str:
        """Abbreviate a file path intelligently - show basename or relative path."""
        try:
            path = Path(path_str)

            # If it's just a filename (no directory parts), return as-is
            if len(path.parts) == 1:
                return path_str

            # Try to get relative path from current working directory
            try:
                rel_path = path.relative_to(Path.cwd())
                rel_str = str(rel_path)
                # Use relative if it's shorter and not too long
                if len(rel_str) < len(path_str) and len(rel_str) <= max_length:
                    return rel_str
            except (ValueError, Exception):
                pass

            # If absolute path is reasonable length, use it
            if len(path_str) <= max_length:
                return path_str

            # Otherwise, just show basename (filename only)
            return path.name
        except Exception:
            # Fallback to original string if any error
            return truncate_value(path_str, max_length)

    # Tool-specific formatting - show the most important argument(s)
    if tool_name in ("read_file", "write_file", "edit_file"):
        # File operations: show the primary file path argument (file_path or path)
        path_value = tool_args.get("file_path")
        if path_value is None:
            path_value = tool_args.get("path")
        if path_value is not None:
            path = abbreviate_path(str(path_value))
            return f"{tool_name}({path})"

    elif tool_name == "grep":
        # Grep: show the search pattern
        if "pattern" in tool_args:
            pattern = str(tool_args["pattern"])
            pattern = truncate_value(pattern, 70)
            return f'{tool_name}("{pattern}")'

    elif tool_name == "shell":
        # Shell: show the command being executed
        if "command" in tool_args:
            command = str(tool_args["command"])
            command = truncate_value(command, 120)
            return f'{tool_name}("{command}")'

    elif tool_name == "ls":
        # ls: show directory, or empty if current directory
        if tool_args.get("path"):
            path = abbreviate_path(str(tool_args["path"]))
            return f"{tool_name}({path})"
        return f"{tool_name}()"

    elif tool_name == "glob":
        # Glob: show the pattern
        if "pattern" in tool_args:
            pattern = str(tool_args["pattern"])
            pattern = truncate_value(pattern, 80)
            return f'{tool_name}("{pattern}")'

    elif tool_name == "http_request":
        # HTTP: show method and URL
        parts = []
        if "method" in tool_args:
            parts.append(str(tool_args["method"]).upper())
        if "url" in tool_args:
            url = str(tool_args["url"])
            url = truncate_value(url, 80)
            parts.append(url)
        if parts:
            return f"{tool_name}({' '.join(parts)})"

    elif tool_name == "fetch_url":
        # Fetch URL: show the URL being fetched
        if "url" in tool_args:
            url = str(tool_args["url"])
            url = truncate_value(url, 80)
            return f'{tool_name}("{url}")'

    elif tool_name == "task":
        # Task: show the task description
        if "description" in tool_args:
            desc = str(tool_args["description"])
            desc = truncate_value(desc, 100)
            return f'{tool_name}("{desc}")'

    elif tool_name == "write_todos":
        # Todos: show count of items
        if "todos" in tool_args and isinstance(tool_args["todos"], list):
            count = len(tool_args["todos"])
            return f"{tool_name}({count} items)"

    # Fallback: generic formatting for unknown tools
    # Show all arguments in key=value format
    args_str = ", ".join(f"{k}={truncate_value(str(v), 50)}" for k, v in tool_args.items())
    return f"{tool_name}({args_str})"


def format_tool_message_content(content: Any) -> str:
    """Convert ToolMessage content into a printable string."""
    if content is None:
        return ""
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            else:
                try:
                    parts.append(json.dumps(item))
                except Exception:
                    parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def format_token_count(tokens: int) -> str:
    """Format token count with abbreviation (e.g., 1.2k, 150k, 1.1m)."""
    if tokens >= 1_000_000:
        value = tokens / 1_000_000
        return f"{value:.1f}m" if value < 10 else f"{int(value)}m"
    elif tokens >= 1_000:
        value = tokens / 1_000
        return f"{value:.1f}k" if value < 10 else f"{int(value)}k"
    return str(tokens)


class TokenTracker:
    """Track token usage across the conversation.

    Tracks both current context (for compaction) and cumulative session usage.
    """

    def __init__(self) -> None:
        self.current_context = 0  # Current context window size (for /context)
        self.total_session_tokens = 0  # Cumulative tokens used (for UI display)
        self.last_output = 0

    def reset(self) -> None:
        """Reset to 0 (for /clear command)."""
        self.current_context = 0
        self.total_session_tokens = 0
        self.last_output = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        """Update token tracking after a response.

        Args:
            input_tokens: Total input tokens reported by API
            output_tokens: Tokens generated by assistant
        """
        # Current context = what was sent + what was generated (overwrites)
        self.current_context = input_tokens + output_tokens
        # Session total accumulates
        self.total_session_tokens += input_tokens + output_tokens
        self.last_output = output_tokens

    def format_session_total(self) -> str:
        """Get abbreviated session total for UI display."""
        return format_token_count(self.total_session_tokens)


def render_todo_list(todos: list[dict]) -> str | None:
    """Render todo list as formatted text with checkboxes.

    Returns plain markup text (not a Panel) to avoid nested borders
    when displayed in a Textual container with its own border.
    """
    if not todos:
        return None

    lines = []
    for todo in todos:
        status = todo.get("status", "pending")
        content = todo.get("content", "")

        if status == "completed":
            icon = "[#24FF6A]✔[/#24FF6A]"
            style = "#24FF6A dim"
        elif status == "in_progress":
            icon = "[cyan bold]▶[/cyan bold]"
            style = "white"
        else:  # pending
            icon = "[dim]○[/dim]"
            style = "dim"

        lines.append(f"{icon} [{style}]{content}[/{style}]")

    return "\n".join(lines)


def _format_line_span(start: int | None, end: int | None) -> str:
    if start is None and end is None:
        return ""
    if start is not None and end is None:
        return f"(starting at line {start})"
    if start is None and end is not None:
        return f"(through line {end})"
    if start == end:
        return f"(line {start})"
    return f"(lines {start}-{end})"


def render_file_operation(record: FileOperationRecord) -> list[RenderableType]:
    """Render a concise summary of a filesystem tool call."""
    output_renderables = []
    label_lookup = {
        "read_file": "Read",
        "write_file": "Write",
        "edit_file": "Update",
    }
    label = label_lookup.get(record.tool_name, record.tool_name)
    header = Text()
    header.append("⏺ ", style=COLORS["tool"])
    header.append(f"{label}({record.display_path})", style=f"bold {COLORS['tool']}")
    output_renderables.append(header)

    def _get_detail_text(message: str, *, style: str = COLORS["dim"]) -> Text:
        detail = Text()
        detail.append("  ⎿  ", style=style)
        detail.append(message, style=style)
        return detail

    if record.status == "error":
        output_renderables.append(
            _get_detail_text(record.error or "Error executing file operation", style="red")
        )
        return output_renderables

    if record.tool_name == "read_file":
        lines = record.metrics.lines_read
        span = _format_line_span(record.metrics.start_line, record.metrics.end_line)
        detail = f"Read {lines} line{'s' if lines != 1 else ''}"
        if span:
            detail = f"{detail} {span}"
        detail = f"Read {lines} line{'s' if lines != 1 else ''}"
        if span:
            detail = f"{detail} {span}"
        output_renderables.append(_get_detail_text(detail))
    else:
        if record.tool_name == "write_file":
            added = record.metrics.lines_added
            removed = record.metrics.lines_removed
            lines = record.metrics.lines_written
            detail = f"Wrote {lines} line{'s' if lines != 1 else ''}"
            if added or removed:
                detail = f"{detail} (+{added} / -{removed})"
        else:
            added = record.metrics.lines_added
            removed = record.metrics.lines_removed
            detail = f"Edited {record.metrics.lines_written} total line{'s' if record.metrics.lines_written != 1 else ''}"
            if added or removed:
                detail = f"{detail} (+{added} / -{removed})"
        output_renderables.append(_get_detail_text(detail))

    # Skip diff display for HIL-approved operations that succeeded
    # (user already saw the diff during approval)
    if record.diff and not (record.hitl_approved and record.status == "success"):
        output_renderables.extend(render_diff(record))

    return output_renderables


def render_diff(record: FileOperationRecord) -> list[RenderableType]:
    """Render diff for a file operation."""
    if not record.diff:
        return []
    return render_diff_block(record.diff, f"Diff {record.display_path}")


def _wrap_diff_line(
    code: str,
    marker: str,
    color: str,
    line_num: int | None,
    width: int,
    term_width: int,
) -> list[str]:
    """Wrap long diff lines with proper indentation.

    Args:
        code: Code content to wrap
        marker: Diff marker ('+', '-', ' ')
        color: Color for the line
        line_num: Line number to display (None for continuation lines)
        width: Width for line number column
        term_width: Terminal width

    Returns:
        List of formatted lines (may be multiple if wrapped)
    """
    # Escape Rich markup in code content
    code = escape(code)

    prefix_len = width + 4  # line_num + space + marker + 2 spaces
    available_width = term_width - prefix_len

    if len(code) <= available_width:
        if line_num is not None:
            return [f"[dim]{line_num:>{width}}[/dim] [{color}]{marker}  {code}[/{color}]"]
        return [f"{' ' * width} [{color}]{marker}  {code}[/{color}]"]

    lines = []
    remaining = code
    first = True

    while remaining:
        if len(remaining) <= available_width:
            chunk = remaining
            remaining = ""
        else:
            # Try to break at a good point (space, comma, etc.)
            chunk = remaining[:available_width]
            # Look for a good break point in the last 20 chars
            break_point = max(
                chunk.rfind(" "),
                chunk.rfind(","),
                chunk.rfind("("),
                chunk.rfind(")"),
            )
            if break_point > available_width - 20:
                # Found a good break point
                chunk = remaining[: break_point + 1]
                remaining = remaining[break_point + 1 :]
            else:
                # No good break point, just split
                chunk = remaining[:available_width]
                remaining = remaining[available_width:]

        if first and line_num is not None:
            lines.append(f"[dim]{line_num:>{width}}[/dim] [{color}]{marker}  {chunk}[/{color}]")
            first = False
        else:
            lines.append(f"{' ' * width} [{color}]{marker}  {chunk}[/{color}]")

    return lines


def format_diff_rich(diff_lines: list[str]) -> str:
    """Format diff lines with line numbers and colors.

    Args:
        diff_lines: Diff lines from unified diff

    Returns:
        Rich-formatted diff string with line numbers
    """
    if not diff_lines:
        return "[dim]No changes detected[/dim]"

    # Get terminal width
    term_width = shutil.get_terminal_size().columns

    # Find max line number for width calculation
    max_line = max(
        (
            int(m.group(i))
            for line in diff_lines
            if (m := re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)", line))
            for i in (1, 2)
        ),
        default=0,
    )
    width = max(3, len(str(max_line)))

    formatted_lines = []
    old_num = new_num = 0

    # Rich colors with backgrounds for better visibility
    # White text on dark backgrounds for additions/deletions
    addition_color = "white on dark_green"
    deletion_color = "white on dark_red"
    context_color = "dim"

    for line in diff_lines:
        if line.strip() == "...":
            formatted_lines.append(f"[{context_color}]...[/{context_color}]")
        elif line.startswith(("---", "+++")):
            continue
        elif m := re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)", line):
            old_num, new_num = int(m.group(1)), int(m.group(2))
        elif line.startswith("-"):
            formatted_lines.extend(
                _wrap_diff_line(line[1:], "-", deletion_color, old_num, width, term_width)
            )
            old_num += 1
        elif line.startswith("+"):
            formatted_lines.extend(
                _wrap_diff_line(line[1:], "+", addition_color, new_num, width, term_width)
            )
            new_num += 1
        elif line.startswith(" "):
            formatted_lines.extend(
                _wrap_diff_line(line[1:], " ", context_color, old_num, width, term_width)
            )
            old_num += 1
            new_num += 1

    return "\n".join(formatted_lines)


def render_diff_block(diff: str, title: str) -> list[RenderableType]:
    """Render a diff string with line numbers and colors."""
    output_renderables = []
    try:
        # Parse diff into lines and format with line numbers
        diff_lines = diff.splitlines()
        formatted_diff = format_diff_rich(diff_lines)

        # Print with a simple header
        output_renderables.append(Text(""))
        output_renderables.append(
            Text(f"[bold {COLORS['primary']}]═══ {title} ═══[/bold {COLORS['primary']}]")
        )
        output_renderables.append(Text(formatted_diff))
        output_renderables.append(Text(""))
    except (ValueError, AttributeError, IndexError, OSError):
        # Fallback to simple rendering if formatting fails
        output_renderables.append(Text(""))
        output_renderables.append(
            Text(f"[bold {COLORS['primary']}]{title}[/bold {COLORS['primary']}]")
        )
        output_renderables.append(Text(diff))
        output_renderables.append(Text(""))
    return output_renderables


def show_interactive_help() -> list[RenderableType]:
    """Show available commands during interactive session."""
    output_renderables = []
    output_renderables.append(Text(""))
    output_renderables.append(Text("[bold]Interactive Commands:[/bold]", style=COLORS["primary"]))
    output_renderables.append(Text(""))

    for cmd, desc in COMMANDS.items():
        output_renderables.append(Text(f"  /{cmd:<12} {desc}", style=COLORS["dim"]))

    output_renderables.append(Text(""))
    output_renderables.append(Text("[bold]Editing Features:[/bold]", style=COLORS["primary"]))
    output_renderables.append(Text("  Enter           Submit your message", style=COLORS["dim"]))
    output_renderables.append(
        Text(
            "  Alt+Enter       Insert newline (Option+Enter on Mac, or ESC then Enter)",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text("  Ctrl+E          Open in external editor (nano by default)", style=COLORS["dim"])
    )
    output_renderables.append(
        Text("  Ctrl+T          Toggle auto-approve mode", style=COLORS["dim"])
    )
    output_renderables.append(Text("  Arrow keys      Navigate input", style=COLORS["dim"]))
    output_renderables.append(
        Text("  Ctrl+C          Cancel input or interrupt agent mid-work", style=COLORS["dim"])
    )
    output_renderables.append(Text(""))
    output_renderables.append(Text("[bold]Special Features:[/bold]", style=COLORS["primary"]))
    output_renderables.append(
        Text(
            "  @filename       Type @ to auto-complete files and inject content",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text("  /command        Type / to see available commands", style=COLORS["dim"])
    )
    output_renderables.append(
        Text(
            "  !command        Type ! to run bash commands (e.g., !ls, !git status)",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text("                  Completions appear automatically as you type", style=COLORS["dim"])
    )
    output_renderables.append(Text(""))
    output_renderables.append(Text("[bold]Auto-Approve Mode:[/bold]", style=COLORS["primary"]))
    output_renderables.append(
        Text("  Ctrl+T          Toggle auto-approve mode", style=COLORS["dim"])
    )
    output_renderables.append(
        Text(
            "  --auto-approve  Start CLI with auto-approve enabled (via command line)",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text(
            "  When enabled, tool actions execute without confirmation prompts", style=COLORS["dim"]
        )
    )
    output_renderables.append(Text(""))

    output_renderables.append(Text("[bold]Configuration Commands:[/bold]", style=COLORS["primary"]))
    output_renderables.append(
        Text("  /setup                      Open full setup wizard", style=COLORS["dim"])
    )
    output_renderables.append(
        Text("  /models                     Configure LLM provider and model", style=COLORS["dim"])
    )
    output_renderables.append(
        Text(
            "  /integrations               Configure CRM and service integrations",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text("  /mcp                        Configure MCP server connections", style=COLORS["dim"])
    )
    output_renderables.append(
        Text(
            "  /sync [name]                Re-sync service schema (all or specific)",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(Text(""))

    output_renderables.append(Text("[bold]Agent Commands:[/bold]", style=COLORS["primary"]))
    output_renderables.append(
        Text("  sdrbot --agent NAME         Start with a specific agent", style=COLORS["dim"])
    )
    output_renderables.append(
        Text("  sdrbot list                 List all available agents", style=COLORS["dim"])
    )
    output_renderables.append(
        Text("  sdrbot reset --agent NAME   Reset agent to default prompt", style=COLORS["dim"])
    )
    output_renderables.append(Text(""))

    output_renderables.append(Text("[bold]Skills Commands:[/bold]", style=COLORS["primary"]))
    output_renderables.append(
        Text("  sdrbot skills list          List available skills", style=COLORS["dim"])
    )
    output_renderables.append(
        Text("  sdrbot skills create NAME   Create a new skill", style=COLORS["dim"])
    )
    output_renderables.append(
        Text("  sdrbot skills info NAME     Show skill details", style=COLORS["dim"])
    )
    output_renderables.append(Text(""))

    output_renderables.append(Text("[bold]Local Data Folders:[/bold]", style=COLORS["primary"]))
    output_renderables.append(
        Text("  ./agents/       Agent prompt files (e.g., agent.md)", style=COLORS["dim"])
    )
    output_renderables.append(
        Text(
            "  ./skills/       Custom skills (created via 'sdrbot skills create')",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text("  ./files/        Agent-generated exports, reports, CSVs", style=COLORS["dim"])
    )
    output_renderables.append(
        Text(
            "  ./generated/    Schema-synced CRM tools (created on /services sync)",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text("  ./.sdrbot/      Service configuration (services.json)", style=COLORS["dim"])
    )
    output_renderables.append(Text(""))
    return output_renderables


def show_help() -> list[RenderableType]:
    """Show help information."""
    output_renderables = []
    output_renderables.append(Text(""))
    output_renderables.append(Text(DEEP_AGENTS_ASCII, style=f"bold {COLORS['primary']}"))
    output_renderables.append(Text(""))

    output_renderables.append(Text("[bold]Usage:[/bold]", style=COLORS["primary"]))
    output_renderables.append(
        Text("  deepagents [OPTIONS]                           Start interactive session")
    )
    output_renderables.append(
        Text("  deepagents list                                List all available agents")
    )
    output_renderables.append(
        Text("  deepagents reset --agent AGENT                 Reset agent to default prompt")
    )
    output_renderables.append(
        Text(
            "  deepagents reset --agent AGENT --target SOURCE Reset agent to copy of another agent"
        )
    )
    output_renderables.append(
        Text("  deepagents help                                Show this help message")
    )
    output_renderables.append(Text(""))

    output_renderables.append(Text("[bold]Options:[/bold]", style=COLORS["primary"]))
    output_renderables.append(
        Text("  --agent NAME                  Agent identifier (default: agent)")
    )
    output_renderables.append(
        Text("  --auto-approve                Auto-approve tool usage without prompting")
    )
    output_renderables.append(
        Text(
            "  --sandbox TYPE                Remote sandbox for execution (modal, runloop, daytona)"
        )
    )
    output_renderables.append(
        Text("  --sandbox-id ID               Reuse existing sandbox (skips creation/cleanup)")
    )
    output_renderables.append(Text(""))

    output_renderables.append(Text("[bold]Examples:[/bold]", style=COLORS["primary"]))
    output_renderables.append(
        Text(
            "  deepagents                              # Start with default agent",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text(
            "  deepagents --agent mybot                # Start with agent named 'mybot'",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text(
            "  deepagents --auto-approve               # Start with auto-approve enabled",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text(
            "  deepagents --sandbox runloop            # Execute code in Runloop sandbox",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text(
            "  deepagents --sandbox modal              # Execute code in Modal sandbox",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text(
            "  deepagents --sandbox runloop --sandbox-id dbx_123  # Reuse existing sandbox",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text("  deepagents list                         # List all agents", style=COLORS["dim"])
    )
    output_renderables.append(
        Text(
            "  deepagents reset --agent mybot          # Reset mybot to default",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text(
            "  deepagents reset --agent mybot --target other # Reset mybot to copy of 'other' agent",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(Text(""))

    output_renderables.append(Text("[bold]Long-term Memory:[/bold]", style=COLORS["primary"]))
    output_renderables.append(
        Text(
            "  By default, long-term memory is ENABLED using agent name 'agent'.",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(Text("  Memory includes:", style=COLORS["dim"]))
    output_renderables.append(
        Text("  - Persistent agent.md file with your instructions", style=COLORS["dim"])
    )
    output_renderables.append(
        Text("  - /memories/ folder for storing context across sessions", style=COLORS["dim"])
    )
    output_renderables.append(Text(""))

    output_renderables.append(Text("[bold]Agent Storage:[/bold]", style=COLORS["primary"]))
    output_renderables.append(
        Text("  Agents are stored in: ./agents/AGENT_NAME/", style=COLORS["dim"])
    )
    output_renderables.append(
        Text("  Each agent has an agent.md file containing its prompt", style=COLORS["dim"])
    )
    output_renderables.append(Text(""))

    output_renderables.append(Text("[bold]Interactive Features:[/bold]", style=COLORS["primary"]))
    output_renderables.append(Text("  Enter           Submit your message", style=COLORS["dim"]))
    output_renderables.append(
        Text(
            "  Alt+Enter       Insert newline for multi-line (Option+Enter or ESC then Enter)",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text("  Ctrl+J          Insert newline (alternative)", style=COLORS["dim"])
    )
    output_renderables.append(
        Text("  Ctrl+T          Toggle auto-approve mode", style=COLORS["dim"])
    )
    output_renderables.append(Text("  Arrow keys      Navigate input", style=COLORS["dim"]))
    output_renderables.append(
        Text(
            "  @filename       Type @ to auto-complete files and inject content",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text(
            "  /command        Type / to see available commands (auto-completes)",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(Text(""))

    output_renderables.append(Text("[bold]Interactive Commands:[/bold]", style=COLORS["primary"]))
    output_renderables.append(
        Text("  /help           Show available commands and features", style=COLORS["dim"])
    )
    output_renderables.append(
        Text("  /clear          Clear screen and reset conversation", style=COLORS["dim"])
    )
    output_renderables.append(
        Text("  /context        Show context usage and compaction status", style=COLORS["dim"])
    )
    output_renderables.append(Text("  /quit, /exit    Exit the session", style=COLORS["dim"]))
    output_renderables.append(
        Text("  quit, exit, q   Exit the session (just type and press Enter)", style=COLORS["dim"])
    )
    output_renderables.append(Text(""))

    output_renderables.append(Text("[bold]Configuration Commands:[/bold]", style=COLORS["primary"]))
    output_renderables.append(
        Text("  /setup                      Open full setup wizard", style=COLORS["dim"])
    )
    output_renderables.append(
        Text("  /models                     Configure LLM provider and model", style=COLORS["dim"])
    )
    output_renderables.append(
        Text(
            "  /integrations               Configure CRM and service integrations",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text("  /mcp                        Configure MCP server connections", style=COLORS["dim"])
    )
    output_renderables.append(
        Text(
            "  /sync [name]                Re-sync service schema (all or specific)",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(Text(""))

    output_renderables.append(Text("[bold]Agent Commands:[/bold]", style=COLORS["primary"]))
    output_renderables.append(
        Text("  sdrbot --agent NAME         Start with a specific agent", style=COLORS["dim"])
    )
    output_renderables.append(
        Text("  sdrbot list                 List all available agents", style=COLORS["dim"])
    )
    output_renderables.append(
        Text("  sdrbot reset --agent NAME   Reset agent to default prompt", style=COLORS["dim"])
    )
    output_renderables.append(Text(""))

    output_renderables.append(Text("[bold]Skills Commands:[/bold]", style=COLORS["primary"]))
    output_renderables.append(
        Text("  sdrbot skills list          List available skills", style=COLORS["dim"])
    )
    output_renderables.append(
        Text("  sdrbot skills create NAME   Create a new skill", style=COLORS["dim"])
    )
    output_renderables.append(
        Text("  sdrbot skills info NAME     Show skill details", style=COLORS["dim"])
    )
    output_renderables.append(Text(""))

    output_renderables.append(Text("[bold]Local Data Folders:[/bold]", style=COLORS["primary"]))
    output_renderables.append(
        Text("  ./agents/       Agent prompt files (e.g., agent.md)", style=COLORS["dim"])
    )
    output_renderables.append(
        Text(
            "  ./skills/       Custom skills (created via 'sdrbot skills create')",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text("  ./files/        Agent-generated exports, reports, CSVs", style=COLORS["dim"])
    )
    output_renderables.append(
        Text(
            "  ./generated/    Schema-synced CRM tools (created on /services sync)",
            style=COLORS["dim"],
        )
    )
    output_renderables.append(
        Text("  ./.sdrbot/      Service configuration (services.json)", style=COLORS["dim"])
    )
    output_renderables.append(Text(""))
    return output_renderables
