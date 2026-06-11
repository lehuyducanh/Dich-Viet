import pytest

from music2midi.visualize.geometry import (
    HIGHEST_PITCH,
    LOWEST_PITCH,
    NUM_WHITE_KEYS,
    KeyboardLayout,
    is_black,
    white_index,
)

WIDTH = 1040  # 52 * 20 px


@pytest.fixture
def layout() -> KeyboardLayout:
    return KeyboardLayout(width=WIDTH, kb_top=800.0, kb_height=200.0)


def test_88_keys_have_52_white():
    whites = [p for p in range(LOWEST_PITCH, HIGHEST_PITCH + 1) if not is_black(p)]
    blacks = [p for p in range(LOWEST_PITCH, HIGHEST_PITCH + 1) if is_black(p)]
    assert len(whites) == NUM_WHITE_KEYS == 52
    assert len(blacks) == 36
    assert len(whites) + len(blacks) == 88


def test_white_index_boundaries():
    assert white_index(LOWEST_PITCH) == 0
    assert white_index(HIGHEST_PITCH) == 51


def test_edges_span_full_width(layout: KeyboardLayout):
    left = layout.key_rect(LOWEST_PITCH)
    right = layout.key_rect(HIGHEST_PITCH)
    assert left.x == 0
    assert right.x + right.w == pytest.approx(WIDTH)


def test_x_monotonic_in_pitch(layout: KeyboardLayout):
    centers = [
        layout.key_rect(p).x + layout.key_rect(p).w / 2
        for p in range(LOWEST_PITCH, HIGHEST_PITCH + 1)
    ]
    assert all(a < b for a, b in zip(centers, centers[1:]))


def test_black_keys_overlap_their_white_neighbors(layout: KeyboardLayout):
    for pitch in range(LOWEST_PITCH, HIGHEST_PITCH + 1):
        if not is_black(pitch):
            continue
        black = layout.key_rect(pitch)
        below = layout.key_rect(pitch - 1)
        above = layout.key_rect(pitch + 1)
        assert black.is_black and not below.is_black and not above.is_black
        assert black.x < below.x + below.w
        assert black.x + black.w > above.x
        assert black.h < below.h


def test_out_of_range_pitch_raises(layout: KeyboardLayout):
    with pytest.raises(ValueError):
        layout.key_rect(LOWEST_PITCH - 1)
    with pytest.raises(ValueError):
        layout.key_rect(HIGHEST_PITCH + 1)
