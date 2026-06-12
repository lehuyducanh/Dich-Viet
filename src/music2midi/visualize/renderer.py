"""Synthesia-style falling-notes renderer.

Reference look: dark gradient background, 88-key keyboard along the bottom,
rounded gradient note bars falling toward the keyboard (one color per track),
keys lighting up with light beams, an animated glow, and sparks at the hit
line while notes sound.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pretty_midi
from PIL import Image, ImageDraw

from .. import config
from .effects import (
    BarCache,
    ParticleSystem,
    darken,
    lighten,
    make_background,
    make_light_beam,
    make_radial_glow,
)
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
        effects: bool = True,
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.lookahead_s = lookahead_s
        self.effects = effects
        self.colors = [_hex_to_rgb(c) for c in palette]

        kb_height = height * config.KEYBOARD_HEIGHT_FRAC
        self.kb_top = height - kb_height
        self.layout = KeyboardLayout(width=width, kb_top=self.kb_top, kb_height=kb_height)
        self.fall_speed = self.kb_top / lookahead_s  # px per second

        self._background = make_background(width, height).convert("RGBA")
        self._keyboard_base = self._render_keyboard_base()
        self._kb_mask = self._render_keyboard_mask()
        self._bars = BarCache()
        self._particles = ParticleSystem()

        glow_size = max(8, int(self.layout.white_w * 5))
        self._glow_sprites = [make_radial_glow(c, glow_size, peak_alpha=160) for c in self.colors]
        self._hit_sprites = [
            make_radial_glow(c, int(glow_size * 1.7), peak_alpha=210) for c in self.colors
        ]
        beam_h = int(self.kb_top * 0.30)
        self._beam_sprites = [
            make_light_beam(c, int(self.layout.white_w * 1.6), beam_h) for c in self.colors
        ]

    # --- pre-rendered layers ---

    def _render_keyboard_base(self) -> Image.Image:
        img = Image.new("RGB", (self.width, self.height), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        kb_h = self.height - self.kb_top
        # White keys with a subtle vertical gradient (darker near the hit line).
        for pitch in range(LOWEST_PITCH, HIGHEST_PITCH + 1):
            if is_black(pitch):
                continue
            r = self.layout.key_rect(pitch)
            steps = 12
            for i in range(steps):
                shade = 195 + int(48 * i / (steps - 1))
                y0 = r.y + kb_h * i / steps
                y1 = r.y + kb_h * (i + 1) / steps
                draw.rectangle([r.x + 1, y0, r.x + r.w - 1, y1], fill=(shade, shade, shade - 3))
            draw.line([r.x, r.y, r.x, self.height], fill=(35, 35, 38))
        # Black keys with a soft top highlight.
        for pitch in range(LOWEST_PITCH, HIGHEST_PITCH + 1):
            if not is_black(pitch):
                continue
            r = self.layout.key_rect(pitch)
            draw.rounded_rectangle(
                [r.x, r.y, r.x + r.w, r.y + r.h], radius=2, fill=(16, 16, 19)
            )
            draw.line([r.x + 1, r.y + 1, r.x + r.w - 1, r.y + 1], fill=(70, 70, 78))
        # Hit line: thin dark separator with a faint warm glow strip.
        draw.rectangle([0, self.kb_top - 3, self.width, self.kb_top], fill=(28, 28, 40))
        draw.line([0, self.kb_top - 3, self.width, self.kb_top - 3], fill=(95, 95, 130))
        return img

    def _render_keyboard_mask(self) -> Image.Image:
        mask = Image.new("L", (self.width, self.height), 0)
        ImageDraw.Draw(mask).rectangle(
            [0, self.kb_top - 3, self.width, self.height], fill=255
        )
        return mask

    def _track_color(self, track: int) -> tuple[int, int, int]:
        return self.colors[track % len(self.colors)]

    def _sprite(self, sprites: list[Image.Image], track: int) -> Image.Image:
        return sprites[track % len(sprites)]

    def _composite(self, overlay: Image.Image, sprite: Image.Image, x: int, y: int) -> None:
        """alpha_composite a sprite at (x, y), cropping at frame edges.

        (paste-with-mask would multiply the sprite's alpha into itself and
        wash translucent effects out; alpha_composite blends correctly.)
        """
        crop_x = max(0, -x)
        crop_y = max(0, -y)
        if crop_x or crop_y:
            sprite = sprite.crop((crop_x, crop_y, sprite.width, sprite.height))
            x, y = max(0, x), max(0, y)
        if x >= self.width or y >= self.height or sprite.width == 0 or sprite.height == 0:
            return
        overlay.alpha_composite(sprite, (x, y))

    # --- per-frame drawing ---

    def draw_frame(self, t: float, notes: list[TimedNote], window_start: int) -> Image.Image:
        frame = self._background.copy()

        active: list[TimedNote] = []
        horizon = t + self.lookahead_s
        i = window_start
        while i < len(notes) and notes[i].start <= horizon:
            n = notes[i]
            i += 1
            if n.end < t:
                continue
            playing = n.start <= t <= n.end
            if playing:
                active.append(n)
            x, w = self.layout.note_column(n.pitch)
            y_bottom = self.kb_top - (n.start - t) * self.fall_speed
            bar_h = (n.end - n.start) * self.fall_speed
            y_top = y_bottom - bar_h
            y0 = max(y_top, -20.0)
            y1 = min(y_bottom, self.kb_top)
            w_i, h_i = int(round(w)), int(round(y1 - y0))
            if h_i < 2 or w_i < 2 or y_bottom <= 0 or y_top >= self.kb_top:
                continue
            radius = min(w_i * 0.3, 8.0)
            bar = self._bars.get(self._track_color(n.track), w_i, h_i, radius, playing)
            frame.paste(bar, (int(round(x)), int(round(y0))), bar)

        # Keyboard over the bars.
        frame.paste(self._keyboard_base, (0, 0), self._kb_mask)

        # Pressed keys.
        draw = ImageDraw.Draw(frame)
        for n in active:
            r = self.layout.key_rect(n.pitch)
            color = self._track_color(n.track)
            if r.is_black:
                fill = darken(color, 0.75)
            else:
                fill = lighten(color, 0.15)
            draw.rounded_rectangle(
                [r.x + 1, r.y, r.x + r.w - 1, r.y + r.h],
                radius=2,
                fill=fill,
                outline=darken(color, 0.6),
            )

        if not self.effects:
            return frame

        # Effects overlay: beams, animated hit glow, particles.
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        for n in active:
            r = self.layout.key_rect(n.pitch)
            cx = r.x + r.w / 2
            track = n.track

            beam = self._sprite(self._beam_sprites, track)
            self._composite(
                overlay, beam, int(cx - beam.width / 2), int(self.kb_top - beam.height)
            )

            glow = self._sprite(self._glow_sprites, track)
            self._composite(
                overlay, glow, int(cx - glow.width / 2), int(self.kb_top - glow.height / 2)
            )

            # Brighter flash right after the note lands, fading over ~0.3 s.
            age = t - n.start
            if age < 0.3:
                hit = self._sprite(self._hit_sprites, track).copy()
                fade = 1.0 - age / 0.3
                alpha = hit.getchannel("A").point(lambda a, f=fade: int(a * f))
                hit.putalpha(alpha)
                self._composite(
                    overlay, hit, int(cx - hit.width / 2), int(self.kb_top - hit.height / 2)
                )

            intensity = n.velocity / 127.0
            count = 3 if age < 0.12 else 1
            self._particles.spawn(cx, self.kb_top - 4, self._track_color(track), intensity, count)

        self._particles.update(1.0 / self.fps)
        self._particles.draw(overlay)

        return Image.alpha_composite(frame, overlay)


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
    effects: bool = True,
) -> Path:
    """Render a MIDI file to an mp4. Returns the output path."""
    midi_path = Path(midi_path)
    output_path = Path(output_path)
    palette = palette or config.DEFAULT_PALETTE
    # H.264 needs even dimensions.
    width -= width % 2
    height -= height % 2

    notes, duration = load_notes(midi_path, lead_in_s=config.LEAD_IN_S)
    renderer = PianoRenderer(width, height, fps, lookahead_s, palette, effects=effects)
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
                writer.write(np.asarray(frame.convert("RGB"), dtype=np.uint8).tobytes())

        if with_audio:
            from .audio import synthesize

            wav_path = Path(tmp) / "audio.wav"
            if synthesize(midi_path, wav_path, soundfont=soundfont):
                mux_audio(silent_path, wav_path, output_path, audio_offset_s=config.LEAD_IN_S)
            else:
                silent_path.replace(output_path)

    return output_path
