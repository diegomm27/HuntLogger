# HuntLogger

HuntLogger is a desktop match logger for Hunt: Showdown 1896. It watches locally available game evidence, stores sessions and captures in a local SQLite database, and presents the results in a PySide6 desktop UI.

It exists because Crytek does not provide a public API for extracting this data directly. HuntLogger works only with data the game already exposes locally on the user's machine.

## What it does

- Watches Hunt local files and logs for post-match evidence
- Captures post-match screenshots and extracts visible stats from them
- Tracks game sessions inferred from `Game.log`
- Shows account settings, keybindings, and other locally stored profile data
- Keeps all data local in `%LOCALAPPDATA%/HuntLogger`
- Reads game data only; it does not modify Hunt files, inject into the game, or automate gameplay

## Important limitation

Hunt: Showdown 1896 does not currently write full structured match results to a local file. That means:

- `attributes.xml` is useful for account/profile data
- `Game.log` is useful for timing and session inference
- the post-match screen is the most useful local source for per-match values
- some values may be missing or uncertain when OCR cannot read them cleanly

The application is designed around that limitation.

HuntLogger is read-only with respect to game data. It observes local files, logs, and screenshots, but it does not patch, rewrite, or otherwise modify Hunt data.

## Current data sources

| Source | Purpose |
|---|---|
| `USER/Game.log` | Read-only source for session timing, post-match transitions, and match-end hints |
| `USER/Profiles/default/attributes.xml` | Read-only source for account/profile state, graphics, audio, sensitivity, and keybindings |
| Post-match screenshots | Read-only visual capture used for OCR/vision-based extraction of visible result values |
| Steam `594650.json` library cache | Read-only source for achievement delta tracking when present |
| `userdata/.../3764200/remote/win64_save/data*.bin` | Stored as read-only evidence only; not parsed yet |

## Features

- Match list mixing exact matches and screenshot-derived matches
- Match deletion for bad or partial screenshot groups
- Session history view with map, duration, and confidence
- In-game settings view with wider grouped layout
- Background screenshot parsing for retained captures
- Defensive capture flow that avoids saving desktop screenshots when Hunt is minimized or hidden

## Project layout

```text
hunt-test/
|-- run.py
|-- diagnose.py
|-- build.bat
|-- requirements.txt
`-- src/
    |-- main.py
    |-- config.py
    |-- db.py
    |-- parser.py
    |-- account_parser.py
    |-- evidence.py
    |-- evidence_collector.py
    |-- screen_capture.py
    |-- summary.py
    |-- vision_parser.py
    |-- watcher.py
    `-- ui/
        |-- account_panel.py
        |-- evidence_panel.py
        |-- main_window.py
        |-- match_detail.py
        |-- match_list.py
        |-- theme.py
        `-- widgets.py
```

## Requirements

- Windows
- Python 3.9+
- Hunt: Showdown 1896 installed (obviously xD)

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

## Build

```powershell
build.bat
```

This produces a PyInstaller build in `dist/`.

## How to use

1. Launch the app.
2. Set the Hunt install path in Settings if it is not auto-detected.
3. Keep recording enabled while playing.
4. At post-match, keep Hunt visible long enough for the capture flow to finish.

If Hunt is minimized during the post-match summary, HuntLogger now avoids falling back to desktop screenshots and warns you to restore the game window instead.

## Why this exists

Crytek does not offer a public API for players to pull their Hunt: Showdown 1896 match data, session data, or local post-match history in a structured way.

HuntLogger was built as a community tool around that gap. It does not try to bypass the game with private services or modify game files. Instead, it collects the local evidence already available to the player and organizes it into a usable history.

## Storage

Local app data is stored here:

```text
%LOCALAPPDATA%/HuntLogger/
```

That includes:

- `hunt_logger.db`
- `config.json`
- retained screenshot capture folders

## Known gaps

- OCR-derived matches can still contain partial or unknown values
- binary save files are not decoded yet
- packaged builds should still be validated end to end on a clean machine
- there is no system tray/background mode yet

## License

This project is licensed under the MIT License. See `LICENSE`.

## Launch

This project doesn't include an executable as it is still in development. However, it is made public just in case anyone want to work with it.
