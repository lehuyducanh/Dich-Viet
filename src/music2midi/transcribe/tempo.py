"""Tempo detection (librosa)."""

from __future__ import annotations

from pathlib import Path


def detect_tempo(audio_path: Path, default: float = 120.0) -> float:
    """Estimate a single global BPM for the file; fall back to `default`."""
    import librosa
    import numpy as np

    y, sr = librosa.load(str(audio_path), mono=True)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0])
    if not bpm or bpm <= 0:
        return default
    return round(bpm, 1)
