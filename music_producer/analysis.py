"""Musical analysis of the input song: key, chords, melody extraction.

The producer brain only ever sees the SongAnalysis summary, never raw MIDI —
the same boundary a human producer has when reading a lead sheet.
"""

from __future__ import annotations

from .model import Chord, Note, Song, SongAnalysis

# Krumhansl-Schmuckler key profiles
_MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def analyze(song: Song) -> SongAnalysis:
    pitched = [n for t in song.tracks if not t.is_drums for n in t.notes]
    if not pitched:
        raise ValueError("Input contains no pitched notes to analyze")

    key_root, key_mode = detect_key(pitched)
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


def detect_chords(song: Song, notes: list[Note], key_root: int, key_mode: str) -> list[Chord]:
    """Detect one chord per bar by template-matching the bar's pitch-class weights."""
    bpb = song.beats_per_bar
    bars = song.length_bars
    chords: list[Chord] = []
    prev: Chord | None = None

    for bar in range(bars):
        start, end = bar * bpb, (bar + 1) * bpb
        in_bar = [n for n in notes if n.start < end and n.start + n.duration > start]
        if not in_bar:
            if prev is not None:
                chords.append(Chord(start, bpb, prev.root, prev.quality))
            continue
        hist = [0.0] * 12
        for n in in_bar:
            overlap = min(end, n.start + n.duration) - max(start, n.start)
            weight = overlap * (n.velocity / 127)
            # bass notes anchor the harmony
            if n.pitch < 52:
                weight *= 1.8
            hist[n.pitch % 12] += weight

        best_score, best_root, best_quality = float("-inf"), key_root, "maj"
        for root in range(12):
            for quality, intervals in (("maj", (0, 4, 7)), ("min", (0, 3, 7)), ("dim", (0, 3, 6))):
                score = sum(hist[(root + i) % 12] for i in intervals)
                score += 0.35 * hist[root]  # favor the root being present
                if quality == "dim":
                    score *= 0.85  # diminished is rare; demand stronger evidence
                if score > best_score:
                    best_score, best_root, best_quality = score, root, quality
        prev = Chord(start, bpb, best_root, best_quality)
        chords.append(prev)

    if not chords:
        quality = "maj" if key_mode == "major" else "min"
        chords = [Chord(0, bpb, key_root, quality)]
    return chords


def extract_melody(song: Song) -> list[Note]:
    """Pick the track that most resembles a melody: high register, many notes,
    mostly monophonic."""
    best_track = None
    best_score = float("-inf")
    for t in song.tracks:
        if t.is_drums or not t.notes:
            continue
        mean_pitch = sum(n.pitch for n in t.notes) / len(t.notes)
        # polyphony penalty: count overlapping note pairs
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
