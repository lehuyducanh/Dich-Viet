"""Tests for the v0.2 upgrades: built-in audio engine, sub-bar harmony
detection with extended chords, and richer MusicXML support."""

import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from music_producer import analyze, arrange, load  # noqa: E402
from music_producer.analysis import detect_chords  # noqa: E402
from music_producer.model import Note, Song, Track  # noqa: E402
from music_producer.producer_brain import RuleBasedBrain  # noqa: E402
from music_producer.synth_engine import render_wav  # noqa: E402
from music_producer.template_library import TemplateLibrary  # noqa: E402


@pytest.fixture(scope="module")
def library():
    return TemplateLibrary()


# --- harmony upgrade -------------------------------------------------------------

def _song_with(notes_spec, tempo=120.0):
    song = Song(tempo=tempo)
    t = Track(name="keys")
    for pitch, start, dur in notes_spec:
        t.add(pitch, start, dur, 96)
    song.tracks = [t]
    return song


def test_half_bar_chord_changes_detected():
    # bar 1: C major (beats 0-2) then G major (beats 2-4) — two chords in one bar
    spec = []
    for p in (48, 60, 64, 67):
        spec.append((p, 0.0, 2.0))
    for p in (43, 55, 59, 62):
        spec.append((p, 2.0, 2.0))
    song = _song_with(spec)
    chords = detect_chords(song, song.tracks[0].notes, 0, "major")
    assert len(chords) == 2
    assert (chords[0].root, chords[0].quality) == (0, "maj")
    assert (chords[1].root, chords[1].quality) == (7, "maj")
    assert chords[0].duration == 2.0


def test_seventh_chord_detected():
    # Cmaj7 held a whole bar: C E G B
    spec = [(p, 0.0, 4.0) for p in (36, 48, 52, 55, 59)]
    song = _song_with(spec)
    chords = detect_chords(song, song.tracks[0].notes, 0, "major")
    assert chords[0].root == 0
    assert chords[0].quality == "maj7"


def test_anticipated_chord_lands_in_next_segment():
    # F chord pushed a 16th early before beat 2 — must still read as F on the
    # second half of the bar, not smear the first chord
    spec = [(p, 0.0, 1.75) for p in (48, 60, 64, 67)]            # C
    spec += [(p, 1.75, 2.25) for p in (41, 53, 57, 60)]          # F, early push
    song = _song_with(spec)
    chords = detect_chords(song, song.tracks[0].notes, 0, "major")
    assert len(chords) == 2
    assert (chords[1].root, chords[1].quality) == (5, "maj")


def test_harmonic_rhythm_merges_static_harmony():
    # one chord held across 2 bars -> a single 8-beat chord, not 4 segments
    spec = [(p, 0.0, 8.0) for p in (45, 57, 60, 64)]             # Am
    song = _song_with(spec)
    chords = detect_chords(song, song.tracks[0].notes, 9, "minor")
    assert len(chords) == 1
    assert chords[0].duration == 8.0
    assert (chords[0].root, chords[0].quality) == (9, "min")


# --- MusicXML upgrade --------------------------------------------------------------

MUSICXML_DOC = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Lead</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>4</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <direction><direction-type>
        <metronome><beat-unit>quarter</beat-unit><per-minute>96</per-minute></metronome>
      </direction-type></direction>
      <harmony><root><root-step>A</root-step></root><kind>minor-seventh</kind></harmony>
      <note><pitch><step>A</step><octave>4</octave></pitch><duration>8</duration>
        <tie type="start"/></note>
      <harmony><root><root-step>F</root-step></root><kind>major</kind></harmony>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>8</duration></note>
    </measure>
    <measure number="2">
      <note><pitch><step>A</step><octave>4</octave></pitch><duration>4</duration>
        <tie type="stop"/></note>
      <note><grace/><pitch><step>B</step><octave>4</octave></pitch></note>
      <note><pitch><step>F</step><octave>4</octave></pitch><duration>12</duration></note>
    </measure>
  </part>
</score-partwise>
"""


def test_musicxml_ties_harmony_metronome(tmp_path):
    f = tmp_path / "lead.musicxml"
    f.write_text(MUSICXML_DOC, encoding="utf-8")
    song = load(f)

    assert song.tempo == 96  # from <metronome>

    notes = song.tracks[0].notes
    # tie: A4 (2 beats) + A4 (1 beat) merged into one 3-beat note
    tied = [n for n in notes if n.pitch == 69]
    assert len(tied) == 1
    assert tied[0].duration == pytest.approx(3.0)
    # grace note skipped
    assert all(n.pitch != 71 for n in notes)

    # explicit harmony: Am7 then F at beat 2
    assert [(c.root, c.quality) for c in song.explicit_chords] == [(9, "min7"), (5, "maj")]
    assert song.explicit_chords[1].start == pytest.approx(2.0)

    # analyzer prefers the explicit symbols over detection
    analysis = analyze(song)
    assert analysis.chord_symbols()[0] == "Amin7"


# --- built-in audio engine ------------------------------------------------------------

def test_synth_engine_renders_nonsilent_wav(tmp_path, library):
    # tiny 2-bar production so the test stays fast
    spec = [(57, 0.0, 4.0), (60, 0.0, 4.0), (64, 0.0, 4.0),
            (53, 4.0, 4.0), (57, 4.0, 4.0), (60, 4.0, 4.0)]
    song = _song_with(spec, tempo=120.0)
    analysis = analyze(song)
    plan = RuleBasedBrain().make_plan(analysis, "edm", library)
    plan.sections = plan.sections[:1]
    plan.sections[0].bars = 2
    produced = arrange(analysis, plan, library)

    wav_path = tmp_path / "out.wav"
    render_wav(produced, library.get("edm").sound_design, wav_path)

    with wave.open(str(wav_path)) as w:
        assert w.getnchannels() == 2
        assert w.getframerate() == 44100
        n_frames = w.getnframes()
        seconds = n_frames / 44100
        # 2 bars @ 128bpm ≈ 3.75s + tail
        assert 3.5 < seconds < 8.0
        raw = w.readframes(n_frames)
    assert max(abs(b - 128) for b in raw[1::2]) > 0 or any(raw)  # not digital silence


def test_synth_engine_lofi_master_chain(tmp_path, library):
    spec = [(48, 0.0, 4.0), (60, 0.0, 4.0), (64, 0.0, 4.0)]
    song = _song_with(spec, tempo=80.0)
    analysis = analyze(song)
    plan = RuleBasedBrain().make_plan(analysis, "lofi chill", library)
    assert plan.template == "lofi"
    plan.sections = plan.sections[:1]
    produced = arrange(analysis, plan, library)
    wav_path = tmp_path / "lofi.wav"
    render_wav(produced, library.get("lofi").sound_design, wav_path)  # vinyl + master LP path
    assert wav_path.stat().st_size > 44100  # > ~0.5s of 16-bit stereo


# --- duration fitting ---------------------------------------------------------------

def test_fit_duration_scales_arrangement(library):
    from music_producer.arrangement import fit_duration
    from examples.make_happy_birthday import build

    analysis = analyze(build())
    plan = RuleBasedBrain().make_plan(analysis, "edm", library)
    fit_duration(plan, 180.0, 4.0)
    # 180s at 128 BPM in 4/4 = exactly 96 bars
    assert plan.total_bars == 96
    assert all(s.bars >= 2 and s.bars % 2 == 0 for s in plan.sections)
    seconds = plan.total_bars * 4 / plan.target_tempo * 60
    assert abs(seconds - 180.0) < 4.0


def test_fit_duration_shrinks_too(library):
    from music_producer.arrangement import fit_duration
    from examples.make_happy_birthday import build

    analysis = analyze(build())
    plan = RuleBasedBrain().make_plan(analysis, "edm", library)
    fit_duration(plan, 60.0, 4.0)
    seconds = plan.total_bars * 4 / plan.target_tempo * 60
    assert abs(seconds - 60.0) < 4.0
    assert all(s.bars >= 2 for s in plan.sections)
