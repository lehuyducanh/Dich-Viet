"""Variation engine — the antidote to "sounds like a machine".

Real arrangements never repeat a section verbatim. This module supplies the
small, musical deviations a producer adds by hand:

  - melody variation between repeats (octave lifts, end-of-phrase ornaments)
  - periodic drum fills (tom rolls / snare bursts) on phrase boundaries
  - the final key lift is applied by the arranger using transpose_notes()

All deterministic (seeded by context) so a given plan always renders the same.
"""

from __future__ import annotations

import random

from .model import DRUMS, Note

STEP = 0.25


def vary_melody_loop(loop_notes: list[Note], iteration: int, key_mode: str) -> list[Note]:
    """Return one loop of the melody with iteration-dependent variation.

    iteration 0 is the plain statement; later repeats get tasteful changes so
    a 16-bar verse built from a 2-bar phrase doesn't feel like a copy-paste."""
    if iteration == 0 or not loop_notes:
        return [Note(n.pitch, n.start, n.duration, n.velocity, n.channel) for n in loop_notes]

    rng = random.Random(iteration * 1009)
    out: list[Note] = []
    end = max(n.start + n.duration for n in loop_notes)
    last_third = end * 2 / 3

    for i, n in enumerate(loop_notes):
        pitch, vel = n.pitch, n.velocity
        # every other repeat lifts the closing phrase an octave (a natural climb)
        if iteration % 2 == 1 and n.start >= last_third:
            pitch = min(120, pitch + 12)
        # occasionally accent a note for forward motion
        if rng.random() < 0.18:
            vel = min(127, vel + 10)
        out.append(Note(pitch, n.start, n.duration, vel, n.channel))

    # add a single approach/echo grace note on later repeats
    if iteration % 2 == 0 and len(loop_notes) >= 2:
        anchor = loop_notes[-1]
        step = 2 if key_mode == "major" else 1
        grace_start = anchor.start - STEP
        if grace_start > 0:
            out.append(Note(max(0, anchor.pitch - step), grace_start,
                            STEP * 0.9, max(40, anchor.velocity - 20), anchor.channel))
    return out


def gen_fill(beats_per_bar: float, energy: float, kind: str = "tom") -> list[Note]:
    """A one-bar drum fill (relative to the fill bar's start)."""
    notes: list[Note] = []
    vel_base = int(70 + 45 * energy)
    if kind == "snare":
        steps = int(beats_per_bar / STEP)
        for i in range(steps):
            v = min(127, vel_base + int(40 * i / max(steps - 1, 1)))
            notes.append(Note(DRUMS["snare"], i * STEP, STEP * 0.9, v, 9))
    else:  # descending tom roll over the last two beats
        toms = [DRUMS["htom"], DRUMS["htom"], DRUMS["mtom"], DRUMS["mtom"],
                DRUMS["ltom"], DRUMS["ltom"], DRUMS["snare"], DRUMS["snare"]]
        start = beats_per_bar - 2.0
        for i, drum in enumerate(toms):
            v = min(127, vel_base + i * 4)
            notes.append(Note(drum, start + i * STEP, STEP * 0.9, v, 9))
    notes.append(Note(DRUMS["crash"], beats_per_bar - STEP, STEP, min(127, vel_base + 20), 9))
    return notes


def transpose_notes(notes: list[Note], semitones: int) -> list[Note]:
    if semitones == 0:
        return notes
    return [Note(max(0, min(127, n.pitch + semitones)), n.start, n.duration, n.velocity, n.channel)
            for n in notes]
