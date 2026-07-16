"""mpv playback with fade/stop/volume via JSON IPC (pure Python sockets).

Volume and playback are platform-agnostic (mpv). OS differences live only
in the menu backend (rofi/fzf) and notifications.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path

from soundsbored.notify import notify, warn
from soundsbored.paths import ipc_dir, volume_path, which

DEFAULT_VOLUME = 100
VOLUME_STEP = 10
VOLUME_MIN = 0
VOLUME_MAX = 100


def _fade_secs() -> float:
    try:
        return float(os.environ.get("SOUNDSBORED_FADE_SECS", "1.5"))
    except ValueError:
        return 1.5


def _fade_steps() -> int:
    try:
        return max(1, int(os.environ.get("SOUNDSBORED_FADE_STEPS", "20")))
    except ValueError:
        return 20


def get_volume() -> int:
    """Persistent board volume (0–100). Shared on Linux and macOS."""
    p = volume_path()
    try:
        raw = p.read_text(encoding="utf-8").strip()
        return max(VOLUME_MIN, min(VOLUME_MAX, int(raw)))
    except (OSError, ValueError):
        return DEFAULT_VOLUME


def set_volume(level: int, *, apply_live: bool = True, notify_user: bool = True) -> int:
    """Clamp, persist, optionally push to active mpv instances."""
    level = max(VOLUME_MIN, min(VOLUME_MAX, int(level)))
    try:
        volume_path().parent.mkdir(parents=True, exist_ok=True)
        volume_path().write_text(f"{level}\n", encoding="utf-8")
    except OSError as e:
        warn(f"Could not save volume: {e}")

    if apply_live:
        for s in _active_socks():
            mpv_cmd(s, ["set_property", "volume", level])

    if notify_user:
        notify("Soundsbored", f"Volume {level}%", timeout_ms=900)
    return level


def volume_up(step: int = VOLUME_STEP) -> int:
    return set_volume(get_volume() + step)


def volume_down(step: int = VOLUME_STEP) -> int:
    return set_volume(get_volume() - step)


def _mpv_bin() -> str:
    bin_path = which("mpv")
    if not bin_path:
        raise RuntimeError(
            "mpv not found. Install it (e.g. `brew install mpv` on macOS, "
            "or your distro package manager on Linux)."
        )
    return bin_path


def mpv_cmd(sock_path: Path, command: list) -> bool:
    """Send a JSON IPC command to one mpv unix socket."""
    if not sock_path.is_socket() and not sock_path.exists():
        return False
    payload = (json.dumps({"command": command}) + "\n").encode()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.25)
            s.connect(str(sock_path))
            s.sendall(payload)
            # Drain a bit so mpv doesn't fill the buffer
            try:
                s.recv(4096)
            except (TimeoutError, OSError):
                pass
        return True
    except OSError:
        return False


def prune_ipc() -> None:
    d = ipc_dir()
    if not d.is_dir():
        return
    for sock in d.glob("mpv-*.sock"):
        if not mpv_cmd(sock, ["get_property", "pid"]):
            try:
                sock.unlink(missing_ok=True)
            except OSError:
                pass


def play_file(path: Path | str | None) -> bool:
    if not path:
        notify("Soundsbored", "Missing clip")
        return False
    f = Path(path)
    if not f.is_file():
        notify("Soundsbored", f"Missing clip: {f}")
        return False

    prune_ipc()
    sock = ipc_dir() / f"mpv-{os.getpid()}-{uuid.uuid4().hex[:10]}.sock"
    try:
        mpv = _mpv_bin()
    except RuntimeError as e:
        warn(str(e))
        notify("Soundsbored", str(e))
        return False

    vol = get_volume()
    # Overlapping playback (classic soundboard). Quiet, no video, IPC for fade-out.
    subprocess.Popen(
        [
            mpv,
            "--no-video",
            "--really-quiet",
            f"--volume={vol}",
            "--force-window=no",
            f"--input-ipc-server={sock}",
            "--keep-open=no",
            str(f),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True


def _active_socks() -> list[Path]:
    prune_ipc()
    d = ipc_dir()
    if not d.is_dir():
        return []
    return sorted(d.glob("mpv-*.sock"))


def fade_out_all() -> None:
    socks = _active_socks()
    if not socks:
        notify("Soundsbored", "Nothing playing", timeout_ms=1000)
        return

    secs = _fade_secs()
    steps = _fade_steps()
    delay = secs / steps
    start_vol = get_volume()

    def _worker(targets: list[Path], start: int) -> None:
        for i in range(1, steps + 1):
            vol = max(0, start - (start * i // steps))
            for s in targets:
                mpv_cmd(s, ["set_property", "volume", vol])
            time.sleep(delay)
        for s in targets:
            mpv_cmd(s, ["quit"])
            try:
                s.unlink(missing_ok=True)
            except OSError:
                pass

    threading.Thread(target=_worker, args=(socks, start_vol), daemon=True).start()
    notify("Soundsbored", f"Fade out ({secs}s)…", timeout_ms=1200)


def stop_all() -> None:
    socks = _active_socks()
    for s in socks:
        mpv_cmd(s, ["quit"])
        try:
            s.unlink(missing_ok=True)
        except OSError:
            pass
    notify("Soundsbored", "Stopped", timeout_ms=1000)
