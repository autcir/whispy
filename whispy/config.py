"""Minimal config: ~/.config/whispy/whispy.conf (KEY=value)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path


def _config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg) / "whispy" if xdg else Path.home() / ".config" / "whispy"


def _data_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    return Path(xdg) / "whispy" if xdg else Path.home() / ".local" / "share" / "whispy"


def _default_audio() -> Path:
    if os.environ.get("WHISPY_AUDIO"):
        return Path(os.environ["WHISPY_AUDIO"])
    return Path("/dev/shm/whispy.wav") if Path("/dev/shm").exists() else Path("/tmp/whispy.wav")


def _default_lock() -> Path:
    if os.environ.get("WHISPY_LOCK"):
        return Path(os.environ["WHISPY_LOCK"])
    return Path("/tmp/whispy.lock")


def resolve_model(explicit: str = "") -> str:
    """Pick the best available model.

    If ``explicit`` is set it is used as-is (even if missing → clear error later).
    Otherwise: large-v3-turbo (whispy/whisper-toggle) → base → default path.
    """
    if explicit and explicit.strip():
        return str(Path(explicit).expanduser())

    candidates = [
        _data_dir() / "models" / "ggml-large-v3-turbo.bin",
        Path.home() / ".local/share/whisper-toggle/models/ggml-large-v3-turbo.bin",
        _data_dir() / "models" / "ggml-base.bin",
        Path.home() / ".local/share/whisper-toggle/models/ggml-base.bin",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return str(_data_dir() / "models" / "ggml-base.bin")


@dataclass
class Config:
    whisper_model: str = ""
    whisper_language: str = "it"
    whisper_threads: int = 8
    autopaste: bool = True
    silence_duration: float = 1.5
    # combo di iniezione della paste: nei terminali (Konsole/opencode/jcode/
    # claude code) Ctrl+V è il literal-insert di readline e NON incolla; la
    # paste da clipboard nei terminali è Ctrl+Shift+V. Nei programmi GUI
    # resta ctrl+v. Valori: "ctrl+v" | "ctrl+shift+v".
    paste_combo: str = "ctrl+v"
    silence_threshold: int = 3
    max_record_seconds: int = 120
    keep_audio: bool = False
    ptt_key: str = "META+F12"
    notify_level: str = "normal"  # normal | quiet | off
    # multiprovider: local | openai | groq | openrouter | huggingface | google | nvidia | ollama
    # cloud providers read their API key from an env var (see providers/__init__.py),
    # never from this file. All fields below are plain strings, so the generic
    # dispatch in load() (further down) already parses them — no changes needed there.
    provider: str = "local"
    cloud_model: str = ""  # override the provider's default model; empty = use its default
    ollama_host: str = "http://localhost:11434"  # only used when provider=ollama
    nvidia_server: str = ""  # self-hosted NIM "host:port"; empty = NVIDIA's cloud endpoint
    nvidia_function_id: str = ""  # required for NVIDIA's cloud endpoint — see providers/nvidia.py
    audio_file: Path = field(default_factory=_default_audio)
    lock_file: Path = field(default_factory=_default_lock)

    @property
    def config_file(self) -> Path:
        return _config_dir() / "whispy.conf"

    @property
    def default_model(self) -> Path:
        return Path(resolve_model())

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> Config:
        # deferred import: envfile.py imports _config_dir from this module,
        # so a top-level import here would be circular. Same lazy-import
        # pattern the project already uses in ptt.py/toggle.py.
        from .envfile import load_env_file

        load_env_file()  # KEY=value from whispy.env -> os.environ, never overriding

        cfg = cls()
        target = Path(path) if path else cfg.config_file
        raw_model = ""
        if target.exists():
            for line in target.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip().lower().replace("-", "_")
                value = value.strip().strip('"').strip("'")
                if key in {"audio_file", "lock_file"}:
                    setattr(cfg, key, Path(value))
                    continue
                if key == "whisper_model":
                    raw_model = value
                    continue
                if not hasattr(cfg, key):
                    continue
                current = getattr(cfg, key)
                if isinstance(current, bool):
                    setattr(cfg, key, value.lower() in {"1", "true", "yes", "on"})
                elif isinstance(current, int):
                    setattr(cfg, key, int(value))
                elif isinstance(current, float):
                    setattr(cfg, key, float(value))
                elif isinstance(current, Path):
                    setattr(cfg, key, Path(value))
                else:
                    setattr(cfg, key, value)
        cfg.whisper_model = resolve_model(raw_model or cfg.whisper_model)
        return cfg

    def set_key(self, key: str, value: str, path: str | os.PathLike[str] | None = None) -> Path:
        """Set one ``KEY=value`` line in whispy.conf, leaving the rest alone.

        :meth:`save` rewrites the whole file from the dataclass, which drops
        every comment the user wrote. Changing a single setting — which is
        what ``whispy use`` does — should not cost them their notes, so this
        edits the one line in place and appends it if it wasn't there.
        """
        target = Path(path) if path else self.config_file
        target.parent.mkdir(parents=True, exist_ok=True)
        key = key.strip().upper()
        line = f"{key}={value}"

        if not target.exists():
            target.write_text(line + "\n", encoding="utf-8")
            return target

        lines = target.read_text(encoding="utf-8").splitlines()
        for i, existing in enumerate(lines):
            stripped = existing.strip()
            if stripped.startswith("#") or "=" not in stripped:
                continue
            if stripped.split("=", 1)[0].strip().upper().replace("-", "_") == key:
                lines[i] = line
                break
        else:
            lines.append(line)

        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target

    def save(self, path: str | os.PathLike[str] | None = None) -> None:
        """Write this config back to whispy.conf as KEY=value lines.

        ``whisper_model`` is the one field skipped when blank: it's normally
        auto-resolved fresh on every load() via resolve_model(), and writing
        out whatever it resolved to *this time* would pin that guess forever
        instead of letting future loads keep re-detecting.
        """
        target = Path(path) if path else self.config_file
        target.parent.mkdir(parents=True, exist_ok=True)
        skip = {"audio_file", "lock_file"}
        lines = []
        for f in fields(self):
            if f.name in skip:
                continue
            if f.name == "whisper_model" and not self.whisper_model.strip():
                continue
            value = getattr(self, f.name)
            key = f.name.upper()
            if isinstance(value, bool):
                lines.append(f"{key}={'true' if value else 'false'}")
            else:
                lines.append(f"{key}={value}")
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
