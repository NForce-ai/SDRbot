"""Main entry point and CLI loop for deepagents."""

import argparse
import asyncio
import os
import sys

# Only import lightweight modules at top level for faster startup
from sdrbot_cli.version import __version__


def check_cli_dependencies() -> None:
    """Check if CLI optional dependencies are installed."""
    pass


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="sdrbot",
        description="DeepAgents - AI Coding Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # List command
    subparsers.add_parser("list", help="List all available agents")

    # Help command
    subparsers.add_parser("help", help="Show help information")

    # Setup command
    subparsers.add_parser("setup", help="Run the setup wizard")

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
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show the version and exit",
    )

    return parser.parse_args()


async def main(
    assistant_id: str,
    session_state,
    sandbox_type: str = "none",
    sandbox_id: str | None = None,
    setup_script_path: str | None = None,
) -> None:
    """Main entry point with conditional sandbox support, launching Textual TUI."""
    from sdrbot_cli.config import console, load_model_config
    from sdrbot_cli.integrations.sandbox_factory import create_sandbox
    from sdrbot_cli.mcp.manager import shutdown_mcp
    from sdrbot_cli.tui.app import SDRBotTUI

    # Check if model is configured - if not, we'll show setup wizard in TUI
    model_config = load_model_config()
    needs_setup = not model_config or not model_config.get("provider")

    # Store setup state and sandbox config for later use
    session_state.needs_setup = needs_setup
    session_state.sandbox_type = sandbox_type
    session_state.sandbox_id = sandbox_id
    session_state.setup_script_path = setup_script_path

    exit_code = 0
    try:
        # Branch 1: User wants a sandbox
        if sandbox_type != "none":
            try:
                with create_sandbox(
                    sandbox_type, sandbox_id=sandbox_id, setup_script_path=setup_script_path
                ) as sandbox_backend:
                    session_state.sandbox_backend = sandbox_backend
                    app = SDRBotTUI(session_state=session_state, assistant_id=assistant_id)
                    await app.run_async()
            except (ImportError, ValueError, RuntimeError, NotImplementedError) as e:
                console.print()
                console.print("[red]❌ Sandbox creation failed[/red]")
                console.print(f"[dim]{e}[/dim]")
                exit_code = 1
            except KeyboardInterrupt:
                console.print("\n\n[yellow]Interrupted[/yellow]")
            except Exception as e:
                console.print(f"\n[bold red]❌ Error:[/bold red] {e}\n")
                console.print_exception()
                exit_code = 1

        # Branch 2: User wants local mode (none or default) or needs setup
        else:
            try:
                app = SDRBotTUI(session_state=session_state, assistant_id=assistant_id)
                await app.run_async()
            except KeyboardInterrupt:
                console.print("\n\n[yellow]Interrupted[/yellow]")
            except Exception as e:
                console.print(f"\n[bold red]❌ Error:[/bold red] {e}\n")
                console.print_exception()
                exit_code = 1
    finally:
        # Clean up MCP connections on exit
        await shutdown_mcp()

    if exit_code != 0:
        sys.exit(exit_code)


def cli_main() -> None:
    """Entry point for console script."""
    # Fix for gRPC fork issue on macOS
    if sys.platform == "darwin":
        os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

    # Check dependencies first
    check_cli_dependencies()

    # Lazy import console only when needed
    from sdrbot_cli.config import SessionState, console

    try:
        args = parse_args()

        if args.command == "help":
            from sdrbot_cli.ui import show_help

            for renderable in show_help():
                console.print(renderable)
        elif args.command == "list":
            from sdrbot_cli.agent import list_agents

            list_agents()
        elif args.command == "setup":
            # Run TUI with setup wizard forced open
            session_state = SessionState(auto_approve=False, no_splash=True, is_tui=True)
            session_state.force_setup = True
            asyncio.run(
                main(
                    args.agent if hasattr(args, "agent") else "default",
                    session_state,
                )
            )
        else:
            # Create session state from args
            session_state = SessionState(
                auto_approve=args.auto_approve, no_splash=args.no_splash, is_tui=True
            )

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
