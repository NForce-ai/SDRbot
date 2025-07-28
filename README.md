# Claude Everything

A general-purpose AI agent built with LangGraph that includes two default tools:
1. **Sub-agent spawning**: Create new agent instances for handling subtasks
2. **Todo list management**: Organize tasks using a "replace entire state" pattern

## Features

- **General Purpose**: Handles a wide variety of tasks with Claude's capabilities
- **Sub-agent Delegation**: Spawn independent sub-agents for complex subtasks
- **Todo Management**: Built-in task tracking with priority and status management
- **Extensible**: Additional tools can be passed in at runtime
- **LangGraph Integration**: Built on LangGraph for robust state management

## Installation

```bash
pip install -e .
```

## Usage

### Basic Usage

```python
from claude_everything.graph import graph
from langchain_core.messages import HumanMessage

# Simple usage
result = await graph.ainvoke({
    "messages": [HumanMessage(content="Help me plan a project")]
})
```

### With Additional Tools

```python
from claude_everything.graph import graph
from langchain_core.messages import HumanMessage

# Define custom tools
def custom_calculator(expression: str) -> str:
    """Calculate mathematical expressions."""
    try:
        result = eval(expression)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {e}"

# Use with additional tools
result = await graph.ainvoke({
    "messages": [HumanMessage(content="Calculate 15 * 23 + 7")],
    "additional_tools": [custom_calculator]
})
```

## Default Tools

### 1. Sub-agent Tool (`spawn_sub_agent`)

Spawns a new agent instance to handle specific subtasks:

```python
# The agent can use this internally like:
# spawn_sub_agent(
#     task_description="Research the latest developments in AI",
#     additional_context="Focus on developments from 2024"
# )
```

### 2. Todo List Tool (`update_todo_list`)

Manages tasks with a replace-entire-state pattern:

```python
# The agent can use this internally like:
# update_todo_list(todos_json='[
#     {"id": "1", "content": "Research topic", "status": "completed", "priority": "high"},
#     {"id": "2", "content": "Write summary", "status": "in_progress", "priority": "medium"}
# ]')
```

Todo items have the following structure:
- `id`: Unique identifier
- `content`: Task description
- `status`: One of "pending", "in_progress", "completed"
- `priority`: One of "high", "medium", "low"

## Running with LangGraph CLI

```bash
# Start the development server
langgraph dev

# Deploy to LangGraph Cloud
langgraph deploy
```

## Architecture

The agent follows a standard LangGraph pattern:

1. **State Management**: Maintains conversation messages, todo list, and additional tools
2. **Model Calling**: Uses configurable language models (OpenAI, Anthropic, Fireworks)
3. **Tool Execution**: Processes tool calls with special handling for todo list updates
4. **Routing**: Continues conversation or ends based on model output

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/

# Code formatting
ruff format src/
ruff check src/
```