"""Message definitions for SDRbot TUI."""

from rich.console import RenderableType
from textual.message import Message


class AgentMessage(Message):
    """Message from the agent to be displayed in the chat log."""

    def __init__(self, renderable: RenderableType) -> None:
        self.renderable = renderable
        super().__init__()


class AgentExit(Message):
    """Message indicating the agent has exited."""

    pass


class TaskListUpdate(Message):
    """Message to update the task list display."""

    def __init__(self, todos: list[dict]) -> None:
        self.todos = todos
        super().__init__()


class TokenUpdate(Message):
    """Message to update the token display."""

    def __init__(self, total_tokens: int) -> None:
        self.total_tokens = total_tokens
        super().__init__()


class StatusUpdate(Message):
    """Message to update the agent status."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__()


class ToolApprovalRequest(Message):
    """Message requesting tool approval from the user."""

    def __init__(self, future) -> None:
        self.future = future  # asyncio.Future to set the result on
        super().__init__()


class ToolCountUpdate(Message):
    """Message to update the tool count display."""

    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__()


class SkillCountUpdate(Message):
    """Message to update the skill count display."""

    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__()


class SyncingUpdate(Message):
    """Message to update the syncing status."""

    def __init__(self, is_syncing: bool) -> None:
        self.is_syncing = is_syncing
        super().__init__()


class AutoApproveUpdate(Message):
    """Message to update the auto-approve status indicator."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        super().__init__()


class ImageCountUpdate(Message):
    """Message to update the image attachment bar."""

    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__()


class ClearChatLog(Message):
    """Message to clear the chat log widget."""

    pass
