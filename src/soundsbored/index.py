"""Clip index (TSV) helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from soundsbored.paths import index_path


@dataclass(frozen=True)
class Clip:
    category: str
    role: str  # normal | hotkey | toggle_a | toggle_b | random
    name: str
    slug: str
    path: Path
    url: str


def load_index(path: Path | None = None) -> list[Clip]:
    p = path or index_path()
    if not p.is_file():
        return []
    clips: list[Clip] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        category, role, name, slug, file_path = parts[:5]
        url = parts[5] if len(parts) > 5 else ""
        clips.append(
            Clip(
                category=category,
                role=role,
                name=name,
                slug=slug,
                path=Path(file_path),
                url=url,
            )
        )
    return clips


def index_is_empty(path: Path | None = None) -> bool:
    return not any(True for _ in load_index(path))


def category_items(clips: list[Clip], category: str) -> list[Clip]:
    return [c for c in clips if c.category == category and c.role == "normal"]


def hotkey_by_name_match(clips: list[Clip], needle: str) -> Clip | None:
    """Match a single hotkey clip by name substring (hotkey or legacy toggle roles)."""
    needle = needle.lower()
    roles = {"hotkey", "toggle_a", "toggle_b"}
    for c in clips:
        if c.category == "hotkeys" and c.role in roles and needle in c.name.lower():
            return c
    return None


def toggle_clip(clips: list[Clip], role: str) -> Clip | None:
    for c in clips:
        if c.category == "hotkeys" and c.role == role:
            return c
    return None


def random_clips(clips: list[Clip]) -> list[Clip]:
    return [c for c in clips if c.category == "hotkeys" and c.role == "random"]


def find_by_name(clips: list[Clip], name: str) -> Clip | None:
    want = name.lower()
    for c in clips:
        if c.name.lower() == want:
            return c
    return None
