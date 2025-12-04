"""Memory tools for agent self-management without approval requirements."""

from langchain.tools import tool

from sdrbot_cli.config import settings


def create_memory_tools(assistant_id: str) -> list:
    """Create memory tools for the given agent.

    Args:
        assistant_id: The agent identifier

    Returns:
        List of memory tools
    """
    memory_path = settings.get_agent_memory_path(assistant_id)

    @tool
    def write_memory(content: str) -> str:
        """Write content to your long-term memory file.

        Use this to save learned preferences, patterns, and information that should
        persist across sessions. This tool overwrites the entire memory file.

        For partial updates, read your memory first, modify it, then write back.

        Args:
            content: The full content to write to memory.md

        Returns:
            Confirmation message
        """
        try:
            memory_path.parent.mkdir(parents=True, exist_ok=True)
            memory_path.write_text(content)
            return (
                f"Memory updated successfully ({len(content)} characters written to {memory_path})"
            )
        except Exception as e:
            return f"Error writing memory: {e}"

    @tool
    def read_memory() -> str:
        """Read your long-term memory file.

        Returns the contents of your memory.md file, which contains learned
        preferences, patterns, and information from previous sessions.

        Returns:
            The contents of your memory file, or a message if empty/missing
        """
        try:
            if memory_path.exists():
                content = memory_path.read_text()
                if content.strip():
                    return content
                return "(Memory file is empty)"
            return "(No memory file exists yet)"
        except Exception as e:
            return f"Error reading memory: {e}"

    @tool
    def append_memory(content: str) -> str:
        """Append content to your long-term memory file.

        Use this to add new information without overwriting existing memory.
        Adds the content to the end of the file with a newline separator.

        Args:
            content: The content to append to memory.md

        Returns:
            Confirmation message
        """
        try:
            memory_path.parent.mkdir(parents=True, exist_ok=True)
            existing = ""
            if memory_path.exists():
                existing = memory_path.read_text()

            # Add newline separator if file has content
            if existing.strip():
                new_content = existing.rstrip() + "\n\n" + content
            else:
                new_content = content

            memory_path.write_text(new_content)
            return (
                f"Memory appended successfully ({len(content)} characters added to {memory_path})"
            )
        except Exception as e:
            return f"Error appending to memory: {e}"

    return [write_memory, read_memory, append_memory]
