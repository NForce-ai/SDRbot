"""Cross-platform clipboard copy with OSC52 fallback for SSH/tmux sessions."""

from __future__ import annotations

import os
import sys


def _osc52_copy(text: str) -> bool:
    """Emit an OSC 52 escape sequence to set the system clipboard.

    Works inside tmux, screen, and most modern terminal emulators
    (even over SSH) as long as the terminal supports OSC 52.
    """
    import base64

    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    seq = f"\033]52;c;{encoded}\a"

    # Inside tmux we need to wrap the sequence so tmux forwards it.
    if os.environ.get("TMUX"):
        seq = f"\033Ptmux;\033{seq}\033\\"

    try:
        sys.stdout.write(seq)
        sys.stdout.flush()
        return True
    except OSError:
        return False


def copy_to_clipboard(text: str) -> bool:
    """Copy *text* to the system clipboard.

    Tries ``pyperclip`` first (native clipboard on desktop environments).
    Falls back to **OSC 52** so it still works inside SSH / tmux sessions.

    Returns:
        ``True`` if the copy appeared to succeed, ``False`` otherwise.
    """
    # 1. pyperclip — works on macOS, Windows, Linux with xclip/xsel
    try:
        import pyperclip

        pyperclip.copy(text)
        return True
    except Exception:
        pass

    # 2. OSC 52 fallback — works over SSH/tmux if terminal supports it
    return _osc52_copy(text)
