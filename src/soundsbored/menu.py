"""Interactive menus: rofi (Linux), fzf (macOS/fallback), plain CLI."""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from soundsbored.paths import which


class MenuResultKind(Enum):
    SELECT = auto()
    CANCEL = auto()
    NEXT_CAT = auto()
    PREV_CAT = auto()
    HOTKEY = auto()  # index 0..3 → sad, damn, toggle, laugh
    FADE = auto()
    STOP = auto()


@dataclass
class MenuResult:
    kind: MenuResultKind
    selected: str | None = None
    hotkey_index: int | None = None


def rofi_theme() -> Path | None:
    override = os.environ.get("SOUNDSBORED_ROFI_THEME")
    if override:
        p = Path(override).expanduser()
        return p if p.is_file() else None
    home = Path.home()
    for candidate in (
        home / ".config" / "rofi" / "config-soundsbored.rasi",
        home / ".config" / "rofi" / "config.rasi",
    ):
        if candidate.is_file():
            return candidate
    return None


def detect_backend() -> str:
    """
    Pick a menu backend by capability (not a big OS if/else tree).

    Order:
      1. SOUNDSBORED_MENU override
      2. rofi when available and not on macOS (primary Linux UX)
      3. fzf when available (primary macOS UX; also fine on Linux)
      4. plain numbered CLI

    Shared features (playback, volume, download) never branch on OS —
    only the thin UI/notification layers do.
    """
    forced = os.environ.get("SOUNDSBORED_MENU", "").strip().lower()
    if forced in {"rofi", "fzf", "cli"}:
        return forced
    # Prefer rofi on Linux/BSD when installed; macOS almost never has it.
    if platform.system() != "Darwin" and which("rofi"):
        return "rofi"
    if which("fzf"):
        return "fzf"
    return "cli"


def show_menu(
    lines: list[str],
    *,
    prompt: str,
    message: str,
    separator_index: int | None = None,
    hotkey_start: int | None = None,
) -> MenuResult:
    backend = detect_backend()
    if backend == "rofi":
        return _rofi(lines, prompt=prompt, message=message, separator_index=separator_index, hotkey_start=hotkey_start)
    if backend == "fzf":
        return _fzf(lines, prompt=prompt, message=message)
    return _cli(lines, prompt=prompt, message=message)


def _rofi(
    lines: list[str],
    *,
    prompt: str,
    message: str,
    separator_index: int | None,
    hotkey_start: int | None,
) -> MenuResult:
    cmd = [
        "rofi",
        "-dmenu",
        "-i",
        "-p",
        prompt,
        "-mesg",
        message,
        "-format",
        "s",
        "-selected-row",
        "0",
        "-kb-custom-1",
        "Right",
        "-kb-custom-2",
        "Left",
        "-kb-custom-3",
        "Alt+1",
        "-kb-custom-4",
        "Alt+2",
        "-kb-custom-5",
        "Alt+3",
        "-kb-custom-6",
        "Alt+4",
        "-kb-custom-7",
        "Alt+f",
        "-kb-custom-8",
        "Alt+x",
    ]
    theme = rofi_theme()
    if theme:
        cmd.extend(["-config", str(theme)])
    if separator_index is not None:
        cmd.extend(["-u", str(separator_index)])
    if hotkey_start is not None:
        cmd.extend(["-a", f"{hotkey_start}-{len(lines) - 1}"])

    proc = subprocess.run(
        cmd,
        input="\n".join(lines) + "\n",
        text=True,
        capture_output=True,
    )
    rc = proc.returncode
    selected = (proc.stdout or "").rstrip("\n")

    if rc in (1, 130):
        return MenuResult(MenuResultKind.CANCEL)
    if rc == 10:
        return MenuResult(MenuResultKind.NEXT_CAT)
    if rc == 11:
        return MenuResult(MenuResultKind.PREV_CAT)
    if rc == 12:
        return MenuResult(MenuResultKind.HOTKEY, hotkey_index=0)
    if rc == 13:
        return MenuResult(MenuResultKind.HOTKEY, hotkey_index=1)
    if rc == 14:
        return MenuResult(MenuResultKind.HOTKEY, hotkey_index=2)
    if rc == 15:
        return MenuResult(MenuResultKind.HOTKEY, hotkey_index=3)
    if rc == 16:
        return MenuResult(MenuResultKind.FADE)
    if rc == 17:
        return MenuResult(MenuResultKind.STOP)
    if rc == 0:
        if not selected:
            return MenuResult(MenuResultKind.CANCEL)
        return MenuResult(MenuResultKind.SELECT, selected=selected)
    return MenuResult(MenuResultKind.CANCEL)


def _fzf(lines: list[str], *, prompt: str, message: str) -> MenuResult:
    """
    fzf bindings (macOS-friendly) via --expect:
      right / ctrl-n  → next category
      left / ctrl-p   → previous category
      ctrl-f          → fade out
      ctrl-x          → stop
      ctrl-1..4       → hotkeys
    """
    header = f"{message}\nctrl-n next · ctrl-p prev · ctrl-f fade · ctrl-x stop · ctrl-1..4 hotkeys"
    expect_keys = "right,left,ctrl-n,ctrl-p,ctrl-f,ctrl-x,ctrl-1,ctrl-2,ctrl-3,ctrl-4"
    cmd = [
        "fzf",
        "--ansi",
        "--height=80%",
        "--layout=reverse",
        "--border",
        "--prompt",
        f"{prompt} > ",
        "--header",
        header,
        "--expect",
        expect_keys,
    ]
    proc = subprocess.run(
        cmd,
        input="\n".join(lines) + "\n",
        text=True,
        capture_output=True,
    )
    out = (proc.stdout or "")
    if proc.returncode != 0 and not out.strip():
        return MenuResult(MenuResultKind.CANCEL)

    # --expect: first line is key (empty if Enter), second line is selection
    parts = out.splitlines()
    key = parts[0] if parts else ""
    selected = parts[1] if len(parts) > 1 else ""

    key_map: dict[str, MenuResult] = {
        "right": MenuResult(MenuResultKind.NEXT_CAT),
        "ctrl-n": MenuResult(MenuResultKind.NEXT_CAT),
        "left": MenuResult(MenuResultKind.PREV_CAT),
        "ctrl-p": MenuResult(MenuResultKind.PREV_CAT),
        "ctrl-f": MenuResult(MenuResultKind.FADE),
        "ctrl-x": MenuResult(MenuResultKind.STOP),
        "ctrl-1": MenuResult(MenuResultKind.HOTKEY, hotkey_index=0),
        "ctrl-2": MenuResult(MenuResultKind.HOTKEY, hotkey_index=1),
        "ctrl-3": MenuResult(MenuResultKind.HOTKEY, hotkey_index=2),
        "ctrl-4": MenuResult(MenuResultKind.HOTKEY, hotkey_index=3),
    }
    if key in key_map:
        return key_map[key]
    if not selected:
        return MenuResult(MenuResultKind.CANCEL)
    return MenuResult(MenuResultKind.SELECT, selected=selected)


def _cli(lines: list[str], *, prompt: str, message: str) -> MenuResult:
    print()
    print(f"=== {prompt} ===")
    print(message)
    print()
    for i, line in enumerate(lines, start=1):
        print(f"  {i:2d}. {line}")
    print()
    print("  n  next category   p  previous")
    print("  f  fade out        x  stop all")
    print("  1-4 hotkeys        q  quit")
    try:
        choice = input("> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return MenuResult(MenuResultKind.CANCEL)

    if not choice or choice in {"q", "quit", "exit"}:
        return MenuResult(MenuResultKind.CANCEL)
    if choice in {"n", "next", "right"}:
        return MenuResult(MenuResultKind.NEXT_CAT)
    if choice in {"p", "prev", "previous", "left"}:
        return MenuResult(MenuResultKind.PREV_CAT)
    if choice in {"f", "fade"}:
        return MenuResult(MenuResultKind.FADE)
    if choice in {"x", "stop"}:
        return MenuResult(MenuResultKind.STOP)
    if choice in {"1", "2", "3", "4"} and choice.isdigit() and not choice.startswith("0"):
        # Ambiguous: number could be hotkey OR list index.
        # Single digit 1-4 when there are many items: treat as list index if
        # user typed a number that maps to a row; use h1-h4 for hotkeys.
        idx = int(choice) - 1
        if 0 <= idx < len(lines):
            return MenuResult(MenuResultKind.SELECT, selected=lines[idx])
    if choice.startswith("h") and choice[1:].isdigit():
        hk = int(choice[1:]) - 1
        if 0 <= hk <= 3:
            return MenuResult(MenuResultKind.HOTKEY, hotkey_index=hk)
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(lines):
            return MenuResult(MenuResultKind.SELECT, selected=lines[idx])

    print("Invalid choice.")
    return MenuResult(MenuResultKind.SELECT, selected="")  # noop re-show handled by empty
