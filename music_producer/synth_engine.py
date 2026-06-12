"""Internal software synthesizer: renders a Song straight to a stereo WAV.

No soundfont, no DAW, no external binaries — just numpy DSP:
  - subtractive synths per layer (saw/supersaw/square/triangle/sine/noise,
    unison detune, sub oscillator, FIR lowpass, ADSR)
  - synthesized drums (kick = pitched sine sweep, snare/clap/hats = shaped
    noise, toms, crash, ride, shaker) with per-hit caching
  - tempo-synced sidechain ducking driven by the actual kick pattern
  - tempo-synced feedback delay, FFT-convolution reverb bus
  - optional lo-fi master treatment (vinyl crackle + tone rolloff)
  - soft-saturation master limiter, 16-bit stereo WAV out

Everything is vectorized; a full 80-bar track renders in seconds.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from .model import Song, Track
from .sound_design import Patch, master_options, patch_for

SR = 44100


def render_wav(song: Song, sound_design: dict | None, path: str | Path,
               sr: int = SR, tail: float = 2.5) -> Path:
    path = Path(path)
    spb = 60.0 / song.tempo                                   # seconds per beat
    n = int((song.length_beats * spb + tail) * sr)
    master = np.zeros((2, n), dtype=np.float64)
    reverb_bus = np.zeros((2, n), dtype=np.float64)

    duck = _duck_curve(song, sr, spb, n)

    for track in song.tracks:
        patch = patch_for(track.name if not track.is_drums else "drums", sound_design)
        if track.is_drums:
            buf = _render_drums(track, sr, spb, n)
        else:
            buf = _render_synth(track, patch, sr, spb, n)
            if patch.delay > 0:
                buf += patch.delay * _delay(buf, sr, spb)
            if patch.sidechain > 0:
                buf *= 1.0 - patch.sidechain * duck
        if patch.reverb > 0:
            reverb_bus += patch.reverb * buf
        master += patch.gain * buf

    master += 0.7 * _reverb(reverb_bus, sr)

    opts = master_options(sound_design)
    if opts.get("cutoff"):
        master = _fir_lowpass(master, float(opts["cutoff"]), sr)
    if opts.get("vinyl"):
        master += float(opts["vinyl"]) * _vinyl_crackle(n, sr)

    # soft-knee limiter + normalize
    peak = np.max(np.abs(master)) or 1.0
    master = np.tanh(master / peak * 1.4) / np.tanh(1.4)

    _write_wav(path, master, sr)
    return path


# --- synth voices ---------------------------------------------------------------

def _render_synth(track: Track, patch: Patch, sr: int, spb: float, n: int) -> np.ndarray:
    mono = np.zeros(n, dtype=np.float64)
    rng = np.random.default_rng(abs(hash(track.name)) % (2 ** 31))
    # fixed unison detune offsets per track so the timbre is stable
    if patch.voices > 1:
        offsets = np.linspace(-patch.detune, patch.detune, patch.voices)
    else:
        offsets = np.array([0.0])
    phases = rng.uniform(0, 1, size=len(offsets))

    for note in track.notes:
        f = 440.0 * 2 ** ((note.pitch + 12 * patch.octave - 69) / 12)
        start = int(note.start * spb * sr)
        dur_s = max(note.duration * spb, 0.02)
        length = int((dur_s + patch.release) * sr)
        if start >= n:
            continue
        length = min(length, n - start)
        if length <= 8:
            continue

        t = np.arange(length) / sr
        sig = np.zeros(length)
        if patch.osc == "noise":
            sig = rng.standard_normal(length) * 0.45
            sig += 0.35 * np.sin(2 * np.pi * f * t)        # tonal center for risers
        else:
            for off, ph in zip(offsets, phases):
                fv = f * 2 ** (off / 12)
                phase = fv * t + ph
                if patch.osc in ("saw", "supersaw"):
                    sig += 2.0 * (phase % 1.0) - 1.0
                elif patch.osc == "square":
                    sig += np.sign(np.sin(2 * np.pi * phase))
                elif patch.osc == "triangle":
                    sig += 2.0 * np.abs(2.0 * (phase % 1.0) - 1.0) - 1.0
                else:  # sine
                    sig += np.sin(2 * np.pi * phase)
            sig /= max(1.0, len(offsets) * 0.7)
        if patch.sub:
            sig += 0.6 * np.sin(2 * np.pi * (f / 2) * t)

        env = _adsr(length, int(dur_s * sr), patch, sr)
        mono[start:start + length] += sig * env * (note.velocity / 127.0)

    mono = _fir_lowpass(mono[None, :], patch.cutoff, sr)[0]

    # constant-power pan + Haas-delay stereo width
    theta = (patch.pan + 1) * np.pi / 4
    left, right = mono * np.cos(theta), mono * np.sin(theta)
    if patch.width > 0:
        shift = int(0.009 * patch.width * sr)
        if shift > 0:
            delayed = np.concatenate([np.zeros(shift), mono[:-shift]])
            left = left * 0.85 + delayed * 0.35 * np.cos(theta)
            right = right * 0.85 + mono * 0.35 * np.sin(theta)
    return np.stack([left, right])


def _adsr(length: int, sustain_len: int, patch: Patch, sr: int) -> np.ndarray:
    a = max(1, int(patch.attack * sr))
    d = max(1, int(patch.decay * sr))
    r = max(1, int(patch.release * sr))
    env = np.zeros(length)
    idx = np.arange(length)
    env = np.where(idx < a, idx / a, env)
    env = np.where((idx >= a) & (idx < a + d),
                   1.0 + (patch.sustain - 1.0) * (idx - a) / d, env)
    env = np.where((idx >= a + d) & (idx < sustain_len), patch.sustain, env)
    rel_start = max(sustain_len, a + d)
    rel_level = patch.sustain if sustain_len >= a + d else env[min(rel_start, length - 1)]
    env = np.where(idx >= rel_start,
                   rel_level * np.maximum(0.0, 1.0 - (idx - rel_start) / r), env)
    return env


# --- drums ----------------------------------------------------------------------

_drum_cache: dict[tuple[int, int, int], np.ndarray] = {}


def _drum_sample(pitch: int, sr: int) -> np.ndarray:
    key = (pitch, sr, 0)
    if key in _drum_cache:
        return _drum_cache[key]
    rng = np.random.default_rng(pitch * 7919)

    def env(n_samples: float, curve: float = 6.0) -> np.ndarray:
        m = int(n_samples)
        return np.exp(-curve * np.arange(m) / m)

    if pitch == 36:  # kick: pitched sine sweep + click
        m = int(0.42 * sr)
        t = np.arange(m) / sr
        freq = 42 + 118 * np.exp(-t * 28)
        phase = np.cumsum(freq) / sr
        sig = np.sin(2 * np.pi * phase) * env(m, 7)
        sig[:int(0.004 * sr)] += rng.standard_normal(int(0.004 * sr)) * 0.4
    elif pitch in (38, 40):  # snare: tone + bright noise
        m = int(0.22 * sr)
        t = np.arange(m) / sr
        sig = 0.5 * np.sin(2 * np.pi * 196 * t) * env(m, 18)
        sig += _highpassed_noise(rng, m, sr, 1800) * env(m, 9) * 0.9
    elif pitch == 39:  # clap: three noise bursts + tail
        m = int(0.25 * sr)
        sig = np.zeros(m)
        for i, off in enumerate((0.0, 0.012, 0.026)):
            o = int(off * sr)
            burst = int(0.02 * sr)
            sig[o:o + burst] += _highpassed_noise(rng, burst, sr, 1200) * (0.8 - 0.15 * i)
        tail_start = int(0.03 * sr)
        sig[tail_start:] += _highpassed_noise(rng, m - tail_start, sr, 1500) * env(m - tail_start, 10) * 0.6
    elif pitch == 37:  # rimshot
        m = int(0.08 * sr)
        t = np.arange(m) / sr
        sig = 0.6 * np.sin(2 * np.pi * 420 * t) * env(m, 22) + _highpassed_noise(rng, m, sr, 2500) * env(m, 25) * 0.5
    elif pitch == 42:  # closed hat
        m = int(0.055 * sr)
        sig = _highpassed_noise(rng, m, sr, 6500) * env(m, 14)
    elif pitch == 44:  # pedal hat
        m = int(0.04 * sr)
        sig = _highpassed_noise(rng, m, sr, 6000) * env(m, 16)
    elif pitch == 46:  # open hat
        m = int(0.38 * sr)
        sig = _highpassed_noise(rng, m, sr, 6000) * env(m, 5)
    elif pitch in (45, 47, 50):  # toms
        base = {45: 96, 47: 128, 50: 168}[pitch]
        m = int(0.3 * sr)
        t = np.arange(m) / sr
        freq = base * (1 + 0.6 * np.exp(-t * 22))
        sig = np.sin(2 * np.pi * np.cumsum(freq) / sr) * env(m, 8)
    elif pitch == 49:  # crash
        m = int(1.6 * sr)
        sig = _highpassed_noise(rng, m, sr, 4500) * env(m, 4) * 0.9
    elif pitch == 51:  # ride
        m = int(0.6 * sr)
        t = np.arange(m) / sr
        sig = _highpassed_noise(rng, m, sr, 5500) * env(m, 6) * 0.5
        sig += 0.18 * np.sin(2 * np.pi * 5230 * t) * env(m, 7)
    elif pitch in (54, 70):  # tambourine / shaker
        m = int(0.07 * sr)
        sig = _highpassed_noise(rng, m, sr, 7500 if pitch == 70 else 5500) * env(m, 12)
    else:  # generic percussive blip
        m = int(0.1 * sr)
        t = np.arange(m) / sr
        sig = np.sin(2 * np.pi * 300 * t) * env(m, 15)

    _drum_cache[key] = sig
    return sig


def _highpassed_noise(rng, m: int, sr: int, cutoff: float) -> np.ndarray:
    noise = rng.standard_normal(max(m, 1))
    return noise - _fir_lowpass(noise[None, :], cutoff, sr)[0]


def _render_drums(track: Track, sr: int, spb: float, n: int) -> np.ndarray:
    mono = np.zeros(n, dtype=np.float64)
    for note in track.notes:
        start = int(note.start * spb * sr)
        if start >= n:
            continue
        sample = _drum_sample(note.pitch, sr)
        length = min(len(sample), n - start)
        mono[start:start + length] += sample[:length] * (note.velocity / 127.0)
    return np.stack([mono, mono])


# --- buses & master -----------------------------------------------------------------

def _duck_curve(song: Song, sr: int, spb: float, n: int) -> np.ndarray:
    """1.0 at each kick hit, decaying to 0 — multiply as (1 - amount*duck)."""
    duck = np.zeros(n)
    kicks = [note.start for t in song.tracks if t.is_drums
             for note in t.notes if note.pitch == 36]
    if not kicks:
        return duck
    rec = max(1, int(0.55 * spb * sr))      # recover over just past half a beat
    shape = np.maximum(0.0, 1.0 - np.arange(rec) / rec) ** 1.6
    for k in kicks:
        s = int(k * spb * sr)
        if s >= n:
            continue
        e = min(s + rec, n)
        duck[s:e] = np.maximum(duck[s:e], shape[:e - s])
    return duck


def _delay(buf: np.ndarray, sr: int, spb: float, feedback: float = 0.42) -> np.ndarray:
    d = int(0.75 * spb * sr)                # dotted-eighth delay
    out = np.zeros_like(buf)
    for k in range(1, 6):
        shift = k * d
        if shift >= buf.shape[1]:
            break
        g = feedback ** k
        # ping-pong: odd taps swap channels
        src = buf[::-1] if k % 2 == 1 else buf
        out[:, shift:] += g * src[:, :-shift]
    return out


_reverb_ir: dict[int, np.ndarray] = {}


def _reverb(bus: np.ndarray, sr: int, seconds: float = 1.9) -> np.ndarray:
    if not np.any(bus):
        return bus
    if sr not in _reverb_ir:
        rng = np.random.default_rng(1234)
        m = int(seconds * sr)
        t = np.arange(m) / sr
        ir = rng.standard_normal((2, m)) * np.exp(-3.2 * t / seconds)
        ir[:, :int(0.01 * sr)] *= np.linspace(0, 1, int(0.01 * sr))  # pre-delay ramp
        ir /= np.sqrt(np.sum(ir ** 2, axis=1, keepdims=True))
        _reverb_ir[sr] = ir
    ir = _reverb_ir[sr]

    n = bus.shape[1]
    size = 1
    while size < n + ir.shape[1]:
        size <<= 1
    out = np.zeros_like(bus)
    for ch in range(2):
        spec = np.fft.rfft(bus[ch], size) * np.fft.rfft(ir[ch], size)
        out[ch] = np.fft.irfft(spec, size)[:n]
    return out * 0.32


def _vinyl_crackle(n: int, sr: int) -> np.ndarray:
    rng = np.random.default_rng(42)
    bed = rng.standard_normal(n) * 0.006
    bed = _fir_lowpass(bed[None, :], 4000, sr)[0]
    ticks = (rng.uniform(size=n) > 1 - 2.2 / sr) * rng.standard_normal(n) * 0.25
    mono = bed + ticks
    return np.stack([mono, mono])


# --- primitives -----------------------------------------------------------------

_kernel_cache: dict[int, np.ndarray] = {}


def _fir_lowpass(buf: np.ndarray, cutoff: float, sr: int, taps: int = 63) -> np.ndarray:
    cutoff = min(cutoff, sr / 2 - 100)
    key = int(cutoff)
    if key not in _kernel_cache:
        m = np.arange(taps) - (taps - 1) / 2
        h = np.sinc(2 * cutoff / sr * m) * np.hamming(taps)
        _kernel_cache[key] = h / h.sum()
    h = _kernel_cache[key]
    return np.stack([np.convolve(ch, h, mode="same") for ch in buf])


def _write_wav(path: Path, stereo: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    interleaved = pcm.T.reshape(-1).tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(interleaved)
