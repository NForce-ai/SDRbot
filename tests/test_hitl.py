from deepagents.graph import create_deep_agent
from tests.utils import assert_all_deepagent_qualities, get_weather, sample_tool, get_soccer_scores
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
import uuid

SAMPLE_TOOL_CONFIG = {
    "sample_tool": True,
    "get_weather": False,
    "get_soccer_scores": {
        "allow_accept": True,
        "allow_reject": True,
        "allow_respond": False,
        "description": "Ohohohooooo"
    },
}

class TestHITL:
    def test_hitl_agent(self):
        checkpointer = MemorySaver()
        agent = create_deep_agent(tools=[sample_tool, get_weather, get_soccer_scores], tool_configs=SAMPLE_TOOL_CONFIG, checkpointer=checkpointer)
        config = {
            "configurable": {
                "thread_id": uuid.uuid4()
            }
        }
        assert_all_deepagent_qualities(agent)
        result = agent.invoke({"messages": [{"role": "user", "content": "Call the sample tool, get the weather in New York and get scores for the latest soccer games in parallel"}]}, config=config)
        agent_messages = [msg for msg in result.get("messages", []) if msg.type == "ai"]
        tool_calls = [tool_call for msg in agent_messages for tool_call in msg.tool_calls]
        assert any([tool_call["name"] == "sample_tool" for tool_call in tool_calls])
        assert any([tool_call["name"] == "get_weather" for tool_call in tool_calls])
        assert any([tool_call["name"] == "get_soccer_scores" for tool_call in tool_calls])
        
        assert result["__interrupt__"] is not None
        interrupts = result["__interrupt__"][0].value
        assert len(interrupts) == 2
        assert any([interrupt["action_request"]["action"] == "sample_tool" for interrupt in interrupts])
        assert any([interrupt["action_request"]["action"] == "get_soccer_scores" for interrupt in interrupts])

        result2 = agent.invoke(
            Command(
                resume=[{"type": "accept"}, {"type": "accept"}]
            ),
            config=config
        )
        tool_results = [msg for msg in result2.get("messages", []) if msg.type == "tool"]
        assert any([tool_result.name == "sample_tool" for tool_result in tool_results])
        assert any([tool_result.name == "get_weather" for tool_result in tool_results])
        assert any([tool_result.name == "get_soccer_scores" for tool_result in tool_results])
        assert "__interrupt__" not in result2
