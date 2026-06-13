"""Tests for the orchestration layer, variation engine, mix/stems, and meter."""

import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from music_producer import analyze, arrange  # noqa: E402
from music_producer.model import Note, Song, Track  # noqa: E402
from music_producer.producer_brain import RuleBasedBrain  # noqa: E402
from music_producer.template_library import TemplateLibrary  # noqa: E402
from music_producer import instruments as inst  # noqa: E402
from music_producer.orchestrator import (RuleBasedOrchestrator, merged_sound_design,  # noqa: E402
                                         orch_from_dict)
from music_producer.variation import transpose_notes, vary_melody_loop  # noqa: E402
from music_producer.meter import to_four_four  # noqa: E402


@pytest.fixture(scope="module")
def library():
    return TemplateLibrary()


def _demo():
    from examples.make_happy_birthday import build
    return analyze(build())


# --- catalog & orchestrator -----------------------------------------------------

def test_catalog_has_options_per_layer():
    for layer in ("bass", "pad", "arp", "melody", "lead", "fx"):
        assert inst.options_for(layer), layer
        # default must be a real option
        assert inst.DEFAULT_INSTRUMENT[layer] in inst.options_for(layer)


def test_rule_based_orchestration_valid(library):
    analysis = _demo()
    plan = RuleBasedBrain().make_plan(analysis, "edm sôi động", library)
    orch = RuleBasedOrchestrator().make_orchestration(analysis, plan, "edm sôi động")
    # one instrument per layer, each a real catalog entry
    for layer, name in orch.instruments.items():
        assert name in inst.options_for(layer)
    # a brightness value per section
    assert len(orch.section_filter) == len(plan.sections)
    assert all(0.0 <= b <= 1.0 for b in orch.section_filter)
    assert orch.fills_every in (4, 8, 16)


def test_orch_from_dict_clamps_and_fills(library):
    analysis = _demo()
    plan = RuleBasedBrain().make_plan(analysis, "edm", library)
    raw = {
        "instruments": {"bass": "not_a_real_bass", "lead": "square_lead"},
        "section_filter": [0.5, 2.0],          # too few + out of range
        "fills_every": 7,                       # invalid -> 8
        "final_lift": 99,                       # clamp -> 4
        "melody_variation": True,
        "master_lufs": -50,                     # clamp
        "notes": "x",
    }
    orch = orch_from_dict(raw, plan)
    assert orch.instruments["bass"] in inst.options_for("bass")  # fell back
    assert orch.instruments["lead"] == "square_lead"             # honored
    assert len(orch.section_filter) == len(plan.sections)        # padded
    assert all(0.0 <= b <= 1.0 for b in orch.section_filter)
    assert orch.fills_every == 8
    assert orch.final_lift == 4
    assert orch.master_lufs >= -20.0


def test_merged_sound_design_applies_instrument(library):
    analysis = _demo()
    plan = RuleBasedBrain().make_plan(analysis, "edm", library)
    orch = RuleBasedOrchestrator().make_orchestration(analysis, plan, "edm")
    orch.instruments["bass"] = "808"
    sd = merged_sound_design(library.get("edm").sound_design, orch)
    # the 808 patch override (sine sub) is now in the bass sound design
    assert sd["bass"]["osc"] == "sine"
    assert sd["bass"]["sub"] is True


# --- variation engine -----------------------------------------------------------

def test_melody_variation_changes_later_repeats():
    loop = [Note(60, 0.0, 1.0, 96), Note(62, 1.0, 1.0, 96),
            Note(64, 2.0, 1.0, 96), Note(67, 3.0, 1.0, 96)]
    base = vary_melody_loop(loop, 0, "major")
    assert [n.pitch for n in base] == [60, 62, 64, 67]   # iteration 0 = verbatim
    varied = vary_melody_loop(loop, 1, "major")
    assert [n.pitch for n in varied] != [60, 62, 64, 67]  # later repeat differs


def test_transpose_notes_clamps():
    notes = [Note(60, 0, 1, 96), Note(125, 0, 1, 96)]
    out = transpose_notes(notes, 5)
    assert out[0].pitch == 65
    assert out[1].pitch == 127  # clamped


def test_fills_add_drum_notes(library):
    analysis = _demo()
    plan = RuleBasedBrain().make_plan(analysis, "edm", library)
    orch = RuleBasedOrchestrator().make_orchestration(analysis, plan, "edm")

    orch.fills_every = 0
    no_fills = arrange(analysis, plan, library, orch)
    orch.fills_every = 8
    with_fills = arrange(analysis, plan, library, orch)

    def drum_count(song):
        return sum(len(t.notes) for t in song.tracks if t.is_drums)

    assert drum_count(with_fills) > drum_count(no_fills)


def test_final_lift_transposes_last_drop(library):
    analysis = _demo()
    plan = RuleBasedBrain().make_plan(analysis, "edm", library)
    orch = RuleBasedOrchestrator().make_orchestration(analysis, plan, "edm")
    orch.melody_variation = False

    orch.final_lift = 0
    flat = arrange(analysis, plan, library, orch)
    orch.final_lift = 2
    lifted = arrange(analysis, plan, library, orch)

    # compare the bass notes in the final section window
    bpb = 4.0
    last_start = (plan.total_bars - plan.sections[-1].bars) * bpb
    # the final section is the outro; use the last 'drop' instead
    def bass_pitches(song, lo, hi):
        return sorted(n.pitch for t in song.tracks if t.name == "bass"
                      for n in t.notes if lo <= n.start < hi)

    # find last drop window
    bar = 0
    drop_lo = drop_hi = None
    for s in plan.sections:
        if s.name == "drop":
            drop_lo, drop_hi = bar * bpb, (bar + s.bars) * bpb
        bar += s.bars
    flat_p = bass_pitches(flat, drop_lo, drop_hi)
    lifted_p = bass_pitches(lifted, drop_lo, drop_hi)
    assert flat_p and lifted_p
    assert flat_p != lifted_p  # the last drop was transposed


def test_arrange_sets_automation(library):
    analysis = _demo()
    plan = RuleBasedBrain().make_plan(analysis, "edm", library)
    orch = RuleBasedOrchestrator().make_orchestration(analysis, plan, "edm")
    song = arrange(analysis, plan, library, orch)
    assert song.automation                      # filter automation segments present
    assert len(song.automation) == len(plan.sections)
    assert song.master_lufs == orch.master_lufs


# --- meter handling -------------------------------------------------------------

def test_remeter_three_four_to_four_four():
    song = Song(tempo=120.0, time_signature=(3, 4))
    t = Track(name="m")
    t.add(60, 0.0, 1.0, 96)
    t.add(62, 3.0, 1.0, 96)   # start of bar 2 in 3/4
    song.tracks = [t]
    out = to_four_four(song)
    assert out.time_signature == (4, 4)
    # bar-2 downbeat (beat 3 in 3/4) maps to beat 4 in 4/4 (scale 4/3)
    assert out.tracks[0].notes[1].start == pytest.approx(4.0)


def test_remeter_noop_on_four_four():
    song = Song(tempo=120.0, time_signature=(4, 4))
    assert to_four_four(song) is song


# --- stems ----------------------------------------------------------------------

def test_render_stems(tmp_path, library):
    from music_producer.synth_engine import render_stems

    analysis = _demo()
    plan = RuleBasedBrain().make_plan(analysis, "edm", library)
    plan.sections = plan.sections[:1]
    plan.sections[0].bars = 2
    orch = RuleBasedOrchestrator().make_orchestration(analysis, plan, "edm")
    orch.section_filter = orch.section_filter[:1]
    song = arrange(analysis, plan, library, orch)

    sd = merged_sound_design(library.get("edm").sound_design, orch)
    paths = render_stems(song, sd, tmp_path / "stems")
    assert len(paths) == len(song.tracks)
    for p in paths:
        assert p.exists()
        with wave.open(str(p)) as w:
            assert w.getnchannels() == 2
            assert w.getnframes() > 0


def test_orchestration_preset_roundtrip(tmp_path, library):
    from music_producer.plan_io import load_orchestration, save_orchestration

    analysis = _demo()
    plan = RuleBasedBrain().make_plan(analysis, "edm", library)
    orch = RuleBasedOrchestrator().make_orchestration(analysis, plan, "edm")
    orch.instruments["lead"] = "square_lead"
    orch.final_lift = 2

    p = tmp_path / "orch.json"
    save_orchestration(orch, p)
    loaded = load_orchestration(p, plan)
    assert loaded.instruments["lead"] == "square_lead"
    assert loaded.final_lift == 2
    assert len(loaded.section_filter) == len(plan.sections)
