"""Musical analysis of the input song: key, chords, melody extraction.

Chord detection works at half-bar resolution with an extended quality set
(triads + 7ths + sus4), handles anticipated (syncopated) chord changes, and
merges segments into the actual harmonic rhythm. If the input carries explicit
chord symbols (MusicXML <harmony>), those win over detection.

The producer brain only ever sees the SongAnalysis summary, never raw MIDI —
the same boundary a human producer has when reading a lead sheet.
"""

from __future__ import annotations

from .model import Chord, Note, Song, SongAnalysis

# Krumhansl-Schmuckler key profiles
_MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

# (quality, intervals, weight) — triads slightly favored so 7ths/sus need real evidence
_CHORD_TEMPLATES = [
    ("maj",  (0, 4, 7),      1.00),
    ("min",  (0, 3, 7),      1.00),
    ("dim",  (0, 3, 6),      0.82),
    ("sus4", (0, 5, 7),      0.72),
    ("maj7", (0, 4, 7, 11),  0.88),
    ("min7", (0, 3, 7, 10),  0.88),
    ("dom7", (0, 4, 7, 10),  0.86),
]

_MAJOR_SCALE = {0, 2, 4, 5, 7, 9, 11}
_MINOR_SCALE = {0, 2, 3, 5, 7, 8, 10}

# how far ahead of a segment boundary a note may land and still count as the
# next segment's (anticipated) harmony — classic push/syncopation
ANTICIPATION = 0.26  # beats (just over a 16th)


def analyze(song: Song) -> SongAnalysis:
    pitched = [n for t in song.tracks if not t.is_drums for n in t.notes]
    if not pitched and not song.explicit_chords:
        raise ValueError("Input contains no pitched notes to analyze")

    if pitched:
        key_root, key_mode = detect_key(pitched)
    else:
        first = song.explicit_chords[0]
        key_root, key_mode = first.root, ("minor" if first.quality.startswith("min") else "major")

    if song.explicit_chords:
        chords = _normalize_explicit(song.explicit_chords, song)
    else:
        chords = detect_chords(song, pitched, key_root, key_mode)

    melody = extract_melody(song)

    return SongAnalysis(
        tempo=song.tempo,
        time_signature=song.time_signature,
        key_root=key_root,
        key_mode=key_mode,
        chords=chords,
        melody=melody,
        length_bars=song.length_bars,
    )


def _pc_histogram(notes: list[Note]) -> list[float]:
    hist = [0.0] * 12
    for n in notes:
        hist[n.pitch % 12] += n.duration * (n.velocity / 127)
    return hist


def detect_key(notes: list[Note]) -> tuple[int, str]:
    hist = _pc_histogram(notes)
    best = (float("-inf"), 0, "major")
    for root in range(12):
        for mode, profile in (("major", _MAJOR_PROFILE), ("minor", _MINOR_PROFILE)):
            score = sum(hist[(root + i) % 12] * profile[i] for i in range(12))
            if score > best[0]:
                best = (score, root, mode)
    return best[1], best[2]


def _segment_histogram(notes: list[Note], start: float, end: float) -> list[float]:
    """Pitch-class weights for [start, end). Notes that *start* slightly before
    the boundary are pulled in as anticipated harmony; notes merely sustaining
    across the boundary count less than freshly struck ones."""
    hist = [0.0] * 12
    for n in notes:
        n_end = n.start + n.duration
        if n.start >= end or n_end <= start - ANTICIPATION:
            continue
        overlap = min(end, n_end) - max(start, n.start)
        anticipated = start - ANTICIPATION <= n.start < start
        if overlap <= 0 and not anticipated:
            continue
        weight = max(overlap, 0.0) * (n.velocity / 127)
        if anticipated:
            # struck just ahead of the boundary: belongs to this segment
            weight = max(weight, (min(end, n_end) - n.start) * (n.velocity / 127) * 0.9)
        elif n.start < start - ANTICIPATION:
            weight *= 0.70  # sustained from before — slightly weaker evidence
        if n.pitch < 52:
            weight *= 1.8  # bass notes anchor the harmony
        hist[n.pitch % 12] += weight
    return hist


def _best_chord(hist: list[float], key_root: int, key_mode: str) -> tuple[int, str, float]:
    scale = _MAJOR_SCALE if key_mode == "major" else _MINOR_SCALE
    total = sum(hist) or 1.0
    best_score, best_root, best_quality = float("-inf"), key_root, "maj"
    for root in range(12):
        for quality, intervals, weight in _CHORD_TEMPLATES:
            in_chord = sum(hist[(root + i) % 12] for i in intervals)
            out_of_chord = total - in_chord
            # template weight < 1 makes richer chords prove their extra tone;
            # a superset (e.g. maj7 over maj) only wins when the 7th carries
            # real mass, since 0.88 * (in + seventh) must beat 1.0 * in
            score = in_chord * weight - 0.30 * out_of_chord
            score += 0.35 * hist[root]
            # mild diatonic prior: chords whose tones live in the key
            if all(((root + i - key_root) % 12) in scale for i in intervals):
                score *= 1.06
            if score > best_score:
                best_score, best_root, best_quality = score, root, quality
    return best_root, best_quality, best_score


def _score_of(hist: list[float], root: int, quality: str,
              key_root: int, key_mode: str) -> float:
    scale = _MAJOR_SCALE if key_mode == "major" else _MINOR_SCALE
    total = sum(hist) or 1.0
    entry = next((e for e in _CHORD_TEMPLATES if e[0] == quality), _CHORD_TEMPLATES[0])
    _, intervals, weight = entry
    in_chord = sum(hist[(root + i) % 12] for i in intervals)
    score = in_chord * weight - 0.30 * (total - in_chord) + 0.35 * hist[root]
    if all(((root + i - key_root) % 12) in scale for i in intervals):
        score *= 1.06
    return score


def detect_chords(song: Song, notes: list[Note], key_root: int, key_mode: str) -> list[Chord]:
    """Half-bar segmentation -> chord per segment -> merge into harmonic rhythm."""
    bpb = song.beats_per_bar
    seg_len = bpb / 2
    n_segments = max(1, int(song.length_beats / seg_len + 0.999))

    raw: list[Chord | None] = []
    prev_chord: Chord | None = None
    for i in range(n_segments):
        start, end = i * seg_len, (i + 1) * seg_len
        hist = _segment_histogram(notes, start, end)
        if sum(hist) < 1e-6:
            raw.append(None)  # silence: extend whatever came before
            continue
        root, quality, score = _best_chord(hist, key_root, key_mode)
        # hysteresis: keep the previous chord unless the new one clearly wins,
        # so passing tones don't fake a harmony change
        if prev_chord is not None and (root, quality) != (prev_chord.root, prev_chord.quality):
            prev_score = _score_of(hist, prev_chord.root, prev_chord.quality, key_root, key_mode)
            if prev_score >= 0.80 * score:
                root, quality = prev_chord.root, prev_chord.quality
        prev_chord = Chord(start, seg_len, root, quality)
        raw.append(prev_chord)

    # fill silent segments from the previous chord
    prev: Chord | None = None
    for i, c in enumerate(raw):
        if c is None and prev is not None:
            raw[i] = Chord(i * seg_len, seg_len, prev.root, prev.quality)
        elif c is not None:
            prev = c
    chords = [c for c in raw if c is not None]
    if not chords:
        quality = "maj" if key_mode == "major" else "min"
        return [Chord(0, bpb, key_root, quality)]

    return _merge(chords)


def _merge(chords: list[Chord]) -> list[Chord]:
    """Merge adjacent equal segments; absorb a 7th/sus into a neighboring plain
    triad on the same root (one harmony, not two)."""
    merged: list[Chord] = []
    for c in chords:
        if merged and merged[-1].root == c.root and _same_family(merged[-1].quality, c.quality):
            last = merged[-1]
            quality = max((last.quality, c.quality), key=len)  # keep the richer color
            merged[-1] = Chord(last.start, last.duration + c.duration, last.root, quality)
        else:
            merged.append(Chord(c.start, c.duration, c.root, c.quality))
    return merged


def _same_family(a: str, b: str) -> bool:
    """maj+maj7 (or min+min7) over the same root are one harmony; sus4 is a
    different color and must not be absorbed."""
    if a == b:
        return True
    families = ({"maj", "maj7", "dom7"}, {"min", "min7"})
    return any(a in f and b in f for f in families)


def _normalize_explicit(explicit: list[Chord], song: Song) -> list[Chord]:
    """Explicit symbols (MusicXML <harmony>) -> contiguous, gap-free timeline."""
    chords = sorted(explicit, key=lambda c: c.start)
    out: list[Chord] = []
    length = max(song.length_beats, chords[-1].start + chords[-1].duration)
    for i, c in enumerate(chords):
        end = chords[i + 1].start if i + 1 < len(chords) else length
        if end <= c.start:
            continue
        out.append(Chord(c.start, end - c.start, c.root, c.quality))
    return _merge(out) if out else [Chord(0, song.beats_per_bar, 0, "maj")]


def extract_melody(song: Song) -> list[Note]:
    """Pick the track that most resembles a melody: high register, many notes,
    mostly monophonic."""
    best_track = None
    best_score = float("-inf")
    for t in song.tracks:
        if t.is_drums or not t.notes:
            continue
        mean_pitch = sum(n.pitch for n in t.notes) / len(t.notes)
        overlaps = 0
        notes = t.notes
        for i in range(1, len(notes)):
            if notes[i].start < notes[i - 1].start + notes[i - 1].duration - 1e-6:
                overlaps += 1
        poly_ratio = overlaps / len(notes)
        score = mean_pitch + min(len(notes), 200) * 0.2 - poly_ratio * 60
        if score > best_score:
            best_score, best_track = score, t
    return list(best_track.notes) if best_track else []
