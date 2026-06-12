"""Core data model for the music producer pipeline.

All time values are expressed in beats (quarter notes) so the pipeline is
tempo-independent until the final MIDI render.
"""

from __future__ import annotations

from dataclasses import dataclass, field


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# General MIDI percussion (channel 10) key map used by the generators.
DRUMS = {
    "kick": 36,
    "snare": 38,
    "clap": 39,
    "rimshot": 37,
    "chh": 42,       # closed hi-hat
    "phh": 44,       # pedal hi-hat
    "ohh": 46,       # open hi-hat
    "ltom": 45,
    "mtom": 47,
    "htom": 50,
    "crash": 49,
    "ride": 51,
    "tamb": 54,
    "shaker": 70,
}


@dataclass
class Note:
    pitch: int                # MIDI note number 0-127
    start: float              # beats from song start
    duration: float           # beats
    velocity: int = 96        # 1-127
    channel: int = 0


@dataclass
class Track:
    name: str
    notes: list[Note] = field(default_factory=list)
    program: int = 0          # General MIDI program number
    channel: int = 0
    is_drums: bool = False

    def add(self, pitch: int, start: float, duration: float, velocity: int = 96) -> None:
        self.notes.append(Note(pitch, start, duration, velocity, self.channel))

    @property
    def end(self) -> float:
        return max((n.start + n.duration for n in self.notes), default=0.0)


@dataclass
class Song:
    tempo: float = 120.0
    time_signature: tuple[int, int] = (4, 4)
    tracks: list[Track] = field(default_factory=list)

    @property
    def beats_per_bar(self) -> float:
        num, den = self.time_signature
        return num * 4.0 / den

    @property
    def length_beats(self) -> float:
        return max((t.end for t in self.tracks), default=0.0)

    @property
    def length_bars(self) -> int:
        bpb = self.beats_per_bar
        if bpb <= 0:
            return 0
        return int(self.length_beats / bpb + 0.999)


@dataclass
class Chord:
    """One detected chord, aligned to a bar (or half-bar)."""
    start: float              # beats
    duration: float           # beats
    root: int                 # pitch class 0-11
    quality: str              # "maj" | "min" | "dim" | "sus" ...

    INTERVALS = {
        "maj": (0, 4, 7),
        "min": (0, 3, 7),
        "dim": (0, 3, 6),
        "sus4": (0, 5, 7),
        "maj7": (0, 4, 7, 11),
        "min7": (0, 3, 7, 10),
        "dom7": (0, 4, 7, 10),
    }

    @property
    def name(self) -> str:
        suffix = {"maj": "", "min": "m"}.get(self.quality, self.quality)
        return f"{NOTE_NAMES[self.root]}{suffix}"

    def pitches(self, octave: int = 4) -> list[int]:
        base = 12 * (octave + 1) + self.root
        return [base + i for i in self.INTERVALS.get(self.quality, (0, 4, 7))]


@dataclass
class SongAnalysis:
    """Everything the producer brain needs to know about the input."""
    tempo: float
    time_signature: tuple[int, int]
    key_root: int             # pitch class 0-11
    key_mode: str             # "major" | "minor"
    chords: list[Chord]
    melody: list[Note]        # the most melodic monophonic-ish line found
    length_bars: int

    @property
    def key_name(self) -> str:
        return f"{NOTE_NAMES[self.key_root]} {self.key_mode}"

    def chord_symbols(self) -> list[str]:
        return [c.name for c in self.chords]


@dataclass
class PlanSection:
    name: str                 # intro / verse / build / drop / breakdown / outro
    bars: int
    energy: float             # 0.0 - 1.0, drives pattern intensity & velocity
    layers: list[str]         # subset of: drums, bass, pad, arp, melody, lead, fx


@dataclass
class ProductionPlan:
    """The LLM (or rule-based fallback) output: how to produce the track."""
    template: str             # template name from the library
    target_tempo: float
    transpose: int            # semitones applied to harmonic material
    energy: float             # overall energy 0-1
    sections: list[PlanSection]
    title: str = "Untitled"
    notes: str = ""           # producer's rationale, written into the README/log

    @property
    def total_bars(self) -> int:
        return sum(s.bars for s in self.sections)
