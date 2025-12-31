"""Middleware for loading and exposing agent skills to the system prompt.

This middleware implements Anthropic's "Agent Skills" pattern with progressive disclosure:
1. Parse YAML frontmatter from skill .md files at session start
2. Inject skills metadata (name + description) into system prompt
3. Agent reads full skill content when relevant to a task

Skills are loaded from three sources (later overrides earlier):
- Built-in: Shipped with SDRbot (sdrbot_cli/skills/builtin/)
- Agent: Per-agent skills (./agents/{agent}/skills/)
- User: Project-wide custom skills (./skills/)
"""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import NotRequired, TypedDict, cast

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from langgraph.runtime import Runtime

from sdrbot_cli.skills.load import SkillMetadata, list_skills


class SkillsState(AgentState):
    """State for the skills middleware."""

    skills_metadata: NotRequired[list[SkillMetadata]]
    """List of loaded skill metadata (name, description, path)."""


class SkillsStateUpdate(TypedDict):
    """State update for the skills middleware."""

    skills_metadata: list[SkillMetadata]
    """List of loaded skill metadata (name, description, path)."""


# Skills System Documentation
SKILLS_SYSTEM_PROMPT = """

## Skills System

You have access to a skills library that provides specialized capabilities and domain knowledge.

{skills_locations}

**Available Skills:**

{skills_list}

**How to Use Skills (Progressive Disclosure):**

Skills follow a **progressive disclosure** pattern - you know they exist (name + description above), but you only read the full instructions when needed:

1. **Recognize when a skill applies**: Check if the user's task matches any skill's description
2. **Read the skill's full instructions**: The skill list above shows the exact path to use with read_file
3. **Follow the skill's instructions**: SKILL.md contains step-by-step workflows, best practices, and examples
4. **Access supporting files**: Skills may include Python scripts, configs, or reference docs - use absolute paths

**When to Use Skills:**
- When the user's request matches a skill's domain (e.g., "research X" → web-research skill)
- When you need specialized knowledge or structured workflows
- When a skill provides proven patterns for complex tasks

**Skills are Self-Documenting:**
- Each SKILL.md tells you exactly what the skill does and how to use it
- The skill list above shows the full path for each skill's SKILL.md file

**Executing Skill Scripts:**
Skills may contain Python scripts or other executable files. Always use absolute paths from the skill list.

**Example Workflow:**

User: "Can you research the latest developments in quantum computing?"

1. Check available skills above → See "web-research" skill with its full path
2. Read the skill using the path shown in the list
3. Follow the skill's research workflow (search → organize → synthesize)
4. Use any helper scripts with absolute paths

Remember: Skills are tools to make you more capable and consistent. When in doubt, check if a skill exists for the task!
"""


class SkillsMiddleware(AgentMiddleware):
    """Middleware for loading and exposing agent skills.

    This middleware implements Anthropic's agent skills pattern:
    - Loads skills metadata (name, description) from YAML frontmatter at session start
    - Injects skills list into system prompt for discoverability
    - Agent reads full skill content when relevant (progressive disclosure)

    Skills are loaded from three sources (later overrides earlier):
    - Built-in: Shipped with SDRbot
    - Agent: Per-agent skills (./agents/{agent}/skills/)
    - User: Project-wide custom skills (./skills/)

    Args:
        skills_dir: Path to the user skills directory (./skills/).
        assistant_id: The agent identifier.
    """

    state_schema = SkillsState

    def __init__(
        self,
        *,
        skills_dir: str | Path,
        assistant_id: str,
    ) -> None:
        """Initialize the skills middleware.

        Args:
            skills_dir: Path to the user skills directory.
            assistant_id: The agent identifier.
        """
        self.skills_dir = Path(skills_dir).expanduser()
        self.assistant_id = assistant_id
        self.system_prompt_template = SKILLS_SYSTEM_PROMPT

    def _format_skills_locations(self) -> str:
        """Format skills locations for display in system prompt."""
        return """Skills are loaded from:
- **Built-in**: Shipped with SDRbot
- **Agent**: `./agents/{agent}/skills/`
- **User**: `./skills/` (overrides built-in)"""

    def _format_skills_list(self, skills: list[SkillMetadata]) -> str:
        """Format skills metadata for display in system prompt."""
        if not skills:
            return "(No skills available. Create skills in ./skills/ or ./agents/{agent}/skills/)"

        # Group skills by source
        builtin_skills = [s for s in skills if s["source"] == "builtin"]
        agent_skills = [s for s in skills if s["source"] == "agent"]
        user_skills = [s for s in skills if s["source"] == "user"]

        lines = []

        # Show built-in skills
        if builtin_skills:
            lines.append("**Built-in Skills:**")
            for skill in builtin_skills:
                lines.append(f"- **{skill['name']}**: {skill['description']}")
                lines.append(f"  → Read `{skill['path']}` for full instructions")
            lines.append("")

        # Show agent skills
        if agent_skills:
            lines.append("**Agent Skills:**")
            for skill in agent_skills:
                lines.append(f"- **{skill['name']}**: {skill['description']}")
                lines.append(f"  → Read `{skill['path']}` for full instructions")
            lines.append("")

        # Show user skills
        if user_skills:
            lines.append("**User Skills:**")
            for skill in user_skills:
                lines.append(f"- **{skill['name']}**: {skill['description']}")
                lines.append(f"  → Read `{skill['path']}` for full instructions")

        return "\n".join(lines)

    def before_agent(self, state: SkillsState, runtime: Runtime) -> SkillsStateUpdate | None:
        """Load skills metadata before agent execution.

        This runs once at session start to discover available skills from
        built-in, agent, and user directories.

        Args:
            state: Current agent state.
            runtime: Runtime context.

        Returns:
            Updated state with skills_metadata populated.
        """
        from sdrbot_cli.config import settings

        # Re-load skills on every interaction to capture changes
        skills = list_skills(
            user_skills_dir=self.skills_dir,
            agent_skills_dir=settings.get_agent_skills_dir(self.assistant_id),
        )
        return SkillsStateUpdate(skills_metadata=skills)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Inject skills documentation into the system prompt.

        This runs on every model call to ensure skills info is always available.

        Args:
            request: The model request being processed.
            handler: The handler function to call with the modified request.

        Returns:
            The model response from the handler.
        """
        # Get skills metadata from state
        skills_metadata = request.state.get("skills_metadata", [])

        # Format skills locations and list
        skills_locations = self._format_skills_locations()
        skills_list = self._format_skills_list(skills_metadata)

        # Format the skills documentation
        skills_section = self.system_prompt_template.format(
            skills_locations=skills_locations,
            skills_list=skills_list,
        )

        if request.system_prompt:
            system_prompt = request.system_prompt + "\n\n" + skills_section
        else:
            system_prompt = skills_section

        return handler(request.override(system_prompt=system_prompt))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """(async) Inject skills documentation into the system prompt.

        Args:
            request: The model request being processed.
            handler: The handler function to call with the modified request.

        Returns:
            The model response from the handler.
        """
        # The state is guaranteed to be SkillsState due to state_schema
        state = cast("SkillsState", request.state)
        skills_metadata = state.get("skills_metadata", [])

        # Format skills locations and list
        skills_locations = self._format_skills_locations()
        skills_list = self._format_skills_list(skills_metadata)

        # Format the skills documentation
        skills_section = self.system_prompt_template.format(
            skills_locations=skills_locations,
            skills_list=skills_list,
        )

        # Inject into system prompt
        if request.system_prompt:
            system_prompt = request.system_prompt + "\n\n" + skills_section
        else:
            system_prompt = skills_section

        return await handler(request.override(system_prompt=system_prompt))
