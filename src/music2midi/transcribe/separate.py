"""Source separation with Demucs (htdemucs, CPU).

Uses the `demucs.separate.main()` entry point — the stable API in the demucs
4.0.x releases on PyPI (`demucs.api` only exists on the unreleased main
branch).
"""

from __future__ import annotations

from pathlib import Path

STEM_ORDER = ("vocals", "drums", "bass", "other")


def separate_stems(audio_path: Path, out_dir: Path, model: str = "htdemucs") -> dict[str, Path]:
    """Split a song into stems. Returns {stem_name: wav_path}.

    First run downloads the ~80 MB htdemucs checkpoint to ~/.cache.
    """
    import demucs.separate

    out_dir.mkdir(parents=True, exist_ok=True)
    demucs.separate.main(
        ["-n", model, "-d", "cpu", "-o", str(out_dir), str(audio_path)]
    )

    stem_dir = out_dir / model / audio_path.stem
    paths = {name: stem_dir / f"{name}.wav" for name in STEM_ORDER}
    missing = [name for name, p in paths.items() if not p.exists()]
    if missing:
        raise RuntimeError(f"Demucs did not produce expected stems: {missing} in {stem_dir}")
    return paths
