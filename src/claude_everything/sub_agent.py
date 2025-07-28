from claude_everything.model import model
from claude_everything.prompts import TASK_DESCRIPTION
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool


def create_task_tool(tools, prompt_prefix):
    sub_agent = create_react_agent(
        model,
        prompt=prompt_prefix,
        tools=tools
    )

    @tool(description=TASK_DESCRIPTION)
    def task(description: str, subagent_type: str):
        if subagent_type != "general-purpose":
            return f"Error: invoked agent of type {subagent_type}, the only allowed type is `general-purpose`"
        result = sub_agent.invoke({
            "messages": [{"role": "user", "content": description}]
        })
        return result['messages'][-1].content

    return task
