"""StateBackend: Store files in LangGraph agent state (ephemeral)."""

import re
from typing import Any, Literal, Optional, TYPE_CHECKING

from langchain.tools import ToolRuntime

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from .utils import (
    create_file_data,
    update_file_data,
    file_data_to_string,
    format_read_response,
    perform_string_replacement,
    _glob_search_files,
    grep_matches_from_files,
)
from deepagents.backends.utils import FileInfo, GrepMatch
from deepagents.backends.protocol import WriteResult, EditResult


class StateBackend:
    """Backend that stores files in agent state (ephemeral).
    
    Uses LangGraph's state management and checkpointing. Files persist within
    a conversation thread but not across threads. State is automatically
    checkpointed after each agent step.
    
    Special handling: Since LangGraph state must be updated via Command objects
    (not direct mutation), operations return Command objects instead of None.
    This is indicated by the uses_state=True flag.
    """
    
    def __init__(self, runtime: "ToolRuntime"):
        """Initialize StateBackend with runtime.
        
        Args:"""
        self.runtime = runtime
    
    def ls_info(self, path: str) -> list[FileInfo]:
        """List files from state.
        
        Args:
            path: Absolute path to directory.
        
        Returns:
            List of FileInfo-like dicts.
        """
        files = self.runtime.state.get("files", {})
        infos: list[FileInfo] = []
        for k, fd in files.items():
            if not k.startswith(path):
                continue
            size = len("\n".join(fd.get("content", [])))
            infos.append({
                "path": k,
                "is_dir": False,
                "size": int(size),
                "modified_at": fd.get("modified_at", ""),
            })
        infos.sort(key=lambda x: x.get("path", ""))
        return infos

    # Removed legacy ls() convenience to keep lean surface
    
    def read(
        self, 
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """Read file content with line numbers.
        
        Args:
            file_path: Absolute file path
            offset: Line offset to start reading from (0-indexed)
            limit: Maximum number of lines to readReturns:
            Formatted file content with line numbers, or error message.
        """
        files = self.runtime.state.get("files", {})
        file_data = files.get(file_path)
        
        if file_data is None:
            return f"Error: File '{file_path}' not found"
        
        return format_read_response(file_data, offset, limit)
    
    def write(
        self, 
        file_path: str,
        content: str,
    ) -> WriteResult:
        """Create a new file with content.
        Returns WriteResult with files_update to update LangGraph state.
        """
        files = self.runtime.state.get("files", {})
        
        if file_path in files:
            return WriteResult(error=f"Cannot write to {file_path} because it already exists. Read and then make an edit, or write to a new path.")
        
        new_file_data = create_file_data(content)
        return WriteResult(path=file_path, files_update={file_path: new_file_data})
    
    def edit(
        self, 
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Edit a file by replacing string occurrences.
        Returns EditResult with files_update and occurrences.
        """
        files = self.runtime.state.get("files", {})
        file_data = files.get(file_path)
        
        if file_data is None:
            return EditResult(error=f"Error: File '{file_path}' not found")
        
        content = file_data_to_string(file_data)
        result = perform_string_replacement(content, old_string, new_string, replace_all)
        
        if isinstance(result, str):
            return EditResult(error=result)
        
        new_content, occurrences = result
        new_file_data = update_file_data(file_data, new_content)
        return EditResult(path=file_path, files_update={file_path: new_file_data}, occurrences=int(occurrences))
    
    # Removed legacy grep() convenience to keep lean surface

    def grep_raw(
        self,
        pattern: str,
        path: str = "/",
        glob: Optional[str] = None,
    ) -> list[GrepMatch] | str:
        files = self.runtime.state.get("files", {})
        return grep_matches_from_files(files, pattern, path, glob)
    
    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        files = self.runtime.state.get("files", {})
        result = _glob_search_files(files, pattern, path)
        if result == "No files found":
            return []
        paths = result.split("\n")
        infos: list[FileInfo] = []
        for p in paths:
            fd = files.get(p)
            size = len("\n".join(fd.get("content", []))) if fd else 0
            infos.append({
                "path": p,
                "is_dir": False,
                "size": int(size),
                "modified_at": fd.get("modified_at", "") if fd else "",
            })
        return infos

# Provider classes removed: prefer callables like `lambda rt: StateBackend(rt)`
