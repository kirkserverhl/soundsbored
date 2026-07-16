"""Parse soundboard.txt and download clips with yt-dlp."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from soundsbored.notify import warn
from soundsbored.paths import clips_dir, index_path, soundboard_list_path, which

AUDIO_EXTS = ("opus", "m4a", "webm", "mp3", "ogg", "wav", "flac")


def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "clip"


def _detect_js_runtime() -> str | None:
    """Return yt-dlp --js-runtimes value if node/deno/bun is on PATH."""
    for name in ("node", "deno", "bun"):
        path = which(name)
        if path:
            return f"{name}:{path}"
    return None


def _existing_audio(base: Path) -> Path | None:
    for ext in AUDIO_EXTS:
        candidate = Path(f"{base}.{ext}")
        if candidate.is_file():
            return candidate
    return None


def _classify(name: str, section: str, after_police: bool) -> tuple[str, str]:
    """Return (category, role) for a clip name."""
    nlc = name.lower()
    cat: str
    role: str

    if after_police or section == "hotkeys":
        cat = "hotkeys"
        if "wooo" in nlc:
            role = "toggle_a"
        elif "awww" in nlc or re.search(r"\baww\b", nlc):
            role = "toggle_b"
        elif "laugh" in nlc:
            role = "random"
        else:
            role = "hotkey"
    else:
        if section in ("intros", "openings"):
            cat = "openings"
        elif section in ("in-call", "incall"):
            cat = "in-call"
        elif section.startswith("closers") or section.startswith("misc"):
            cat = "closers"
        else:
            cat = section or "misc"
        role = "normal"

    # Name-based overrides (hotkey strip + toggle + random)
    if "police" in nlc and "siren" in nlc:
        cat, role = "closers", "normal"
    elif "sad" in nlc and "trombone" in nlc:
        cat, role = "hotkeys", "hotkey"
    elif "damn" in nlc and "son" in nlc:
        cat, role = "hotkeys", "hotkey"
    elif "wooo" in nlc:
        cat, role = "hotkeys", "toggle_a"
    elif "awww" in nlc or re.search(r"\baww\b", nlc):
        cat, role = "hotkeys", "toggle_b"
    elif "laugh" in nlc:
        cat, role = "hotkeys", "random"

    return cat, role


def download_all(list_path: Path | None = None) -> Path:
    """Download all clips and write index.tsv. Returns index path."""
    list_file = list_path or soundboard_list_path()
    if not list_file.is_file():
        raise FileNotFoundError(f"Missing list: {list_file}")

    ytdlp = which("yt-dlp")
    if not ytdlp:
        # Fall back to python -m yt_dlp if package installed
        try:
            import yt_dlp  # noqa: F401

            ytdlp_cmd: list[str] = [shutil.which("python3") or "python3", "-m", "yt_dlp"]
        except ImportError as e:
            raise RuntimeError(
                "yt-dlp is required. Install with:\n"
                "  pip install 'soundsbored[download]'\n"
                "  # or: brew install yt-dlp / pip install yt-dlp"
            ) from e
    else:
        ytdlp_cmd = [ytdlp]

    # YouTube now wants a JS runtime for reliable extraction (node/deno/bun).
    js_runtime = _detect_js_runtime()
    if js_runtime:
        ytdlp_cmd.extend(["--js-runtimes", js_runtime])
    else:
        warn(
            "No JS runtime found for yt-dlp (recommended on macOS).\n"
            "  brew install node\n"
            "  # or: brew install deno\n"
            "YouTube downloads may fail or be incomplete without one."
        )

    clips = clips_dir()
    clips.mkdir(parents=True, exist_ok=True)
    idx = index_path()

    print(f"==> Parsing {list_file}")
    # Re-parse with after_police tracking inline (full port of bash logic)
    entries_tsv: list[str] = []

    section = ""
    current_name = ""
    current_urls: list[str] = []
    after_police = False

    def flush_entry(name: str, urls: list[str]) -> None:
        nonlocal after_police
        if not name or not urls:
            return

        cat, role = _classify(name, section, after_police)
        slug = slugify(name)
        nlc = name.lower()

        for i, url in enumerate(urls, start=1):
            if len(urls) > 1:
                base = clips / f"{slug}-{i:02d}"
            else:
                base = clips / slug

            existing = _existing_audio(base)
            if existing:
                print(f"  skip (exists): {name} → {existing.name}")
                entries_tsv.append(
                    f"{cat}\t{role}\t{name}\t{slug}\t{existing}\t{url}"
                )
                continue

            print(f"  download: {name}")
            print(f"    {url}")
            out_tmpl = f"{base}.%(ext)s"
            cmd = ytdlp_cmd + [
                "--no-playlist",
                "-x",
                "--audio-format",
                "opus",
                "--audio-quality",
                "0",
                "-o",
                out_tmpl,
                "--no-overwrites",
                "--quiet",
                "--progress",
                url,
            ]
            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError:
                warn(f"    WARN: yt-dlp failed for {name} ({url})")
                continue

            got = _existing_audio(base)
            if got is None:
                # yt-dlp may have used a slightly different name
                matches = sorted(clips.glob(f"{base.name}.*"), key=lambda p: p.stat().st_mtime, reverse=True)
                matches = [m for m in matches if m.suffix.lstrip(".") in AUDIO_EXTS]
                got = matches[0] if matches else None

            if got and got.is_file():
                entries_tsv.append(f"{cat}\t{role}\t{name}\t{slug}\t{got}\t{url}")
            else:
                warn(f"    WARN: download finished but file not found for {name}")

        if "police" in nlc and "siren" in nlc:
            after_police = True

    for raw in list_file.read_text(encoding="utf-8").splitlines():
        line = raw.replace("\r", "").strip()
        if not line or line.startswith("//"):
            continue

        if line.startswith("##") and line.endswith("##") and not line.startswith("##Make"):
            if current_name:
                flush_entry(current_name, current_urls)
                current_name = ""
                current_urls = []
            local_sec = line[2:-2].strip().lower()
            local_sec = re.sub(r"\s+", " ", local_sec)
            if local_sec.startswith("intro") or local_sec.startswith("opening"):
                section = "intros"
            elif local_sec.startswith("in-call") or local_sec.startswith("incall") or local_sec == "in call":
                section = "in-call"
            elif local_sec.startswith("closer") or local_sec.startswith("misc"):
                section = "closers"
            else:
                section = local_sec
            after_police = False
            print(f"-- section: {section}")
            continue

        if line.startswith("##Make") or line.startswith("## Make"):
            continue

        if line.startswith("#") and not line.startswith("##"):
            if current_name:
                flush_entry(current_name, current_urls)
            current_name = line[1:].strip()
            current_urls = []
            continue

        if line.startswith("http://") or line.startswith("https://"):
            if not current_name:
                current_name = "unnamed"
            current_urls.append(line)
            continue

        if not line.startswith("#") and not line.startswith("http://") and not line.startswith("https://"):
            if current_name and current_urls:
                flush_entry(current_name, current_urls)
                current_urls = []
            current_name = line
            current_urls = []

    if current_name:
        flush_entry(current_name, current_urls)

    header = "# category\trole\tname\tslug\tpath\turl\n"
    idx.write_text(header + "\n".join(entries_tsv) + ("\n" if entries_tsv else ""), encoding="utf-8")

    n_files = sum(1 for p in clips.iterdir() if p.is_file() and p.name != "index.tsv")
    print()
    print(f"==> Done. Index: {idx}")
    print(f"    Clips: {n_files} files")
    return idx
