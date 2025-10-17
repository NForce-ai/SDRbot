import pytest
from langchain.agents import create_agent
from langchain.tools import ToolRuntime

from deepagents.middleware.filesystem import (
    FILESYSTEM_SYSTEM_PROMPT,
    FILESYSTEM_SYSTEM_PROMPT_LONGTERM_SUPPLEMENT,
    FileData,
    FilesystemMiddleware,
    FilesystemState,
)
from deepagents.middleware.subagents import DEFAULT_GENERAL_PURPOSE_DESCRIPTION, TASK_SYSTEM_PROMPT, TASK_TOOL_DESCRIPTION, SubAgentMiddleware


class TestAddMiddleware:
    def test_filesystem_middleware(self):
        middleware = [FilesystemMiddleware()]
        agent = create_agent(model="claude-sonnet-4-20250514", middleware=middleware, tools=[])
        assert "files" in agent.stream_channels
        agent_tools = agent.nodes["tools"].bound._tools_by_name.keys()
        assert "ls" in agent_tools
        assert "read_file" in agent_tools
        assert "write_file" in agent_tools
        assert "edit_file" in agent_tools

    def test_subagent_middleware(self):
        middleware = [SubAgentMiddleware(default_tools=[], subagents=[], default_model="claude-sonnet-4-20250514")]
        agent = create_agent(model="claude-sonnet-4-20250514", middleware=middleware, tools=[])
        assert "task" in agent.nodes["tools"].bound._tools_by_name.keys()

    def test_multiple_middleware(self):
        middleware = [FilesystemMiddleware(), SubAgentMiddleware(default_tools=[], subagents=[], default_model="claude-sonnet-4-20250514")]
        agent = create_agent(model="claude-sonnet-4-20250514", middleware=middleware, tools=[])
        assert "files" in agent.stream_channels
        agent_tools = agent.nodes["tools"].bound._tools_by_name.keys()
        assert "ls" in agent_tools
        assert "read_file" in agent_tools
        assert "write_file" in agent_tools
        assert "edit_file" in agent_tools
        assert "task" in agent_tools


class TestFilesystemMiddleware:
    def test_init_local(self):
        middleware = FilesystemMiddleware(long_term_memory=False)
        assert middleware.long_term_memory is False
        assert middleware.system_prompt == FILESYSTEM_SYSTEM_PROMPT
        assert len(middleware.tools) == 4

    def test_init_longterm(self):
        middleware = FilesystemMiddleware(long_term_memory=True)
        assert middleware.long_term_memory is True
        assert middleware.system_prompt == (FILESYSTEM_SYSTEM_PROMPT + FILESYSTEM_SYSTEM_PROMPT_LONGTERM_SUPPLEMENT)
        assert len(middleware.tools) == 4

    def test_init_custom_system_prompt_shortterm(self):
        middleware = FilesystemMiddleware(long_term_memory=False, system_prompt="Custom system prompt")
        assert middleware.long_term_memory is False
        assert middleware.system_prompt == "Custom system prompt"
        assert len(middleware.tools) == 4

    def test_init_custom_system_prompt_longterm(self):
        middleware = FilesystemMiddleware(long_term_memory=True, system_prompt="Custom system prompt")
        assert middleware.long_term_memory is True
        assert middleware.system_prompt == "Custom system prompt"
        assert len(middleware.tools) == 4

    def test_init_custom_tool_descriptions_shortterm(self):
        middleware = FilesystemMiddleware(long_term_memory=False, custom_tool_descriptions={"ls": "Custom ls tool description"})
        assert middleware.long_term_memory is False
        assert middleware.system_prompt == FILESYSTEM_SYSTEM_PROMPT
        ls_tool = next(tool for tool in middleware.tools if tool.name == "ls")
        assert ls_tool.description == "Custom ls tool description"

    def test_init_custom_tool_descriptions_longterm(self):
        middleware = FilesystemMiddleware(long_term_memory=True, custom_tool_descriptions={"ls": "Custom ls tool description"})
        assert middleware.long_term_memory is True
        assert middleware.system_prompt == (FILESYSTEM_SYSTEM_PROMPT + FILESYSTEM_SYSTEM_PROMPT_LONGTERM_SUPPLEMENT)
        ls_tool = next(tool for tool in middleware.tools if tool.name == "ls")
        assert ls_tool.description == "Custom ls tool description"

    def test_ls_shortterm(self):
        state = FilesystemState(
            messages=[],
            files={
                "test.txt": FileData(
                    content=["Hello world"],
                    modified_at="2021-01-01",
                    created_at="2021-01-01",
                ),
                "test2.txt": FileData(
                    content=["Goodbye world"],
                    modified_at="2021-01-01",
                    created_at="2021-01-01",
                ),
            },
        )
        middleware = FilesystemMiddleware(long_term_memory=False)
        ls_tool = next(tool for tool in middleware.tools if tool.name == "ls")
        result = ls_tool.invoke(
            {"runtime": ToolRuntime(state=state, context=None, tool_call_id="", store=None, stream_writer=lambda _: None, config={})}
        )
        assert result == ["test.txt", "test2.txt"]

    def test_ls_shortterm_with_path(self):
        state = FilesystemState(
            messages=[],
            files={
                "/test.txt": FileData(
                    content=["Hello world"],
                    modified_at="2021-01-01",
                    created_at="2021-01-01",
                ),
                "/pokemon/test2.txt": FileData(
                    content=["Goodbye world"],
                    modified_at="2021-01-01",
                    created_at="2021-01-01",
                ),
                "/pokemon/charmander.txt": FileData(
                    content=["Ember"],
                    modified_at="2021-01-01",
                    created_at="2021-01-01",
                ),
                "/pokemon/water/squirtle.txt": FileData(
                    content=["Water"],
                    modified_at="2021-01-01",
                    created_at="2021-01-01",
                ),
            },
        )
        middleware = FilesystemMiddleware(long_term_memory=False)
        ls_tool = next(tool for tool in middleware.tools if tool.name == "ls")
        result = ls_tool.invoke(
            {
                "path": "pokemon/",
                "runtime": ToolRuntime(state=state, context=None, tool_call_id="", store=None, stream_writer=lambda _: None, config={}),
            }
        )
        assert "/pokemon/test2.txt" in result
        assert "/pokemon/charmander.txt" in result


@pytest.mark.requires("langchain_openai")
class TestSubagentMiddleware:
    """Test the SubagentMiddleware class."""

    def test_subagent_middleware_init(self):
        middleware = SubAgentMiddleware(
            default_model="gpt-4o-mini",
        )
        assert middleware is not None
        assert middleware.system_prompt is TASK_SYSTEM_PROMPT
        assert len(middleware.tools) == 1
        assert middleware.tools[0].name == "task"
        expected_desc = TASK_TOOL_DESCRIPTION.format(available_agents=f"- general-purpose: {DEFAULT_GENERAL_PURPOSE_DESCRIPTION}")
        assert middleware.tools[0].description == expected_desc

    def test_default_subagent_with_tools(self):
        middleware = SubAgentMiddleware(
            default_model="gpt-4o-mini",
            default_tools=[],
        )
        assert middleware is not None
        assert middleware.system_prompt == TASK_SYSTEM_PROMPT

    def test_default_subagent_custom_system_prompt(self):
        middleware = SubAgentMiddleware(
            default_model="gpt-4o-mini",
            default_tools=[],
            system_prompt="Use the task tool to call a subagent.",
        )
        assert middleware is not None
        assert middleware.system_prompt == "Use the task tool to call a subagent."
