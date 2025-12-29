"""Custom summarization middleware with accurate token counting.

This middleware provides context compression when token limits are approached,
using accurate token counting via the model's tokenizer rather than character-based
approximations.
"""

import uuid
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, AgentState
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    ToolMessage,
)
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.runtime import Runtime

from sdrbot_cli.token_counting import count_message_tokens

# Concise summary prompt focused on extracting key context
SUMMARY_PROMPT = """Extract the most important context from this conversation that should be preserved.
Focus on:
- Key decisions made
- Important facts/data discovered
- Current task state and progress
- Any constraints or requirements established

Respond ONLY with the extracted context, no preamble.

<messages>
{messages}
</messages>"""


class CustomSummarizationMiddleware(AgentMiddleware):
    """Summarization middleware with accurate token counting and dynamic threshold.

    Unlike the default SummarizationMiddleware, this:
    - Uses model.get_num_tokens_from_messages() for accurate counting
    - Accepts a pre-calculated overhead to account for system prompt + tools
    - Has a cleaner, more concise summary prompt
    - Provides a callback for UI notifications
    """

    def __init__(
        self,
        model: BaseChatModel,
        *,
        context_overhead: int = 0,
        max_total_tokens: int = 170_000,
        messages_to_keep: int = 6,
        summary_prompt: str = SUMMARY_PROMPT,
        on_summarize: Callable[[str], None] | None = None,
        session_state=None,
    ) -> None:
        """Initialize the middleware.

        Args:
            model: The language model for token counting and summarization
            context_overhead: Pre-calculated overhead (system prompt + tools)
            max_total_tokens: Maximum total context before triggering summarization
            messages_to_keep: Number of recent messages to preserve after summarization
            summary_prompt: Custom prompt for generating summaries
            on_summarize: Optional callback when summarization occurs (for UI feedback)
            session_state: Optional session state for storing compaction savings
        """
        super().__init__()
        self.model = model
        self.context_overhead = context_overhead
        self.max_total_tokens = max_total_tokens
        self.messages_to_keep = messages_to_keep
        self.summary_prompt = summary_prompt
        self.on_summarize = on_summarize
        self.session_state = session_state

        # Effective threshold for messages = total limit - overhead
        self._message_threshold = max(0, max_total_tokens - context_overhead)

    def update_overhead(self, overhead: int) -> None:
        """Update the context overhead (call after tools/config change)."""
        self.context_overhead = overhead
        self._message_threshold = max(0, self.max_total_tokens - overhead)

    def before_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:  # noqa: ARG002
        """Check token count and summarize if needed."""
        messages = state["messages"]
        self._ensure_message_ids(messages)

        message_tokens = count_message_tokens(self.model, messages)

        if message_tokens < self._message_threshold:
            return None

        cutoff_index = self._find_cutoff(messages, self.messages_to_keep)
        if cutoff_index <= 0:
            return None

        if self.on_summarize:
            self.on_summarize("Compacting...")

        messages_to_summarize = messages[:cutoff_index]
        preserved_messages = messages[cutoff_index:]

        summary = self._create_summary(messages_to_summarize)

        # Stub ToolMessage content in preserved messages to save tokens
        stubbed_preserved = self._stub_tool_messages(preserved_messages)

        summary_message = HumanMessage(
            content=f"[Previous conversation summary]\n\n{summary}",
            id=str(uuid.uuid4()),
        )
        new_messages = [summary_message, *stubbed_preserved]

        # Calculate and store savings
        if self.session_state:
            new_tokens = count_message_tokens(self.model, new_messages)
            savings = message_tokens - new_tokens
            self.session_state._last_compaction_savings = max(0, savings)

        # Signal compaction complete - reset status to "Thinking..."
        if self.on_summarize:
            self.on_summarize(None)

        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *new_messages,
            ]
        }

    async def abefore_model(
        self,
        state: AgentState,
        runtime: Runtime,  # noqa: ARG002
    ) -> dict[str, Any] | None:
        """Async version - check token count and summarize if needed."""
        messages = state["messages"]
        self._ensure_message_ids(messages)

        message_tokens = count_message_tokens(self.model, messages)

        if message_tokens < self._message_threshold:
            return None

        cutoff_index = self._find_cutoff(messages, self.messages_to_keep)
        if cutoff_index <= 0:
            return None

        if self.on_summarize:
            self.on_summarize("Compacting...")

        messages_to_summarize = messages[:cutoff_index]
        preserved_messages = messages[cutoff_index:]

        summary = await self._acreate_summary(messages_to_summarize)

        # Stub ToolMessage content in preserved messages to save tokens
        stubbed_preserved = self._stub_tool_messages(preserved_messages)

        summary_message = HumanMessage(
            content=f"[Previous conversation summary]\n\n{summary}",
            id=str(uuid.uuid4()),
        )
        new_messages = [summary_message, *stubbed_preserved]

        # Calculate and store savings
        if self.session_state:
            new_tokens = count_message_tokens(self.model, new_messages)
            savings = message_tokens - new_tokens
            self.session_state._last_compaction_savings = max(0, savings)

        # Signal compaction complete - reset status to "Thinking..."
        if self.on_summarize:
            self.on_summarize(None)

        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *new_messages,
            ]
        }

    def _ensure_message_ids(self, messages: list[AnyMessage]) -> None:
        """Ensure all messages have unique IDs."""
        for msg in messages:
            if msg.id is None:
                msg.id = str(uuid.uuid4())

    def _stub_tool_messages(self, messages: list[AnyMessage]) -> list[AnyMessage]:
        """Replace ToolMessage content with stubs to save tokens.

        The actual tool results are captured in the conversation summary,
        so we only need stubs to maintain message structure.
        """
        result = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                # Create a new ToolMessage with stubbed content
                stubbed = ToolMessage(
                    content="[Tool result included in conversation summary]",
                    tool_call_id=msg.tool_call_id,
                    id=msg.id,
                    name=getattr(msg, "name", None),
                )
                result.append(stubbed)
            else:
                result.append(msg)
        return result

    def _find_cutoff(self, messages: list[AnyMessage], messages_to_keep: int) -> int:
        """Find cutoff point for compaction, keeping the last N messages."""
        if len(messages) <= messages_to_keep:
            return 0
        return len(messages) - messages_to_keep

    def _create_summary(self, messages: list[AnyMessage]) -> str:
        """Generate summary synchronously."""
        if not messages:
            return "No previous conversation."

        try:
            formatted = self._format_messages_for_summary(messages)
            response = self.model.invoke(
                self.summary_prompt.format(messages=formatted),
                config={"callbacks": []},
            )
            content = response.content
            if isinstance(content, str):
                return content.strip()
            return str(content).strip()
        except Exception as e:
            return f"[Summary generation failed: {e}]"

    async def _acreate_summary(self, messages: list[AnyMessage]) -> str:
        """Generate summary asynchronously."""
        if not messages:
            return "No previous conversation."

        try:
            formatted = self._format_messages_for_summary(messages)
            response = await self.model.ainvoke(
                self.summary_prompt.format(messages=formatted),
                config={"callbacks": []},
            )
            content = response.content
            if isinstance(content, str):
                return content.strip()
            return str(content).strip()
        except Exception as e:
            return f"[Summary generation failed: {e}]"

    def _format_messages_for_summary(self, messages: list[AnyMessage]) -> str:
        """Format messages for the summary prompt."""
        lines = []
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            role = msg.__class__.__name__.replace("Message", "")
            if len(content) > 2000:
                content = content[:2000] + "..."
            lines.append(f"[{role}]: {content}")
        return "\n\n".join(lines)
