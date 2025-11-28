"""Main entry point and CLI loop for deepagents."""

import argparse
import asyncio
import os
import random
import sys
from pathlib import Path

from deepagents.backends.protocol import SandboxBackendProtocol

from sdrbot_cli.agent import create_agent_with_config, list_agents, reset_agent
from sdrbot_cli.commands import execute_bash_command, handle_command
from sdrbot_cli.config import (
    COLORS,
    DEEP_AGENTS_ASCII,
    SessionState,
    console,
    create_model,
    settings,
)
from sdrbot_cli.execution import execute_task
from sdrbot_cli.input import create_prompt_session
from sdrbot_cli.integrations.sandbox_factory import (
    create_sandbox,
)
from sdrbot_cli.setup_wizard import run_setup_wizard
from sdrbot_cli.skills import execute_skills_command, setup_skills_parser
from sdrbot_cli.tools import fetch_url, http_request, web_search
from sdrbot_cli.ui import TokenTracker, show_help


def check_cli_dependencies() -> None:
    """Check if CLI optional dependencies are installed."""
    # These imports are not directly used in this file, but their presence is checked here.
    # Ruff flags them as F401 (unused import), but they are intentionally imported for the check.
    # The actual modules that use them import them directly.

    # The previous logic was: if import fails, add to missing and exit.
    # This is not a direct import for use, but a check for availability.
    # So, we can remove the explicit imports here and rely on the sub-modules importing them.
    # The `_check_dependencies` function itself doesn't need to import them.
    pass


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="DeepAgents - AI Coding Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # List command
    subparsers.add_parser("list", help="List all available agents")

    # Help command
    subparsers.add_parser("help", help="Show help information")

    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Reset an agent")
    reset_parser.add_argument("--agent", required=True, help="Name of agent to reset")
    reset_parser.add_argument(
        "--target", dest="source_agent", help="Copy prompt from another agent"
    )

    # Skills command - setup delegated to skills module
    setup_skills_parser(subparsers)

    # Default interactive mode
    parser.add_argument(
        "--agent",
        default="agent",
        help="Agent identifier for separate memory stores (default: agent).",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve tool usage without prompting (disables human-in-the-loop)",
    )
    parser.add_argument(
        "--sandbox",
        choices=["none", "modal", "daytona", "runloop"],
        default="none",
        help="Remote sandbox for code execution (default: none - local only)",
    )
    parser.add_argument(
        "--sandbox-id",
        help="Existing sandbox ID to reuse (skips creation and cleanup)",
    )
    parser.add_argument(
        "--sandbox-setup",
        help="Path to setup script to run in sandbox after creation",
    )
    parser.add_argument(
        "--no-splash",
        action="store_true",
        help="Disable the startup splash screen",
    )

    return parser.parse_args()


async def simple_cli(
    assistant_id: str | None,
    session_state,
    baseline_tokens: int = 0,
    sandbox_type: str | None = None,
    setup_script_path: str | None = None,
    first_run: bool = True,
) -> None:
    """Main CLI loop.

    Args:
        assistant_id: Agent identifier for memory storage
        session_state: SessionState object containing agent, backend, and settings
        baseline_tokens: Baseline token count for tracking
        sandbox_type: Type of sandbox being used (e.g., "modal", "runloop", "daytona").
                     If None, running in local mode.
        setup_script_path: Path to setup script that was run (if any)
        first_run: If True, show splash screen and greeting (default True)
    """
    # Only show splash on first run, not after reloads
    if first_run:
        if not session_state.no_splash:
            console.print(DEEP_AGENTS_ASCII, style=f"bold {COLORS['primary']}")
            console.print()

    # Only show full UI on first run
    if first_run:
        # Extract sandbox ID from backend if using sandbox mode
        sandbox_id: str | None = None
        if session_state.backend:
            from deepagents.backends.composite import CompositeBackend

            # Check if it's a CompositeBackend with a sandbox default backend
            if isinstance(session_state.backend, CompositeBackend):
                if isinstance(session_state.backend.default, SandboxBackendProtocol):
                    sandbox_id = session_state.backend.default.id
            elif isinstance(session_state.backend, SandboxBackendProtocol):
                sandbox_id = session_state.backend.id

        # Display sandbox info persistently (survives console.clear())
        if sandbox_type and sandbox_id:
            console.print(f"[yellow]⚡ {sandbox_type.capitalize()} sandbox: {sandbox_id}[/yellow]")
            if setup_script_path:
                console.print(
                    f"[green]✓ Setup script ({setup_script_path}) completed successfully[/green]"
                )
            console.print()

        # Show active agent
        agent_name = assistant_id or "agent"
        agent_display = "default" if agent_name == "agent" else agent_name
        console.print(
            f"[dim]Agent:[/dim] [cyan]{agent_display}[/cyan] [dim](./agents/{agent_name}.md)[/dim]"
        )
        console.print()

        greetings = [
            "RevOps agent standing by. What's the mission?",
            "Quotas don't hit themselves. Let's get to work.",
            "Ready to hunt. Who are we targeting today?",
            "Pipeline awaiting updates. How can I help?",
        ]
        console.print(random.choice(greetings), style=COLORS["agent"])

        console.print()

        if session_state.auto_approve:
            console.print(
                "  [yellow]⚡ Auto-approve: ON[/yellow] [dim](tools run without confirmation)[/dim]"
            )
            console.print()

        # Localize modifier names and show key symbols (macOS vs others)
        if sys.platform == "darwin":
            tips = (
                "Tips:\n"
                "  - ⏎ Enter to submit\n"
                "  - ⌥ Option + ⏎ Enter (or Esc+Enter) for newline\n"
                "  - ⌃E to open editor\n"
                "  - ⌃T to toggle auto-approve\n"
                "  - ⌃C to interrupt\n"
                "  - /help to list commands\n"
            )
        else:
            tips = (
                "Tips:\n"
                "  - Enter to submit\n"
                "  - Alt+Enter (or Esc+Enter) for newline\n"
                "  - Ctrl+E to open editor\n"
                "  - Ctrl+T to toggle auto-approve\n"
                "  - Ctrl+C to interrupt\n"
                "  - /help to list commands\n"
            )
        console.print(tips, style=f"dim {COLORS['dim']}")

        console.print()

    # Create prompt session and token tracker
    session = create_prompt_session(assistant_id, session_state)
    token_tracker = TokenTracker()
    token_tracker.set_baseline(baseline_tokens)

    while True:
        try:
            user_input = await session.prompt_async()
            if session_state.exit_hint_handle:
                session_state.exit_hint_handle.cancel()
                session_state.exit_hint_handle = None
            session_state.exit_hint_until = None
            user_input = user_input.strip()
        except EOFError:
            break
        except KeyboardInterrupt:
            console.print("\nGoodbye!", style=COLORS["primary"])
            break

        if not user_input:
            continue

        # Check for slash commands first
        if user_input.startswith("/"):
            result = handle_command(user_input, session_state, token_tracker)
            if result == "exit":
                console.print("\nGoodbye!", style=COLORS["primary"])
                break
            if result:
                # Command was handled, continue to next input
                continue

        # Check for bash commands (!)
        if user_input.startswith("!"):
            execute_bash_command(user_input)
            continue

        # Handle regular quit keywords
        if user_input.lower() in ["quit", "exit", "q"]:
            console.print("\nGoodbye!", style=COLORS["primary"])
            break

        await execute_task(
            user_input,
            session_state.agent,
            assistant_id,
            session_state,
            token_tracker,
            backend=session_state.backend,
        )


async def _run_agent_session(
    model,
    assistant_id: str,
    session_state,
    sandbox_backend=None,
    sandbox_type: str | None = None,
    setup_script_path: str | None = None,
) -> None:
    """Helper to create agent and run CLI session.

    Extracted to avoid duplication between sandbox and local modes.

    Args:
        model: LLM model to use
        assistant_id: Agent identifier for memory storage
        session_state: Session state with auto-approve settings
        sandbox_backend: Optional sandbox backend for remote execution
        sandbox_type: Type of sandbox being used
        setup_script_path: Path to setup script that was run (if any)
    """

    # Helper function to create/recreate the agent
    def create_agent():
        tools = [http_request, fetch_url]
        if settings.has_tavily:
            tools.append(web_search)
        return create_agent_with_config(
            model, assistant_id, tools, sandbox=sandbox_backend, sandbox_type=sandbox_type
        )

    # Create initial agent
    agent, composite_backend = create_agent()
    session_state.agent = agent
    session_state.backend = composite_backend

    # Set up reload callback so commands can trigger agent reload
    def reload_agent():
        console.print("[dim]Reloading agent...[/dim]")
        new_agent, new_backend = create_agent()
        session_state.agent = new_agent
        session_state.backend = new_backend
        console.print("[green]✓ Agent reloaded with updated tools[/green]")
        console.print()

    session_state.set_reload_callback(reload_agent)

    # Calculate baseline token count for accurate token tracking
    from .agent import get_system_prompt
    from .token_utils import calculate_baseline_tokens

    agent_dir = settings.get_agent_dir(assistant_id)
    system_prompt = get_system_prompt(assistant_id=assistant_id, sandbox_type=sandbox_type)
    baseline_tokens = calculate_baseline_tokens(model, agent_dir, system_prompt, assistant_id)

    # Run the CLI loop (no more reload return - reloads happen in-place)
    await simple_cli(
        assistant_id,
        session_state,
        baseline_tokens,
        sandbox_type=sandbox_type,
        setup_script_path=setup_script_path,
        first_run=True,
    )


async def main(
    assistant_id: str,
    session_state,
    sandbox_type: str = "none",
    sandbox_id: str | None = None,
    setup_script_path: str | None = None,
) -> None:
    """Main entry point with conditional sandbox support.

    Args:
        assistant_id: Agent identifier for memory storage
        session_state: Session state with auto-approve settings
        sandbox_type: Type of sandbox ("none", "modal", "runloop", "daytona")
        sandbox_id: Optional existing sandbox ID to reuse
        setup_script_path: Optional path to setup script to run in sandbox
    """
    # Clear terminal at startup
    console.clear()

    run_setup_wizard()

    # Reload environment to pick up changes from setup wizard
    import dotenv

    dotenv.load_dotenv(Path.cwd() / ".env", override=True)
    settings.reload()

    # Sync any enabled services that haven't been synced yet
    from sdrbot_cli.services import sync_enabled_services_if_needed

    sync_enabled_services_if_needed()

    model = create_model()

    # Branch 1: User wants a sandbox
    if sandbox_type != "none":
        # Try to create sandbox
        try:
            console.print()
            with create_sandbox(
                sandbox_type, sandbox_id=sandbox_id, setup_script_path=setup_script_path
            ) as sandbox_backend:
                console.print(f"[yellow]⚡ Remote execution enabled ({sandbox_type})[/yellow]")
                console.print()

                await _run_agent_session(
                    model,
                    assistant_id,
                    session_state,
                    sandbox_backend,
                    sandbox_type=sandbox_type,
                    setup_script_path=setup_script_path,
                )
        except (ImportError, ValueError, RuntimeError, NotImplementedError) as e:
            # Sandbox creation failed - fail hard (no silent fallback)
            console.print()
            console.print("[red]❌ Sandbox creation failed[/red]")
            console.print(f"[dim]{e}[/dim]")
            sys.exit(1)
        except KeyboardInterrupt:
            console.print("\n\n[yellow]Interrupted[/yellow]")
            sys.exit(0)
        except Exception as e:
            console.print(f"\n[bold red]❌ Error:[/bold red] {e}\n")
            console.print_exception()
            sys.exit(1)

    # Branch 2: User wants local mode (none or default)
    else:
        try:
            await _run_agent_session(model, assistant_id, session_state, sandbox_backend=None)
        except KeyboardInterrupt:
            console.print("\n\n[yellow]Interrupted[/yellow]")
            sys.exit(0)
        except Exception as e:
            console.print(f"\n[bold red]❌ Error:[/bold red] {e}\n")
            console.print_exception()
            sys.exit(1)


def cli_main() -> None:
    """Entry point for console script."""
    # Fix for gRPC fork issue on macOS
    # https://github.com/grpc/grpc/issues/37642
    if sys.platform == "darwin":
        os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

    # Check dependencies first
    check_cli_dependencies()

    try:
        args = parse_args()

        if args.command == "help":
            show_help()
        elif args.command == "list":
            list_agents()
        elif args.command == "reset":
            reset_agent(args.agent, args.source_agent)
        elif args.command == "skills":
            execute_skills_command(args)
        else:
            # Create session state from args
            session_state = SessionState(auto_approve=args.auto_approve, no_splash=args.no_splash)

            # API key validation happens in create_model()
            asyncio.run(
                main(
                    args.agent,
                    session_state,
                    args.sandbox,
                    args.sandbox_id,
                    args.sandbox_setup,
                )
            )
    except KeyboardInterrupt:
        # Clean exit on Ctrl+C - suppress ugly traceback
        console.print("\n\n[yellow]Interrupted[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    cli_main()
