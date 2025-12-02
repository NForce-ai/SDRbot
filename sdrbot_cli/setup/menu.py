"""Menu utilities for the setup wizard."""

import html

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import HTML, to_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout


class CancelledError(Exception):
    """Raised when user cancels input with ESC."""

    pass


async def show_menu(
    options: list[tuple[str, str, str]], title: str = "Select an option"
) -> str | None:
    """
    Show an interactive menu in the terminal using prompt_toolkit.

    Args:
        options: List of tuples (id, label, status_markup)
        title: Title of the menu

    Returns:
        The selected id, or None if cancelled.
    """
    bindings = KeyBindings()

    # Filter out separator items for navigation but keep them for display
    navigable_indices = [i for i, (id_, _, _) in enumerate(options) if id_ != "---"]
    selected_nav_index = 0  # Index into navigable_indices

    result_id = None

    @bindings.add("up")
    def _(event):
        nonlocal selected_nav_index
        selected_nav_index = max(0, selected_nav_index - 1)

    @bindings.add("down")
    def _(event):
        nonlocal selected_nav_index
        selected_nav_index = min(len(navigable_indices) - 1, selected_nav_index + 1)

    @bindings.add("enter")
    def _(event):
        nonlocal result_id
        actual_index = navigable_indices[selected_nav_index]
        result_id = options[actual_index][0]
        event.app.exit()

    @bindings.add("c-c")
    @bindings.add("q")
    @bindings.add("escape")
    def _(event):
        event.app.exit()

    def get_formatted_text():
        text = []
        escaped_title = html.escape(title)
        text.extend(
            to_formatted_text(
                HTML(
                    f"<b>{escaped_title}</b> <gray>(↑↓ Navigate, Enter Select, Esc Back)</gray>\n\n"
                )
            )
        )

        # Get actual selected index
        selected_actual_index = navigable_indices[selected_nav_index] if navigable_indices else -1

        for i, (id_, label, status) in enumerate(options):
            # Handle separator
            if id_ == "---":
                escaped_label = html.escape(label)
                text.extend(to_formatted_text(HTML(f"    {escaped_label}")))
                text.append(("", "\n"))
                continue

            # Pad label BEFORE escaping so alignment is correct
            padded_label = f"{label:<35}"
            escaped_padded_label = html.escape(padded_label)

            # Convert rich-style markup in status to HTML-ish for prompt_toolkit
            # First escape any special chars in the status text
            pt_status = html.escape(status)
            # Then convert our rich-style tags to prompt_toolkit style tags
            pt_status = pt_status.replace("[green]", "<style fg='green'>").replace(
                "[/green]", "</style>"
            )
            pt_status = pt_status.replace("[red]", "<style fg='red'>").replace("[/red]", "</style>")
            pt_status = pt_status.replace("[yellow]", "<style fg='yellow'>").replace(
                "[/yellow]", "</style>"
            )
            pt_status = pt_status.replace("[cyan]", "<style fg='cyan'>").replace(
                "[/cyan]", "</style>"
            )
            pt_status = pt_status.replace("[dim]", "<style fg='gray'>").replace(
                "[/dim]", "</style>"
            )

            if i == selected_actual_index:
                # Highlighted row - use tuple format to avoid nested HTML issues
                prefix = "  > "
                text.append(("bg:#2e3440 #ffffff", f"{prefix}{padded_label} "))
                # Add status with its own styling
                if status:
                    text.extend(to_formatted_text(HTML(pt_status)))
                text.append(("", "\n"))
            else:
                # Normal row
                row_content = f"    {escaped_padded_label} {pt_status}"
                text.extend(to_formatted_text(HTML(row_content)))
                text.append(("", "\n"))

        return text

    window_height = len(options) + 3

    layout = Layout(Window(content=FormattedTextControl(get_formatted_text), height=window_height))

    app = Application(
        layout=layout,
        key_bindings=bindings,
        mouse_support=False,
        full_screen=False,
    )

    await app.run_async()
    return result_id


async def show_choice_menu(
    options: list[tuple[str, str]], title: str = "Select an option", allow_cancel: bool = True
) -> str | None:
    """
    Show an interactive choice menu using keyboard navigation.

    Args:
        options: List of tuples (value, label)
        title: Title of the menu
        allow_cancel: If True (default), pressing ESC raises CancelledError.
                      If False, ESC returns None.

    Returns:
        The selected value, or None if cancelled and allow_cancel=False.

    Raises:
        CancelledError: If user presses ESC and allow_cancel=True.
    """
    # Convert to the format show_menu expects: (id, label, status)
    menu_options = [(value, label, "") for value, label in options]
    result = await show_menu(menu_options, title=title)
    if result is None and allow_cancel:
        raise CancelledError()
    return result
