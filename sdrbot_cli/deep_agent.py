"""Custom deep agent factory with configurable summarization.

This module provides a drop-in replacement for deepagents.create_deep_agent
that allows customizing the summarization middleware with accurate token counting.
"""

from collections.abc import Callable, Sequence
from typing import Any

from deepagents.backends.protocol import BackendProtocol
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.subagents import CompiledSubAgent, SubAgent, SubAgentMiddleware
from langchain.agents import create_agent
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    InterruptOnConfig,
    TodoListMiddleware,
)
from langchain.agents.middleware.types import AgentMiddleware
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from sdrbot_cli.summarization import CustomSummarizationMiddleware
from sdrbot_cli.token_counting import calculate_context_overhead

BASE_AGENT_PROMPT = (
    "In order to complete the objective that the user asks of you, "
    "you have access to a number of standard tools."
)


def create_custom_deep_agent(
    model: BaseChatModel,
    tools: Sequence[BaseTool] | None = None,
    *,
    system_prompt: str | None = None,
    middleware: Sequence[AgentMiddleware] = (),
    subagents: list[SubAgent | CompiledSubAgent] | None = None,
    backend: BackendProtocol | None = None,
    interrupt_on: dict[str, bool | InterruptOnConfig] | None = None,
    max_total_tokens: int = 170_000,
    messages_to_keep: int = 6,
    on_summarize: Callable[[str], None] | None = None,
    context_overhead: int | None = None,
    session_state=None,
    **kwargs: Any,
) -> CompiledStateGraph:
    """Create a deep agent with accurate summarization.

    Unlike the standard create_deep_agent, this:
    - Calculates context overhead (system prompt + tools) accurately
    - Uses model's tokenizer instead of char/4 approximation
    - Allows customizing summarization parameters
    - Provides callback for summarization UI feedback

    Args:
        model: The language model to use
        tools: Tools available to the agent
        system_prompt: Additional system instructions
        middleware: Additional middleware to apply
        subagents: Subagents configuration
        backend: Backend for file operations
        interrupt_on: Human-in-the-loop configuration
        max_total_tokens: Maximum total context before summarization
        messages_to_keep: Messages to preserve after summarization
        on_summarize: Callback when summarization occurs
        context_overhead: Pre-calculated overhead (system + tools + memory). If None, calculates internally.
        **kwargs: Additional args passed to create_agent

    Returns:
        Configured deep agent
    """
    # Build full system prompt
    full_prompt = f"{system_prompt}\n\n{BASE_AGENT_PROMPT}" if system_prompt else BASE_AGENT_PROMPT

    # Use provided overhead or calculate (provided is more accurate as it includes memory section)
    tools_list = list(tools) if tools else []
    if context_overhead is None:
        context_overhead = calculate_context_overhead(model, full_prompt, tools_list)

    # Create our custom summarization middleware
    summarization_middleware = CustomSummarizationMiddleware(
        model=model,
        context_overhead=context_overhead,
        max_total_tokens=max_total_tokens,
        messages_to_keep=messages_to_keep,
        on_summarize=on_summarize,
        session_state=session_state,
    )

    # Build middleware stack
    deepagent_middleware: list[AgentMiddleware] = [
        TodoListMiddleware(),
        FilesystemMiddleware(backend=backend),
        SubAgentMiddleware(
            default_model=model,
            default_tools=tools,
            subagents=subagents or [],
            default_middleware=[
                TodoListMiddleware(),
                FilesystemMiddleware(backend=backend),
                # Subagents get their own summarization with same settings
                CustomSummarizationMiddleware(
                    model=model,
                    context_overhead=context_overhead,
                    max_total_tokens=max_total_tokens,
                    messages_to_keep=messages_to_keep,
                ),
                AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
                PatchToolCallsMiddleware(),
            ],
            default_interrupt_on=interrupt_on,
            general_purpose_agent=True,
        ),
        summarization_middleware,
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
        PatchToolCallsMiddleware(),
    ]

    if middleware:
        deepagent_middleware.extend(middleware)

    if interrupt_on:
        deepagent_middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))

    return create_agent(
        model,
        system_prompt=full_prompt,
        tools=tools,
        middleware=deepagent_middleware,
        **kwargs,
    ).with_config({"recursion_limit": 1000})
