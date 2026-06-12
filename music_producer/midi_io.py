"""Input parsing: Standard MIDI files (via mido) and MusicXML.

MusicXML support covers: pitched notes (incl. chords & multiple voices via
backup/forward), tied notes (merged), grace notes (skipped), transposing
instruments (<transpose>), tempo from <sound tempo> and <metronome>, time
signatures, and explicit chord symbols (<harmony>) which feed the analyzer
directly instead of chord detection.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import mido

from .model import Chord, Note, Song, Track

GM_DRUM_CHANNEL = 9


def load(path: str | Path) -> Song:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".mid", ".midi"):
        return load_midi(path)
    if suffix in (".xml", ".musicxml", ".mxl"):
        return load_musicxml(path)
    raise ValueError(f"Unsupported input format: {suffix} (expected .mid/.midi/.xml/.musicxml/.mxl)")


def load_midi(path: str | Path) -> Song:
    mid = mido.MidiFile(str(path))
    tpb = mid.ticks_per_beat or 480
    song = Song()

    tempo_us = 500000  # default 120 BPM
    found_tempo = False

    for i, mtrack in enumerate(mid.tracks):
        abs_ticks = 0
        open_notes: dict[tuple[int, int], tuple[int, int]] = {}  # (ch, pitch) -> (start, vel)
        notes: list[Note] = []
        name = mtrack.name or f"track{i}"
        program = 0
        channels: set[int] = set()

        for msg in mtrack:
            abs_ticks += msg.time
            if msg.type == "set_tempo" and not found_tempo:
                tempo_us = msg.tempo
                found_tempo = True
            elif msg.type == "time_signature":
                song.time_signature = (msg.numerator, msg.denominator)
            elif msg.type == "program_change":
                program = msg.program
                channels.add(msg.channel)
            elif msg.type == "note_on" and msg.velocity > 0:
                open_notes[(msg.channel, msg.note)] = (abs_ticks, msg.velocity)
                channels.add(msg.channel)
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                key = (msg.channel, msg.note)
                if key in open_notes:
                    start, vel = open_notes.pop(key)
                    notes.append(Note(
                        pitch=msg.note,
                        start=start / tpb,
                        duration=max((abs_ticks - start) / tpb, 1 / 32),
                        velocity=vel,
                        channel=msg.channel,
                    ))

        if notes:
            is_drums = channels == {GM_DRUM_CHANNEL}
            channel = next(iter(channels)) if len(channels) == 1 else 0
            song.tracks.append(Track(
                name=name, notes=sorted(notes, key=lambda n: n.start),
                program=program, channel=channel, is_drums=is_drums,
            ))

    song.tempo = round(mido.tempo2bpm(tempo_us), 2)
    return song


# --- MusicXML ----------------------------------------------------------------

_STEP_TO_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# MusicXML <kind> values -> our chord qualities
_KIND_TO_QUALITY = {
    "major": "maj", "": "maj", "major-sixth": "maj",
    "minor": "min", "minor-sixth": "min",
    "diminished": "dim", "half-diminished": "dim", "diminished-seventh": "dim",
    "suspended-fourth": "sus4", "suspended-second": "sus4",
    "major-seventh": "maj7",
    "minor-seventh": "min7", "minor-ninth": "min7", "minor-11th": "min7",
    "dominant": "dom7", "dominant-seventh": "dom7", "dominant-ninth": "dom7",
    "dominant-11th": "dom7", "dominant-13th": "dom7",
    "power": "maj", "augmented": "maj",
}


def load_musicxml(path: str | Path) -> Song:
    path = Path(path)
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path) as zf:
            inner = _mxl_rootfile(zf)
            root = ET.fromstring(zf.read(inner))
    else:
        root = ET.parse(path).getroot()
    if root.tag == "score-timewise":
        raise ValueError("score-timewise MusicXML is not supported; export as score-partwise")

    song = Song()
    _read_first_tempo(root, song)
    ts = root.find(".//attributes/time")
    if ts is not None:
        song.time_signature = (
            int(ts.findtext("beats", "4")),
            int(ts.findtext("beat-type", "4")),
        )

    part_names = {
        sp.get("id"): (sp.findtext("part-name") or "").strip()
        for sp in root.findall(".//score-part")
    }

    for pi, part in enumerate(root.findall(".//part")):
        name = part_names.get(part.get("id"), "") or f"part{pi}"
        channel = pi if pi < GM_DRUM_CHANNEL else pi + 1  # never collide with drums
        track = Track(name=name, channel=min(channel, 15))
        divisions = 1          # divisions per quarter note
        transpose = 0          # chromatic transposition for this part
        cursor = 0.0           # beats
        pending_ties: dict[int, Note] = {}  # pitch -> note awaiting its tie-stop

        for measure in part.findall("measure"):
            div_el = measure.find("attributes/divisions")
            if div_el is not None and div_el.text:
                divisions = int(div_el.text)
            tr = measure.find("attributes/transpose")
            if tr is not None:
                transpose = (int(tr.findtext("chromatic", "0") or 0)
                             + 12 * int(tr.findtext("octave-change", "0") or 0))
            measure_start = cursor

            for el in measure:
                if el.tag == "backup":
                    cursor -= int(el.findtext("duration", "0")) / divisions
                elif el.tag == "forward":
                    cursor += int(el.findtext("duration", "0")) / divisions
                elif el.tag == "harmony" and pi == 0:
                    chord = _parse_harmony(el, cursor, divisions)
                    if chord is not None:
                        song.explicit_chords.append(chord)
                elif el.tag == "sound" and el.get("tempo"):
                    if song.tempo == 120.0:
                        song.tempo = float(el.get("tempo"))
                elif el.tag == "note":
                    cursor = _parse_note(el, track, cursor, divisions, transpose, pending_ties)
            cursor = max(cursor, measure_start)

        track.notes.extend(pending_ties.values())  # unterminated ties still sound
        if track.notes:
            track.notes.sort(key=lambda n: n.start)
            song.tracks.append(track)

    song.explicit_chords.sort(key=lambda c: c.start)
    return song


def _parse_note(el: ET.Element, track: Track, cursor: float, divisions: int,
                transpose: int, pending_ties: dict[int, Note]) -> float:
    if el.find("grace") is not None:  # grace notes carry no duration
        return cursor
    dur = int(el.findtext("duration", "0")) / divisions
    is_chord_note = el.find("chord") is not None
    start = cursor if not is_chord_note else cursor - dur

    pitch_el = el.find("pitch")
    if pitch_el is not None and el.find("rest") is None and el.find("unpitched") is None:
        step = pitch_el.findtext("step", "C")
        alter = int(float(pitch_el.findtext("alter", "0") or 0))
        octave = int(pitch_el.findtext("octave", "4"))
        midi = 12 * (octave + 1) + _STEP_TO_PC[step] + alter + transpose
        midi = max(0, min(127, midi))

        ties = {t.get("type") for t in el.findall("tie")}
        if "stop" in ties and midi in pending_ties:
            pending_ties[midi].duration += dur
            if "start" not in ties:           # tie chain ends here
                track.notes.append(pending_ties.pop(midi))
        else:
            note = Note(midi, start, max(dur, 1 / 32), 90, track.channel)
            if "start" in ties:
                pending_ties[midi] = note     # hold until the tie resolves
            else:
                track.notes.append(note)

    if not is_chord_note:
        cursor += dur
    return cursor


def _parse_harmony(el: ET.Element, cursor: float, divisions: int) -> Chord | None:
    root_el = el.find("root")
    if root_el is None:
        return None
    step = root_el.findtext("root-step")
    if not step or step not in _STEP_TO_PC:
        return None
    alter = int(float(root_el.findtext("root-alter", "0") or 0))
    pc = (_STEP_TO_PC[step] + alter) % 12
    kind = (el.findtext("kind") or "").strip()
    quality = _KIND_TO_QUALITY.get(kind, "maj")
    offset = int(el.findtext("offset", "0") or 0) / divisions
    # duration is provisional; the analyzer stretches each symbol to the next one
    return Chord(start=max(0.0, cursor + offset), duration=1.0, root=pc, quality=quality)


def _read_first_tempo(root: ET.Element, song: Song) -> None:
    sound = root.find(".//sound[@tempo]")
    if sound is not None:
        song.tempo = float(sound.get("tempo"))
        return
    metronome = root.find(".//metronome")
    if metronome is not None:
        per_min = metronome.findtext("per-minute")
        if per_min:
            try:
                bpm = float(per_min)
            except ValueError:
                return
            unit = metronome.findtext("beat-unit", "quarter")
            scale = {"half": 2.0, "quarter": 1.0, "eighth": 0.5}.get(unit, 1.0)
            if metronome.find("beat-unit-dot") is not None:
                scale *= 1.5
            song.tempo = bpm * scale


def _mxl_rootfile(zf: zipfile.ZipFile) -> str:
    """Resolve the main document via META-INF/container.xml (fallback: first xml)."""
    try:
        container = ET.fromstring(zf.read("META-INF/container.xml"))
        rootfile = container.find(".//rootfile")
        if rootfile is not None and rootfile.get("full-path"):
            return rootfile.get("full-path")
    except KeyError:
        pass
    inner = [n for n in zf.namelist() if n.endswith(".xml") and not n.startswith("META-INF")]
    if not inner:
        raise ValueError("No MusicXML document found inside .mxl archive")
    return inner[0]
