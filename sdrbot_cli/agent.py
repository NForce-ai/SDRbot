"""Agent management and creation for the CLI."""

import os
import shutil
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
from sdrbot_cli.shell import ShellMiddleware
from sdrbot_cli.skills import SkillsMiddleware

# Import Salesforce tools
from sdrbot_cli.skills.salesforce.tools import (
    list_objects,
    describe_object,
    soql_query,
    create_record,
    update_record,
)

# Import HubSpot tools
from sdrbot_cli.skills.hubspot.tools import (
    hubspot_list_object_types,
    hubspot_describe_object,
    hubspot_search_objects,
    hubspot_create_object,
    hubspot_update_object,
)

# Import Attio tools
from sdrbot_cli.skills.attio.tools import (
    attio_list_objects,
    attio_describe_object,
    attio_query_records,
    attio_create_record,
    attio_update_record,
)

# Import Lusha tools
from sdrbot_cli.skills.lusha.tools import (
    lusha_enrich_person,
    lusha_enrich_company,
    lusha_prospect,
)


def list_agents() -> None:
    """List all available agents."""
    agents_dir = settings.user_deepagents_dir

    if not agents_dir.exists() or not any(agents_dir.iterdir()):
        console.print("[yellow]No agents found.[/yellow]")
        console.print(
            "[dim]Agents will be created in ~/.deepagents/ when you first use them.[/dim]",
            style=COLORS["dim"],
        )
        return

    console.print("\n[bold]Available Agents:[/bold]\n", style=COLORS["primary"])

    for agent_path in sorted(agents_dir.iterdir()):
        if agent_path.is_dir():
            agent_name = agent_path.name
            agent_md = agent_path / "agent.md"

            if agent_md.exists():
                console.print(f"  • [bold]{agent_name}[/bold]", style=COLORS["primary"])
                console.print(f"    {agent_path}", style=COLORS["dim"])
            else:
                console.print(
                    f"  • [bold]{agent_name}[/bold] [dim](incomplete)[/dim]", style=COLORS["tool"]
                )
                console.print(f"    {agent_path}", style=COLORS["dim"])

    console.print()


def reset_agent(agent_name: str, source_agent: str | None = None) -> None:
    """Reset an agent to default or copy from another agent."""
    agents_dir = settings.user_deepagents_dir
    agent_dir = agents_dir / agent_name

    if source_agent:
        source_dir = agents_dir / source_agent
        source_md = source_dir / "agent.md"

        if not source_md.exists():
            console.print(
                f"[bold red]Error:[/bold red] Source agent '{source_agent}' not found "
                "or has no agent.md"
            )
            return

        source_content = source_md.read_text()
        action_desc = f"contents of agent '{source_agent}'"
    else:
        source_content = get_default_coding_instructions()
        action_desc = "default"

    if agent_dir.exists():
        shutil.rmtree(agent_dir)
        console.print(f"Removed existing agent directory: {agent_dir}", style=COLORS["tool"])

    agent_dir.mkdir(parents=True, exist_ok=True)
    agent_md = agent_dir / "agent.md"
    agent_md.write_text(source_content)

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
    agent_dir_path = f"~/.deepagents/{assistant_id}"

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

Your skills are stored at: `{agent_dir_path}/skills/`
Skills may contain scripts or supporting files. When executing skill scripts with bash, use the real filesystem path:
Example: `bash python {agent_dir_path}/skills/web-research/script.py`

### Human-in-the-Loop Tool Approval

Some tool calls require user approval before execution. When a tool call is rejected by the user:
1. Accept their decision immediately - do NOT retry the same command
2. Explain that you understand they rejected the action
3. Suggest an alternative approach or ask for clarification
4. Never attempt the exact same rejected command again

Respect the user's decisions and work with them collaboratively.

### Web Search Tool Usage

When you use the web_search tool:
1. The tool will return search results with titles, URLs, and content excerpts
2. You MUST read and process these results, then respond naturally to the user
3. NEVER show raw JSON or tool results directly to the user
4. Synthesize the information from multiple sources into a coherent answer
5. Cite your sources by mentioning page titles or URLs when relevant
6. If the search doesn't find what you need, explain what you found and ask clarifying questions

The user only sees your text responses - not tool results. Always provide a complete, natural language answer after using web_search.

### Todo List Management
                                                                                                                                            
When using the write_todos tool:                                                                                                            
1. Keep the todo list MINIMAL - aim for 3-6 items maximum                                                                                   
2. Only create todos for complex, multi-step tasks that truly need tracking                                                                 
3. Break down work into clear, actionable items without over-fragmenting                                                                    
4. For simple tasks (1-2 steps), just do them directly without creating todos                                                               
5. When first creating a todo list for a task, ALWAYS ask the user if the plan looks good before starting work                              
   - Create the todos, let them render, then ask: "Does this plan look good?" or similar                                                    
   - Wait for the user's response before marking the first todo as in_progress                                                              
   - If they want changes, adjust the plan accordingly                                                                                      
6. Update todo status promptly as you complete each item                                                                                    
                                                                                                                                            
The todo list is a planning tool - use it judiciously to avoid overwhelming the user with excessive task tracking.

### Salesforce Usage Guidelines

You are an expert Salesforce administrator and RevOps agent. You do not know the specific schema of the user's Salesforce instance ahead of time, so you must use **Dynamic Discovery**:

1.  **Search First:** When asked to work with an object (e.g., "Commissions"), use `list_objects(query="Commission")` to find the correct API name (e.g., `Commission__c`).
2.  **Describe Always:** Before creating or updating a record, you MUST use `describe_object(object_name)` to understand the field names, types, and required fields. **Do not guess field names.**
3.  **Query for IDs:** If you need to link records (e.g., assign a Commission to a Contact), use `soql_query` to find the target record's ID first.
4.  **Act:** Only after you have the API name, the schema, and necessary IDs, should you call `create_record` or `update_record`.

Example Workflow:
- User: "Add a commission for John Doe."
- You: `list_objects("Commission")` -> Found `Sales_Commission__c`.
- You: `describe_object("Sales_Commission__c")` -> Found fields `Amount__c`, `Payee__c` (Contact lookup).
- You: `soql_query("SELECT Id FROM Contact WHERE Name = 'John Doe'")` -> Found ID `003...`.
- You: `create_record("Sales_Commission__c", json.dumps({{"Amount__c": 100, "Payee__c": "003..."}}))`.

### HubSpot Usage Guidelines

Similar to Salesforce, use **Dynamic Discovery** for HubSpot:
1.  **List:** Use `hubspot_list_object_types()` to find internal names (e.g., standard 'contacts' or custom '2-1234').
2.  **Describe:** Use `hubspot_describe_object(object_type)` to check properties. Note that HubSpot properties are lowercase (e.g., `firstname`, not `FirstName`).
3.  **Search:** Use `hubspot_search_objects(object_type, query_string="...")` to find records.
4.  **Act:** Use `hubspot_create_object` or `hubspot_update_object`.

### Attio Usage Guidelines

For Attio CRM (v2 API):
1.  **List:** Use `attio_list_objects()` to find object slugs (e.g. `people`, `companies`, `dealflow`).
2.  **Describe:** Use `attio_describe_object(object_slug)` to see attributes.
    - **Important:** Attio values are often nested. Check the type!
    - Example: `email_addresses` is a list of objects `[{{"email_address": "..."}}]`.
3.  **Search:** Use `attio_query_records(object_slug, filter_json=...)`.
4.  **Act:** Use `attio_create_record` or `attio_update_record`.

### Lusha Prospecting Guidelines

Use Lusha to find and enrich contact data:
1.  **Prospecting:** Use `lusha_prospect` to find new leads by criteria (e.g. `json.dumps({{"jobTitle": ["CTO"], "companyName": "Stripe"}})`).
2.  **Enrichment:** Use `lusha_enrich_person` (via LinkedIn/Email) or `lusha_enrich_company` (via Domain) to get contact details and firmographics.
3.  **Workflow:** Find -> Enrich -> Create in CRM.
"""
    )

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


def _format_web_search_description(
    tool_call: ToolCall, _state: AgentState, _runtime: Runtime
) -> str:
    """Format web_search tool call for approval prompt."""
    args = tool_call["args"]
    query = args.get("query", "unknown")
    max_results = args.get("max_results", 5)

    return f"Query: {query}\nMax results: {max_results}\n\n⚠️  This will use Tavily API credits"


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

    web_search_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_web_search_description,
    }

    fetch_url_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_fetch_url_description,
    }

    task_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_task_description,
    }
    
    # Salesforce interrupts
    create_record_interrupt: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": lambda t, s, r: f"Create Record ({t['args'].get('object_name')}): {t['args'].get('data')[:100]}...",
    }
    update_record_interrupt: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": lambda t, s, r: f"Update Record ({t['args'].get('object_name')} - {t['args'].get('record_id')}): {t['args'].get('data')[:100]}...",
    }
    soql_interrupt: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": lambda t, s, r: f"Run SOQL: {t['args'].get('query')}",
    }

    # HubSpot interrupts
    hs_create_interrupt: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": lambda t, s, r: f"HubSpot Create ({t['args'].get('object_type')}): {t['args'].get('properties_json')[:100]}...",
    }
    hs_update_interrupt: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": lambda t, s, r: f"HubSpot Update ({t['args'].get('object_type')} - {t['args'].get('object_id')}): {t['args'].get('properties_json')[:100]}...",
    }
    hs_search_interrupt: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": lambda t, s, r: f"HubSpot Search ({t['args'].get('object_type')})",
    }

    # Attio interrupts
    attio_create_interrupt: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": lambda t, s, r: f"Attio Create ({t['args'].get('object_slug')}): {t['args'].get('values_json')[:100]}...",
    }
    attio_update_interrupt: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": lambda t, s, r: f"Attio Update ({t['args'].get('object_slug')}): {t['args'].get('values_json')[:100]}...",
    }
    attio_query_interrupt: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": lambda t, s, r: f"Attio Query ({t['args'].get('object_slug')}): {t['args'].get('filter_json')}",
    }

    # Lusha interrupts (Costly operations)
    lusha_enrich_interrupt: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": lambda t, s, r: f"Lusha Enrich: {t['args'].get('email') or t['args'].get('linkedin_url') or t['args'].get('domain')}",
    }
    lusha_prospect_interrupt: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": lambda t, s, r: f"Lusha Prospect Search: {t['args'].get('filters_json')}",
    }

    return {
        "shell": shell_interrupt_config,
        "execute": execute_interrupt_config,
        "write_file": write_file_interrupt_config,
        "edit_file": edit_file_interrupt_config,
        "web_search": web_search_interrupt_config,
        "fetch_url": fetch_url_interrupt_config,
        "task": task_interrupt_config,
        "create_record": create_record_interrupt,
        "update_record": update_record_interrupt,
        "soql_query": soql_interrupt,
        "hubspot_create_object": hs_create_interrupt,
        "hubspot_update_object": hs_update_interrupt,
        "hubspot_search_objects": hs_search_interrupt,
        "attio_create_record": attio_create_interrupt,
        "attio_update_record": attio_update_interrupt,
        "attio_query_records": attio_query_interrupt,
        "lusha_enrich_person": lusha_enrich_interrupt,
        "lusha_enrich_company": lusha_enrich_interrupt,
        "lusha_prospect": lusha_prospect_interrupt,
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
    # Setup agent directory for persistent memory (same for both local and remote modes)
    agent_dir = settings.ensure_agent_dir(assistant_id)
    agent_md = agent_dir / "agent.md"
    if not agent_md.exists():
        source_content = get_default_coding_instructions()
        agent_md.write_text(source_content)

    # Skills directory - per-agent (user-level)
    skills_dir = settings.ensure_user_skills_dir(assistant_id)

    # Project-level skills directory (if in a project)
    project_skills_dir = settings.get_project_skills_dir()

    # CONDITIONAL SETUP: Local vs Remote Sandbox
    if sandbox is None:
        # ========== LOCAL MODE ==========
        # Backend: Local filesystem for code (no virtual routes)
        composite_backend = CompositeBackend(
            default=FilesystemBackend(),  # Current working directory
            routes={},  # No virtualization - use real paths
        )

        # Middleware: AgentMemoryMiddleware, SkillsMiddleware, ShellToolMiddleware
        agent_middleware = [
            AgentMemoryMiddleware(settings=settings, assistant_id=assistant_id),
            SkillsMiddleware(
                skills_dir=skills_dir,
                assistant_id=assistant_id,
                project_skills_dir=project_skills_dir,
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
                project_skills_dir=project_skills_dir,
            ),
        ]

    # Get the system prompt (sandbox-aware and with skills)
    system_prompt = get_system_prompt(assistant_id=assistant_id, sandbox_type=sandbox_type)

    interrupt_on = _add_interrupt_on()
    
    # Add Salesforce tools
    tools.extend([
        list_objects,
        describe_object,
        soql_query,
        create_record,
        update_record,
        hubspot_list_object_types,
        hubspot_describe_object,
        hubspot_search_objects,
        hubspot_create_object,
        hubspot_update_object,
        attio_list_objects,
        attio_describe_object,
        attio_query_records,
        attio_create_record,
        attio_update_record,
        lusha_enrich_person,
        lusha_enrich_company,
        lusha_prospect,
    ])

    agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        backend=composite_backend,
        middleware=agent_middleware,
        interrupt_on=interrupt_on,
    ).with_config(config)

    agent.checkpointer = InMemorySaver()

    return agent, composite_backend
