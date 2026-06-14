"""Note transcription per audio stem using Spotify's basic-pitch (ONNX backend)."""

from __future__ import annotations

from pathlib import Path

# Per-stem prediction tuning: bass needs a lower frequency window and benefits
# from slightly laxer onset detection; vocals are monophonic-ish.
_STEM_PARAMS = {
    "vocals": {"minimum_frequency": 80.0, "maximum_frequency": 1500.0},
    "bass": {"minimum_frequency": 30.0, "maximum_frequency": 500.0, "onset_threshold": 0.4},
    "other": {},
    "mix": {},
}


def transcribe_stem(audio_path: Path, stem: str = "mix") -> "object":
    """Run basic-pitch on one audio file. Returns a pretty_midi.PrettyMIDI."""
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict

    params = _STEM_PARAMS.get(stem, {})
    _, midi_data, _ = predict(
        str(audio_path),
        model_or_model_path=ICASSP_2022_MODEL_PATH,
        **params,
    )
    return midi_data
