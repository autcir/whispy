# Whispy

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow)
![Ruff](https://img.shields.io/badge/Ruff-passed-261230?logo=ruff&logoColor=white)
![Wayland](https://img.shields.io/badge/Wayland-ready-brightgreen)
![Stars](https://img.shields.io/github/stars/ciroautuori/whispy?style=social)
![Last Commit](https://img.shields.io/github/last-commit/ciroautuori/whispy)
![Version](https://img.shields.io/badge/version-0.5.0-green)

**Hold a key. Speak. Release. The text lands at your cursor.**

Local voice dictation for Linux — offline, no account, no subscription.

```
  ┌─ hold Meta+F12 ───────────────────────────────────┐
  │                                                   │
  │   🎙  "remind me to buy bread tomorrow"            │
  │                                                   │
  └─ release ─────────────────────────────────────────┘
                       ↓  ~1.5s
  remind me to buy bread tomorrow▮
```

Whisper runs **on your machine** — on CUDA if you have it. Nothing leaves your computer: no cloud, no telemetry, no account.

Built on [whisper.cpp](https://github.com/ggerganov/whisper.cpp), for KDE, GNOME, Hyprland, and any Wayland or X11 desktop.

---

## Quick Start

### Arch Linux

```bash
sudo pacman -S alsa-utils wl-clipboard ydotool libnotify python-evdev
yay -S whisper.cpp-cuda          # or whisper.cpp for CPU-only

git clone https://github.com/ciroautuori/whispy.git
cd whispy
./install.sh
```

### Debian / Ubuntu / Fedora

```bash
# Debian/Ubuntu — Fedora: swap apt for dnf
sudo apt install alsa-utils wl-clipboard ydotool libnotify-bin python3-evdev

git clone https://github.com/ciroautuori/whispy.git
cd whispy
./install.sh
```

`whisper-cli` is not packaged on most distros — build it from [whisper.cpp](https://github.com/ggerganov/whisper.cpp) and make sure it lands on your `PATH`.

### Get a model

```bash
mkdir -p ~/.local/share/whispy/models
cd ~/.local/share/whispy/models

# small and fast (~150 MB)
curl -LO https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin

# recommended if you have a GPU (~1.6 GB, far more accurate)
curl -LO https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
```

Whispy picks the model on its own: it prefers `large-v3-turbo` and falls back to `base`. `./install.sh` tells you if no model is present yet and prints the exact command.

### Check everything works

```bash
whispy gui
```

The control panel shows every backend with a status dot, and each row has a
**Test** button that records ~5 seconds from your microphone and transcribes it
for real. If `local` gives you back your own words, you're done — that is the
whole setup.

Prefer the terminal? `whispy providers` prints the same list, and
`tail -f /tmp/whispy.log` shows what happens while you dictate.

Whispy also installs a launcher entry. Clicking it opens this panel;
**right-clicking** it gives you a quick menu — dictate once, or switch backend
without opening anything:

```
┌───────────────────────┐
│ Whispy                │
│   Dictate now         │
│  ─────────────────    │
│   ● Local             │
│     Faster-Whisper    │
└───────────────────────┘
```

### Enable push-to-talk

Reading the keyboard requires the `input` group — log out and back in after this:

```bash
sudo usermod -aG input $USER
systemctl --user enable --now whispy-ptt
```

Hold `Meta+F12`, speak, release. That's the whole thing.

---

## How It Works

```
┌──────────────────────────────────────────────────────────────┐
│                          Whispy                              │
│                                                              │
│  ┌────────────────────────────────────────────────────┐      │
│  │              Key listener (evdev)                  │      │
│  │                                                    │      │
│  │   key down ──► start arecord ──► /dev/shm (RAM)    │      │
│  │   key up   ──► stop, then transcribe               │      │
│  └────────────────────────────────────────────────────┘      │
│                          │                                   │
│  ┌────────────────────────────────────────────────────┐      │
│  │              whisper.cpp (local)                   │      │
│  │                                                    │      │
│  │   16 kHz mono WAV → whisper-cli → text             │      │
│  │   CUDA when available, CPU otherwise               │      │
│  │   hallucination filter drops silence artifacts     │      │
│  └────────────────────────────────────────────────────┘      │
│                          │                                   │
│  ┌────────────────────────────────────────────────────┐      │
│  │              Injection                             │      │
│  │                                                    │      │
│  │   wl-copy → clipboard → ydotool Ctrl+V → cursor    │      │
│  │   clipboard always set, so Ctrl+V works regardless │      │
│  └────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────┘
```

Audio lives in `/dev/shm` (RAM), is deleted right after transcription, and never touches the disk or the network.

---

## Why?

Linux desktop dictation either doesn't exist or ships your voice to someone else's server. Whispy does one thing: it takes what you say and puts it where your cursor is.

- **Fully local** — whisper.cpp on your hardware, zero network calls
- **Fast** — ~1.5s for a sentence with `large-v3-turbo` on GPU
- **True push-to-talk** — hold to record, release to transcribe, like a radio
- **Quiet** — one notification that updates itself, then disappears
- **Small** — ~3k lines of Python, no mandatory runtime dependencies
- **Wayland-first** — works where `xdotool` cannot reach

### Why push-to-talk needs evdev

Global shortcuts in KDE and GNOME report only the **key press**, never the release. Push-to-talk is therefore impossible through a normal desktop hotkey. Whispy reads the keyboard directly through `evdev`, which reports both edges — that's the only reason the `input` group is needed.

---

## Modes

| Mode | Command | How it stops | Needs |
|------|---------|--------------|-------|
| **Push-to-talk** | `whispy ptt` | when you release the key | `evdev` + `input` group |
| **Toggle** | `whispy` | second press, or `MAX_RECORD_SECONDS` | nothing extra |

### Push-to-talk (recommended)

```bash
systemctl --user enable --now whispy-ptt    # survives reboots
journalctl --user -u whispy-ptt -f          # watch it work
```

The daemon idles at zero cost while you're not speaking.

### Toggle

Press once to start, press again to transcribe. If you forget the second press, it stops on its own after `MAX_RECORD_SECONDS`.

Bind `/home/YOUR_USER/.local/bin/whispy-hotkey` to a shortcut — **the absolute path, and the `-hotkey` one**. Desktop shortcuts start with a bare environment (KDE gives `PATH=/usr/bin:/bin` and no session variables); `whispy-hotkey` sets up what the paste path needs, `whispy` does not.

Or skip the shortcut entirely and use **Dictate now** from the launcher's right-click menu, which already points at the wrapper.

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `whispy` | One toggle step: start recording, or stop and transcribe |
| `whispy gui` | Desktop control panel: provider, API keys, recording settings |
| `whispy use <provider>` | Switch backend, e.g. `whispy use groq` |
| `whispy ptt` | Push-to-talk in the foreground (useful for debugging) |
| `whispy providers` | List every backend and the environment variable it reads |
| `whispy desktop` | Rewrite the launcher entry and its right-click menu |
| `whispy version` | Print the version |

Logs go to `/tmp/whispy.log` — `tail -f` it while you dictate.

---

## Providers

**You do not need any of this to use Whispy.** The default, `local`, runs
offline on your own machine and needs no account and no key. The other backends
exist for when you want them — a laptop with no GPU, or a language your local
model handles poorly.

Three ways to switch, all equivalent:

- **Right-click the Whispy icon** in your application menu and pick one. Only
  the providers that can actually run right now are listed, so the menu grows
  as you add keys.
- `whispy use groq` from a terminal.
- Pick one in `whispy gui` — it applies as soon as you select it.

API keys are read from environment variables, never from `whispy.conf` (that
file is plaintext). The control panel can store them for you in
`~/.config/whispy/whispy.env`, chmod 600 — that's the easy path. The manual one
is `export GROQ_API_KEY=...` in your shell profile.

| Provider | `PROVIDER=` | Description | Needs |
|----------|-------------|-------------|-------|
| **Local** | `local` | Default. `whisper.cpp`, fully offline. | `whisper-cli` on `PATH` |
| **Faster-Whisper** | `faster_whisper` | Local, Python-only alternative to `whisper.cpp`. | `pip install 'whispy[faster-whisper]'` |
| **OpenAI** | `openai` | Cloud. Official Whisper API. | `OPENAI_API_KEY` |
| **Groq** | `groq` | Cloud. Free, ultra-fast `whisper-large-v3-turbo`. | `GROQ_API_KEY` |
| **OpenRouter** | `openrouter` | Cloud. Routes to several Whisper-family models. | `OPENROUTER_API_KEY` |
| **Hugging Face** | `huggingface` | Cloud, serverless inference. | `HF_TOKEN` |
| **Google** | `google` | Cloud Speech-to-Text v1. | `GOOGLE_API_KEY` |
| **NVIDIA** | `nvidia` | Riva/NIM ASR over gRPC. | `NVIDIA_API_KEY` + `NVIDIA_FUNCTION_ID=` in the config, `pip install nvidia-riva-client` |
| **Ollama** | `ollama` | Local, best-effort — Ollama has no dedicated STT API. | an audio-capable model pulled locally |

The cloud providers speak plain HTTP through the standard library, so none of
them needs an SDK installed. Run `whispy providers` for the same table with
the defaults currently in effect.

---

## Configuration

`~/.config/whispy/whispy.conf`, all keys optional:

```ini
PROVIDER=local                  # see the Providers table above
CLOUD_MODEL=                    # empty = that provider's default model
WHISPER_MODEL=                  # empty = auto-detect
WHISPER_LANGUAGE=en             # en, it, … ("auto" to detect)
WHISPER_THREADS=8
AUTOPASTE=1                     # 0 = clipboard only, no injection
PASTE_COMBO=ctrl+shift+v        # key combo sent to paste the text
PTT_KEY=META+F12                # push-to-talk key
NOTIFY_LEVEL=normal             # normal | quiet (errors only) | off
MAX_RECORD_SECONDS=8            # toggle safety net, honoured as written
KEEP_AUDIO=0                    # 1 keeps the WAV for inspection
OLLAMA_HOST=http://localhost:11434   # provider=ollama only
NVIDIA_SERVER=                  # self-hosted NIM host:port; empty = NVIDIA cloud
NVIDIA_FUNCTION_ID=             # required by the NVIDIA cloud endpoint
```

`PASTE_COMBO` is the key sequence injected at the focused window after a
successful transcription (`ctrl+v` by dataclass default). **Terminals do not
paste with `Ctrl+V`** — konsole, readline apps, and modern TUIs bind it to
literal-insert — so on terminal-heavy setups keep `PASTE_COMBO=ctrl+shift+v`
(the shipped default in installed configs). GUI apps accept both. See
`docs/OPERATIONS.md` §3.5 for the full injection story.

### Choosing the key

`PTT_KEY` takes a single key or a combo: `MENU`, `RIGHTCTRL`, `META+F12`, `CTRL+ALT+K`. Names follow `evdev`, with `META`, `SUPER`, `CTRL`, `ALT`, and `SHIFT` as convenience aliases.

The **Menu key** (☰) is an excellent choice: almost nothing else uses it, so it never collides.

> If you pick a combo built on `META`, make sure your desktop hasn't already bound it — otherwise one press fires two things.

### Notification levels

| Level | Behavior |
|-------|----------|
| `normal` | One bubble that updates through the cycle, closed on success |
| `quiet` | Errors only |
| `off` | Silence |

On success with auto-paste, the notification is **closed** rather than repeating text you can already see. Errors stay on screen.

---

## Troubleshooting

**Start here.** The definitive operations runbook — every failure mode seen on
the reference Arch/KDE system, with exact fixes — lives in
[`docs/OPERATIONS.md`](docs/OPERATIONS.md). Read it before filing a bug.

Whispy logs every step of every dictation:

```bash
tail -f /tmp/whispy.log
```

Dictate one sentence while that runs. A healthy cycle looks like this:

```
record start pid=12345 autostop=8s
stop pid=12345 age=2.1s → transcribe model=ggml-large-v3-turbo.bin lang=it
audio size=92044 dur≈2.88s
ok: 'buongiorno a tutti'
```

Where it stops tells you which step failed — and the same message is shown as a
desktop notification.

### Nothing happens at all

| The log says | Meaning | Fix |
|--------------|---------|-----|
| nothing at all | The key never reached Whispy | Check the shortcut, or `systemctl --user status whispy-ptt` |
| `Microphone unavailable` | `arecord` couldn't open the mic | Another app is holding it, or no input device is selected |
| `model not found: …` | No model on disk | Download one — see [Get a model](#get-a-model) |
| `whisper-cli not found` | whisper.cpp isn't on `PATH` | Install it, then reopen your terminal |
| `unknown provider …` | Typo in `PROVIDER=` | `whispy providers` lists the valid names |
| `… needs GROQ_API_KEY set …` | A cloud backend has no key | Enter it in `whispy gui` → **Save Keys**, or `export` it |

### Push-to-talk doesn't react

```bash
systemctl --user status whispy-ptt
journalctl --user -u whispy-ptt -n 30
```

| Cause | Fix |
|-------|-----|
| Not in the `input` group | `sudo usermod -aG input $USER`, then **log out and back in** |
| Keyboard plugged in after start | `systemctl --user restart whispy-ptt` |
| `PTT_KEY` already used by the desktop | Pick another one, e.g. `MENU` |

### It transcribes but doesn't paste

**Terminal gotcha first:** in Konsole / tmux / readline apps (and in this
setup, opencode, jcode and Claude Code) `Ctrl+V` is *literal-insert*, not
paste. The text is already in your clipboard, but it won't land at the
cursor unless the paste combo is the terminal one. The config key is
`PASTE_COMBO` — set it to `ctrl+shift+v` (default in shipped configs) and
restart `whispy-ptt`:

```bash
echo 'PASTE_COMBO=ctrl+shift+v' >> ~/.config/whispy/whispy.conf
systemctl --user restart whispy-ptt
```

Injection uses ydotool, which needs its **user** daemon (socket under
`$XDG_RUNTIME_DIR`):

```bash
systemctl --user enable --now ydotoold     # user daemon, vdev under /dev/input
systemctl --user status ydotoold
```

The text is in the clipboard either way — paste manually if injection fails.
Set `AUTOPASTE=0` to disable injection entirely.

> Note: a *system* `ydotoold.service` (root, `/tmp/.ydotool_socket`) is not
> the one Whispy talks to and is best kept disabled — see
> `docs/OPERATIONS.md` §3.5.

### "No text" or wrong transcriptions

- Recordings shorter than **0.5s** are discarded — hold the key a moment longer
- Set `WHISPER_LANGUAGE` explicitly instead of leaving `auto`
- Switch to `large-v3-turbo`; `base` is weak on non-English speech
- The last failed recording is kept at `/tmp/whispy-last-failed.wav` — play it back, and if you can't hear yourself the problem is the microphone, not Whisper

### It feels slow

```bash
whisper-cli --help | grep -i gpu     # CUDA build?
nvidia-smi                            # GPU visible?
```

A CPU build with `large-v3-turbo` takes seconds, not milliseconds — use `ggml-base.bin` or install a CUDA build.

If something else is holding your VRAM (a local model server, a game), the GPU build cannot allocate its buffers. Whispy notices and retries on CPU, so dictation still works — just slower. Free the VRAM to get the fast path back.

If you're on **toggle** mode and the wait is always identical, that's not slowness: it's `MAX_RECORD_SECONDS` expiring because the second press never came.

---

## Requirements

| Tool | Purpose | Required |
|------|---------|----------|
| `whisper-cli` | Transcription | Yes |
| `arecord` (alsa-utils) | Recording | Yes — `sox`/`rec` works as fallback |
| `wl-copy` (wl-clipboard) | Clipboard | Yes |
| `ydotool` + `ydotoold` | Auto-paste on Wayland | Only for `AUTOPASTE=1` |
| `notify-send` (libnotify) | Notifications | Only for `NOTIFY_LEVEL≠off` |
| `python-evdev` | Reading the keyboard | Only for push-to-talk |

Python 3.11+. No mandatory Python runtime dependencies — `evdev` is an optional extra.

---

## Development

```bash
pip install -e '.[dev,ptt]'
./scripts/check.sh          # lint + format + tests, no hardware required
```

103 tests, ~5 seconds, no hardware: `subprocess` and `evdev` devices are stubbed, so they run anywhere — no microphone, no keyboard, no GPU. They cover WAV header repair, ydotool argument parsing, config loading, notification replacement, key combo parsing, device selection, the toggle state machine, every entry in the provider registry, and the error paths that must reach the user.

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Whispy stays small: if a feature doesn't serve *speech → cursor*, it probably doesn't belong.

---

## Tech Stack

- **[whisper.cpp](https://github.com/ggerganov/whisper.cpp)** — local transcription, CUDA-accelerated
- **[evdev](https://python-evdev.readthedocs.io/)** — raw keyboard events, press *and* release
- **[ydotool](https://github.com/ReimuNotMoe/ydotool)** — keystroke injection on Wayland
- **ALSA / wl-clipboard / libnotify** — recording, clipboard, notifications
- **Python 3.11+** — standard library only at runtime

---

## License

MIT

---

Built by [Ciro Autuori](https://github.com/ciroautuori).
