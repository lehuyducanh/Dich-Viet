from pathlib import Path

import pytest

from music2midi.midi.examples import build_demo_song
from music2midi.midi.model import Note, Song, Track


def test_beats_seconds_roundtrip():
    song = Song(tempo_bpm=90)
    assert song.beats_to_seconds(3.0) == pytest.approx(2.0)
    assert song.seconds_to_beats(song.beats_to_seconds(7.5)) == pytest.approx(7.5)


def test_note_clamping():
    n = Note(pitch=300, start=-1.0, duration=1.0, velocity=0)
    assert n.pitch == 127
    assert n.start == 0.0
    assert n.velocity == 1


def test_cleaned_drops_unplayable_notes_and_empty_tracks():
    song = Song(
        tracks=[
            Track(notes=[Note(pitch=60, start=0, duration=0), Note(pitch=62, start=1, duration=1)]),
            Track(notes=[Note(pitch=64, start=0, duration=-2)]),
        ]
    )
    cleaned = song.cleaned()
    assert len(cleaned.tracks) == 1
    assert len(cleaned.tracks[0].notes) == 1
    assert cleaned.tracks[0].notes[0].pitch == 62


def test_midi_save_load_roundtrip(tmp_path: Path):
    song = build_demo_song()
    midi_path = tmp_path / "demo.mid"
    song.save_midi(midi_path)
    assert midi_path.stat().st_size > 0

    loaded = Song.load_midi(midi_path)
    assert loaded.tempo_bpm == pytest.approx(song.tempo_bpm, abs=0.5)
    assert len(loaded.tracks) == len(song.tracks)
    for orig, back in zip(song.tracks, loaded.tracks):
        assert len(back.notes) == len(orig.notes)
        assert back.program == orig.program
        for a, b in zip(orig.notes, back.notes):
            assert b.pitch == a.pitch
            assert b.start == pytest.approx(a.start, abs=0.01)
            assert b.duration == pytest.approx(a.duration, abs=0.01)
