"""End-to-end and unit tests for the music producer pipeline (no LLM required)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from examples.make_demo_input import build as build_demo  # noqa: E402
from music_producer import analyze, arrange, load, render_midi  # noqa: E402
from music_producer.model import Note  # noqa: E402
from music_producer.producer_brain import RuleBasedBrain, _plan_from_dict  # noqa: E402
from music_producer.template_library import LEVELS, TemplateLibrary  # noqa: E402


@pytest.fixture(scope="module")
def library():
    return TemplateLibrary()


@pytest.fixture(scope="module")
def demo_song():
    return build_demo()


@pytest.fixture(scope="module")
def demo_analysis(demo_song):
    return analyze(demo_song)


def test_templates_load_and_validate(library):
    assert {"edm", "house", "trap", "lofi", "synthwave", "dnb"} <= set(library.names())
    for t in library.templates.values():
        for level in t.bass_style:
            assert level in LEVELS
        assert t.default_arrangement, t.name


def test_analysis_detects_key_and_chords(demo_analysis):
    # demo progression is Am F C G — relative major C / minor A both acceptable
    assert demo_analysis.key_name in ("A minor", "C major")
    assert demo_analysis.length_bars == 8
    symbols = demo_analysis.chord_symbols()
    assert symbols[0] == "Am"
    assert symbols[1] == "F"
    assert symbols[2] == "C"
    assert symbols[3] == "G"
    assert len(demo_analysis.melody) > 10


def test_rule_based_brain_matches_theme_keywords(demo_analysis, library):
    brain = RuleBasedBrain()
    assert brain.make_plan(demo_analysis, "nhạc EDM sôi động cho festival", library).template == "edm"
    assert brain.make_plan(demo_analysis, "lofi chill để học bài", library).template == "lofi"
    assert brain.make_plan(demo_analysis, "trap 808 thật dark", library).template == "trap"


def test_rule_based_brain_honors_bpm_in_theme(demo_analysis, library):
    plan = RuleBasedBrain().make_plan(demo_analysis, "EDM 128bpm", library)
    assert plan.target_tempo == 128


def test_llm_plan_validation_clamps_bad_values(library):
    raw = {
        "template": "nonexistent-genre",
        "target_tempo": 999,
        "transpose": 40,
        "energy": 3.0,
        "title": "X",
        "notes": "",
        "sections": [
            {"name": "drop", "bars": 9999, "energy": 5, "layers": ["drums", "bogus-layer"]},
        ],
    }
    plan = _plan_from_dict(raw, library)
    assert plan.template in library.names()
    assert plan.transpose <= 11
    assert plan.energy <= 1.0
    assert plan.sections[0].bars <= 64
    assert plan.sections[0].layers == ["drums"]


def test_full_pipeline_renders_midi(tmp_path, demo_analysis, library):
    plan = RuleBasedBrain().make_plan(demo_analysis, "EDM sôi động", library)
    song = arrange(demo_analysis, plan, library)

    layer_names = {t.name for t in song.tracks}
    assert "drums" in layer_names and "bass" in layer_names
    assert song.tempo == plan.target_tempo
    expected_beats = plan.total_bars * 4
    assert song.length_beats <= expected_beats + 2  # crash tails may ring past the bar

    out = tmp_path / "out.mid"
    render_midi(song, out)
    assert out.exists() and out.stat().st_size > 1000

    # round-trip: the rendered file must be loadable and non-empty
    reloaded = load(out)
    assert abs(reloaded.tempo - plan.target_tempo) < 1
    assert sum(len(t.notes) for t in reloaded.tracks) > 500


def test_all_templates_produce_output(tmp_path, demo_analysis, library):
    brain = RuleBasedBrain()
    for name in library.names():
        plan = brain.make_plan(demo_analysis, name, library)
        plan.template = name
        song = arrange(demo_analysis, plan, library)
        assert sum(len(t.notes) for t in song.tracks) > 100, name
        render_midi(song, tmp_path / f"{name}.mid")


def test_notes_within_midi_range(demo_analysis, library):
    plan = RuleBasedBrain().make_plan(demo_analysis, "dnb nhanh dồn dập", library)
    song = arrange(demo_analysis, plan, library)
    for track in song.tracks:
        for n in track.notes:
            assert 0 <= n.pitch <= 127
            assert 1 <= n.velocity <= 127
            assert n.start >= 0
