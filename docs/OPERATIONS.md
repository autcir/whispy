# Whispy — Operations & Troubleshooting (RUNBOOK)

Definitive operations guide. Every failure mode found on the reference Arch/KDE
system, with the exact fix. Read **§3 runbook top-down** when something stops
working. Last updated: 2026-08-11 (whisper 0.5.0).

---

## 1. Data flow (what must happen on a successful dictation)

```
hold META+F12
   │  evdev keydown (code 125+88) — read by python-evdev in the ptt service
   ▼
whispy-ptt.service (user unit, `whispy ptt`)
   │  arecord -D pulse -r 16000 -c 1 -f S16_LE  →  /dev/shm/whispy.wav
release thumb
   ▼
whisper-cli (CUDA)  →  text
   ▼
wl-copy (clipboard)
   ▼
ydotool key <paste_combo>  →  uinput vdev event29  →  KWin  →  active window
```

Log in real time: `tail -f /tmp/whispy.log`. A good transcription cycle logs:

```
ptt record start pid=...
ptt stop → transcribe
audio size=XXXXX dur≈X.Xs
ok: 'the dictated text'
```

---

## 2. Component inventory (reference system, 2026-08-11)

| Component | Package / binary | Path / socket | Notes |
|---|---|---|---|
| PTT service | user unit `whispy-ptt.service` | ExecStart `/home/ciroautuori/.local/bin/whispy ptt` | Type=simple, Restart=on-failure, RestartSec=3 |
| Transcribe engine | `whisper.cpp-cuda` | `/usr/bin/whisper-cli` | **Must be rebuilt after every ffmpeg major upgrade** |
| Model (preferred) | — | `~/.local/share/whisper-toggle/models/ggml-large-v3-turbo.bin` (1.6 GB) | Set in config as `WHISPER_MODEL` |
| Model (fallback) | — | same dir, `ggml-base.bin` | — |
| Recording | alsa-utils | `arecord` | 16 kHz mono S16_LE → `/dev/shm/whispy.wav` |
| Clipboard | wl-clipboard | `wl-copy` | Wayland |
| Key injector | ydotool | `ydotool` + user daemon on `/run/user/1000/.ydotool_socket` | vdev `/dev/input/event29` name `ydot` |
| Notifications | libnotify | `notify-send` | — |
| Config | — | `~/.config/whispy/whispy.conf` | key=value, see §4 |
| Log | — | `/tmp/whispy.log` | append-only, rotates on service restart |

Environment the ptt service runs with (systemd user session):
`XDG_RUNTIME_DIR=/run/user/1000`, `WAYLAND_DISPLAY=wayland-0`,
`DISPLAY=:0`, `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus`,
`XDG_SESSION_TYPE=wayland`, `XDG_SESSION_DESKTOP=KDE`. `YDOTOOL_SOCKET` is
computed at runtime from `$XDG_RUNTIME_DIR` — no explicit env needed.

---

## 3. Runbook — top-down, in this order

### 3.1 Service alive?
```bash
systemctl --user status whispy-ptt        # ActiveWindow, MainPID
systemctl --user restart whispy-ptt       # apply config/code changes
```

### 3.2 Does the log capture the combo?
```bash
tail -f /tmp/whispy.log
```
- `ptt start combo=[88, 125] devices=[...]` → service listening on evdev.
- Then a cycle must show `record start → audio size → ok:`.
- **Nothing after a keypress** → the combo never reaches evdev (or wrong device).
  Confirm with a raw probe: read every device exposing `KEY_A`+`KEY_Z`
  (exclude the ydotool virtual device) via python-evdev + selectors and log
  codes 88/125. If the probe sees them but the service does not, the service
  was started before the device appeared → restart it.

On the reference system the real keyboards are: `ITE Tech. Inc. ITE
Device(8258) Keyboard` (usb 048d:c693), `C 2.4G Receiver` (usb 260d:1108),
`AT Translated Set 2 keyboard`. The `ydotoold virtual device` (event29) must
be excluded — it has no letters.

### 3.3 Whisper dies with "error while loading shared libraries"
```
whisper-cli failed (127): /usr/bin/whisper-cli: error while loading shared
libraries: libavformat.so.62: cannot open shared object file
```
**Cause:** `whisper.cpp-cuda` is a prebuilt binary linked against ffmpeg 8
(`libavformat.so.62`, `libavcodec.so.62`, `libavutil.so.60`,
`libswresample.so.6`). On 2026-08-07 ffmpeg went 8.1.2 → 9.0 (ABI break):
`/usr/lib/libavformat.so.63` replaced `.62` and the package was **not
rebuilt** → exit 127 on every transcription.

**Fix:**
```bash
yay -S --rebuild whisper.cpp-cuda          # rebuild against ffmpeg 9
ldd /usr/bin/whisper-cli | grep -E 'avformat|avcodec|avutil|swresample'
# must resolve: libavformat.so.63, libavcodec.so.61, libavutil.so.59, ...
```
**Prevention rule:** after any `pacman -Syu` that majors a multimedia library
(ffmpeg, ffmpeg4, gst-plugins…), run `ldd /usr/bin/whisper-cli` and look for
`not found`. This is the number-one silent killer on rolling releases.

### 3.4 Whisper crashes with GGML_ASSERT on CUDA
```
GGML_ASSERT(buffer) failed at ggml-backend.cpp:194
```
**Cause:** VRAM exhausted. On the RTX 5060 Laptop (8 GB) unrelated processes
were holding 3.3 + 2.5 GB. whisper.cpp needs a contiguous buffer per backend.

**Fix:** `nvidia-smi` → kill GPU processes that are not needed → retry.
Not a whispy bug.

### 3.5 Text is copied but never lands at the cursor — terminals
**Cause:** in Konsole / opencode / jcode / claude code, `Ctrl+V` is the
readline **literal-insert** binding and does **not** paste. `wl-copy` had
succeeded, so the text was in the clipboard; `inject_paste` sent `Ctrl+V`
and the terminal swallowed it. This is the "it works sometimes" glitch:
pasting into GUI fields worked, terminal did not.

**Fix (already applied):** config key `PASTE_COMBO=ctrl+shift+v`
(`Ctrl+Shift+V` is the terminal paste shortcut). Code path:
`toggle.py → paste.inject_paste(paste_combo=cfg.paste_combo)`. Verify the
injection on the uinput vdev:
```bash
YDOTOOL_SOCKET=/run/user/1000/.ydotool_socket timeout 3 ydotool key 42:1 29:1 47:1 47:0 29:0 42:0
```
```
# Expected sequence observed on the virtual device (event29):
# EV_KEY 42 (LEFTSHIFT) press → 29 (LEFTCTRL) press → 47 (V) press/release → 29 release → 42 release
```

**Injection constraints on this system (KWin 6.7.4, Wayland):**
- KWin does **not** expose the `virtual-keyboard` protocol → `wtype` fails
  with "Compositor does not support the virtual keyboard protocol". Do not
  make wtype the primary path.
- ydotool is the only working injector, through the **user** daemon socket
  `/run/user/1000/.ydotool_socket` (vdev event29).
- A system `ydotoold.service` (root, `/tmp/.ydotool_socket`, vdev event30)
  is redundant and confusing: whispy does not use it. Keep it disabled.

### 3.6 "Whispy tray" at login — silent failure
**Cause:** `whispy tray` is **not** a subcommand. `whispy/__main__.py`
implements only: `help, version, providers, use, desktop, gui, config, ptt`.
The autostart entry `~/.config/autostart/whispy.desktop` (Exec=`whispy tray`)
exits 1 immediately — this is the "sometimes it doesn't start at all". The
PTT flow does the job; the tray entry is dead weight.

**Action:** remove the desktop file, or implement a real tray command.
```bash
rm ~/.config/autostart/whispy.desktop
```

---

## 4. Configuration reference (`~/.config/whispy/whispy.conf`)

| Key | Reference value | Notes |
|---|---|---|
| `WHISPER_MODEL` | path to `ggml-large-v3-turbo.bin` | fallback chain in `config.py::resolve_model` |
| `WHISPER_LANGUAGE` | `it` | — |
| `WHISPER_THREADS` | `12` | CPU threads (ignored on CUDA) |
| `AUTOPASTE` | `1` | copy + inject combo after transcription |
| `PASTE_COMBO` | `ctrl+shift+v` | **`ctrl+v` breaks terminals** (readline literal-insert). GUI apps accept both |
| `MAX_RECORD_SECONDS` | `8` | auto-stop + transcribe if you don't release |
| `PTT_KEY` | `META+F12` | evdev combo, parsed in `ptt.py` |
| `NOTIFY_LEVEL` | `normal` | — |
| `PROVIDER` | `local` | whisper.cpp; cloud providers reachable via `whispy use` |

Config is parsed lazily (unknown keys skipped; `_`/`-` normalized), so the
file is safe to hand-edit — just restart the service.

---

## 5. Incident log

| Date | Symptom | Root cause | Fix |
|---|---|---|---|
| 2026-07-28 | tray autostart fails at login | `whispy tray` subcommand does not exist | remove desktop entry (§3.6) |
| 2026-08-07 → 11 | **no transcription at all**, exit 127 | ffmpeg 8→9 ABI break; `whisper.cpp-cuda` not rebuilt | `yay -S --rebuild whisper.cpp-cuda` (§3.3) |
| 2026-08-11 | transcription crashes GGML_ASSERT | VRAM saturated by legacy processes | `nvidia-smi` → kill → retry (§3.4) |
| 2026-08-11 | text copied, never pasted into terminals | `Ctrl+V` is literal-insert in readline | `PASTE_COMBO=ctrl+shift+v` (§3.5) |

---

## 6. Gotchas (do not repeat)

1. **ffmpeg major upgrades break prebuilt audio/video binaries.** Always
   `ldd` check after `pacman -Syu` (§3.3). The symptom is a *missing numeric
   `.so`*, never a clean error message.
2. **`Ctrl+V` is not paste in terminals.** Default `PASTE_COMBO` must stay
   `ctrl+shift+v`; users on GNOME/X11 can switch back to `ctrl+v`.
3. **`_ydotool_key` must respect the real exit code** — an unconditional
   `return True` silently kills the wtype/xdotool fallbacks. (Fixed:
   `return r.returncode == 0`.)
4. **wtype is a dead end on KWin** (no virtual-keyboard protocol). Don't
   advertise it.
5. **Only the user ydotool daemon matters** (socket under
   `$XDG_RUNTIME_DIR`). A root `ydotoold` on `/tmp/.ydotool_socket` is a
   second, irrelevant injector — disable it to avoid confusion.
6. **`whispy tray` does not exist.** Adding the autostart entry without the
   subcommand buys a silent failure at every login.
7. Prebuilt CUDA models are large; if VRAM is tight, drop to `ggml-base.bin`
   via `WHISPER_MODEL` before blaming the pipeline.