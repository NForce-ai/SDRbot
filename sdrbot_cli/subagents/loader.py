"""Load subagent definitions from ``.md`` files with YAML frontmatter.

Each ``.md`` file is expected to have the structure::

    ---
    name: my-subagent
    description: A short description
    tools:
      - shell
      - write_file
    ---
    The rest of the file is the system prompt body.

The ``tools`` key is optional.  The parser is regex-based so ``pyyaml``
is **not** required.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a ``---``-delimited YAML frontmatter block from the body.

    Returns ``(metadata_dict, body_text)``.  If there is no valid
    frontmatter the metadata dict is empty and the full text is returned
    as the body.
    """
    match = re.match(r"\A---\s*\n(.*?\n)---\s*\n(.*)", text, re.DOTALL)
    if not match:
        return {}, text

    raw_meta = match.group(1)
    body = match.group(2).strip()

    meta: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[str] | None = None

    for line in raw_meta.splitlines():
        # List item continuation
        list_match = re.match(r"^\s+-\s+(.+)$", line)
        if list_match and current_key and current_list is not None:
            current_list.append(list_match.group(1).strip())
            continue

        # Key-value pair
        kv_match = re.match(r"^(\w[\w_-]*)\s*:\s*(.*)$", line)
        if kv_match:
            # Flush previous list
            if current_key and current_list is not None:
                meta[current_key] = current_list

            key = kv_match.group(1)
            value = kv_match.group(2).strip()

            if value:
                meta[key] = value
                current_key = None
                current_list = None
            else:
                # Possibly starts a list
                current_key = key
                current_list = []
            continue

    # Flush any trailing list
    if current_key and current_list is not None:
        meta[current_key] = current_list

    return meta, body


def load_subagent_file(path: Path) -> dict[str, Any] | None:
    """Load a single subagent definition from a ``.md`` file.

    Returns a dict compatible with the subagent registration format
    (keys: ``name``, ``description``, ``system_prompt``, optionally
    ``tools``), or ``None`` if the file is missing required fields.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    meta, body = _parse_frontmatter(text)
    name = meta.get("name")
    description = meta.get("description")

    if not name or not description:
        return None

    result: dict[str, Any] = {
        "name": name,
        "description": description,
        "system_prompt": body,
    }

    tools = meta.get("tools")
    if isinstance(tools, list):
        result["tools"] = tools

    return result


def scan_subagent_dirs(*dirs: Path) -> list[dict[str, Any]]:
    """Scan one or more directories for ``.md`` subagent definitions.

    Directories that don't exist are silently skipped.  Later directories
    take precedence when names collide (project-level overrides built-in).
    """
    seen: dict[str, dict[str, Any]] = {}

    for d in dirs:
        if not d.is_dir():
            continue
        for md_file in sorted(d.glob("*.md")):
            defn = load_subagent_file(md_file)
            if defn:
                seen[defn["name"]] = defn

    return list(seen.values())
