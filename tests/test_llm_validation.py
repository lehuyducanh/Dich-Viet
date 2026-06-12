"""Validation/repair behavior on canned LLM output — no network calls."""

import pytest

from music2midi.generate.llm import _extract_json, _parse_song


def test_extract_json_strips_code_fences():
    wrapped = 'Here you go:\n```json\n{"title": "X"}\n```\nEnjoy!'
    assert _extract_json(wrapped) == '{"title": "X"}'


def test_extract_json_passthrough():
    raw = '{"title": "X"}'
    assert _extract_json(raw) == raw


def test_parse_song_clamps_out_of_range_values():
    text = """{
      "title": "Test", "tempo_bpm": 100, "time_signature": "4/4",
      "tracks": [{
        "name": "Lead", "program": 200, "is_drum": false,
        "notes": [
          {"pitch": 200, "start": -1.0, "duration": 1.0, "velocity": 300},
          {"pitch": 60, "start": 0.0, "duration": 0.0, "velocity": 80}
        ]
      }]
    }"""
    song = _parse_song(text)
    track = song.tracks[0]
    assert track.program == 127
    # The zero-duration note is dropped by cleaned(); the clamped one survives.
    assert len(track.notes) == 1
    note = track.notes[0]
    assert note.pitch == 127
    assert note.start == 0.0
    assert note.velocity == 127


def test_parse_song_drops_empty_tracks():
    text = """{
      "title": "Test", "tempo_bpm": 90,
      "tracks": [
        {"name": "Empty", "program": 0, "notes": []},
        {"name": "Real", "program": 0,
         "notes": [{"pitch": 60, "start": 0, "duration": 1, "velocity": 80}]}
      ]
    }"""
    song = _parse_song(text)
    assert [t.name for t in song.tracks] == ["Real"]


def test_parse_song_rejects_garbage():
    with pytest.raises(Exception):
        _parse_song("not json at all")


def test_parse_song_defaults_velocity():
    text = """{
      "title": "T", "tempo_bpm": 120,
      "tracks": [{"name": "A", "program": 0,
                  "notes": [{"pitch": 64, "start": 0, "duration": 2}]}]
    }"""
    song = _parse_song(text)
    assert song.tracks[0].notes[0].velocity == 80
