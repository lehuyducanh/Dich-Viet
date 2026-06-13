"""Meter handling — re-groove a source in 3/4 or 6/8 into 4/4.

Many traditional tunes (waltzes, Happy Birthday, folk songs) are in 3/4 or
6/8. To remix them into a 4/4 genre like EDM you first re-meter them so phrases
land on 4/4 downbeats. This applies a uniform time-scale (4/3 for 3/4, 2/3 per
group for 6/8) — a defensible automatic conversion that keeps note order and
relative rhythm while filling whole 4/4 bars. For tricky material, hand-editing
in a notation editor still beats any automatic conversion.
"""

from __future__ import annotations

from .model import Note, Song, Track


def to_four_four(song: Song) -> Song:
    """Return a copy of the song re-metered to 4/4 if it isn't already."""
    num, den = song.time_signature
    if (num, den) == (4, 4):
        return song
    if den == 4 and num in (3, 6):
        scale = 4.0 / num          # 3/4 -> *4/3 ; 6/4 -> *4/6
    elif (num, den) == (6, 8):
        scale = 4.0 / 3.0          # 6/8 (two dotted beats) -> 4/4
    else:
        scale = 4.0 / (num * 4.0 / den)  # general: stretch a bar to 4 beats

    out = Song(tempo=song.tempo, time_signature=(4, 4))
    out.explicit_chords = [
        type(c)(c.start * scale, c.duration * scale, c.root, c.quality)
        for c in song.explicit_chords
    ]
    for t in song.tracks:
        nt = Track(name=t.name, program=t.program, channel=t.channel, is_drums=t.is_drums)
        nt.notes = [Note(n.pitch, n.start * scale, n.duration * scale, n.velocity, n.channel)
                    for n in t.notes]
        out.tracks.append(nt)
    return out
