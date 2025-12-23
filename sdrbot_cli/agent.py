"""Agent management and creation for the CLI."""

import os
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.sandbox import SandboxBackendProtocol
from langchain.agents.middleware import (
    InterruptOnConfig,
)
from langchain.agents.middleware.types import AgentState
from langchain.messages import ToolCall
from langchain.tools import BaseTool
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.pregel import Pregel
from langgraph.runtime import Runtime

from sdrbot_cli.agent_memory import AgentMemoryMiddleware
from sdrbot_cli.config import COLORS, config, console, get_default_coding_instructions, settings
from sdrbot_cli.integrations.sandbox_factory import get_default_working_dir
from sdrbot_cli.mcp.manager import get_mcp_manager
from sdrbot_cli.memory_tools import create_memory_tools
from sdrbot_cli.services import get_enabled_tools
from sdrbot_cli.shell import ShellMiddleware
from sdrbot_cli.skills import SkillsMiddleware
from sdrbot_cli.skills.load import list_skills
from sdrbot_cli.tracing import get_tracing_callbacks


def list_agents() -> None:
    """List all available agents."""
    agents_dir = settings.agents_dir

    if not agents_dir.exists():
        console.print("[yellow]No agents found.[/yellow]")
        console.print(
            "[dim]Agents will be created in ./agents/ when you first use them.[/dim]",
            style=COLORS["dim"],
        )
        return

    agent_dirs = [d for d in agents_dir.iterdir() if d.is_dir()]
    if not agent_dirs:
        console.print("[yellow]No agents found.[/yellow]")
        console.print(
            "[dim]Agents will be created in ./agents/ when you first use them.[/dim]",
            style=COLORS["dim"],
        )
        return

    console.print("\n[bold]Available Agents:[/bold]\n", style=COLORS["primary"])

    for agent_dir in sorted(agent_dirs):
        agent_name = agent_dir.name
        display_name = "default" if agent_name == "agent" else agent_name
        console.print(f"  • [bold]{display_name}[/bold]", style=COLORS["primary"])
        console.print(f"    {agent_dir}", style=COLORS["dim"])

    console.print()


def reset_agent(agent_name: str, source_agent: str | None = None) -> None:
    """Reset an agent to default or copy from another agent."""
    if source_agent:
        source_prompt = settings.get_agent_prompt_path(source_agent)

        if not source_prompt.exists():
            console.print(
                f"[bold red]Error:[/bold red] Source agent '{source_agent}' not found "
                f"at {source_prompt}"
            )
            return

        source_content = source_prompt.read_text()
        action_desc = f"contents of agent '{source_agent}'"
    else:
        source_content = get_default_coding_instructions()
        action_desc = "default"

    settings.ensure_agent_prompt(agent_name, source_content)

    agent_dir = settings.get_agent_dir(agent_name)
    console.print(f"✓ Agent '{agent_name}' reset to {action_desc}", style=COLORS["primary"])
    console.print(f"Location: {agent_dir}\n", style=COLORS["dim"])


def get_system_prompt(assistant_id: str, sandbox_type: str | None = None) -> str:
    """Get the base system prompt for the agent.

    Args:
        assistant_id: The agent identifier for path references
        sandbox_type: Type of sandbox provider ("modal", "runloop", "daytona").
                     If None, agent is operating in local mode.

    Returns:
        The system prompt string (without agent.md content)
    """
    skills_dir = settings.get_skills_dir()

    if sandbox_type:
        # Get provider-specific working directory

        working_dir = get_default_working_dir(sandbox_type)

        working_dir_section = f"""### Current Working Directory

You are operating in a **remote Linux sandbox** at `{working_dir}`.

All code execution and file operations happen in this sandbox environment.

**Important:**
- The CLI is running locally on the user's machine, but you execute code remotely
- Use `{working_dir}` as your working directory for all operations

"""
    else:
        cwd = Path.cwd()
        working_dir_section = f"""<env>
Working directory: {cwd}
</env>

### Current Working Directory

The filesystem backend is currently operating in: `{cwd}`

### File System and Paths

**IMPORTANT - Path Handling:**
- All file paths must be absolute paths (e.g., `{cwd}/file.txt`)
- Use the working directory from <env> to construct absolute paths
- Example: To create a file in your working directory, use `{cwd}/research_project/file.md`
- Never use relative paths - always construct full absolute paths

"""

    return (
        working_dir_section
        + f"""### Skills Directory

Skills are stored at: `{skills_dir}/`
Skills may contain scripts or supporting files. When executing skill scripts with bash, use the real filesystem path:
Example: `bash python {skills_dir}/web-research/script.py`

### Human-in-the-Loop Tool Approval

Some tool calls require user approval before execution. When a tool call is rejected by the user:
1. Accept their decision immediately - do NOT retry the same command
2. Explain that you understand they rejected the action
3. Suggest an alternative approach or ask for clarification
4. Never attempt the exact same rejected command again

Respect the user's decisions and work with them collaboratively.

### Action Plan Management

If the user explicitly asks you to plan something, or if you're being asked to carry out a task with more than 3 steps, use the write_todos tool to document the plan and present it to them.

If you do use the write_todos:
1. Aim for 3-6 action items unless the task is truly complex in which case its fine to plan more extensively.
2. Update the plan status as you complete each item.
3. You can keep your final response succint since the plan will be presented to them in a separate widget.
"""
        + _get_enabled_services_prompt()
    )


def _get_enabled_services_prompt() -> str:
    """Generate runtime prompt section for enabled services."""
    from sdrbot_cli.services.registry import load_config

    config = load_config()
    enabled = [
        s for s in ["hubspot", "salesforce", "attio", "lusha", "hunter"] if config.is_enabled(s)
    ]

    if not enabled:
        return """### Services

No CRM services are enabled. Use `/services enable <name>` to enable a service.
"""

    # Build the services section dynamically
    lines = ["### Enabled Services\n"]

    # Count CRMs for the single-CRM rule
    crm_services = [s for s in enabled if s in ["hubspot", "salesforce", "attio"]]

    if len(crm_services) == 1:
        lines.append(
            f"**CRM:** {crm_services[0].title()} (use this for all CRM operations - don't ask which CRM)\n"
        )
    elif len(crm_services) > 1:
        lines.append(f"**CRMs:** {', '.join(s.title() for s in crm_services)}\n")

    # Add enrichment services
    enrichment = [s for s in enabled if s in ["lusha", "hunter"]]
    if enrichment:
        lines.append(f"**Enrichment:** {', '.join(s.title() for s in enrichment)}\n")

    lines.append(
        "\nUse the available tools directly. Each tool's docstring shows exact field names and types."
    )

    # Add service-specific tips
    if "salesforce" in enabled:
        lines.append("\n**Salesforce tip:** Use `salesforce_soql_query` for complex queries.")
    if "hubspot" in enabled:
        lines.append(
            "\n**HubSpot tip:** Use `hubspot_create_association` to link records between objects."
        )
    if "lusha" in enabled:
        lines.append("\n**Lusha tip:** Find -> Enrich -> Create in CRM workflow.")
    if "hunter" in enabled:
        lines.append(
            "\n**Hunter tip:** Verify emails with `hunter_email_verifier` before adding to CRM."
        )

    return "\n".join(lines)


def _format_write_file_description(
    tool_call: ToolCall, _state: AgentState, _runtime: Runtime
) -> str:
    """Format write_file tool call for approval prompt."""
    args = tool_call["args"]
    file_path = args.get("file_path", "unknown")
    content = args.get("content", "")

    action = "Overwrite" if Path(file_path).exists() else "Create"
    line_count = len(content.splitlines())

    return f"File: {file_path}\nAction: {action} file\nLines: {line_count}"


def _format_edit_file_description(
    tool_call: ToolCall, _state: AgentState, _runtime: Runtime
) -> str:
    """Format edit_file tool call for approval prompt."""
    args = tool_call["args"]
    file_path = args.get("file_path", "unknown")
    replace_all = bool(args.get("replace_all", False))

    return (
        f"File: {file_path}\n"
        f"Action: Replace text ({'all occurrences' if replace_all else 'single occurrence'})"
    )


def _format_fetch_url_description(
    tool_call: ToolCall, _state: AgentState, _runtime: Runtime
) -> str:
    """Format fetch_url tool call for approval prompt."""
    args = tool_call["args"]
    url = args.get("url", "unknown")
    timeout = args.get("timeout", 30)

    return f"URL: {url}\nTimeout: {timeout}s\n\n⚠️  Will fetch and convert web content to markdown"


def _format_task_description(tool_call: ToolCall, _state: AgentState, _runtime: Runtime) -> str:
    """Format task (subagent) tool call for approval prompt.

    The task tool signature is: task(description: str, subagent_type: str)
    The description contains all instructions that will be sent to the subagent.
    """
    args = tool_call["args"]
    description = args.get("description", "unknown")
    subagent_type = args.get("subagent_type", "unknown")

    # Truncate description if too long for display
    description_preview = description
    if len(description) > 500:
        description_preview = description[:500] + "..."

    return (
        f"Subagent Type: {subagent_type}\n\n"
        f"Task Instructions:\n"
        f"{'─' * 40}\n"
        f"{description_preview}\n"
        f"{'─' * 40}\n\n"
        f"⚠️  Subagent will have access to file operations and shell commands"
    )


def _format_shell_description(tool_call: ToolCall, _state: AgentState, _runtime: Runtime) -> str:
    """Format shell tool call for approval prompt."""
    args = tool_call["args"]
    command = args.get("command", "N/A")
    return f"Shell Command: {command}\nWorking Directory: {Path.cwd()}"


def _format_execute_description(tool_call: ToolCall, _state: AgentState, _runtime: Runtime) -> str:
    """Format execute tool call for approval prompt."""
    args = tool_call["args"]
    command = args.get("command", "N/A")
    return f"Execute Command: {command}\nLocation: Remote Sandbox"


def _add_interrupt_on() -> dict[str, InterruptOnConfig]:
    """Configure human-in-the-loop interrupt_on settings for destructive tools."""
    shell_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_shell_description,
    }

    execute_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_execute_description,
    }

    write_file_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_write_file_description,
    }

    edit_file_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_edit_file_description,
    }

    fetch_url_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_fetch_url_description,
    }

    task_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_task_description,
    }

    # Note: Service tool interrupts are dynamically registered in create_agent_with_config()
    # based on the tools returned by get_enabled_tools()

    return {
        "shell": shell_interrupt_config,
        "execute": execute_interrupt_config,
        "write_file": write_file_interrupt_config,
        "edit_file": edit_file_interrupt_config,
        "fetch_url": fetch_url_interrupt_config,
        "task": task_interrupt_config,
    }


def create_agent_with_config(
    model: str | BaseChatModel,
    assistant_id: str,
    tools: list[BaseTool],
    *,
    sandbox: SandboxBackendProtocol | None = None,
    sandbox_type: str | None = None,
) -> tuple[Pregel, CompositeBackend]:
    """Create and configure an agent with the specified model and tools.

    Args:
        model: LLM model to use
        assistant_id: Agent identifier for memory storage
        tools: Additional tools to provide to agent
        sandbox: Optional sandbox backend for remote execution (e.g., ModalBackend).
                 If None, uses local filesystem + shell.
        sandbox_type: Type of sandbox provider ("modal", "runloop", "daytona")

    Returns:
        2-tuple of graph and backend
    """
    # Setup agent directory with prompt.md and memory.md (creates if needed)
    default_content = get_default_coding_instructions()
    settings.ensure_agent_prompt(assistant_id, default_content)
    settings.ensure_agent_memory(assistant_id)

    # Ensure skills and files directories exist
    skills_dir = settings.ensure_skills_dir()
    settings.ensure_files_dir()

    # CONDITIONAL SETUP: Local vs Remote Sandbox
    if sandbox is None:
        # ========== LOCAL MODE ==========
        # Backend: Local filesystem for code (no virtual routes)
        composite_backend = CompositeBackend(
            default=FilesystemBackend(),  # Current working directory
            routes={},  # No virtualization - use real paths
        )

        # Middleware: AgentMemoryMiddleware, SkillsMiddleware, ShellMiddleware
        agent_middleware = [
            AgentMemoryMiddleware(settings=settings, assistant_id=assistant_id),
            SkillsMiddleware(
                skills_dir=skills_dir,
                assistant_id=assistant_id,
            ),
            ShellMiddleware(
                workspace_root=str(Path.cwd()),
                env=os.environ,
            ),
        ]
    else:
        # ========== REMOTE SANDBOX MODE ==========
        # Backend: Remote sandbox for code (no /memories/ route needed with filesystem-based memory)
        composite_backend = CompositeBackend(
            default=sandbox,  # Remote sandbox (ModalBackend, etc.)
            routes={},  # No virtualization
        )

        # Middleware: AgentMemoryMiddleware and SkillsMiddleware
        # NOTE: File operations (ls, read, write, edit, glob, grep) and execute tool
        # are automatically provided by create_deep_agent when backend is a SandboxBackend.
        agent_middleware = [
            AgentMemoryMiddleware(settings=settings, assistant_id=assistant_id),
            SkillsMiddleware(
                skills_dir=skills_dir,
                assistant_id=assistant_id,
            ),
        ]

    # Get the system prompt (sandbox-aware and with skills)
    system_prompt = get_system_prompt(assistant_id=assistant_id, sandbox_type=sandbox_type)

    interrupt_on = _add_interrupt_on()

    # Load memory tools (no approval required)
    memory_tools = create_memory_tools(assistant_id)
    tools.extend(memory_tools)

    # Load tools from enabled services
    service_tools = get_enabled_tools()
    tools.extend(service_tools)

    # Load tools from MCP servers
    mcp_manager = get_mcp_manager()
    mcp_tools = mcp_manager.get_all_tools()
    tools.extend(mcp_tools)

    # Register interrupt configs for dynamically-loaded service tools
    for tool in service_tools:
        tool_name = tool.name
        if tool_name not in interrupt_on:
            # Add interrupt config for service tools based on their type
            if "_create_" in tool_name or "_update_" in tool_name:
                interrupt_on[tool_name] = {
                    "allowed_decisions": ["approve", "reject"],
                    "description": lambda t,
                    s,
                    r,
                    name=tool_name: f"{name}: {str(t['args'])[:150]}...",
                }
            elif "_delete_" in tool_name:
                interrupt_on[tool_name] = {
                    "allowed_decisions": ["approve", "reject"],
                    "description": lambda t,
                    s,
                    r,
                    name=tool_name: f"{name}: Deleting record {t['args'].get('record_id', 'unknown')}",
                }
            elif (
                "_search" in tool_name
                or "_query" in tool_name
                or "_soql" in tool_name
                or "_sosl" in tool_name
            ):
                interrupt_on[tool_name] = {
                    "allowed_decisions": ["approve", "reject"],
                    "description": lambda t,
                    s,
                    r,
                    name=tool_name: f"{name}: {str(t['args'])[:150]}...",
                }
            elif "lusha_" in tool_name or "hunter_" in tool_name:
                # Lusha and Hunter tools use credits - always require approval
                interrupt_on[tool_name] = {
                    "allowed_decisions": ["approve", "reject"],
                    "description": lambda t,
                    s,
                    r,
                    name=tool_name: f"{name}: {str(t['args'])[:150]}...",
                }

    # Register interrupt configs for MCP tools
    for tool in mcp_tools:
        tool_name = tool.name
        if tool_name not in interrupt_on:
            interrupt_on[tool_name] = {
                "allowed_decisions": ["approve", "reject"],
                "description": lambda t,
                s,
                r,
                name=tool_name: f"[MCP] {name}: {str(t['args'])[:150]}...",
            }

    # Get tracing callbacks
    tracing_callbacks = get_tracing_callbacks()

    # Build config with callbacks if any are configured
    agent_config = dict(config)
    if tracing_callbacks:
        agent_config["callbacks"] = tracing_callbacks

    agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        backend=composite_backend,
        middleware=agent_middleware,
        interrupt_on=interrupt_on,
    ).with_config(agent_config)

    agent.checkpointer = InMemorySaver()

    # Count skills
    skill_count = len(
        list_skills(
            user_skills_dir=skills_dir,
            agent_skills_dir=settings.get_agent_skills_dir(assistant_id),
        )
    )

    # Tool count includes deepagents built-in tools (9):
    # write_todos, ls, read_file, write_file, edit_file, glob, grep, execute, task
    DEEPAGENTS_BUILTIN_TOOLS = 9
    tool_count = len(tools) + DEEPAGENTS_BUILTIN_TOOLS

    return agent, composite_backend, tool_count, skill_count
