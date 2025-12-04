"""Utilities for accurate token counting using LangChain models."""

from pathlib import Path

from langchain_core.messages import SystemMessage

from sdrbot_cli.config import console, settings


def calculate_baseline_tokens(model, agent_dir: Path, system_prompt: str, assistant_id: str) -> int:
    """Calculate baseline context tokens using the model's official tokenizer.

    This uses the model's get_num_tokens_from_messages() method to get
    accurate token counts for the initial context (system prompt + memory).

    Note: Tool definitions cannot be accurately counted before the first API call
    due to LangChain limitations. They will be included in the total after the
    first message is sent (~5,000 tokens).

    Args:
        model: LangChain model instance (ChatAnthropic or ChatOpenAI)
        agent_dir: Path to agent directory (unused, kept for compatibility)
        system_prompt: The base system prompt string
        assistant_id: The agent identifier for path references

    Returns:
        Token count for system prompt + memory (tools not included)
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

    # Count tokens using the model's official method
    messages = [SystemMessage(content=full_system_prompt)]

    try:
        # Note: tools parameter is not supported by LangChain's token counting
        # Tool tokens will be included in the API response after first message
        return model.get_num_tokens_from_messages(messages)
    except Exception as e:
        # Fallback if token counting fails
        console.print(f"[yellow]Warning: Could not calculate baseline tokens: {e}[/yellow]")
        return 0


def get_memory_system_prompt(assistant_id: str) -> str:
    """Get the long-term memory system prompt text.

    Args:
        assistant_id: The agent identifier for path references
    """
    # Import from agent_memory middleware
    from .agent_memory import LONGTERM_MEMORY_SYSTEM_PROMPT

    memory_path = settings.get_agent_memory_path(assistant_id)

    return LONGTERM_MEMORY_SYSTEM_PROMPT.format(
        memory_path=str(memory_path),
    )
