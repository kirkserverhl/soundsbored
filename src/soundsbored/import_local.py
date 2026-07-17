"""Import local audio from an unprocessed bin into the clip index.

Used for machine-local drops (not always in git). Converts to opus, normalizes
loudness toward -14 LUFS when ffmpeg is available, and appends as in-call
(or a chosen category) with url=local:<original-name>.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from soundsbored.download import slugify
from soundsbored.notify import notify, warn
from soundsbored.paths import clips_dir, data_root, ensure_layout, index_path, which

AUDIO_EXTS = {".opus", ".m4a", ".webm", ".mp3", ".ogg", ".wav", ".flac", ".aac"}
TARGET_I = -14.0
TARGET_TP = -1.5

# Friendly display names for known drop-ins (optional)
NAME_OVERRIDES: dict[str, str] = {
    "cisco hold music": "Cisco Hold Music",
    "cisco hold music.": "Cisco Hold Music",
    "dj air horn sound effect": "DJ Air Horn",
    "french fry pizza": "French Fry Pizza",
    "i'll be back arnold schwarzenegger sound effect (download)": "I'll Be Back",
    "i'll be back arnold schwarzenegger sound effect": "I'll Be Back",
    "i'm rich bitch (biatch)!! ___ dave chappelle": "I'm Rich Bitch",
    "i'm rich bitch (biatch)!! dave chappelle": "I'm Rich Bitch",
    "seinfeld noise feat. seinfeld": "Seinfeld Bass",
    "seinfeld noise feat seinfeld": "Seinfeld Bass",
}


def unprocessed_dirs() -> list[Path]:
    """Candidate unprocessed bins (data dir first, then repo if present)."""
    dirs: list[Path] = []
    primary = data_root() / "unprocessed"
    dirs.append(primary)
    # Dev clone next to package: ../../unprocessed from src/soundsbored/
    repo_up = Path(__file__).resolve().parents[2] / "unprocessed"
    if repo_up not in dirs:
        dirs.append(repo_up)
    return dirs


def _display_name(stem: str) -> str:
    key = re.sub(r"\s+", " ", stem.strip().lower())
    key = key.rstrip(".")
    if key in NAME_OVERRIDES:
        return NAME_OVERRIDES[key]
    # Title-ish fallback
    return re.sub(r"[_\.]+", " ", stem).strip()


def _measure_lufs(path: Path) -> float | None:
    r = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    m = re.findall(r"I:\s*([-\d.]+)\s*LUFS", r.stderr)
    return float(m[-1]) if m else None


def _convert_normalize(src: Path, dst: Path) -> bool:
    """Convert to opus; loudnorm to TARGET_I when possible."""
    ffmpeg = which("ffmpeg")
    if not ffmpeg:
        warn("ffmpeg not found — cannot convert local import")
        return False

    raw = dst.with_suffix(".raw.tmp.opus")
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-y", "-i", str(src), "-c:a", "libopus", "-b:a", "128k", str(raw)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not raw.is_file():
        warn(f"convert failed: {src.name}")
        raw.unlink(missing_ok=True)
        return False

    # two-pass loudnorm
    r1 = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-y",
            "-i",
            str(raw),
            "-af",
            f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    err = r1.stderr
    start, end = err.rfind("{"), err.rfind("}")
    if start >= 0 and end > start:
        try:
            m = json.loads(err[start : end + 1])
            af = (
                f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA=11:linear=true:"
                f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
                f"offset={m['target_offset']}"
            )
            r2 = subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-y",
                    "-i",
                    str(raw),
                    "-af",
                    af,
                    "-c:a",
                    "libopus",
                    "-b:a",
                    "128k",
                    str(dst),
                ],
                capture_output=True,
                text=True,
            )
            raw.unlink(missing_ok=True)
            if r2.returncode == 0 and dst.is_file():
                return True
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    # fallback gain
    before = _measure_lufs(raw)
    if before is None:
        raw.replace(dst)
        return dst.is_file()
    gain = max(-20.0, min(24.0, TARGET_I - before))
    af = f"volume={gain:.2f}dB,alimiter=limit=0.89:level=false"
    r3 = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-y",
            "-i",
            str(raw),
            "-af",
            af,
            "-c:a",
            "libopus",
            "-b:a",
            "128k",
            str(dst),
        ],
        capture_output=True,
        text=True,
    )
    raw.unlink(missing_ok=True)
    return r3.returncode == 0 and dst.is_file()


def _load_index_rows(path: Path) -> list[str]:
    if not path.is_file():
        return []
    rows: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            rows.append(line)
    return rows


def import_unprocessed(
    category: str = "in-call",
    *,
    source_dir: Path | None = None,
) -> int:
    """
    Import audio files from unprocessed/ into clips + index.

    Returns number of clips imported.
    """
    ensure_layout()
    clips = clips_dir()
    clips.mkdir(parents=True, exist_ok=True)
    idx = index_path()

    bins: list[Path] = [source_dir] if source_dir else unprocessed_dirs()
    sources: list[Path] = []
    for d in bins:
        if d is None or not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
                sources.append(p)

    if not sources:
        print("No audio files found in unprocessed bins:")
        for d in bins:
            if d is not None:
                print(f"  {d}")
        print("Drop .mp3/.wav/… files there, then re-run: soundsbored import")
        return 0

    rows = _load_index_rows(idx)
    by_slug = {r.split("\t")[3]: i for i, r in enumerate(rows) if "\t" in r}
    imported = 0

    print(f"==> Importing {len(sources)} file(s) → category={category}")
    for src in sources:
        name = _display_name(src.stem)
        slug = slugify(name)
        dst = clips / f"{slug}.opus"
        print(f"→ {name} ({src.name})")
        if not _convert_normalize(src, dst):
            warn(f"  failed: {src.name}")
            continue
        lufs = _measure_lufs(dst)
        print(f"  ok  → {dst.name}  LUFS={lufs}")
        row = f"{category}\tnormal\t{name}\t{slug}\t{dst}\tlocal:{src.name}"
        if slug in by_slug:
            rows[by_slug[slug]] = row
        else:
            # Insert after last row of same category if possible
            insert_at = len(rows)
            for i, r in enumerate(rows):
                if r.startswith(f"{category}\t"):
                    insert_at = i + 1
            rows.insert(insert_at, row)
            by_slug[slug] = insert_at
            # rebuild by_slug indices after insert
            by_slug = {r.split("\t")[3]: i for i, r in enumerate(rows) if "\t" in r}
        imported += 1

        # Move source into processed/
        done = src.parent / "processed"
        done.mkdir(parents=True, exist_ok=True)
        dest = done / src.name
        if dest.exists():
            dest.unlink()
        shutil.move(str(src), str(dest))
        print(f"  moved → {done.name}/{src.name}")

    header = "# category\trole\tname\tslug\tpath\turl\n"
    idx.write_text(header + "\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
    print(f"\n==> Imported {imported} clip(s). Index: {idx}")
    if imported:
        notify("Soundsbored", f"Imported {imported} local clip(s) → {category}")
    return imported
