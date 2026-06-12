"""Source separation with Demucs (htdemucs, CPU)."""

from __future__ import annotations

from pathlib import Path


def separate_stems(audio_path: Path, out_dir: Path, model: str = "htdemucs") -> dict[str, Path]:
    """Split a song into stems. Returns {stem_name: wav_path}.

    First run downloads the ~80 MB htdemucs checkpoint to ~/.cache.
    """
    import demucs.api

    separator = demucs.api.Separator(model=model, device="cpu", progress=True)
    _, stems = separator.separate_audio_file(str(audio_path))

    paths: dict[str, Path] = {}
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, tensor in stems.items():
        wav_path = out_dir / f"{name}.wav"
        demucs.api.save_audio(tensor, str(wav_path), samplerate=separator.samplerate)
        paths[name] = wav_path
    return paths
