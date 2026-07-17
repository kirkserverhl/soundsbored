# Soundsbored

Multi-category soundboard — **one Python package** for:

| Platform | Menu | Typical install |
|----------|------|-----------------|
| **Arch / Linux** | **rofi** | Editable clone + thin Hyprland wrapper |
| **macOS** | **fzf** | `pipx install` from this repo |

Same categories, hotkeys, playback, download, and clip index on both. Only the menu UI is capability-detected (`rofi` → `fzf` → numbered CLI).

## Features

- Categories: **Openings → In-Call → Closers / Misc**
- Persistent hotkey strip on every page:
  - **Sad Trombone**, **Damn Son**, **Wooo**, **Awww** (separate buttons)
  - Random **Laugh Track**, **Fade**, **Stop**
  - Menu volume up/down (remembered)
- Overlapping **mpv** playback (classic soundboard)
- Smooth fade-out or hard stop
- `soundsbored download` — yt-dlp from `soundboard.txt`
- `soundsbored import` — drop local files into `unprocessed/`, convert + level into **In-Call**
- First-run auto-download when the clip index is empty

## Architecture

```
soundsbored (this repo)          ← single source of truth
  ├─ src/soundsbored/            ← Python package
  ├─ data/soundboard.txt         ← default clip list (seeded into data dir)
  └─ unprocessed/                ← optional local drop bin (gitignored audio)

Runtime data (not in git):
  Linux:  ~/.local/share/soundsbored/
  macOS:  ~/Library/Application Support/soundsbored/
    clips/index.tsv + *.opus
    soundboard.txt
    state/
```

Arch Hyprland keybind should call a **thin wrapper** that execs this package
(see [Linux (Arch) setup](#linux-arch-setup) below) — not a second bash reimplementation.

## System requirements

| Tool | Purpose | macOS | Linux |
|------|---------|-------|-------|
| **Python** 3.10+ | Runtime | brew / system | distro |
| **mpv** | Playback | `brew install mpv` | distro |
| **yt-dlp** | YouTube downloads | `brew install yt-dlp` | distro / pip |
| **ffmpeg** | Convert / normalize local imports | `brew install ffmpeg` | distro |
| **fzf** | Menu (macOS) | `brew install fzf` | optional |
| **rofi** | Menu (Linux) | — | distro |
| **node** (optional) | Reliable YouTube extract | `brew install node` | distro |

## Install — macOS (work laptop)

```bash
brew install mpv fzf yt-dlp ffmpeg python node

# Option A: pipx
brew install pipx && pipx ensurepath
pipx install "git+https://github.com/YOUR_USER/soundsbored.git"
pipx inject soundsbored yt-dlp

# Option B: editable clone
git clone https://github.com/YOUR_USER/soundsbored.git
cd soundsbored
python3 -m venv .venv
source .venv/bin/activate   # fish: source .venv/bin/activate.fish
pip install -e ".[download]"
```

Replace `YOUR_USER` with the GitHub owner. Open a new terminal if `soundsbored` is not on `PATH`.

## Install — Linux (Arch) setup

Keep **one clone** (e.g. `~/soundsbored`) and install editable:

```bash
cd ~/soundsbored
python3 -m venv .venv
.venv/bin/pip install -e ".[download]"
.venv/bin/soundsbored doctor
```

Point your Hyprland keybind wrapper at that venv (example already used on this machine):

```bash
# ~/.config/hyprgruv/scripts/soundsbored.sh  (or your SCRIPTS path)
#!/usr/bin/env bash
set -euo pipefail
REPO="${SOUNDSBORED_REPO:-$HOME/soundsbored}"
exec "$REPO/.venv/bin/soundsbored" "$@"
```

Optional rofi theme for a corner panel (no click-to-exit):  
`~/.config/rofi/config-soundsbored.rasi` — used automatically when present.

Data dir matches the old bash setup: `~/.local/share/soundsbored/` (clips + index are reused).

## Usage

```bash
soundsbored                 # open menu (Openings)
soundsbored in-call         # start on In-Call
soundsbored closers

soundsbored download        # refresh YouTube clips; keeps local: rows
soundsbored import          # unprocessed/* → In-Call (convert + normalize)
soundsbored import closers  # import into Closers instead

soundsbored fade
soundsbored stop
soundsbored info
soundsbored doctor
soundsbored version
```

### Menu controls

| Action | rofi (Linux) | fzf (macOS) | CLI |
|--------|--------------|-------------|-----|
| Next / prev category | `→` / `←` | `→`/`Ctrl-n` · `←`/`Ctrl-p` | `n` / `p` |
| Sad / Damn / Wooo / Awww | `Alt+1`…`Alt+4` | `Ctrl-1`…`Ctrl-4` | `h1`…`h4` |
| Random laugh | `Alt+l` | `Ctrl-l` | menu item |
| Fade / Stop | `Alt+f` / `Alt+x` | `Ctrl-f` / `Ctrl-x` | `f` / `x` |
| Filter | type | type | number |
| Quit | `Esc` | `Esc` | `q` |

```bash
export SOUNDSBORED_MENU=fzf   # force: rofi | fzf | cli
export SOUNDSBORED_DATA=~/somewhere   # override data root
```

## Clip list & local imports

**YouTube / remote clips** live in `soundboard.txt` (seeded from the package on first run).

**Machine-local drops** (not always shared via git — audio is gitignored):

1. Put files in either:
   - `~/.local/share/soundsbored/unprocessed/` (Linux), or  
   - `~/Library/Application Support/soundsbored/unprocessed/` (macOS), or  
   - `./unprocessed/` in a dev clone  
2. Run: `soundsbored import`  
3. Files are converted to opus, leveled (~−14 LUFS), indexed under **In-Call**, and moved to `unprocessed/processed/`

`soundsbored download` **preserves** index rows whose URL starts with `local:` so re-downloads do not wipe imports.

## Keeping Mac and Arch in sync

1. Develop / change features in **this git repo** only.  
2. On Arch: `git pull` + `.venv/bin/pip install -e ".[download]"` (or restart if already editable).  
3. On Mac: `pipx upgrade soundsbored` or `git pull` + reinstall editable.  
4. Clip **binaries** stay per-machine (or copy `clips/` if you want identical audio).  
5. Clip **list** is shared via `soundboard.txt` in git; after editing, copy to the runtime list or delete the runtime list and re-seed:

```bash
# optional: refresh seeded list from package (keeps existing clips/)
cp ~/soundsbored/src/soundsbored/data/soundboard.txt \
   ~/.local/share/soundsbored/soundboard.txt   # Linux
```

## Deploy checklist (new machine)

```bash
# 1. tools
# macOS: brew install mpv fzf yt-dlp ffmpeg python node
# Arch:  sudo pacman -S mpv rofi yt-dlp ffmpeg python-pip

# 2. package
pipx install "git+https://github.com/YOUR_USER/soundsbored.git"
# or editable clone

# 3. first run
soundsbored doctor
soundsbored download
soundsbored               # Linux: rofi · macOS: fzf

# 4. optional local FX
mkdir -p "$(soundsbored info | awk '/data:/{print $2}')/unprocessed"
# drop mp3s, then:
soundsbored import
```

## License

MIT — see `LICENSE`.
