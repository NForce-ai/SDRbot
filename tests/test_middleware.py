from langchain.agents import create_agent
from deepagents.middleware import (
    PlanningMiddleware,
    FilesystemMiddleware,
    SubAgentMiddleware,
)

SAMPLE_MODEL = "claude-3-5-sonnet-20240620"

class TestAddMiddleware:
    def test_planning_middleware(self):
        middleware = [PlanningMiddleware()]
        agent = create_agent(model=SAMPLE_MODEL, middleware=middleware, tools=[])
        assert "todos" in agent.stream_channels
        assert "write_todos" in agent.nodes["tools"].bound._tools_by_name.keys()

    def test_filesystem_middleware(self):
        middleware = [FilesystemMiddleware()]
        agent = create_agent(model=SAMPLE_MODEL, middleware=middleware, tools=[])
        assert "files" in agent.stream_channels
        agent_tools = agent.nodes["tools"].bound._tools_by_name.keys()
        assert "ls" in agent_tools
        assert "read_file" in agent_tools
        assert "write_file" in agent_tools
        assert "edit_file" in agent_tools

    def test_subagent_middleware(self):
        middleware = [
            SubAgentMiddleware(
                default_subagent_tools=[],
                subagents=[],
                model=SAMPLE_MODEL
            )
        ]
        agent = create_agent(model=SAMPLE_MODEL, middleware=middleware, tools=[])
        assert "task" in agent.nodes["tools"].bound._tools_by_name.keys()

    def test_multiple_middleware(self):
        middleware = [
            PlanningMiddleware(),
            FilesystemMiddleware(),
            SubAgentMiddleware(
                default_subagent_tools=[],
                subagents=[],
                model=SAMPLE_MODEL
            )
        ]
        agent = create_agent(model=SAMPLE_MODEL, middleware=middleware, tools=[])
        assert "todos" in agent.stream_channels
        assert "files" in agent.stream_channels
        agent_tools = agent.nodes["tools"].bound._tools_by_name.keys()
        assert "write_todos" in agent_tools
        assert "ls" in agent_tools
        assert "read_file" in agent_tools
        assert "write_file" in agent_tools
        assert "edit_file" in agent_tools
        assert "task" in agent_tools
