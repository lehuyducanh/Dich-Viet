"""End-to-end audio -> multi-track Song transcription."""

from __future__ import annotations

import tempfile
from pathlib import Path

import typer

from ..midi.gm import STEM_NAMES, STEM_PROGRAMS
from ..midi.model import Note, Song, Track

PITCHED_STEMS = ("vocals", "bass", "other")


def _missing_extra_hint(exc: ImportError) -> RuntimeError:
    return RuntimeError(
        f"Transcription dependencies missing ({exc.name}). Install them with:\n"
        "  pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu\n"
        '  pip install "music2midi[transcribe]"'
    )


def _track_from_basic_pitch(pm: "object", song: Song, stem: str) -> Track:
    """Convert one basic-pitch PrettyMIDI result into a beats-based Track."""
    track = Track(
        name=STEM_NAMES.get(stem, stem.title()),
        program=STEM_PROGRAMS.get(stem, 0),
    )
    for inst in pm.instruments:  # type: ignore[attr-defined]
        for n in inst.notes:
            track.notes.append(
                Note(
                    pitch=n.pitch,
                    start=song.seconds_to_beats(n.start),
                    duration=song.seconds_to_beats(n.end - n.start),
                    velocity=n.velocity,
                )
            )
    track.notes.sort(key=lambda n: n.start)
    return track


def transcribe_audio(
    audio_path: Path,
    stems: list[str] | None = None,
    drums_mode: str = "skip",
    separate: bool = True,
) -> Song:
    from .pitch import transcribe_stem
    from .tempo import detect_tempo

    stems = [s for s in (stems or list(PITCHED_STEMS)) if s != "drums"]

    typer.echo("Detecting tempo...")
    try:
        tempo_bpm = detect_tempo(audio_path)
    except ImportError as exc:
        raise _missing_extra_hint(exc) from exc
    typer.echo(f"  tempo: {tempo_bpm} bpm")
    song = Song(title=audio_path.stem, tempo_bpm=tempo_bpm)

    if not separate:
        typer.echo("Transcribing full mix (no separation)...")
        try:
            pm = transcribe_stem(audio_path, stem="mix")
        except ImportError as exc:
            raise _missing_extra_hint(exc) from exc
        track = _track_from_basic_pitch(pm, song, "other")
        track.name = "Mix"
        song.tracks.append(track)
        return song.cleaned()

    from .separate import separate_stems

    with tempfile.TemporaryDirectory() as tmp:
        typer.echo("Separating stems with Demucs (CPU — this can take a while)...")
        try:
            stem_paths = separate_stems(audio_path, Path(tmp))
        except ImportError as exc:
            raise _missing_extra_hint(exc) from exc

        for stem in stems:
            if stem not in stem_paths:
                typer.echo(f"  stem '{stem}' not produced by Demucs, skipping")
                continue
            typer.echo(f"Transcribing {stem}...")
            pm = transcribe_stem(stem_paths[stem], stem=stem)
            track = _track_from_basic_pitch(pm, song, stem)
            typer.echo(f"  {len(track.notes)} notes")
            song.tracks.append(track)

        if drums_mode == "onset" and "drums" in stem_paths:
            from .drums import transcribe_drums

            typer.echo("Transcribing drums (rough onset classification)...")
            drum_track = transcribe_drums(stem_paths["drums"], tempo_bpm)
            typer.echo(f"  {len(drum_track.notes)} hits")
            song.tracks.append(drum_track)

    return song.cleaned()
