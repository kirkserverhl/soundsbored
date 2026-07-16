"""XDG / platform data paths for soundsbored."""

from __future__ import annotations

import os
import shutil
from importlib import resources
from pathlib import Path

from platformdirs import user_data_dir


def data_root() -> Path:
    """Runtime data root (clips, state, soundboard list)."""
    override = os.environ.get("SOUNDSBORED_DATA")
    if override:
        return Path(override).expanduser().resolve()
    return Path(user_data_dir("soundsbored", appauthor=False))


def clips_dir() -> Path:
    return data_root() / "clips"


def state_dir() -> Path:
    return data_root() / "state"


def ipc_dir() -> Path:
    return state_dir() / "ipc"


def index_path() -> Path:
    return clips_dir() / "index.tsv"


def toggle_path() -> Path:
    return state_dir() / "wooo_awww"


def volume_path() -> Path:
    return state_dir() / "volume"


def soundboard_list_path() -> Path:
    return data_root() / "soundboard.txt"


def ensure_layout() -> None:
    """Create data dirs and seed default soundboard.txt if missing."""
    data_root().mkdir(parents=True, exist_ok=True)
    clips_dir().mkdir(parents=True, exist_ok=True)
    state_dir().mkdir(parents=True, exist_ok=True)
    ipc_dir().mkdir(parents=True, exist_ok=True)

    dest = soundboard_list_path()
    if not dest.exists():
        bundled = _bundled_soundboard()
        if bundled is not None:
            shutil.copyfile(bundled, dest)


def _bundled_soundboard() -> Path | None:
    """Locate the package-shipped default soundboard.txt."""
    # Prefer importlib.resources (installed package)
    try:
        ref = resources.files("soundsbored") / "data" / "soundboard.txt"
        if ref.is_file():
            # resources may return a Traversable; materialize to a real path if needed
            with resources.as_file(ref) as p:
                return Path(p)
    except (TypeError, FileNotFoundError, ModuleNotFoundError):
        pass

    # Dev / editable install: repo data/ next to package root
    candidates = [
        Path(__file__).resolve().parents[2] / "data" / "soundboard.txt",
        Path(__file__).resolve().parent / "data" / "soundboard.txt",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def which(cmd: str) -> str | None:
    return shutil.which(cmd)
