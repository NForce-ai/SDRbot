import pytest
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from deepagents.backends.protocol import WriteResult, EditResult

from deepagents.backends.state import StateBackend


def make_runtime(files=None):
    return ToolRuntime(
        state={
            "messages": [],
            "files": files or {},
        },
        context=None,
        tool_call_id="t1",
        store=None,
        stream_writer=lambda _: None,
        config={},
    )


def test_write_read_edit_ls_grep_glob_state_backend():
    rt = make_runtime()
    be = StateBackend(rt)

    # write
    res = be.write("/notes.txt", "hello world")
    assert isinstance(res, WriteResult)
    assert res.error is None and res.files_update is not None
    # apply state update
    rt.state["files"].update(res.files_update)

    # read
    content = be.read("/notes.txt")
    assert "hello world" in content

    # edit unique occurrence
    res2 = be.edit("/notes.txt", "hello", "hi", replace_all=False)
    assert isinstance(res2, EditResult)
    assert res2.error is None and res2.files_update is not None
    rt.state["files"].update(res2.files_update)

    content2 = be.read("/notes.txt")
    assert "hi world" in content2

    # ls_info should include the file
    listing = be.ls_info("/")
    assert any(fi["path"] == "/notes.txt" for fi in listing)

    # grep_raw
    matches = be.grep_raw("hi", path="/")
    assert isinstance(matches, list) and any(m["path"] == "/notes.txt" for m in matches)

    # invalid regex yields string error
    err = be.grep_raw("[", path="/")
    assert isinstance(err, str)

    # glob_info
    infos = be.glob_info("*.txt", path="/")
    assert any(i["path"] == "/notes.txt" for i in infos)


def test_state_backend_errors():
    rt = make_runtime()
    be = StateBackend(rt)

    # edit missing file
    err = be.edit("/missing.txt", "a", "b")
    assert isinstance(err, EditResult) and err.error and "not found" in err.error

    # write duplicate
    res = be.write("/dup.txt", "x")
    assert isinstance(res, WriteResult) and res.files_update is not None
    rt.state["files"].update(res.files_update)
    dup_err = be.write("/dup.txt", "y")
    assert isinstance(dup_err, WriteResult) and dup_err.error and "already exists" in dup_err.error
