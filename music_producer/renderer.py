"""Render a Song to a Standard MIDI File (and optionally audio via FluidSynth)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import mido

from .model import Song

TPB = 480  # ticks per beat


def render_midi(song: Song, path: str | Path) -> Path:
    path = Path(path)
    mid = mido.MidiFile(ticks_per_beat=TPB, type=1)

    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(song.tempo), time=0))
    meta.append(mido.MetaMessage(
        "time_signature",
        numerator=song.time_signature[0], denominator=song.time_signature[1], time=0,
    ))
    mid.tracks.append(meta)

    for track in song.tracks:
        mtrack = mido.MidiTrack()
        mtrack.append(mido.MetaMessage("track_name", name=track.name, time=0))
        if not track.is_drums:
            mtrack.append(mido.Message("program_change", program=track.program,
                                       channel=track.channel, time=0))

        events: list[tuple[int, int, mido.Message]] = []  # (ticks, order, msg)
        for n in track.notes:
            on_tick = max(0, int(round(n.start * TPB)))
            off_tick = max(on_tick + 1, int(round((n.start + n.duration) * TPB)))
            ch = 9 if track.is_drums else track.channel
            events.append((on_tick, 1, mido.Message(
                "note_on", note=n.pitch, velocity=n.velocity, channel=ch, time=0)))
            events.append((off_tick, 0, mido.Message(
                "note_off", note=n.pitch, velocity=0, channel=ch, time=0)))

        events.sort(key=lambda e: (e[0], e[1]))
        prev = 0
        for tick, _, msg in events:
            msg.time = tick - prev
            mtrack.append(msg)
            prev = tick
        mid.tracks.append(mtrack)

    path.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(path))
    return path


def render_audio(midi_path: str | Path, wav_path: str | Path,
                 soundfont: str | Path | None = None) -> Path | None:
    """Optional audio bounce. Requires the `fluidsynth` binary and a .sf2 soundfont."""
    binary = shutil.which("fluidsynth")
    if binary is None:
        return None
    soundfont = soundfont or _find_soundfont()
    if soundfont is None:
        return None
    wav_path = Path(wav_path)
    subprocess.run(
        [binary, "-ni", "-g", "0.7", str(soundfont), str(midi_path),
         "-F", str(wav_path), "-r", "44100"],
        check=True, capture_output=True,
    )
    return wav_path


def _find_soundfont() -> Path | None:
    candidates = [
        Path("/usr/share/sounds/sf2/FluidR3_GM.sf2"),
        Path("/usr/share/soundfonts/FluidR3_GM.sf2"),
        Path("/usr/share/sounds/sf2/default-GM.sf2"),
    ]
    return next((p for p in candidates if p.exists()), None)
