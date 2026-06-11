"""Synthesia-style falling-notes renderer.

Reference look: black background, 88-key keyboard along the bottom, rounded
note bars falling toward the keyboard (one color per track), keys lighting up
with a soft glow when a note reaches the hit line.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pretty_midi
from PIL import Image, ImageDraw

from .. import config
from .geometry import HIGHEST_PITCH, LOWEST_PITCH, KeyboardLayout, is_black
from .video import FrameWriter, mux_audio


@dataclass(frozen=True)
class TimedNote:
    track: int
    pitch: int
    start: float  # seconds, including lead-in
    end: float
    velocity: int


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _lighten(rgb: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(int(v + (255 - v) * amount) for v in rgb)  # type: ignore[return-value]


def load_notes(midi_path: Path, lead_in_s: float) -> tuple[list[TimedNote], float]:
    """Flatten a MIDI file into render notes sorted by start time.

    Returns (notes, total_duration_seconds). Pitches outside the 88-key range
    are folded by octaves into range so nothing silently disappears.
    """
    pm = pretty_midi.PrettyMIDI(str(midi_path))
    notes: list[TimedNote] = []
    for track_idx, inst in enumerate(pm.instruments):
        for n in inst.notes:
            pitch = n.pitch
            while pitch < LOWEST_PITCH:
                pitch += 12
            while pitch > HIGHEST_PITCH:
                pitch -= 12
            notes.append(
                TimedNote(
                    track=track_idx,
                    pitch=pitch,
                    start=n.start + lead_in_s,
                    end=n.end + lead_in_s,
                    velocity=n.velocity,
                )
            )
    notes.sort(key=lambda n: n.start)
    last_end = max((n.end for n in notes), default=lead_in_s)
    return notes, last_end + config.TAIL_S


class PianoRenderer:
    def __init__(
        self,
        width: int,
        height: int,
        fps: int,
        lookahead_s: float,
        palette: list[str],
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.lookahead_s = lookahead_s
        self.colors = [_hex_to_rgb(c) for c in palette]

        kb_height = height * config.KEYBOARD_HEIGHT_FRAC
        self.kb_top = height - kb_height
        self.layout = KeyboardLayout(width=width, kb_top=self.kb_top, kb_height=kb_height)
        self.fall_speed = self.kb_top / lookahead_s  # px per second

        self._keyboard_base = self._render_keyboard_base()
        self._glow_sprites = [self._render_glow(c) for c in self.colors]

    # --- pre-rendered layers ---

    def _render_keyboard_base(self) -> Image.Image:
        img = Image.new("RGB", (self.width, self.height), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        # White keys first, then black keys on top.
        for pitch in range(LOWEST_PITCH, HIGHEST_PITCH + 1):
            if is_black(pitch):
                continue
            r = self.layout.key_rect(pitch)
            draw.rectangle(
                [r.x, r.y, r.x + r.w - 1, r.y + r.h],
                fill=(230, 230, 228),
                outline=(40, 40, 40),
            )
        for pitch in range(LOWEST_PITCH, HIGHEST_PITCH + 1):
            if not is_black(pitch):
                continue
            r = self.layout.key_rect(pitch)
            draw.rectangle([r.x, r.y, r.x + r.w, r.y + r.h], fill=(18, 18, 20))
        # Thin separator above the keyboard (the hit line).
        draw.rectangle([0, self.kb_top - 2, self.width, self.kb_top], fill=(60, 60, 70))
        return img

    def _render_glow(self, rgb: tuple[int, int, int]) -> Image.Image:
        """Radial gradient sprite composited where a note meets the keyboard."""
        size = max(8, int(self.layout.white_w * 4))
        arr = np.zeros((size, size, 4), dtype=np.uint8)
        yy, xx = np.mgrid[0:size, 0:size]
        center = (size - 1) / 2
        dist = np.sqrt((xx - center) ** 2 + (yy - center) ** 2) / center
        alpha = np.clip(1.0 - dist, 0.0, 1.0) ** 2 * 110
        arr[..., 0], arr[..., 1], arr[..., 2] = rgb
        arr[..., 3] = alpha.astype(np.uint8)
        sprite = Image.fromarray(arr, "RGBA")
        return sprite

    def _track_color(self, track: int) -> tuple[int, int, int]:
        return self.colors[track % len(self.colors)]

    # --- per-frame drawing ---

    def draw_frame(self, t: float, notes: list[TimedNote], window_start: int) -> Image.Image:
        frame = Image.new("RGB", (self.width, self.height), (5, 5, 8))
        draw = ImageDraw.Draw(frame)

        active: list[TimedNote] = []
        horizon = t + self.lookahead_s
        i = window_start
        while i < len(notes) and notes[i].start <= horizon:
            n = notes[i]
            i += 1
            if n.end < t:
                continue
            x, w = self.layout.note_column(n.pitch)
            y_bottom = self.kb_top - (n.start - t) * self.fall_speed
            bar_h = (n.end - n.start) * self.fall_speed
            y_top = y_bottom - bar_h
            if y_bottom <= 0 or y_top >= self.kb_top:
                if n.start <= t <= n.end:
                    active.append(n)
                continue
            color = self._track_color(n.track)
            playing = n.start <= t <= n.end
            if playing:
                active.append(n)
                color = _lighten(color, 0.25)
            y0 = max(y_top, -20.0)
            y1 = min(y_bottom, self.kb_top)
            if y1 - y0 < 1 or w < 1:
                continue
            # Pillow rejects radii larger than half of either dimension.
            radius = max(0, min(w * 0.3, 8, (y1 - y0) / 2 - 1, w / 2 - 1))
            draw.rounded_rectangle(
                [x, y0, x + w, y1],
                radius=radius,
                fill=color,
                outline=_lighten(color, 0.5),
                width=1,
            )

        # Keyboard on top of the bars.
        frame.paste(self._keyboard_base, (0, 0), self._keyboard_mask())

        # Pressed keys + glow for active notes.
        for n in active:
            r = self.layout.key_rect(n.pitch)
            color = self._track_color(n.track)
            fill = color if not r.is_black else tuple(int(v * 0.8) for v in color)
            draw = ImageDraw.Draw(frame)
            draw.rectangle([r.x, r.y, r.x + r.w, r.y + r.h], fill=fill)
            glow = self._glow_sprites[n.track % len(self._glow_sprites)]
            gx = int(r.x + r.w / 2 - glow.width / 2)
            gy = int(self.kb_top - glow.height / 2)
            frame.paste(glow, (gx, gy), glow)

        return frame

    def _keyboard_mask(self) -> Image.Image:
        if not hasattr(self, "_kb_mask"):
            mask = Image.new("L", (self.width, self.height), 0)
            ImageDraw.Draw(mask).rectangle(
                [0, self.kb_top - 2, self.width, self.height], fill=255
            )
            self._kb_mask = mask
        return self._kb_mask


def render_video(
    midi_path: str | Path,
    output_path: str | Path,
    width: int = config.DEFAULT_WIDTH,
    height: int = config.DEFAULT_HEIGHT,
    fps: int = config.DEFAULT_FPS,
    lookahead_s: float = config.DEFAULT_LOOKAHEAD_S,
    palette: list[str] | None = None,
    with_audio: bool = True,
    soundfont: Path | None = None,
) -> Path:
    """Render a MIDI file to an mp4. Returns the output path."""
    midi_path = Path(midi_path)
    output_path = Path(output_path)
    palette = palette or config.DEFAULT_PALETTE
    # H.264 needs even dimensions.
    width -= width % 2
    height -= height % 2

    notes, duration = load_notes(midi_path, lead_in_s=config.LEAD_IN_S)
    renderer = PianoRenderer(width, height, fps, lookahead_s, palette)
    total_frames = int(duration * fps)

    with tempfile.TemporaryDirectory() as tmp:
        silent_path = Path(tmp) / "silent.mp4" if with_audio else output_path

        window_start = 0
        with FrameWriter(silent_path, width, height, fps) as writer:
            for frame_idx in range(total_frames):
                t = frame_idx / fps
                # Retire notes from the front once fully past (the list is
                # sorted by start; later-but-finished notes are skipped in the
                # draw loop until the front catches up).
                while window_start < len(notes) and notes[window_start].end < t:
                    window_start += 1
                frame = renderer.draw_frame(t, notes, window_start)
                writer.write(np.asarray(frame, dtype=np.uint8).tobytes())

        if with_audio:
            from .audio import synthesize

            wav_path = Path(tmp) / "audio.wav"
            if synthesize(midi_path, wav_path, soundfont=soundfont):
                mux_audio(silent_path, wav_path, output_path, audio_offset_s=config.LEAD_IN_S)
            else:
                silent_path.replace(output_path)

    return output_path
