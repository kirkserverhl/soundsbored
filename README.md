# Soundsbored

Multi-category soundboard for **Linux** (rofi) and **macOS** (fzf).

Port of the Hyprland/rofi soundboard: category browser, persistent hotkeys (Sad Trombone, Damn Son, Wooo/Awww toggle, random laugh), overlapping **mpv** playback, fade-out, and clip downloads via **yt-dlp**.

## Features

- Categories: **Openings → In-Call → Closers / Misc**
- Persistent hotkey strip on every page
- Overlapping clip playback (classic soundboard behavior)
- Smooth fade-out or hard stop
- First-run (or `soundsbored download`) pulls audio from your `soundboard.txt`
- Installable Python package — `pip install` from GitHub on a work Mac

## System requirements

| Tool | Purpose | macOS | Linux |
|------|---------|-------|-------|
| **Python** 3.10+ | Runtime | built-in / brew | distro |
| **mpv** | Playback | `brew install mpv` | distro package |
| **yt-dlp** | Clip download | `brew install yt-dlp` | distro / pip |
| **fzf** | Menu (macOS default) | `brew install fzf` | optional |
| **rofi** | Menu (Linux default) | — | distro package |

Optional: `ffmpeg` (often pulled in by yt-dlp for audio extract).

## Install from GitHub (macOS work laptop)

```bash
# 1. System tools
brew install mpv fzf yt-dlp ffmpeg python

# 2a. Easiest: pipx (isolated app install)
brew install pipx
pipx ensurepath
pipx install "git+https://github.com/YOUR_USER/soundsbored.git"
pipx inject soundsbored yt-dlp   # optional Python yt-dlp fallback

# 2b. Or: virtualenv
git clone https://github.com/YOUR_USER/soundsbored.git
cd soundsbored
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[download]"
```

Replace `YOUR_USER` with your GitHub username. After install, `soundsbored` should be on your `PATH` (open a new terminal if needed).

### Editable / local clone

```bash
git clone https://github.com/YOUR_USER/soundsbored.git
cd soundsbored
python3 -m venv .venv
source .venv/bin/activate   # fish: source .venv/bin/activate.fish
pip install -e ".[download]"
```

## Usage

```bash
# Open the soundboard (downloads clips on first run)
soundsbored

# Start on a specific category
soundsbored openings
soundsbored in-call
soundsbored closers

# Re-download / refresh clips from soundboard.txt
soundsbored download

# Control playback without opening the menu
soundsbored fade
soundsbored stop

# Show data dir + detected menu backend
soundsbored info
```

### Menu controls

| Action | rofi (Linux) | fzf (macOS) | plain CLI |
|--------|--------------|-------------|-----------|
| Next category | `→` | `→` / `Ctrl-n` | `n` |
| Previous category | `←` | `←` / `Ctrl-p` | `p` |
| Hotkeys 1–4 | `Alt+1`…`Alt+4` | `Ctrl-1`…`Ctrl-4` | `h1`…`h4` |
| Fade out | `Alt+f` | `Ctrl-f` | `f` |
| Stop | `Alt+x` | `Ctrl-x` | `x` |
| Filter | type to filter | type to filter | pick number |
| Quit | `Esc` | `Esc` | `q` |

Force a menu backend:

```bash
export SOUNDSBORED_MENU=fzf   # rofi | fzf | cli
```

## Data layout

| Platform | Default data directory |
|----------|------------------------|
| Linux | `~/.local/share/soundsbored/` |
| macOS | `~/Library/Application Support/soundsbored/` |

Contents:

```
soundboard.txt     # clip list (seeded from package default on first run)
clips/             # downloaded audio + index.tsv
state/             # toggle state + mpv IPC sockets
```

Override the root:

```bash
export SOUNDSBORED_DATA="$HOME/Soundsbored"
```

Edit `soundboard.txt` then run `soundsbored download`. Format:

```text
## Intros ##

# Clip Name
https://www.youtube.com/watch?v=...

## In-Call ##
...
```

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `SOUNDSBORED_DATA` | platform data dir | Runtime data root |
| `SOUNDSBORED_MENU` | auto | `rofi` / `fzf` / `cli` |
| `SOUNDSBORED_ROFI_THEME` | auto | Path to `.rasi` theme |
| `SOUNDSBORED_FADE_SECS` | `1.5` | Fade duration |
| `SOUNDSBORED_FADE_STEPS` | `20` | Fade steps |

## Push this repo to GitHub

From the machine where this package lives:

```bash
cd soundsbored
git init
git add .
git commit -m "Initial soundsbored Python package"
gh repo create soundsbored --public --source=. --remote=origin --push
# or: git remote add origin git@github.com:YOUR_USER/soundsbored.git && git push -u origin main
```

Then on the Mac:

```bash
brew install mpv fzf yt-dlp ffmpeg pipx
pipx ensurepath
pipx install "git+https://github.com/YOUR_USER/soundsbored.git"
soundsbored download   # first-time clip fetch
soundsbored
```

## Linux notes (existing rofi setup)

If you already use the bash/rofi version under Hyprland, this package coexists:

- Same `soundboard.txt` semantics and category/hotkey behavior
- Default Linux data dir matches `~/.local/share/soundsbored`
- Uses your `~/.config/rofi/config-soundsbored.rasi` when present

You can keep the old bash script or switch the keybind to `soundsbored`.

## License

MIT
