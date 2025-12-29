"""Utilities for accurate token counting using LangChain models.

This module provides baseline token calculation that is consistent with
the summarization middleware's counting method.
"""

from langchain_core.tools import BaseTool

from sdrbot_cli.config import settings


def calculate_baseline_tokens(
    model,
    system_prompt: str,
    tools: list[BaseTool],
    assistant_id: str,
) -> int:
    """Calculate baseline context tokens including tools.

    Uses the unified token counting module for consistency with
    the summarization middleware.

    Args:
        model: LangChain model instance
        system_prompt: The base system prompt string
        tools: List of tools available to the agent
        assistant_id: The agent identifier for memory path

    Returns:
        Token count for system prompt + memory + tools
    """
    # Load memory content from ./agents/{agent}/memory.md
    memory_path = settings.get_agent_memory_path(assistant_id)
    memory = ""
    if memory_path.exists():
        try:
            memory = memory_path.read_text()
        except Exception:
            pass

    # Build the complete system prompt as it will be sent
    # This mimics what AgentMemoryMiddleware.wrap_model_call() does
    memory_section = f"<agent_memory>\n{memory or '(No memory.md file yet)'}\n</agent_memory>"

    # Get the long-term memory system prompt
    memory_system_prompt = get_memory_system_prompt(assistant_id)

    # Combine all parts in the same order as the middleware
    full_system_prompt = memory_section + "\n\n" + system_prompt + "\n\n" + memory_system_prompt

    # Use unified counting (includes tools)
    try:
        from sdrbot_cli.token_counting import count_system_prompt_tokens, count_tool_tokens

        system_tokens = count_system_prompt_tokens(model, full_system_prompt)
        tool_tokens = count_tool_tokens(model, tools)
        return system_tokens + tool_tokens
    except Exception:
        return 0


def get_memory_system_prompt(assistant_id: str) -> str:
    """Get the long-term memory system prompt text.

    Args:
        assistant_id: The agent identifier for path references
    """
    # Import from agent_memory middleware
    from sdrbot_cli.agent_memory import LONGTERM_MEMORY_SYSTEM_PROMPT

    memory_path = settings.get_agent_memory_path(assistant_id)

    return LONGTERM_MEMORY_SYSTEM_PROMPT.format(
        memory_path=str(memory_path),
    )
