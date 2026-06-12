import importlib.util
import wave
from pathlib import Path

import numpy as np
import pytest

from music2midi.transcribe.pipeline import transcribe_audio

_HAS_DEPS = all(
    importlib.util.find_spec(m) is not None for m in ("librosa", "basic_pitch", "onnxruntime")
)


def _write_sine_wav(path: Path, freq: float = 440.0, seconds: float = 5.0, sr: int = 22050):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    # Pulsed tone (8 notes) so both tempo and onset detection have something to find.
    envelope = (np.sin(2 * np.pi * (8 / seconds / 2) * t) > 0).astype(float)
    samples = (0.6 * envelope * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(samples.tobytes())


@pytest.mark.skipif(_HAS_DEPS, reason="transcribe extras installed; hint test not applicable")
def test_missing_deps_raise_helpful_error(tmp_path: Path):
    wav = tmp_path / "tone.wav"
    _write_sine_wav(wav)
    with pytest.raises(RuntimeError, match=r"music2midi\[transcribe\]"):
        transcribe_audio(wav, separate=False)


@pytest.mark.slow
@pytest.mark.skipif(not _HAS_DEPS, reason="transcribe extras not installed")
def test_transcribe_sine_no_separate(tmp_path: Path):
    wav = tmp_path / "tone.wav"
    _write_sine_wav(wav, freq=440.0)  # A4 = MIDI 69
    song = transcribe_audio(wav, separate=False)
    notes = [n for t in song.tracks for n in t.notes]
    assert len(notes) >= 4
    near_a4 = [n for n in notes if abs(n.pitch - 69) <= 1]
    assert len(near_a4) >= len(notes) // 2
