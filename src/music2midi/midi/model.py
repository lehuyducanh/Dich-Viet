"""Shared song data model.

All three features (transcribe, visualize, generate) funnel through `Song`:
the LLM emits it as JSON, transcription builds it from pretty_midi, and the
visualizer consumes the .mid file written by `save_midi`.

Note timing is expressed in beats (quarter notes); a single `tempo_bpm` per
song converts beats to seconds.
"""

from __future__ import annotations

from pathlib import Path

import pretty_midi
from pydantic import BaseModel, Field, field_validator


class Note(BaseModel):
    pitch: int = Field(..., description="MIDI pitch 0-127")
    start: float = Field(..., description="Start time in beats (quarter notes)")
    duration: float = Field(..., description="Duration in beats")
    velocity: int = Field(80, description="MIDI velocity 1-127")

    @field_validator("pitch")
    @classmethod
    def _clamp_pitch(cls, v: int) -> int:
        return max(0, min(127, v))

    @field_validator("velocity")
    @classmethod
    def _clamp_velocity(cls, v: int) -> int:
        return max(1, min(127, v))

    @field_validator("start")
    @classmethod
    def _non_negative_start(cls, v: float) -> float:
        return max(0.0, v)


class Track(BaseModel):
    name: str = "Track"
    program: int = Field(0, description="General MIDI program number 0-127")
    is_drum: bool = False
    notes: list[Note] = Field(default_factory=list)

    @field_validator("program")
    @classmethod
    def _clamp_program(cls, v: int) -> int:
        return max(0, min(127, v))


class Song(BaseModel):
    title: str = "Untitled"
    tempo_bpm: float = Field(120.0, gt=0)
    time_signature: str = "4/4"
    key: str | None = None
    tracks: list[Track] = Field(default_factory=list)

    def cleaned(self) -> "Song":
        """Drop unplayable notes (zero/negative duration) and empty tracks."""
        tracks = []
        for track in self.tracks:
            notes = [n for n in track.notes if n.duration > 0]
            if notes:
                tracks.append(track.model_copy(update={"notes": notes}))
        return self.model_copy(update={"tracks": tracks})

    # --- beats <-> seconds ---

    def beats_to_seconds(self, beats: float) -> float:
        return beats * 60.0 / self.tempo_bpm

    def seconds_to_beats(self, seconds: float) -> float:
        return seconds * self.tempo_bpm / 60.0

    # --- pretty_midi conversion ---

    def to_pretty_midi(self) -> pretty_midi.PrettyMIDI:
        pm = pretty_midi.PrettyMIDI(initial_tempo=self.tempo_bpm)
        try:
            num, den = (int(p) for p in self.time_signature.split("/"))
            pm.time_signature_changes.append(pretty_midi.TimeSignature(num, den, 0.0))
        except (ValueError, AttributeError):
            pass
        for track in self.tracks:
            inst = pretty_midi.Instrument(
                program=track.program, is_drum=track.is_drum, name=track.name
            )
            for note in track.notes:
                start_s = self.beats_to_seconds(note.start)
                end_s = self.beats_to_seconds(note.start + note.duration)
                if end_s <= start_s:
                    continue
                inst.notes.append(
                    pretty_midi.Note(
                        velocity=note.velocity, pitch=note.pitch, start=start_s, end=end_s
                    )
                )
            pm.instruments.append(inst)
        return pm

    @classmethod
    def from_pretty_midi(
        cls, pm: pretty_midi.PrettyMIDI, title: str = "Untitled", tempo_bpm: float | None = None
    ) -> "Song":
        if tempo_bpm is None:
            tempo_bpm = float(pm.estimate_tempo()) if pm.instruments else 120.0
        song = cls(title=title, tempo_bpm=tempo_bpm)
        for i, inst in enumerate(pm.instruments):
            track = Track(
                name=inst.name or f"Track {i + 1}", program=inst.program, is_drum=inst.is_drum
            )
            for n in inst.notes:
                track.notes.append(
                    Note(
                        pitch=n.pitch,
                        start=song.seconds_to_beats(n.start),
                        duration=song.seconds_to_beats(n.end - n.start),
                        velocity=n.velocity,
                    )
                )
            song.tracks.append(track)
        return song

    # --- file IO ---

    def save_midi(self, path: str | Path) -> None:
        self.to_pretty_midi().write(str(path))

    @classmethod
    def load_midi(cls, path: str | Path, title: str | None = None) -> "Song":
        pm = pretty_midi.PrettyMIDI(str(path))
        tempo = None
        _, tempi = pm.get_tempo_changes()
        if len(tempi):
            tempo = float(tempi[0])
        return cls.from_pretty_midi(pm, title=title or Path(path).stem, tempo_bpm=tempo)
