"""Copy to the clipboard and paste at the cursor (Wayland / X11)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

# Linux input-event-codes.h
KEY_LEFTCTRL = 29
KEY_RIGHTCTRL = 97
KEY_LEFTSHIFT = 42
KEY_RIGHTSHIFT = 54
KEY_LEFTALT = 56
KEY_RIGHTALT = 100
KEY_LEFTMETA = 125
KEY_RIGHTMETA = 126
KEY_V = 47


def ydotool_ctrl_v_args() -> list[str]:
    """ydotool key arguments for Ctrl+V with explicit press/release.

    NEVER use ``29+47``: ydotool 1.x does strtol→29 and last char≠0 → sticky Ctrl DOWN.
    """
    return [
        f"{KEY_LEFTCTRL}:1",
        f"{KEY_V}:1",
        f"{KEY_V}:0",
        f"{KEY_LEFTCTRL}:0",
    ]


def ydotool_release_modifiers_args() -> list[str]:
    return [
        f"{KEY_LEFTCTRL}:0",
        f"{KEY_RIGHTCTRL}:0",
        f"{KEY_LEFTSHIFT}:0",
        f"{KEY_RIGHTSHIFT}:0",
        f"{KEY_LEFTALT}:0",
        f"{KEY_RIGHTALT}:0",
        f"{KEY_LEFTMETA}:0",
        f"{KEY_RIGHTMETA}:0",
    ]


def _ensure_ydotool_socket() -> None:
    if os.environ.get("YDOTOOL_SOCKET"):
        return
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        sock = os.path.join(runtime, ".ydotool_socket")
        if os.path.exists(sock):
            os.environ["YDOTOOL_SOCKET"] = sock


def _ydotool_key(*events: str) -> bool:
    if not shutil.which("ydotool"):
        return False
    _ensure_ydotool_socket()
    r = subprocess.run(["ydotool", "key", *events], check=False)
    return r.returncode == 0


def _release_modifiers() -> None:
    _ydotool_key(*ydotool_release_modifiers_args())


def _paste_ctrl_v(shift: bool = False) -> bool:
    time.sleep(0.15)
    _release_modifiers()
    time.sleep(0.05)
    if shift:
        ok = _ydotool_key(
            f"{KEY_LEFTSHIFT}:1", *ydotool_ctrl_v_args(), f"{KEY_LEFTSHIFT}:0"
        )
    else:
        ok = _ydotool_key(*ydotool_ctrl_v_args())
    _release_modifiers()
    return ok


def copy_to_clipboard(text: str) -> bool:
    """Copy text to the clipboard. Returns True on success."""
    if not text:
        return False
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    data = text.encode()

    if session == "wayland" or shutil.which("wl-copy"):
        if shutil.which("wl-copy"):
            r = subprocess.run(["wl-copy"], input=data, check=False)
            return r.returncode == 0
        return False

    if shutil.which("xsel"):
        return subprocess.run(["xsel", "-b", "-i"], input=data, check=False).returncode == 0
    if shutil.which("xclip"):
        return (
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=data,
                check=False,
            ).returncode
            == 0
        )
    return False


def inject_paste(paste_combo: str = "ctrl+v") -> bool:
    """Simulate Ctrl+V / Ctrl+Shift+V (clipboard already filled).

    Su questo KWin 6 il compositor NON espone il protocollo virtual-keyboard
    (wtype fallisce con 'Compositor does not support...'), quindi l'unica via di
    iniezione è ydotool via uinput. wtype resta come fallback per altri sistemi.

    Nei terminali (Konsole/opencode/jcode/claude code) Ctrl+V è il literal-insert
    di readline e non incolla: lì serve ctrl+shift+v.
    """
    shift = "shift" in paste_combo.lower()
    if shutil.which("ydotool") and _paste_ctrl_v(shift=shift):
        return True
    if shutil.which("wtype"):
        keys = ["wtype", "-M", "ctrl"]
        if shift:
            keys.extend(["-M", "shift"])
        keys += ["v", "-m"]
        if shift:
            keys.append("shift")
        keys.append("ctrl")
        r = subprocess.run(keys, check=False)
        if r.returncode == 0:
            return True
    if shutil.which("xdotool"):
        combo = "ctrl+shift+v" if shift else "ctrl+v"
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", combo],
            check=False,
        )
        return True
    return False


def paste_text(text: str) -> bool:
    """Copy + attempt auto-paste at the cursor. Returns True if the inject worked."""
    if not text:
        return False
    if not copy_to_clipboard(text):
        print(text)
        print("[whispy] clipboard failed — text on stdout", file=sys.stderr)
        return False
    if inject_paste():
        return True
    print("[whispy] copied to clipboard — press Ctrl+V", file=sys.stderr)
    return False
