"""Environment variable utilities for the setup wizard."""

import os
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from rich.prompt import Confirm

from sdrbot_cli.config import COLORS, console

from .menu import CancelledError


async def get_or_prompt(
    env_var_name: str,
    display_name: str,
    is_secret: bool = False,
    required: bool = False,
    force: bool = False,
    default: str | None = None,
) -> str | None:
    """
    Gets an environment variable or prompts the user for it.

    Args:
        env_var_name: Name of the environment variable
        display_name: Human-readable name to display
        is_secret: If True, mask input
        required: If True, require a value
        force: If True, prompt even if value exists
        default: Default value to suggest

    Returns:
        The value, or None if not provided

    Raises:
        CancelledError: If user presses ESC or Ctrl+C to cancel.
    """
    # If force is True, ignore existing env var and prompt anyway
    if not force:
        value = os.getenv(env_var_name)
        if value:
            console.print(
                f"[{COLORS['dim']}][✓] {display_name} already set. "
                f"Masked: {'*' * 8 if is_secret else value}[/{COLORS['dim']}]"
            )
            return value

    # Create key bindings that support ESC to cancel
    bindings = KeyBindings()

    @bindings.add("escape")
    def _(event):
        event.app.exit(exception=CancelledError())

    @bindings.add("c-c")
    def _(event):
        event.app.exit(exception=CancelledError())

    session: PromptSession = PromptSession(key_bindings=bindings)

    if required:
        console.print(f"[{COLORS['primary']}]Missing {display_name}.[/]")
        console.print(f"[{COLORS['dim']}](Press ESC to cancel)[/{COLORS['dim']}]")
        return await session.prompt_async(
            f"  Please enter your {display_name}: ",
            is_password=is_secret,
            default=default or "",
        )
    else:
        if Confirm.ask(
            f"[{COLORS['primary']}]Do you want to configure {display_name}?[/", default=False
        ):
            console.print(f"[{COLORS['dim']}](Press ESC to cancel)[/{COLORS['dim']}]")
            return await session.prompt_async(
                f"  Please enter your {display_name}: ",
                is_password=is_secret,
                default=default or "",
            )
    return None


def save_env_vars(env_vars: dict) -> None:
    """
    Save dictionary of env vars to .env file.

    Preserves existing comments and lines not being overwritten.
    """
    project_root = Path.cwd()
    env_file = project_root / ".env"

    current_env_content = ""
    if env_file.exists():
        current_env_content = env_file.read_text()

    with open(env_file, "w") as f:
        # Preserve existing comments and lines not being overwritten
        for line in current_env_content.splitlines():
            stripped = line.strip()

            # Always preserve comments
            if stripped.startswith("#"):
                f.write(line + "\n")
                continue

            # Preserve empty lines
            if not stripped:
                f.write(line + "\n")
                continue

            # Check if this is a key=value line
            key_val = line.split("=", 1)
            if len(key_val) == 2:
                key = key_val[0].strip()
                # Only preserve if not being overwritten
                if key not in env_vars:
                    f.write(line + "\n")

        # Write new/updated values
        for key, value in env_vars.items():
            if value is not None:
                f.write(f'{key}="{value}"\n')

    console.print(f"[{COLORS['dim']}]Credentials saved to {env_file}[/{COLORS['dim']}]")


def reload_env_and_settings() -> None:
    """Reload environment variables and settings after .env changes."""
    from dotenv import load_dotenv

    from sdrbot_cli.config import settings

    load_dotenv(Path.cwd() / ".env", override=True)
    settings.reload()
