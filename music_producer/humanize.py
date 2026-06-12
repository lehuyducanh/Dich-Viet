"""Humanization: swing, micro-timing and velocity variation.

Deterministic per-track (seeded) so the same input always renders the same
output — useful for tests and for users tweaking one parameter at a time.
"""

from __future__ import annotations

import random

from .model import Track

STEP = 0.25


def humanize(track: Track, swing: float = 0.0,
             timing_jitter: float = 0.012, velocity_jitter: int = 6) -> None:
    rng = random.Random(hash(track.name) & 0xFFFFFFFF)

    for n in track.notes:
        # swing: delay every off-16th (and off-8th) proportionally
        if swing > 0:
            pos_in_beat = n.start % 0.5
            if abs(pos_in_beat - STEP) < 1e-3:
                n.start += swing * STEP * 0.6

        # kick drums stay on the grid; everything else breathes a little
        if not (track.is_drums and n.pitch == 36):
            n.start = max(0.0, n.start + rng.uniform(-timing_jitter, timing_jitter))

        n.velocity = max(16, min(127, n.velocity + rng.randint(-velocity_jitter, velocity_jitter)))
