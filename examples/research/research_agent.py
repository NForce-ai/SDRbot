import os
from typing import Literal, Annotated

from tavily import TavilyClient

from langchain_core.tools import InjectedToolCallId
from langgraph.types import Command
from langchain_core.messages import ToolMessage, tool

from claude_everything.graph import create_deep_agent
from langgraph.prebuilt.chat_agent_executor import AgentState


class ResearchAgentState(AgentState):
    report: str


def internet_search(query, max_results: int = 5, topic: Literal["general", "news", "finance"] = "general", include_raw_content: bool = False):
    """Run a web search"""
    tavily_async_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    search_docs = tavily_async_client.search(
            query,
            max_results=max_results,
            include_raw_content=include_raw_content,
            topic=topic
        )
    return search_docs


def write_report(report: str, tool_call_id: Annotated[str, InjectedToolCallId]):
    """Use this to write your final report to a file.

    the `report` argument should be the whole report. Make sure it is comprehensive."""
    return Command(update={
        "report": report,
        "messages": [
            ToolMessage(f"Wrote final report", tool_call_id=tool_call_id)
        ]
    })


research_prompt_prefix = """You are an expert researcher. Your job is to write a through research report.

You have access to a few tools.

## `internet_search`

Use this to run an internet search for a given query. You can specify the number of results, the topic, and whether raw content should be included.
"""
agent = create_deep_agent([internet_search], research_prompt_prefix, state_schema=ResearchAgentState, main_agent_tools=[write_report])
