"""Unified token counting for consistent context size tracking.

This module provides the single source of truth for all token counting,
ensuring consistency between the UI token display and the summarization
middleware threshold calculations.
"""

import json

import tiktoken
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.tools import BaseTool

# Use cl100k_base encoding (used by GPT-4, Claude, etc.)
_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens in a string using tiktoken."""
    return len(_ENCODING.encode(text))


def count_message_tokens(model: BaseChatModel, messages: list[BaseMessage]) -> int:
    """Count tokens in messages using model's official tokenizer.

    Args:
        model: LangChain model instance with get_num_tokens_from_messages support
        messages: List of messages to count

    Returns:
        Token count for all messages
    """
    if not messages:
        return 0
    try:
        return model.get_num_tokens_from_messages(messages)
    except Exception:
        # Fallback: rough estimate if tokenizer unavailable
        total = 0
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            total += len(content) // 4 + 3
        return total


def count_tool_tokens(model: BaseChatModel, tools: list) -> int:
    """Count tokens in tool definitions.

    Serializes each tool to its JSON schema representation and counts tokens.
    This approximates how the API receives tool definitions.

    Args:
        model: LangChain model instance with get_num_tokens support
        tools: List of tools (BaseTool instances or functions)

    Returns:
        Token count for all tool definitions
    """
    if not tools:
        return 0

    total = 0

    for tool in tools:
        try:
            # Handle BaseTool instances
            if hasattr(tool, "get_input_schema"):
                schema = tool.get_input_schema().schema()
                tool_def = json.dumps(
                    {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": schema,
                    },
                    separators=(",", ":"),
                )
                total += count_tokens(tool_def)
            # Handle raw functions (decorated with @tool or similar)
            elif callable(tool):
                # Get function name and docstring
                name = getattr(tool, "__name__", "unknown")
                doc = getattr(tool, "__doc__", "") or ""
                # Count tokens using tiktoken + schema overhead
                tool_text = f"{name}: {doc}"
                total += count_tokens(tool_text) + 50  # +50 for schema overhead
            else:
                # Unknown type, use fallback
                total += 100
        except Exception:
            # Fallback estimate if anything fails
            total += 100

    return total


def count_system_prompt_tokens(model: BaseChatModel, system_prompt: str) -> int:
    """Count tokens in system prompt.

    Args:
        model: LangChain model instance
        system_prompt: The full system prompt string

    Returns:
        Token count for system prompt
    """
    if not system_prompt:
        return 0
    try:
        # Use get_num_tokens_from_messages for accurate system message counting
        return model.get_num_tokens_from_messages([SystemMessage(content=system_prompt)])
    except Exception:
        # Fallback: rough estimate
        return len(system_prompt) // 4 + 3


def calculate_context_overhead(
    model: BaseChatModel,
    system_prompt: str,
    tools: list[BaseTool],
) -> int:
    """Calculate the fixed context overhead (system prompt + tools).

    This represents the tokens consumed before any conversation happens.

    Args:
        model: LangChain model instance
        system_prompt: The full system prompt string
        tools: List of tools available to the agent

    Returns:
        Total overhead token count
    """
    return count_system_prompt_tokens(model, system_prompt) + count_tool_tokens(model, tools)


def calculate_total_context(
    model: BaseChatModel,
    system_prompt: str,
    tools: list[BaseTool],
    messages: list[BaseMessage],
) -> int:
    """Calculate total context size (overhead + messages).

    Args:
        model: LangChain model instance
        system_prompt: The full system prompt string
        tools: List of tools available to the agent
        messages: Current conversation messages

    Returns:
        Total context token count
    """
    return calculate_context_overhead(model, system_prompt, tools) + count_message_tokens(
        model, messages
    )
