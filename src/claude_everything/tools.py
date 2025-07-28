from typing import Literal, Annotated
from typing_extensions import TypedDict
from langchain_core.tools import tool,  InjectedToolCallId
from langgraph.types import Command
from langchain_core.messages import ToolMessage

from claude_everything.prompts import WRITE_TODOS_DESCRIPTION


class Todo(TypedDict):
    """Todo to track"""
    content: str
    status: Literal["pending", "in_progress", "completed"]


@tool(description=WRITE_TODOS_DESCRIPTION)
def write_todos(
    todos: list[Todo],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    return Command(update={
        "todos": todos,
        "messages": [
            ToolMessage(f"Updated todo list to {todos}", tool_call_id=tool_call_id)
        ]
    })


