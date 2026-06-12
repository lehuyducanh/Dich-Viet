"""Layer generators: turn template patterns + detected chords into notes.

Every generator works in *section-local* beats; the arranger offsets them
to the section's absolute position.
"""

from __future__ import annotations

from .model import DRUMS, Chord, Note
from .template_library import Template

STEP = 0.25  # one grid step = a 16th note

_GRID_VELOCITY = {"x": 118, "o": 96, "s": 64}


def _vel(base: int, energy: float) -> int:
    return max(20, min(127, int(base * (0.55 + 0.5 * energy))))


def level_for_energy(energy: float) -> str:
    if energy < 0.45:
        return "low"
    if energy < 0.78:
        return "mid"
    return "high"


def chord_at(chords: list[Chord], abs_beat: float) -> Chord:
    """Chord active at an absolute song position; progressions loop."""
    if not chords:
        return Chord(0, 4, 0, "maj")
    total = chords[-1].start + chords[-1].duration
    t = abs_beat % total if total > 0 else 0
    for c in chords:
        if c.start <= t < c.start + c.duration:
            return c
    return chords[-1]


# --- Drums --------------------------------------------------------------------

def gen_drums(template: Template, level: str, bars: int, beats_per_bar: float,
              energy: float, is_build: bool = False, next_is_peak: bool = False) -> list[Note]:
    patterns = template.drum_patterns.get(level) or template.drum_patterns["mid"]
    notes: list[Note] = []
    steps_per_bar = int(beats_per_bar / STEP)

    for bar in range(bars):
        bar_start = bar * beats_per_bar
        ramp = (bar + 1) / bars if is_build else 1.0  # builds get louder bar by bar
        for drum, grid in patterns.items():
            pitch = DRUMS.get(drum)
            if pitch is None:
                continue
            for step in range(steps_per_bar):
                ch = grid[step % 16]
                if ch == ".":
                    continue
                vel = _vel(_GRID_VELOCITY.get(ch, 96), energy)
                if is_build:
                    vel = max(30, min(127, int(vel * (0.6 + 0.4 * ramp))))
                notes.append(Note(pitch, bar_start + step * STEP, STEP * 0.9, vel, 9))

    # crash to open a high-energy section
    if level == "high" and bars > 0:
        notes.append(Note(DRUMS["crash"], 0.0, 2.0, _vel(115, energy), 9))
    # snare fill at the end of the section leading into a peak
    if next_is_peak and not is_build and bars >= 2:
        fill_start = (bars - 1) * beats_per_bar + beats_per_bar / 2
        for i in range(int(beats_per_bar / 2 / STEP)):
            vel = _vel(70 + i * 7, energy)
            notes.append(Note(DRUMS["snare"], fill_start + i * STEP, STEP * 0.9, vel, 9))
    return notes


# --- Bass ---------------------------------------------------------------------

def _bass_root(chord: Chord, octave: int = 2) -> int:
    return 12 * (octave + 1) + chord.root


def gen_bass(style: str, chords: list[Chord], section_start: float, bars: int,
             beats_per_bar: float, energy: float) -> list[Note]:
    """Basslines track the harmonic rhythm: the chord is looked up at every
    note onset, so mid-bar chord changes (half-bar harmony, pushes) land."""
    notes: list[Note] = []
    vel = _vel(100, energy)

    def root_at(local: float, octave: int = 2) -> int:
        return 12 * (octave + 1) + chord_at(chords, section_start + local).root

    for bar in range(bars):
        local = bar * beats_per_bar

        if style == "sustained_roots":
            # re-strike on every chord change inside the bar
            pos = local
            while pos < local + beats_per_bar - 1e-6:
                chord = chord_at(chords, section_start + pos)
                seg_end = min(local + beats_per_bar,
                              _next_change(chords, section_start + pos) - section_start)
                notes.append(Note(12 * 3 + chord.root, pos, seg_end - pos, vel - 12))
                pos = seg_end
        elif style == "four_floor_roots":
            for b in range(int(beats_per_bar)):
                notes.append(Note(root_at(local + b), local + b, 0.9, vel))
        elif style == "eighth_pump":
            for i in range(int(beats_per_bar * 2)):
                t = local + i * 0.5
                notes.append(Note(root_at(t), t, 0.45, vel if i % 2 == 0 else vel - 18))
        elif style == "sixteenth_pump":
            for i in range(int(beats_per_bar * 4)):
                t = local + i * STEP
                v = vel if i % 4 == 0 else (vel - 14 if i % 2 == 0 else vel - 26)
                notes.append(Note(root_at(t), t, STEP * 0.85, v))
        elif style == "offbeat_eighths":
            for i in range(int(beats_per_bar * 2)):
                if i % 2 == 1:  # off-beats only — classic EDM pump against the kick
                    t = local + i * 0.5
                    notes.append(Note(root_at(t), t, 0.42, vel))
        elif style == "root_fifth_octave":
            for i in range(int(beats_per_bar * 2)):
                t = local + i * 0.5
                root = root_at(t)
                seq = [root, root + 12, root + 7, root + 12]
                if i % 2 == 1:
                    notes.append(Note(seq[(i // 2) % 4], t, 0.45, vel - 8))
                elif i == 0:
                    notes.append(Note(root, t, 0.45, vel))
        elif style == "trap_808":
            root = root_at(local)
            half = chord_at(chords, section_start + local + beats_per_bar / 2)
            notes.append(Note(root - 12, local, beats_per_bar * 0.55, vel))
            if half.root != root % 12:  # chord changed mid-bar: follow it
                notes.append(Note(12 * 2 + half.root, local + beats_per_bar / 2,
                                  beats_per_bar * 0.4, vel - 4))
            elif bar % 2 == 1:
                notes.append(Note(root - 12, local + beats_per_bar - 1.0, 0.5, vel - 10))
                notes.append(Note(root, local + beats_per_bar - 0.5, 0.5, vel - 6))
        elif style == "lazy_roots":
            root = root_at(local)
            second = root_at(local + beats_per_bar / 2)
            if second == root:
                second = root + 7 - 12 if root + 7 - 12 > 24 else root + 7
            notes.append(Note(root, local, beats_per_bar / 2 - 0.25, vel - 20))
            notes.append(Note(second, local + beats_per_bar / 2,
                              beats_per_bar / 2 - 0.5, vel - 26))
        elif style == "rolling_octaves":
            for i in range(int(beats_per_bar * 2)):
                t = local + i * 0.5
                root = root_at(t)
                pitch = root if i % 4 in (0, 1) else root + 12
                notes.append(Note(pitch, t, 0.48, vel - (0 if i % 2 == 0 else 16)))
        else:
            notes.append(Note(root_at(local), local, beats_per_bar, vel - 12))
    return notes


def _next_change(chords: list[Chord], abs_beat: float) -> float:
    """Absolute beat of the next chord change after abs_beat (looping)."""
    if not chords:
        return abs_beat + 4.0
    total = chords[-1].start + chords[-1].duration
    t = abs_beat % total if total > 0 else 0
    for c in chords:
        if c.start <= t < c.start + c.duration:
            return abs_beat + (c.start + c.duration - t)
    return abs_beat + total - t


# --- Pad ------------------------------------------------------------------------

def gen_pad(chords: list[Chord], section_start: float, bars: int,
            beats_per_bar: float, energy: float) -> list[Note]:
    """Sustained voicings following the real harmonic rhythm (half-bar
    resolution), holding at most 2 bars before re-triggering."""
    notes: list[Note] = []
    vel = _vel(64, energy)
    section_len = bars * beats_per_bar
    half = beats_per_bar / 2

    pos = 0.0
    while pos < section_len - 1e-6:
        chord = chord_at(chords, section_start + pos)
        # extend in half-bar steps while the harmony holds (cap at 2 bars)
        end = pos + half
        while end < section_len - 1e-6 and end - pos < 2 * beats_per_bar - 1e-6:
            nxt = chord_at(chords, section_start + end)
            if nxt.root != chord.root or nxt.quality != chord.quality:
                break
            end += half
        duration = end - pos - 0.1
        for p in chord.pitches(octave=4):
            notes.append(Note(p, pos, duration, vel))
        # add the 9th for color on sustained pads
        notes.append(Note(chord.pitches(octave=4)[0] + 14, pos, duration, vel - 18))
        pos = end
    return notes


# --- Arp ------------------------------------------------------------------------

def gen_arp(style: str, chords: list[Chord], section_start: float, bars: int,
            beats_per_bar: float, energy: float) -> list[Note]:
    notes: list[Note] = []
    vel = _vel(78, energy)
    rate = 0.5 if style.endswith("8") else STEP
    half = beats_per_bar / 2
    for seg in range(bars * 2):  # refresh the chord pool every half bar
        local = seg * half
        chord = chord_at(chords, section_start + local)
        pool = chord.pitches(octave=5) + [chord.pitches(octave=6)[0]]
        if style.startswith("updown"):
            seq = pool + pool[-2:0:-1]
        else:  # "up*"
            seq = pool
        steps = int(half / rate)
        for i in range(steps):
            global_i = seg * steps + i  # keep the cycle phase continuous
            pitch = seq[global_i % len(seq)]
            accent = 8 if global_i % 4 == 0 else 0
            notes.append(Note(pitch, local + i * rate, rate * 0.85, min(127, vel + accent)))
    return notes


# --- Melody / Lead ----------------------------------------------------------------

def gen_melody(melody: list[Note], bars: int, beats_per_bar: float,
               energy: float, octave_shift: int = 0) -> list[Note]:
    """Tile the client's original melody across the section."""
    if not melody:
        return []
    base = min(n.start for n in melody)
    length = max(n.start + n.duration for n in melody) - base
    loop_bars = max(1, int(length / beats_per_bar + 0.999))
    loop_len = loop_bars * beats_per_bar
    section_len = bars * beats_per_bar

    vel = _vel(98, energy)
    out: list[Note] = []
    offset = 0.0
    while offset < section_len - 1e-6:
        for n in melody:
            start = offset + (n.start - base)
            if start >= section_len:
                continue
            duration = min(n.duration, section_len - start)
            pitch = max(0, min(127, n.pitch + 12 * octave_shift))
            out.append(Note(pitch, start, duration, min(127, vel + (n.velocity - 96) // 3)))
        offset += loop_len
    return out


# --- FX -----------------------------------------------------------------------------

def gen_fx(bars: int, beats_per_bar: float, energy: float, key_root: int) -> list[Note]:
    """Riser: chromatic 16th run climbing across the final two bars of the section."""
    notes: list[Note] = []
    riser_bars = min(2, bars)
    start = (bars - riser_bars) * beats_per_bar
    steps = int(riser_bars * beats_per_bar / STEP)
    base = 48 + key_root
    for i in range(steps):
        pitch = min(120, base + int(i * 24 / max(steps - 1, 1)))
        vel = _vel(50 + int(60 * i / max(steps - 1, 1)), energy)
        notes.append(Note(pitch, start + i * STEP, STEP, vel))
    return notes
