"""Main soundboard loop: categories, hotkeys, playback actions."""

from __future__ import annotations

import random
import subprocess
from dataclasses import dataclass
from pathlib import Path

from soundsbored import index as idx
from soundsbored.download import download_all
from soundsbored.index import index_is_empty
from soundsbored.menu import MenuResultKind, detect_backend, show_menu
from soundsbored.notify import notify, warn
from soundsbored.paths import ensure_layout, index_path, toggle_path, volume_path
from soundsbored.player import (
    DEFAULT_VOLUME,
    fade_out_all,
    get_volume,
    play_file,
    stop_all,
    volume_down,
    volume_up,
)

CATEGORIES = ("openings", "in-call", "closers")

CAT_TITLE = {
    "openings": "Openings",
    "in-call": "In-Call",
    "closers": "Closers / Misc",
}

CAT_HINT = {
    "openings": "→  In-Call",
    "in-call": "←  Openings    |    Closers / Misc  →",
    "closers": "←  In-Call",
}

@dataclass
class MenuEntry:
    label: str
    action: str  # play | toggle | laugh | fade | stop | vol_down | vol_up | noop
    path: Path | None = None


def _read_toggle_state() -> int:
    p = toggle_path()
    try:
        return 0 if p.read_text(encoding="utf-8").strip() == "0" else 1
    except OSError:
        return 0


def _write_toggle_state(value: int) -> None:
    toggle_path().write_text(f"{value}\n", encoding="utf-8")


def play_toggle_wooo_awww(clips: list[idx.Clip]) -> None:
    state = _read_toggle_state()
    if state == 0:
        role, next_state, label = "toggle_a", 1, "Wooo"
    else:
        role, next_state, label = "toggle_b", 0, "Awww"
    clip = idx.toggle_clip(clips, role)
    _write_toggle_state(next_state)
    if clip:
        play_file(clip.path)
    next_label = "Wooo" if next_state == 0 else "Awww"
    notify("Soundsbored", f"▶ {label}  (next: {next_label})", timeout_ms=1200)


def play_random_laugh(clips: list[idx.Clip]) -> None:
    laughs = idx.random_clips(clips)
    if not laughs:
        notify("Soundsbored", "No laugh tracks found")
        return
    pick = random.choice(laughs)
    play_file(pick.path)


def build_menu(clips: list[idx.Clip], category: str) -> list[MenuEntry]:
    entries: list[MenuEntry] = []
    for clip in idx.category_items(clips, category):
        entries.append(MenuEntry(label=f"  {clip.name}", action="play", path=clip.path))

    entries.append(MenuEntry(label="────────────────────────────", action="noop"))

    sad = idx.hotkey_by_name_match(clips, "sad")
    damn = idx.hotkey_by_name_match(clips, "damn")

    tstate = _read_toggle_state()
    tlabel = "Wooo / Awww  · next: Wooo" if tstate == 0 else "Wooo / Awww  · next: Awww"
    vol = get_volume()

    entries.append(MenuEntry(label="  ♪  Sad Trombone", action="play", path=sad.path if sad else None))
    entries.append(MenuEntry(label="  ♪  Damn Son", action="play", path=damn.path if damn else None))
    entries.append(MenuEntry(label=f"  ♪  {tlabel}", action="toggle"))
    entries.append(MenuEntry(label="  ♪  Laugh Track (random)", action="laugh"))
    entries.append(MenuEntry(label="  ↷  Fade Out", action="fade"))
    entries.append(MenuEntry(label="  ■  Stop", action="stop"))
    # Menu-item volume only (same labels on Linux rofi and macOS fzf)
    entries.append(MenuEntry(label=f"  🔉  Volume Down  ({vol}%)", action="vol_down"))
    entries.append(MenuEntry(label=f"  🔊  Volume Up    ({vol}%)", action="vol_up"))
    return entries


def _strip_indices(entries: list[MenuEntry]) -> tuple[int, int]:
    """Return (separator_index, hotkey_start) for theming."""
    sep_idx = next((i for i, e in enumerate(entries) if e.action == "noop"), len(entries) - 1)
    return sep_idx, sep_idx + 1


def _resolve_category(name: str) -> str:
    n = (name or "openings").lower()
    if n in {"openings", "intros", "intro", "open"}:
        return "openings"
    if n in {"in-call", "incall", "call", "in"}:
        return "in-call"
    if n in {"closers", "closer", "misc", "close"}:
        return "closers"
    return "openings"


def ensure_clips(auto_download: bool = True) -> list[idx.Clip]:
    ensure_layout()
    if not toggle_path().exists():
        _write_toggle_state(0)
    if not volume_path().exists():
        try:
            volume_path().write_text(f"{DEFAULT_VOLUME}\n", encoding="utf-8")
        except OSError:
            pass

    if index_is_empty():
        if auto_download:
            notify("Soundsbored", "Downloading clips (first run)…")
            try:
                download_all()
            except Exception as e:
                warn(str(e))
                notify("Soundsbored", f"Download failed: {e}")
                raise
        else:
            raise FileNotFoundError(
                f"No clips yet. Run: soundsbored download\n  (index: {index_path()})"
            )

    clips = idx.load_index()
    if not clips:
        raise FileNotFoundError("Clip index is empty after download.")
    return clips


def run_hotkey(clips: list[idx.Clip], hotkey_index: int) -> None:
    if hotkey_index == 0:
        c = idx.hotkey_by_name_match(clips, "sad")
        play_file(c.path if c else None)
    elif hotkey_index == 1:
        c = idx.hotkey_by_name_match(clips, "damn")
        play_file(c.path if c else None)
    elif hotkey_index == 2:
        play_toggle_wooo_awww(clips)
    elif hotkey_index == 3:
        play_random_laugh(clips)


def run_loop(start_category: str = "openings") -> int:
    clips = ensure_clips(auto_download=True)
    current = _resolve_category(start_category)
    backend = detect_backend()

    if backend == "rofi":
        try:
            subprocess.run(["pkill", "-x", "rofi"], check=False, capture_output=True)
        except Exception:
            pass

    while True:
        entries = build_menu(clips, current)
        lines = [e.label for e in entries]
        sep_idx, hot_start = _strip_indices(entries)
        title = CAT_TITLE[current]
        vol = get_volume()
        if backend == "rofi":
            mesg = (
                f"  {CAT_HINT[current]}     ·     vol {vol}%  ·  "
                f"Alt+F fade  ·  Alt+X stop  ·  Alt+1–4 hotkeys"
            )
        elif backend == "fzf":
            mesg = (
                f"{CAT_HINT[current]}  ·  vol {vol}%  ·  "
                f"ctrl-f fade · ctrl-x stop · ctrl-1–4 hotkeys"
            )
        else:
            mesg = f"{CAT_HINT[current]}  ·  vol {vol}%  ·  f fade · x stop · h1–h4 hotkeys"

        result = show_menu(
            lines,
            prompt=title,
            message=mesg,
            separator_index=sep_idx,
            hotkey_start=hot_start,
        )

        if result.kind == MenuResultKind.CANCEL:
            return 0
        if result.kind == MenuResultKind.NEXT_CAT:
            i = CATEGORIES.index(current)
            if i + 1 < len(CATEGORIES):
                current = CATEGORIES[i + 1]
            continue
        if result.kind == MenuResultKind.PREV_CAT:
            i = CATEGORIES.index(current)
            if i - 1 >= 0:
                current = CATEGORIES[i - 1]
            continue
        if result.kind == MenuResultKind.HOTKEY and result.hotkey_index is not None:
            run_hotkey(clips, result.hotkey_index)
            continue
        if result.kind == MenuResultKind.FADE:
            fade_out_all()
            continue
        if result.kind == MenuResultKind.STOP:
            stop_all()
            continue
        if result.kind == MenuResultKind.SELECT:
            selected = result.selected or ""
            if not selected:
                continue
            meta = next((e for e in entries if e.label == selected), None)
            if meta is None:
                continue
            if meta.action == "play":
                play_file(meta.path)
            elif meta.action == "toggle":
                play_toggle_wooo_awww(clips)
            elif meta.action == "laugh":
                play_random_laugh(clips)
            elif meta.action == "fade":
                fade_out_all()
            elif meta.action == "stop":
                stop_all()
            elif meta.action == "vol_down":
                volume_down()
            elif meta.action == "vol_up":
                volume_up()
            continue

    return 0
