"""Skills management screen for the TUI."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, ListItem, ListView, Static

from sdrbot_cli.config import settings
from sdrbot_cli.skills.load import SkillMetadata, list_skills

# Path to shared CSS
SETUP_CSS_PATH = Path(__file__).parent / "setup_common.tcss"


def get_default_skill_template(skill_name: str) -> str:
    """Get the default SKILL.md template for a new skill."""
    return f"""---
name: {skill_name}
description: [Brief description of what this skill does]
---

# {skill_name.title().replace("-", " ")} Skill

## Description

[Provide a detailed explanation of what this skill does and when it should be used]

## When to Use

- [Scenario 1: When the user asks...]
- [Scenario 2: When you need to...]
- [Scenario 3: When the task involves...]

## How to Use

### Step 1: [First Action]
[Explain what to do first]

### Step 2: [Second Action]
[Explain what to do next]

### Step 3: [Final Action]
[Explain how to complete the task]

## Best Practices

- [Best practice 1]
- [Best practice 2]
- [Best practice 3]

## Examples

### Example 1: [Scenario Name]

**User Request:** "[Example user request]"

**Approach:**
1. [Step-by-step breakdown]
2. [Using tools and commands]
3. [Expected outcome]

## Notes

- [Additional tips, warnings, or context]
- [Known limitations or edge cases]
"""


def _get_skill_display_name(skill_name: str) -> str:
    """Get the display name for a skill (convert underscores to spaces)."""
    return skill_name.replace("_", " ")


def _update_frontmatter_name(content: str, new_name: str) -> str:
    """Update the 'name' field in YAML frontmatter.

    If frontmatter exists, updates the name field. Otherwise returns content unchanged.
    """
    import re

    # Match YAML frontmatter between --- delimiters
    frontmatter_pattern = r"^(---\s*\n)(.*?)(\n---)"
    match = re.match(frontmatter_pattern, content, re.DOTALL)

    if not match:
        return content

    prefix, frontmatter, suffix = match.groups()
    rest_of_content = content[match.end() :]

    # Update or add name field in frontmatter
    name_pattern = r"^name:\s*.+$"
    if re.search(name_pattern, frontmatter, re.MULTILINE):
        # Replace existing name
        updated_frontmatter = re.sub(
            name_pattern, f"name: {new_name}", frontmatter, flags=re.MULTILINE
        )
    else:
        # Add name at the beginning of frontmatter
        updated_frontmatter = f"name: {new_name}\n{frontmatter}"

    return f"{prefix}{updated_frontmatter}{suffix}{rest_of_content}"


class SkillsManagementScreen(ModalScreen[bool | None]):
    """Screen for managing agent skills."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    SkillsManagementScreen {
        align: center middle;
    }

    #skills-list {
        max-height: 12;
    }
    """

    BINDINGS = [
        ("escape", "go_back", "Back"),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._needs_reload = False
        self._skills: list[SkillMetadata] = []

    def compose(self) -> ComposeResult:
        with Container(id="skills-container", classes="setup-dialog-wide"):
            yield Static("Skills Manager", classes="setup-title")
            yield Static(
                "Select a skill to edit or manage.",
                classes="setup-hint",
            )
            yield ListView(id="skills-list", classes="setup-list")
            with Horizontal(classes="setup-buttons"):
                yield Button("Back", variant="default", id="btn-back", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate the skills list on mount."""
        self._refresh_list()

    def _refresh_list(self) -> None:
        """Refresh the skills list."""
        list_view = self.query_one("#skills-list", ListView)
        list_view.clear()

        # Get skills directories
        user_skills_dir = settings.get_skills_dir()
        project_skills_dir = settings.get_project_skills_dir()

        # Load all skills
        self._skills = list_skills(
            user_skills_dir=user_skills_dir,
            project_skills_dir=project_skills_dir,
        )

        for skill in sorted(self._skills, key=lambda s: s["name"]):
            display_name = _get_skill_display_name(skill["name"])
            item = ListItem(
                Static(display_name, classes="setup-list-item-label"),
            )
            item.data = {"type": "skill", "skill": skill}
            list_view.append(item)

        # Add "+ New skill" option at the bottom
        new_item = ListItem(
            Static("+ New skill", classes="setup-list-item-label"),
        )
        new_item.data = {"type": "new"}
        list_view.append(new_item)

        list_view.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection."""
        data = getattr(event.item, "data", None)
        if not data:
            return

        if data.get("type") == "new":
            self._create_new_skill()
        elif data.get("type") == "skill":
            skill = data.get("skill")
            self.app.push_screen(
                SkillActionsScreen(skill),
                self._on_action_complete,
            )

    def _on_action_complete(self, result: dict | None) -> None:
        """Handle action screen result."""
        if result:
            action = result.get("action")
            skill = result.get("skill")

            if action == "edit":
                self._edit_skill(skill)
            elif action == "delete":
                self._delete_skill(skill)
        else:
            self._refresh_list()

    def _create_new_skill(self) -> None:
        """Show dialog to create a new skill."""
        self.app.push_screen(
            CreateSkillScreen(),
            self._on_create_complete,
        )

    def _on_create_complete(self, skill_name: str | None) -> None:
        """Handle new skill creation."""
        if skill_name:
            # Create the skill file
            skills_dir = settings.get_skills_dir()
            skill_path = skills_dir / f"{skill_name}.md"

            if not skill_path.exists():
                skills_dir.mkdir(parents=True, exist_ok=True)
                skill_path.write_text(get_default_skill_template(skill_name))
                self._needs_reload = True

            self._refresh_list()
            # Open editor for the new skill
            self._edit_skill_by_path(skill_path, skill_name)

    def _edit_skill(self, skill: SkillMetadata) -> None:
        """Open the file editor for a skill."""
        skill_path = Path(skill["path"])
        self._edit_skill_by_path(skill_path, skill["name"])

    def _edit_skill_by_path(self, skill_path: Path, skill_name: str) -> None:
        """Open the file editor for a skill by path."""
        from sdrbot_cli.tui.file_editor_screen import FileEditorScreen

        display_name = _get_skill_display_name(skill_name)
        self.app.push_screen(
            FileEditorScreen(
                file_path=skill_path,
                title=f"{display_name} skill",
                allow_save_as=True,
            ),
            self._on_edit_complete,
        )

    def _on_edit_complete(self, result: dict | None) -> None:
        """Handle edit completion."""
        if result:
            action = result.get("action")
            if action == "save":
                self._needs_reload = True
                self.notify("Skill updated.")
            elif action == "save_as":
                # Prompt for new skill name and save
                content = result.get("content", "")
                self.app.push_screen(
                    CreateSkillScreen(),
                    lambda name: self._on_save_as_complete(name, content),
                )
                return  # Don't refresh yet
        self._refresh_list()

    def _on_save_as_complete(self, skill_name: str | None, content: str) -> None:
        """Handle save-as completion."""
        if skill_name:
            skills_dir = settings.get_skills_dir()
            skill_path = skills_dir / f"{skill_name}.md"
            try:
                # Update the frontmatter name to match the new skill name
                updated_content = _update_frontmatter_name(content, skill_name)
                skills_dir.mkdir(parents=True, exist_ok=True)
                skill_path.write_text(updated_content)
                self._needs_reload = True
                self.notify(f"Created skill: {_get_skill_display_name(skill_name)}")
            except Exception as e:
                self.notify(f"Error creating skill: {e}", severity="error")
        self._refresh_list()

    def _delete_skill(self, skill: SkillMetadata) -> None:
        """Delete a skill after confirmation."""
        from sdrbot_cli.tui.agents_screen import ConfirmDeleteScreen

        self.app.push_screen(
            ConfirmDeleteScreen("skill", skill["name"]),
            lambda confirmed: self._on_delete_confirmed(confirmed, skill),
        )

    def _on_delete_confirmed(self, confirmed: bool, skill: SkillMetadata) -> None:
        """Handle delete confirmation."""
        if confirmed:
            skill_path = Path(skill["path"])

            try:
                if skill_path.exists():
                    skill_path.unlink()

                self._needs_reload = True
                self.notify(f"Deleted skill: {skill['name']}")
                self._refresh_list()
            except Exception as e:
                self.notify(f"Error deleting skill: {e}", severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-back":
            self.action_go_back()

    def action_go_back(self) -> None:
        """Go back to the main screen."""
        self.dismiss(self._needs_reload)


class SkillActionsScreen(ModalScreen[dict | None]):
    """Screen showing actions for a selected skill."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    SkillActionsScreen {
        align: center middle;
    }

    #actions-list {
        max-height: 6;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, skill: SkillMetadata, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.skill = skill

    def compose(self) -> ComposeResult:
        display_name = _get_skill_display_name(self.skill["name"])
        with Container(id="actions-container", classes="setup-dialog"):
            yield Static(display_name, classes="setup-title")
            yield ListView(id="actions-list", classes="setup-list")
            with Horizontal(classes="setup-buttons"):
                yield Button("Back", variant="default", id="btn-back", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate actions list."""
        list_view = self.query_one("#actions-list", ListView)
        list_view.clear()

        # Build actions list
        actions = [
            ("edit", "Edit"),
            ("delete", "Delete"),
        ]

        for action_id, action_label in actions:
            item = ListItem(Static(action_label))
            item.data = action_id
            list_view.append(item)

        list_view.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle action selection."""
        action = getattr(event.item, "data", None)
        if action in ("edit", "delete"):
            self.dismiss({"action": action, "skill": self.skill})

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-back":
            self.dismiss(None)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(None)


class CreateSkillScreen(ModalScreen[str | None]):
    """Dialog for creating a new skill."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    CreateSkillScreen {
        align: center middle;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="create-container", classes="setup-dialog"):
            yield Static("Create New Skill", classes="setup-title")
            yield Input(placeholder="Skill name (e.g., web research)", id="create-input")
            with Horizontal(classes="setup-buttons"):
                yield Button("Create", variant="success", id="btn-create", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Focus the input on mount."""
        self.query_one("#create-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle enter key in input."""
        self._create()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-create":
            self._create()
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

    def _create(self) -> None:
        """Validate and create the skill."""
        import re

        name_input = self.query_one("#create-input", Input)
        display_name = name_input.value.strip()

        if not display_name:
            self.notify("Please enter a skill name.", severity="warning")
            return

        # Validate name - allow alphanumeric, hyphens, underscores, and spaces
        if not re.match(r"^[a-zA-Z0-9_\- ]+$", display_name):
            self.notify(
                "Invalid name. Use only letters, numbers, hyphens, underscores, and spaces.",
                severity="error",
            )
            return

        # Convert spaces to underscores for directory name
        skill_name = display_name.replace(" ", "_")

        # Check if already exists
        skills_dir = settings.get_skills_dir()
        skill_path = skills_dir / f"{skill_name}.md"
        if skill_path.exists():
            self.notify(f"Skill '{display_name}' already exists.", severity="warning")
            return

        self.dismiss(skill_name)

    def action_cancel(self) -> None:
        """Cancel creation."""
        self.dismiss(None)
