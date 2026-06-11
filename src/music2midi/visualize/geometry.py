"""88-key keyboard layout math.

Pure functions so the layout is unit-testable without rendering. Pitches run
from MIDI 21 (A0) at the left edge to MIDI 108 (C8) at the right edge; the 52
white keys split the video width evenly and black keys sit on the boundary
between their neighboring white keys.
"""

from __future__ import annotations

from dataclasses import dataclass

LOWEST_PITCH = 21  # A0
HIGHEST_PITCH = 108  # C8
NUM_WHITE_KEYS = 52

_BLACK_PITCH_CLASSES = {1, 3, 6, 8, 10}

BLACK_WIDTH_FRAC = 0.6  # relative to white key width
BLACK_HEIGHT_FRAC = 0.62  # relative to white key height


def is_black(pitch: int) -> bool:
    return pitch % 12 in _BLACK_PITCH_CLASSES


def white_index(pitch: int) -> int:
    """Number of white keys strictly below `pitch` within the 88-key range."""
    count = 0
    for p in range(LOWEST_PITCH, pitch):
        if not is_black(p):
            count += 1
    return count


@dataclass(frozen=True)
class KeyRect:
    x: float
    y: float
    w: float
    h: float
    is_black: bool


class KeyboardLayout:
    """Maps pitches to screen rectangles for a keyboard of given size."""

    def __init__(self, width: int, kb_top: float, kb_height: float):
        self.width = width
        self.kb_top = kb_top
        self.kb_height = kb_height
        self.white_w = width / NUM_WHITE_KEYS

    def key_rect(self, pitch: int) -> KeyRect:
        if not LOWEST_PITCH <= pitch <= HIGHEST_PITCH:
            raise ValueError(f"pitch {pitch} outside 88-key range")
        if is_black(pitch):
            # Centered on the boundary between the adjacent white keys.
            boundary_x = (white_index(pitch) ) * self.white_w
            w = self.white_w * BLACK_WIDTH_FRAC
            return KeyRect(
                x=boundary_x - w / 2,
                y=self.kb_top,
                w=w,
                h=self.kb_height * BLACK_HEIGHT_FRAC,
                is_black=True,
            )
        idx = white_index(pitch)
        return KeyRect(
            x=idx * self.white_w,
            y=self.kb_top,
            w=self.white_w,
            h=self.kb_height,
            is_black=False,
        )

    def note_column(self, pitch: int) -> tuple[float, float]:
        """(x, width) of the falling-note bar for a pitch, slightly inset."""
        rect = self.key_rect(pitch)
        inset = rect.w * 0.08
        return rect.x + inset, rect.w - 2 * inset
