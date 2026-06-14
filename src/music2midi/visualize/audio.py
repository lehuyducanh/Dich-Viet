"""MIDI audio synthesis via the fluidsynth CLI, with graceful degradation."""

from __future__ import annotations

import shutil
import subprocess
import warnings
from pathlib import Path

from .. import config


def find_soundfont(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        if explicit.exists():
            return explicit
        warnings.warn(f"SoundFont not found: {explicit}")
        return None
    for candidate in config.SOUNDFONT_SEARCH_PATHS:
        p = Path(candidate)
        if p.exists():
            return p
    return None


def synthesize(midi_path: Path, wav_path: Path, soundfont: Path | None = None) -> bool:
    """Render MIDI to wav with fluidsynth. Returns False (with a warning) when
    fluidsynth or a soundfont is unavailable, so callers can fall back to a
    silent video instead of failing."""
    fluidsynth = shutil.which("fluidsynth")
    if fluidsynth is None:
        warnings.warn(
            "fluidsynth not found — rendering silent video. "
            "Install it with: apt-get install fluidsynth fluid-soundfont-gm"
        )
        return False

    sf2 = find_soundfont(soundfont)
    if sf2 is None:
        warnings.warn(
            "No GM SoundFont found — rendering silent video. "
            "Install one with: apt-get install fluid-soundfont-gm (or pass --soundfont)"
        )
        return False

    cmd = [
        fluidsynth,
        "-ni",
        str(sf2),
        str(midi_path),
        "-F", str(wav_path),
        "-r", "44100",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not wav_path.exists():
        warnings.warn(f"fluidsynth failed ({result.returncode}): {result.stderr.strip()[:200]}")
        return False
    return True
