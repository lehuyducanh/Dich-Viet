"""Built-in demo song used by the `demo` command and the render smoke test."""

from .gm import GM_PROGRAMS
from .model import Note, Song, Track

# "Twinkle Twinkle" first phrase: (pitch, beats) with C major harmony.
_MELODY = [
    (60, 1), (60, 1), (67, 1), (67, 1), (69, 1), (69, 1), (67, 2),
    (65, 1), (65, 1), (64, 1), (64, 1), (62, 1), (62, 1), (60, 2),
]

# Bass roots per bar (4/4): C C F C F C G C
_BASS = [48, 48, 53, 48, 53, 48, 43, 48]


def build_demo_song() -> Song:
    melody = Track(name="Melody", program=GM_PROGRAMS["Acoustic Grand Piano"])
    t = 0.0
    for pitch, beats in _MELODY:
        melody.notes.append(Note(pitch=pitch, start=t, duration=beats * 0.95, velocity=90))
        t += beats

    bass = Track(name="Bass", program=GM_PROGRAMS["Fingered Bass"])
    for bar, root in enumerate(_BASS):
        start = bar * 2.0
        bass.notes.append(Note(pitch=root, start=start, duration=1.9, velocity=70))

    return Song(
        title="Demo: Twinkle",
        tempo_bpm=100,
        time_signature="4/4",
        key="C major",
        tracks=[melody, bass],
    )
