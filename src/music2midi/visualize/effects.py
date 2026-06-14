"""Visual effects for the piano renderer: pre-rendered sprites and particles.

Everything here is deterministic (seeded RNG) so renders are reproducible.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

RGB = tuple[int, int, int]


def lighten(rgb: RGB, amount: float) -> RGB:
    return tuple(int(v + (255 - v) * amount) for v in rgb)  # type: ignore[return-value]


def darken(rgb: RGB, factor: float) -> RGB:
    return tuple(int(v * factor) for v in rgb)  # type: ignore[return-value]


def make_background(width: int, height: int) -> Image.Image:
    """Vertical gradient: deep night blue at the top fading to black at the
    keyboard, with a faint horizontal vignette."""
    top = np.array([10, 11, 22], dtype=np.float32)
    bottom = np.array([2, 2, 5], dtype=np.float32)
    ys = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    rows = top[None, :] * (1 - ys) + bottom[None, :] * ys  # (H, 3)

    xs = np.linspace(-1.0, 1.0, width, dtype=np.float32)[None, :]
    vignette = 1.0 - 0.25 * xs**2  # (1, W)

    arr = rows[:, None, :] * vignette[:, :, None]
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGB")


def make_radial_glow(rgb: RGB, size: int, peak_alpha: int = 130) -> Image.Image:
    """Soft radial gradient sprite for the key hit point."""
    size = max(8, size)
    arr = np.zeros((size, size, 4), dtype=np.uint8)
    yy, xx = np.mgrid[0:size, 0:size]
    center = (size - 1) / 2
    dist = np.sqrt((xx - center) ** 2 + (yy - center) ** 2) / center
    alpha = np.clip(1.0 - dist, 0.0, 1.0) ** 1.8 * peak_alpha
    bright = lighten(rgb, 0.45)
    arr[..., 0], arr[..., 1], arr[..., 2] = bright
    arr[..., 3] = alpha.astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def make_light_beam(rgb: RGB, width: int, height: int, peak_alpha: int = 120) -> Image.Image:
    """Vertical light column rising from a pressed key, fading upward and at
    the sides."""
    width = max(2, width)
    height = max(2, height)
    ys = np.linspace(1.0, 0.0, height, dtype=np.float32)[:, None]  # bright at bottom
    xs = np.linspace(-1.0, 1.0, width, dtype=np.float32)[None, :]
    side = np.clip(1.0 - xs**2, 0.0, 1.0)
    alpha = (ys**1.6) * side * peak_alpha
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    bright = lighten(rgb, 0.35)
    arr[..., 0], arr[..., 1], arr[..., 2] = bright
    arr[..., 3] = alpha.astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def make_gradient_bar(
    rgb: RGB, w: int, h: int, radius: float, playing: bool
) -> Image.Image:
    """Rounded note bar with a vertical gradient (brighter toward the
    keyboard, as if lit from below) and a luminous border."""
    w = max(2, w)
    h = max(2, h)
    base = lighten(rgb, 0.35) if playing else rgb
    top_c = np.array(darken(base, 0.72), dtype=np.float32)
    bottom_c = np.array(lighten(base, 0.30), dtype=np.float32)
    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    rows = top_c[None, :] * (1 - ys) + bottom_c[None, :] * ys
    grad = np.repeat(rows[:, None, :], w, axis=1).astype(np.uint8)

    rgba = np.dstack([grad, np.full((h, w), 255, dtype=np.uint8)])
    bar = Image.fromarray(rgba, "RGBA")

    mask = Image.new("L", (w, h), 0)
    r = max(0.0, min(radius, w / 2 - 1, h / 2 - 1))
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    bar.putalpha(mask)

    border = lighten(base, 0.55)
    ImageDraw.Draw(bar).rounded_rectangle(
        [0, 0, w - 1, h - 1], radius=r, outline=(*border, 255), width=1
    )
    return bar


class BarCache:
    """Memoizes gradient bars; sizes repeat heavily across frames."""

    def __init__(self, max_entries: int = 1024):
        self._cache: dict[tuple, Image.Image] = {}
        self._max = max_entries

    def get(self, rgb: RGB, w: int, h: int, radius: float, playing: bool) -> Image.Image:
        key = (rgb, w, h, round(radius, 1), playing)
        bar = self._cache.get(key)
        if bar is None:
            if len(self._cache) >= self._max:
                self._cache.clear()
            bar = make_gradient_bar(rgb, w, h, radius, playing)
            self._cache[key] = bar
        return bar


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    age: float
    life: float
    size: float
    color: RGB


class ParticleSystem:
    """Sparks that fly up from keys while notes sound."""

    def __init__(self, seed: int = 1234, max_particles: int = 700):
        self._rng = random.Random(seed)
        self._particles: list[Particle] = []
        self._max = max_particles

    def spawn(self, x: float, y: float, color: RGB, intensity: float, count: int) -> None:
        rng = self._rng
        for _ in range(count):
            if len(self._particles) >= self._max:
                return
            angle = rng.uniform(math.pi * 0.15, math.pi * 0.85)  # mostly upward
            speed = rng.uniform(40, 170) * (0.6 + 0.4 * intensity)
            self._particles.append(
                Particle(
                    x=x + rng.uniform(-4, 4),
                    y=y + rng.uniform(-2, 2),
                    vx=math.cos(angle) * speed * rng.choice((-1, 1)) * 0.4,
                    vy=-math.sin(angle) * speed,
                    age=0.0,
                    life=rng.uniform(0.35, 0.9),
                    size=rng.uniform(1.4, 3.2),
                    color=lighten(color, rng.uniform(0.15, 0.45)),
                )
            )

    def update(self, dt: float) -> None:
        alive = []
        for p in self._particles:
            p.age += dt
            if p.age >= p.life:
                continue
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += 60.0 * dt  # slight gravity pull-back
            alive.append(p)
        self._particles = alive

    def draw(self, overlay: Image.Image) -> None:
        draw = ImageDraw.Draw(overlay)
        for p in self._particles:
            fade = 1.0 - p.age / p.life
            s = p.size * (0.6 + 0.4 * fade)
            # Colored halo with a near-white core for a spark look.
            draw.ellipse(
                [p.x - s * 1.8, p.y - s * 1.8, p.x + s * 1.8, p.y + s * 1.8],
                fill=(*p.color, int(90 * fade)),
            )
            draw.ellipse(
                [p.x - s, p.y - s, p.x + s, p.y + s],
                fill=(*lighten(p.color, 0.7), int(255 * fade)),
            )

    def __len__(self) -> int:
        return len(self._particles)
