"""Command-line entry point for soundsbored."""

from __future__ import annotations

import sys

from soundsbored import __version__
from soundsbored.download import download_all
from soundsbored.menu import detect_backend
from soundsbored.notify import warn
from soundsbored.paths import data_root, ensure_layout, soundboard_list_path
from soundsbored.player import fade_out_all, stop_all
from soundsbored.soundboard import run_loop

_CATEGORIES = frozenset(
    {
        "openings",
        "intros",
        "intro",
        "open",
        "in-call",
        "incall",
        "call",
        "in",
        "closers",
        "closer",
        "misc",
        "close",
    }
)


def _print_help() -> None:
    print(
        f"""soundsbored {__version__} — multi-category soundboard

Usage:
  soundsbored [category]     Open menu (default category: openings)
  soundsbored download       Download / refresh clips
  soundsbored fade           Fade out all playing clips
  soundsbored stop           Stop all playing clips
  soundsbored info           Show data paths and menu backend
  soundsbored version        Print version

Categories:
  openings | in-call | closers

Environment:
  SOUNDSBORED_DATA     Override data directory
  SOUNDSBORED_MENU     Force menu backend: rofi | fzf | cli
  SOUNDSBORED_FADE_SECS / SOUNDSBORED_FADE_STEPS
"""
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        return _run_menu("openings")

    head = argv[0]
    if head in {"-h", "--help", "help"}:
        _print_help()
        return 0
    if head in {"-V", "--version", "version"}:
        print(f"soundsbored {__version__}")
        return 0

    try:
        if head == "download":
            ensure_layout()
            download_all()
            return 0
        if head == "fade":
            ensure_layout()
            fade_out_all()
            return 0
        if head == "stop":
            ensure_layout()
            stop_all()
            return 0
        if head == "info":
            ensure_layout()
            print(f"version:  {__version__}")
            print(f"data:     {data_root()}")
            print(f"list:     {soundboard_list_path()}")
            print(f"menu:     {detect_backend()}")
            return 0
        if head in _CATEGORIES:
            return _run_menu(head)

        # Unknown token — try as category alias or show help
        warn(f"Unknown argument: {head}")
        _print_help()
        return 2
    except KeyboardInterrupt:
        print()
        return 130
    except Exception as e:
        warn(f"soundsbored: {e}")
        return 1


def _run_menu(category: str) -> int:
    try:
        return run_loop(category)
    except KeyboardInterrupt:
        print()
        return 130
    except Exception as e:
        warn(f"soundsbored: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
