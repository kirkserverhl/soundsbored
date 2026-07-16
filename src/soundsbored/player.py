"""mpv playback with fade/stop via JSON IPC (pure Python sockets)."""

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
from soundsbored.paths import ipc_dir, which


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

    # Overlapping playback (classic soundboard). Quiet, no video, IPC for fade-out.
    subprocess.Popen(
        [
            mpv,
            "--no-video",
            "--really-quiet",
            "--volume=100",
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

    def _worker(targets: list[Path]) -> None:
        for i in range(1, steps + 1):
            vol = max(0, 100 - (100 * i // steps))
            for s in targets:
                mpv_cmd(s, ["set_property", "volume", vol])
            time.sleep(delay)
        for s in targets:
            mpv_cmd(s, ["quit"])
            try:
                s.unlink(missing_ok=True)
            except OSError:
                pass

    threading.Thread(target=_worker, args=(socks,), daemon=True).start()
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
