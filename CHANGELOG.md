# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `PASTE_COMBO` configuration key: the key sequence injected after a
  successful transcription (default `ctrl+v`, shipped configs set
  `ctrl+shift+v`)
- `docs/OPERATIONS.md`: definitive operations runbook covering the ffmpeg ABI
  break, VRAM exhaustion, terminal paste, and injector troubleshooting, with
  a full incident log and gotcha list

### Fixed

- `_ydotool_key` now respects ydotool's real exit code, so the wtype/xdotool
  fallbacks actually trigger when injection fails instead of being silently
  skipped
- Terminals no longer swallow pastes: `Ctrl+V` is readline literal-insert in
  Konsole/opencode/jcode, so the paste combo defaults to `ctrl+shift+v` for
  terminal setups

## [0.5.0] - 2026-07-28

First tagged release. Local, offline voice dictation for Linux: hold a key,
speak, release, and the text lands at the cursor.

### Added

- `whispy gui` command and `whispy-gui` entry point, plus a control panel
- Desktop launcher: opens the panel, right-click switches provider
- `whispy providers` command; version pinned to `pyproject.toml`
- `cloud_model` configuration fields

### Fixed

- Transcription output kept its punctuation and capitalization, and is cleaned
  once rather than repeatedly
- The provider registry was broken, leaving every backend unreachable
- Transcription failures surfaced instead of being swallowed
- `tkinter` no longer pulled in through the package import, so the test suite
  runs without Tk
- CI hardened for hosts where `evdev` is absent

[0.5.0]: https://github.com/ciroautuori/whispy/releases/tag/v0.5.0
