"""Input parsing: Standard MIDI files (via mido) and basic MusicXML."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import mido

from .model import Note, Song, Track

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


def load_musicxml(path: str | Path) -> Song:
    path = Path(path)
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path) as zf:
            inner = [n for n in zf.namelist()
                     if n.endswith(".xml") and not n.startswith("META-INF")]
            if not inner:
                raise ValueError("No MusicXML document found inside .mxl archive")
            root = ET.fromstring(zf.read(inner[0]))
    else:
        root = ET.parse(path).getroot()

    song = Song()
    tempo_el = root.find(".//sound[@tempo]")
    if tempo_el is not None:
        song.tempo = float(tempo_el.get("tempo"))
    ts = root.find(".//attributes/time")
    if ts is not None:
        song.time_signature = (
            int(ts.findtext("beats", "4")),
            int(ts.findtext("beat-type", "4")),
        )

    for pi, part in enumerate(root.findall(".//part")):
        track = Track(name=f"part{pi}", channel=min(pi, 15) if pi != GM_DRUM_CHANNEL else 0)
        divisions = 1  # divisions per quarter note
        cursor = 0.0   # beats
        for measure in part.findall("measure"):
            div_el = measure.find("attributes/divisions")
            if div_el is not None and div_el.text:
                divisions = int(div_el.text)
            measure_start = cursor
            for el in measure:
                if el.tag == "backup":
                    cursor -= int(el.findtext("duration", "0")) / divisions
                elif el.tag == "forward":
                    cursor += int(el.findtext("duration", "0")) / divisions
                elif el.tag == "note":
                    dur = int(el.findtext("duration", "0")) / divisions
                    is_chord_note = el.find("chord") is not None
                    start = cursor if not is_chord_note else cursor - dur
                    pitch_el = el.find("pitch")
                    if pitch_el is not None and el.find("rest") is None:
                        step = pitch_el.findtext("step", "C")
                        alter = int(pitch_el.findtext("alter", "0") or 0)
                        octave = int(pitch_el.findtext("octave", "4"))
                        midi = 12 * (octave + 1) + _STEP_TO_PC[step] + alter
                        track.notes.append(Note(midi, start, max(dur, 1 / 32), 90, track.channel))
                    if not is_chord_note:
                        cursor += dur
            cursor = max(cursor, measure_start)
        if track.notes:
            track.notes.sort(key=lambda n: n.start)
            song.tracks.append(track)

    return song
