"""Generate a simple demo input: an 8-bar Am-F-C-G progression with a melody.

    python examples/make_demo_input.py [output.mid]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from music_producer.model import Song, Track  # noqa: E402
from music_producer.renderer import render_midi  # noqa: E402

# Am F C G — the classic pop loop, in beats (4/4)
PROGRESSION = [
    (57, "min"), (53, "maj"), (48, "maj"), (55, "maj"),  # A2m F2 C2 G2 roots
]

MELODY = [
    # (pitch, start, dur) — one 2-bar phrase, repeated with variation
    (69, 0.0, 1.0), (72, 1.0, 0.5), (71, 1.5, 0.5), (69, 2.0, 1.5), (67, 3.5, 0.5),
    (65, 4.0, 1.0), (69, 5.0, 1.0), (67, 6.0, 2.0),
    (60, 8.0, 1.0), (64, 9.0, 0.5), (65, 9.5, 0.5), (67, 10.0, 2.0),
    (71, 12.0, 1.0), (69, 13.0, 0.5), (67, 13.5, 0.5), (69, 14.0, 2.0),
]


def build() -> Song:
    song = Song(tempo=100.0)
    chords = Track(name="piano", program=0, channel=0)
    for rep in range(2):  # 8 bars total
        for i, (root, quality) in enumerate(PROGRESSION):
            start = (rep * 4 + i) * 4.0
            third = root + (3 if quality == "min" else 4)
            for p in (root, third, root + 7, root + 12):
                chords.add(p, start, 3.8, 80)
    melody = Track(name="melody", program=73, channel=1)
    for rep in range(2):
        for pitch, start, dur in MELODY:
            melody.add(pitch, start + rep * 16.0, dur, 96)
    song.tracks = [chords, melody]
    return song


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "examples/demo_input.mid"
    render_midi(build(), out)
    print(f"Demo input written to {out}")
