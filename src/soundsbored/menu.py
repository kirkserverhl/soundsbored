"""Interactive menus: rofi (Linux), fzf (macOS/fallback), plain CLI."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from soundsbored.notify import warn
from soundsbored.paths import which


class MenuResultKind(Enum):
    SELECT = auto()
    CANCEL = auto()
    NEXT_CAT = auto()
    PREV_CAT = auto()
    HOTKEY = auto()  # index 0..4 → sad, damn, wooo, awww, laugh
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
    if forced == "cli":
        return "cli"
    if forced == "fzf":
        if which("fzf"):
            return "fzf"
        warn("SOUNDSBORED_MENU=fzf but fzf not found; using cli")
        return "cli"
    if forced == "rofi":
        if which("rofi"):
            return "rofi"
        warn("SOUNDSBORED_MENU=rofi but rofi not found; trying fzf/cli")

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
        return _rofi(
            lines,
            prompt=prompt,
            message=message,
            separator_index=separator_index,
            hotkey_start=hotkey_start,
        )
    if backend == "fzf":
        result = _fzf(lines, prompt=prompt, message=message)
        # If fzf could not start / errored, fall back to numbered CLI
        if result.kind == MenuResultKind.CANCEL and os.environ.get("_SOUNDSBORED_FZF_FAIL"):
            os.environ.pop("_SOUNDSBORED_FZF_FAIL", None)
            warn("fzf failed — using simple numbered menu instead")
            return _cli(lines, prompt=prompt, message=message)
        return result
    return _cli(lines, prompt=prompt, message=message)


def _rofi(
    lines: list[str],
    *,
    prompt: str,
    message: str,
    separator_index: int | None,
    hotkey_start: int | None,
) -> MenuResult:
    # -normal-window: real floating window (movable; no layer-shell input lock)
    # -no-click-to-exit: click other windows without dismissing the board
    cmd = [
        "rofi",
        "-dmenu",
        "-i",
        "-normal-window",
        "-no-click-to-exit",
        "-window-title",
        "soundsbored",
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
        "Alt+l",
        "-kb-custom-8",
        "Alt+f",
        "-kb-custom-9",
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
        return MenuResult(MenuResultKind.HOTKEY, hotkey_index=0)  # sad
    if rc == 13:
        return MenuResult(MenuResultKind.HOTKEY, hotkey_index=1)  # damn
    if rc == 14:
        return MenuResult(MenuResultKind.HOTKEY, hotkey_index=2)  # wooo
    if rc == 15:
        return MenuResult(MenuResultKind.HOTKEY, hotkey_index=3)  # awww
    if rc == 16:
        return MenuResult(MenuResultKind.HOTKEY, hotkey_index=4)  # laugh
    if rc == 17:
        return MenuResult(MenuResultKind.FADE)
    if rc == 18:
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
      ctrl-1..4       → sad / damn / wooo / awww
      ctrl-l          → random laugh

    Important: do NOT capture stderr. When the candidate list is piped on
    stdin, fzf draws its UI on /dev/tty or falls back to stderr. Capturing
    stderr makes the UI impossible and fzf exits immediately (silent cancel).
    """
    fzf = which("fzf")
    if not fzf:
        os.environ["_SOUNDSBORED_FZF_FAIL"] = "1"
        return MenuResult(MenuResultKind.CANCEL)

    header = f"{message} | ctrl-n/p cat · ctrl-1..4 · ctrl-l laugh · ctrl-f fade · ctrl-x stop"
    expect_keys = "right,left,ctrl-n,ctrl-p,ctrl-f,ctrl-x,ctrl-l,ctrl-1,ctrl-2,ctrl-3,ctrl-4"
    cmd = [
        fzf,
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

    try:
        proc = subprocess.run(
            cmd,
            input="\n".join(lines) + "\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=None,  # inherit — required for interactive UI
        )
    except OSError as e:
        warn(f"fzf could not start: {e}")
        os.environ["_SOUNDSBORED_FZF_FAIL"] = "1"
        return MenuResult(MenuResultKind.CANCEL)

    out = proc.stdout or ""
    # User cancel (Esc / Ctrl-C)
    if proc.returncode in (1, 130) and not out.strip():
        return MenuResult(MenuResultKind.CANCEL)
    # Unexpected failure (bad flags, no TTY, etc.)
    if proc.returncode not in (0, 1, 130) and not out.strip():
        warn(f"fzf exited with code {proc.returncode}")
        os.environ["_SOUNDSBORED_FZF_FAIL"] = "1"
        return MenuResult(MenuResultKind.CANCEL)

    # --expect: first line is key (empty if Enter), second line is selection
    parts = out.splitlines()
    key = parts[0] if parts else ""
    selected = parts[1] if len(parts) > 1 else (parts[0] if parts and parts[0] not in {
        "right", "left", "ctrl-n", "ctrl-p", "ctrl-f", "ctrl-x", "ctrl-l",
        "ctrl-1", "ctrl-2", "ctrl-3", "ctrl-4",
    } else "")

    key_map: dict[str, MenuResult] = {
        "right": MenuResult(MenuResultKind.NEXT_CAT),
        "ctrl-n": MenuResult(MenuResultKind.NEXT_CAT),
        "left": MenuResult(MenuResultKind.PREV_CAT),
        "ctrl-p": MenuResult(MenuResultKind.PREV_CAT),
        "ctrl-f": MenuResult(MenuResultKind.FADE),
        "ctrl-x": MenuResult(MenuResultKind.STOP),
        "ctrl-l": MenuResult(MenuResultKind.HOTKEY, hotkey_index=4),
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
    print("  h1–h4 hotkeys      q  quit")
    try:
        if not sys.stdin.isatty():
            warn("stdin is not a TTY — cannot read menu choice")
            return MenuResult(MenuResultKind.CANCEL)
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
    if choice.startswith("h") and choice[1:].isdigit():
        hk = int(choice[1:]) - 1
        if 0 <= hk <= 3:
            return MenuResult(MenuResultKind.HOTKEY, hotkey_index=hk)
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(lines):
            return MenuResult(MenuResultKind.SELECT, selected=lines[idx])

    print("Invalid choice.")
    return MenuResult(MenuResultKind.SELECT, selected="")
