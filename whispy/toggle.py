"""Toggle: first press = record, second = stop + transcribe + paste.

If you do not press again, auto-stop after ``max_record_seconds`` (default 8s)
so you never get stuck recording forever.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import shutil
import sys
import time
from pathlib import Path

from . import notify as notify_mod
from . import paste
from .audio import fix_wav_header, start_recording, stop_recording
from .config import Config
from .transcribe import transcribe, wav_duration_s

# KDE double-fire: do not stop before MIN_AGE_STOP
DEBOUNCE_START = 0.35
MIN_AGE_STOP = 1.0
MIN_SECONDS = 0.5
# if there is no second press, close and transcribe on our own
DEFAULT_AUTOSTOP = 8

LOG = Path("/tmp/whispy.log")
GATE = Path("/tmp/whispy.gate")
STARTED_AT = Path("/tmp/whispy-started-at")
LAST_TXT = Path("/tmp/whispy-last.txt")
AUTOSTOP_PID = Path("/tmp/whispy-autostop.pid")


def _log(msg: str) -> None:
    line = time.strftime("%Y-%m-%d %H:%M:%S") + f" pid={os.getpid()} " + msg
    print(f"[whispy] {msg}", file=sys.stderr)
    with contextlib.suppress(OSError), LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _notify(msg: str, urgency: str = "low", timeout_ms: int = 4000) -> None:
    """A single bubble that updates — see ``whispy.notify``."""
    notify_mod.notify(msg, urgency, timeout_ms)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_lock(lock: Path) -> int | None:
    if not lock.exists():
        return None
    try:
        pid = int(lock.read_text().strip())
    except (ValueError, OSError):
        with contextlib.suppress(OSError):
            lock.unlink(missing_ok=True)
        return None
    if not _alive(pid):
        with contextlib.suppress(OSError):
            lock.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            STARTED_AT.unlink(missing_ok=True)
        return None
    return pid


def _recording_age_s() -> float:
    if not STARTED_AT.exists():
        return 999.0
    try:
        return time.time() - float(STARTED_AT.read_text().strip())
    except (ValueError, OSError):
        return 999.0


def _start_debounced(deb: Path) -> bool:
    now = time.time()
    if deb.exists():
        with contextlib.suppress(OSError):
            if now - deb.stat().st_mtime < DEBOUNCE_START:
                return True
    with contextlib.suppress(OSError):
        deb.touch()
    return False


def _kill_autostop() -> None:
    if not AUTOSTOP_PID.exists():
        return
    try:
        pid = int(AUTOSTOP_PID.read_text().strip())
        os.kill(pid, 15)
    except (ValueError, OSError):
        pass
    with contextlib.suppress(OSError):
        AUTOSTOP_PID.unlink(missing_ok=True)


def _spawn_autostop(recorder_pid: int, max_s: int) -> None:
    """Detached process: if the lock is still there after max_s, stop+transcribe."""
    _kill_autostop()
    pid = os.fork()
    if pid > 0:
        AUTOSTOP_PID.write_text(str(pid))
        return
    # child
    with contextlib.suppress(OSError):
        os.setsid()
    try:
        time.sleep(max(3, max_s))
        lock = Path("/tmp/whispy.lock")
        if not lock.exists():
            os._exit(0)
        try:
            cur = int(lock.read_text().strip())
        except (ValueError, OSError):
            os._exit(0)
        if cur != recorder_pid:
            os._exit(0)
        _log(f"autostop after {max_s}s pid={recorder_pid}")
        # re-enter toggle as stop (same process group not needed)
        from whispy.config import Config as C

        cfg = C.load()
        # force age ok
        STARTED_AT.write_text(str(time.time() - 99))
        # call stop path directly
        stop_recording(recorder_pid)
        with contextlib.suppress(OSError):
            lock.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            STARTED_AT.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            AUTOSTOP_PID.unlink(missing_ok=True)
        _notify("⏳ Transcribing…", timeout_ms=6000)
        code = _transcribe_and_paste(cfg)
        os._exit(code)
    except Exception as exc:  # noqa: BLE001
        _log(f"autostop crash: {exc!r}")
        os._exit(1)


def toggle(cfg: Config | None = None) -> int:
    """One toggle step. Returns 0 on success."""
    cfg = cfg or Config.load()
    lock = cfg.lock_file
    deb = Path("/tmp/whispy-debounce")
    # Honour whatever the user configured (the GUI exposes 3–300s): silently
    # rewriting anything above 30s to 8s made the setting look broken.
    max_s = cfg.max_record_seconds if cfg.max_record_seconds > 0 else DEFAULT_AUTOSTOP

    GATE.touch(exist_ok=True)
    gate_f = GATE.open("r+")
    do_transcribe = False
    try:
        try:
            fcntl.flock(gate_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            _log("busy: another whispy is active")
            _notify("Whispy busy… try again in a moment", "normal")
            return 0

        _log("invoke")

        live = _read_lock(lock)
        if live is not None:
            age = _recording_age_s()
            if age < MIN_AGE_STOP:
                _log(f"stop ignored (age={age:.2f}s < {MIN_AGE_STOP}s, double-fire)")
                return 0

            with contextlib.suppress(OSError):
                deb.touch()
            _kill_autostop()
            _log(
                f"stop pid={live} age={age:.1f}s → transcribe "
                f"model={Path(cfg.whisper_model).name} lang={cfg.whisper_language}"
            )
            _notify("⏳ Transcribing…", timeout_ms=6000)
            stop_recording(live)
            with contextlib.suppress(OSError):
                lock.unlink(missing_ok=True)
            with contextlib.suppress(OSError):
                STARTED_AT.unlink(missing_ok=True)
            time.sleep(0.12)
            do_transcribe = True
        elif _start_debounced(deb):
            _log("debounce: start ignored (double fire)")
        else:
            try:
                proc = start_recording(cfg)
            except RuntimeError as exc:
                _log(str(exc))
                _notify(str(exc), "critical")
                return 1

            try:
                lock.write_text(str(proc.pid))
                STARTED_AT.write_text(str(time.time()))
            except OSError:
                stop_recording(proc.pid)
                _log("could not create lock")
                return 1

            time.sleep(0.15)
            if proc.poll() is not None:
                with contextlib.suppress(OSError):
                    lock.unlink(missing_ok=True)
                with contextlib.suppress(OSError):
                    STARTED_AT.unlink(missing_ok=True)
                _log(f"recorder exited immediately code={proc.returncode}")
                _notify("Microphone unavailable", "critical")
                return 1

            _spawn_autostop(proc.pid, max_s)
            _log(f"record start pid={proc.pid} autostop={max_s}s")
            # stays visible for the whole recording: the only signal that you are in REC
            _notify(f"● REC — press again (max {max_s}s)", timeout_ms=max_s * 1000)
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(gate_f.fileno(), fcntl.LOCK_UN)
        with contextlib.suppress(OSError):
            gate_f.close()

    if do_transcribe:
        return _transcribe_and_paste(cfg)
    return 0


def _transcribe_and_paste(cfg: Config) -> int:
    wav = cfg.audio_file
    if not wav.exists() or wav.stat().st_size <= 44:
        size = wav.stat().st_size if wav.exists() else 0
        _log(f"no audio (path={wav} size={size})")
        _notify("No audio — try again", "normal")
        return 1

    if not fix_wav_header(wav):
        _log(f"invalid WAV: {wav} size={wav.stat().st_size}")
        _notify("Invalid audio", "normal")
        return 1

    dur = wav_duration_s(wav)
    _log(f"audio size={wav.stat().st_size} dur≈{dur:.2f}s")

    if dur < MIN_SECONDS:
        _log(f"too short ({dur:.2f}s)")
        _notify(f"Too short ({dur:.1f}s) — hold the key for at least {MIN_SECONDS:g}s", "normal")
        return 1

    # Deliberately broad: a provider that fails to import (ImportError) or a
    # backend raising something unexpected must still reach the user as a
    # notification. Narrowing this to RuntimeError once made every failure
    # silent — recording worked, the transcript never appeared, nothing logged.
    try:
        text = transcribe(cfg, wav)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc) or repr(exc)
        _log(f"transcribe failed [{type(exc).__name__}]: {msg}")
        _notify(msg[:120], "critical", timeout_ms=6000)
        return 1

    if not text:
        debug = Path("/tmp/whispy-last-failed.wav")
        with contextlib.suppress(OSError):
            shutil.copy2(wav, debug)
        _log(f"no text (failed wav → {debug})")
        _notify("No text. Speak closer to the mic.", "normal")
        return 1

    _log(f"ok: {text[:120]!r}")
    with contextlib.suppress(OSError):
        LAST_TXT.write_text(text + "\n", encoding="utf-8")

    copied = paste.copy_to_clipboard(text)
    injected = False
    if cfg.autopaste and copied:
        time.sleep(0.3)
        injected = paste.inject_paste(paste_combo=cfg.paste_combo)
    if not cfg.autopaste:
        print(text)

    if injected:
        # the text is already on screen: announcing it would be pure noise
        notify_mod.close()
    elif copied:
        # worth saying: the text only exists in the clipboard
        _notify(f"✓ Ctrl+V to paste — {text[:60]}", timeout_ms=4000)
    else:
        _notify(f"✓ {text[:60]}", timeout_ms=3000)

    if not cfg.keep_audio:
        with contextlib.suppress(OSError):
            wav.unlink(missing_ok=True)
    return 0
