"""Tavily Tools."""

from langchain_core.tools import BaseTool, tool
from tavily import TavilyClient

from sdrbot_cli.config import settings

# Shared client instance (lazy loaded)
_tavily_client: TavilyClient | None = None


def get_tavily_client() -> TavilyClient:
    """Get or create Tavily client."""
    global _tavily_client
    if _tavily_client is None:
        if not settings.tavily_api_key:
            raise RuntimeError("Tavily API key not configured (TAVILY_API_KEY).")
        _tavily_client = TavilyClient(api_key=settings.tavily_api_key)
    return _tavily_client


def reset_client():
    """Reset the cached client (useful for testing)."""
    global _tavily_client
    _tavily_client = None


@tool
def tavily_search(query: str, max_results: int = 5) -> str:
    """
    Perform a web search using Tavily.

    Args:
        query: The search query.
        max_results: The maximum number of search results to return.
    """
    try:
        client = get_tavily_client()
        response = client.search(query=query, max_results=max_results, include_answer=True)
        # Extract the answer and results
        answer = response.get("answer")
        results = response.get("results", [])

        output = []
        if answer:
            output.append(f"Answer: {answer}")
        if results:
            output.append("Search Results:")
            for i, result in enumerate(results):
                output.append(f"  {i + 1}. Title: {result.get('title')}")
                output.append(f"     URL: {result.get('url')}")
                output.append(
                    f"     Content: {result.get('content', '')[:200]}..."
                )  # Truncate content

        return "\n".join(output) if output else "No relevant information found."

    except Exception as e:
        return f"Error performing Tavily search: {str(e)}"


def get_tools() -> list[BaseTool]:
    """
    Get all Tavily tools.

    Returns:
        List of Tavily tools.
    """
    return [
        tavily_search,
    ]
