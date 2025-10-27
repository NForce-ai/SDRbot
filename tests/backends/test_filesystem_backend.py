import os
from pathlib import Path

from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.protocol import WriteResult, EditResult


def write_file(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def test_filesystem_backend_normal_mode(tmp_path: Path):
    root = tmp_path
    f1 = root / "a.txt"
    f2 = root / "dir" / "b.py"
    write_file(f1, "hello fs")
    write_file(f2, "print('x')\nhello")

    be = FilesystemBackend(root_dir=str(root), virtual_mode=False)

    # ls_info absolute path
    infos = be.ls_info(str(root))
    paths = {i["path"] for i in infos}
    assert str(f1) in paths and str(f2) in paths

    # read, edit, write
    txt = be.read(str(f1))
    assert "hello fs" in txt
    msg = be.edit(str(f1), "fs", "filesystem", replace_all=False)
    assert isinstance(msg, EditResult) and msg.error is None and msg.occurrences == 1
    msg2 = be.write(str(root / "new.txt"), "new content")
    assert isinstance(msg2, WriteResult) and msg2.error is None and msg2.path.endswith("new.txt")

    # grep_raw
    matches = be.grep_raw("hello", path=str(root))
    assert isinstance(matches, list) and any(m["path"].endswith("a.txt") for m in matches)

    # glob_info
    g = be.glob_info("*.py", path=str(root))
    assert any(i["path"] == str(f2) for i in g)


def test_filesystem_backend_virtual_mode(tmp_path: Path):
    root = tmp_path
    f1 = root / "a.txt"
    f2 = root / "dir" / "b.md"
    write_file(f1, "hello virtual")
    write_file(f2, "content")

    be = FilesystemBackend(root_dir=str(root), virtual_mode=True)

    # ls_info from virtual root
    infos = be.ls_info("/")
    paths = {i["path"] for i in infos}
    assert "/a.txt" in paths and "/dir/b.md" in paths

    # read and edit via virtual path
    txt = be.read("/a.txt")
    assert "hello virtual" in txt
    msg = be.edit("/a.txt", "virtual", "virt", replace_all=False)
    assert isinstance(msg, EditResult) and msg.error is None and msg.occurrences == 1

    # write new file via virtual path
    msg2 = be.write("/new.txt", "x")
    assert isinstance(msg2, WriteResult) and msg2.error is None
    assert (root / "new.txt").exists()

    # grep_raw limited to path
    matches = be.grep_raw("virt", path="/")
    assert isinstance(matches, list) and any(m["path"] == "/a.txt" for m in matches)

    # glob_info
    g = be.glob_info("**/*.md", path="/")
    assert any(i["path"] == "/dir/b.md" for i in g)

    # invalid regex returns error string
    err = be.grep_raw("[", path="/")
    assert isinstance(err, str)

    # path traversal blocked
    try:
        be.read("/../a.txt")
        assert False, "expected ValueError for traversal"
    except ValueError:
        pass
