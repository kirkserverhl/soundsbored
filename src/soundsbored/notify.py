"""Desktop notifications (Linux notify-send / macOS osascript)."""

from __future__ import annotations

import platform
import subprocess
import sys

from soundsbored.paths import which


def notify(title: str, body: str, timeout_ms: int | None = None) -> None:
    """Best-effort notification; never raises."""
    try:
        if platform.system() == "Darwin":
            _mac(title, body)
        elif which("notify-send"):
            _linux(title, body, timeout_ms)
    except Exception:
        pass


def _linux(title: str, body: str, timeout_ms: int | None) -> None:
    cmd = ["notify-send", "-a", "soundsbored"]
    if timeout_ms is not None:
        cmd.extend(["-t", str(timeout_ms)])
    cmd.extend([title, body])
    subprocess.run(cmd, check=False, capture_output=True)


def _mac(title: str, body: str) -> None:
    # Escape for AppleScript string literals
    t = title.replace("\\", "\\\\").replace('"', '\\"')
    b = body.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{b}" with title "{t}"'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def warn(msg: str) -> None:
    print(msg, file=sys.stderr)
