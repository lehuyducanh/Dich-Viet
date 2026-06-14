"""Rough onset-based drum transcription from the Demucs drum stem.

basic-pitch is pitch-based and useless on percussion, so this classifies each
detected onset by spectral band energy: low-band dominant -> kick, otherwise
snare. Hi-hats and cymbals are not distinguished. Explicitly approximate.
"""

from __future__ import annotations

from pathlib import Path

from ..midi.gm import DRUM_KICK, DRUM_SNARE, STEM_NAMES
from ..midi.model import Note, Track

_LOW_BAND_HZ = 150.0


def transcribe_drums(audio_path: Path, tempo_bpm: float) -> Track:
    import librosa
    import numpy as np

    y, sr = librosa.load(str(audio_path), mono=True)
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True)
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)

    stft = np.abs(librosa.stft(y))
    freqs = librosa.fft_frequencies(sr=sr)
    low_mask = freqs < _LOW_BAND_HZ

    track = Track(name=STEM_NAMES["drums"], program=0, is_drum=True)
    for frame, time_s in zip(onset_frames, onset_times):
        col = stft[:, min(frame, stft.shape[1] - 1)]
        total = float(col.sum()) or 1.0
        low_ratio = float(col[low_mask].sum()) / total
        pitch = DRUM_KICK if low_ratio > 0.5 else DRUM_SNARE
        start_beats = time_s * tempo_bpm / 60.0
        track.notes.append(Note(pitch=pitch, start=start_beats, duration=0.25, velocity=100))
    return track
