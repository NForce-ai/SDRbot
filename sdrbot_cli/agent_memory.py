"""Middleware for loading agent-specific long-term memory into the system prompt."""

import contextlib
from collections.abc import Awaitable, Callable
from typing import NotRequired, TypedDict, cast

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from langgraph.runtime import Runtime

from sdrbot_cli.config import Settings


class AgentMemoryState(AgentState):
    """State for the agent memory middleware."""

    memory: NotRequired[str]
    """Agent's long-term memory content."""


class AgentMemoryStateUpdate(TypedDict):
    """A state update for the agent memory middleware."""

    memory: NotRequired[str]
    """Agent's long-term memory content."""


# Long-term Memory Documentation
LONGTERM_MEMORY_SYSTEM_PROMPT = """

## Long-term Memory

Your long-term memory is stored in a file and persists across sessions.

**Memory Location**: `{memory_path}`

Your memory file contains learned preferences, patterns, and information that you've accumulated.
It is loaded at the start of each session and injected into your context.

**When to CHECK/READ memory:**
- **At the start of ANY new session**: Review your memory to recall past context
- **BEFORE answering questions**: If asked "what do you know about X?", check your memory FIRST
- **When user references past work**: Your memory may contain relevant context

**When to UPDATE memory:**
- **IMMEDIATELY when the user describes your role or how you should behave**
- **IMMEDIATELY when the user gives feedback on your work** - Capture what was wrong and how to do better
- When the user explicitly asks you to remember something
- When patterns or preferences emerge (coding styles, conventions, workflows)
- After significant work where context would help in future sessions

**Learning from feedback:**
- When user says something is better/worse, capture WHY and encode it as a pattern
- Each correction is a chance to improve permanently - update your memory
- When user says "remember X" or "be careful about Y", treat this as HIGH PRIORITY
- Look for the underlying principle behind corrections, not just the specific mistake

### Memory Tools (no approval required):

- `read_memory()` - Read your memory file
- `write_memory(content)` - Overwrite your entire memory file
- `append_memory(content)` - Add to the end of your memory file

**Important**:
- Use these dedicated memory tools instead of write_file/edit_file for memory updates
- Memory tools don't require user approval, so you can update memory freely
- Keep memory organized with clear sections (e.g., ## Preferences, ## Patterns, ## Learned)"""


DEFAULT_MEMORY_SNIPPET = """<agent_memory>
{memory}
</agent_memory>"""


class AgentMemoryMiddleware(AgentMiddleware):
    """Middleware for loading agent-specific long-term memory.

    This middleware loads the agent's long-term memory from memory.md
    and injects it into the system prompt. Memory is stored in the agent's
    folder at ./agents/{agent}/memory.md
    """

    state_schema = AgentMemoryState

    def __init__(
        self,
        *,
        settings: Settings,
        assistant_id: str,
        system_prompt_template: str | None = None,
    ) -> None:
        """Initialize the agent memory middleware.

        Args:
            settings: Global settings instance with project detection and paths.
            assistant_id: The agent identifier.
            system_prompt_template: Optional custom template for injecting
                agent memory into system prompt.
        """
        self.settings = settings
        self.assistant_id = assistant_id
        self.memory_path = settings.get_agent_memory_path(assistant_id)
        self.system_prompt_template = system_prompt_template or DEFAULT_MEMORY_SNIPPET

    def before_agent(
        self,
        state: AgentMemoryState,
        runtime: Runtime,
    ) -> AgentMemoryStateUpdate:
        """Load agent memory from file before agent execution.

        Dynamically checks for file existence on every call to catch user updates.

        Args:
            state: Current agent state.
            runtime: Runtime context.

        Returns:
            Updated state with memory populated.
        """
        result: AgentMemoryStateUpdate = {}

        # Load memory from ./agents/{agent}/memory.md
        if "memory" not in state:
            if self.memory_path.exists():
                with contextlib.suppress(OSError, UnicodeDecodeError):
                    result["memory"] = self.memory_path.read_text()

        return result

    def _build_system_prompt(self, request: ModelRequest) -> str:
        """Build the complete system prompt with memory section.

        Args:
            request: The model request containing state and base system prompt.

        Returns:
            Complete system prompt with memory section injected.
        """
        # Extract memory from state
        state = cast("AgentMemoryState", request.state)
        memory = state.get("memory")
        base_system_prompt = request.system_prompt

        # Format memory section
        memory_section = self.system_prompt_template.format(
            memory=memory if memory else "(No memory.md file yet)",
        )

        system_prompt = memory_section

        if base_system_prompt:
            system_prompt += "\n\n" + base_system_prompt

        # Add memory documentation
        system_prompt += "\n\n" + LONGTERM_MEMORY_SYSTEM_PROMPT.format(
            memory_path=str(self.memory_path),
        )

        return system_prompt

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Inject agent memory into the system prompt.

        Args:
            request: The model request being processed.
            handler: The handler function to call with the modified request.

        Returns:
            The model response from the handler.
        """
        system_prompt = self._build_system_prompt(request)
        return handler(request.override(system_prompt=system_prompt))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """(async) Inject agent memory into the system prompt.

        Args:
            request: The model request being processed.
            handler: The handler function to call with the modified request.

        Returns:
            The model response from the handler.
        """
        system_prompt = self._build_system_prompt(request)
        return await handler(request.override(system_prompt=system_prompt))
