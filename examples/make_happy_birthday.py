"""Generate a Happy Birthday input MIDI — a traditional song ready for remixing.

The tune is public domain. The original is in 3/4; like any EDM remixer we
re-groove it into 4/4 (pickup "hap-py" lands on beat 3.5-4, phrases land on
the downbeat). Chords follow the classic I-V7-I-IV-I-V7-I, including a
half-bar V->I change in the final bar.

    python examples/make_happy_birthday.py [output.mid]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from music_producer.model import Song, Track  # noqa: E402
from music_producer.renderer import render_midi  # noqa: E402

# (pitch, start_beats, duration_beats) — 8 bars of 4/4, key C major
MELODY = [
    # "hap-py birth-day to you"  (pickup -> bar 2)
    (67, 2.5, 0.5), (67, 3.0, 0.5),
    (69, 4.0, 1.0), (67, 5.0, 1.0), (72, 6.0, 1.0), (71, 7.0, 0.9),
    # "hap-py birth-day to you"
    (67, 10.5, 0.5), (67, 11.0, 0.5),
    (69, 12.0, 1.0), (67, 13.0, 1.0), (74, 14.0, 1.0), (72, 15.0, 0.9),
    # "hap-py birth-day dear [you]"
    (67, 18.5, 0.5), (67, 19.0, 0.5),
    (79, 20.0, 1.0), (76, 21.0, 1.0), (72, 22.0, 0.5), (71, 22.5, 0.5), (69, 23.0, 0.9),
    # "hap-py birth-day to you"
    (77, 26.5, 0.5), (77, 27.0, 0.5),
    (76, 28.0, 1.0), (72, 29.0, 1.0), (74, 30.0, 1.0), (72, 31.0, 1.0),
]

# (root_midi, quality_third_offset, start, duration) — I V V I I F F G->C
CHORDS = [
    (48, 4, 0.0, 4.0),    # C
    (43, 4, 4.0, 4.0),    # G  (V7 zone)
    (43, 4, 8.0, 4.0),    # G
    (48, 4, 12.0, 4.0),   # C
    (48, 4, 16.0, 4.0),   # C
    (41, 4, 20.0, 4.0),   # F
    (41, 4, 24.0, 4.0),   # F
    (43, 4, 28.0, 2.0),   # G   — half-bar cadence:
    (48, 4, 30.0, 2.0),   # C      V -> I inside the final bar
]


def build() -> Song:
    song = Song(tempo=120.0, time_signature=(4, 4))
    keys = Track(name="piano", program=0, channel=0)
    for root, third, start, dur in CHORDS:
        for p in (root - 12, root, root + third, root + 7):
            keys.add(p, start, dur - 0.1, 78)
    lead = Track(name="melody", program=73, channel=1)
    for pitch, start, dur in MELODY:
        lead.add(pitch, start, dur, 98)
    song.tracks = [keys, lead]
    return song


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "examples/happy_birthday.mid"
    render_midi(build(), out)
    print(f"Happy Birthday input written to {out}")
