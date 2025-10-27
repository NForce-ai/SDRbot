import pytest
from langchain.tools import ToolRuntime
from langgraph.store.memory import InMemoryStore

from deepagents.backends.store import StoreBackend
from deepagents.backends.protocol import WriteResult, EditResult


def make_runtime():
    return ToolRuntime(
        state={"messages": []},
        context=None,
        tool_call_id="t2",
        store=InMemoryStore(),
        stream_writer=lambda _: None,
        config={},
    )


def test_store_backend_crud_and_search():
    rt = make_runtime()
    be = StoreBackend(rt)

    # write new file
    msg = be.write("/docs/readme.md", "hello store")
    assert isinstance(msg, WriteResult) and msg.error is None and msg.path == "/docs/readme.md"

    # read
    txt = be.read("/docs/readme.md")
    assert "hello store" in txt

    # edit
    msg2 = be.edit("/docs/readme.md", "hello", "hi", replace_all=False)
    assert isinstance(msg2, EditResult) and msg2.error is None and msg2.occurrences == 1

    # ls_info (path prefix filter)
    infos = be.ls_info("/docs/")
    assert any(i["path"] == "/docs/readme.md" for i in infos)

    # grep_raw
    matches = be.grep_raw("hi", path="/")
    assert isinstance(matches, list) and any(m["path"] == "/docs/readme.md" for m in matches)

    # glob_info
    g = be.glob_info("*.md", path="/")
    assert len(g) == 0

    g2 = be.glob_info("**/*.md", path="/")
    assert any(i["path"] == "/docs/readme.md" for i in g2)
