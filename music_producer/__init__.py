"""Music Producer Simulator — turn a basic MIDI/sheet into a fully produced track.

Pipeline:
    load -> analyze -> brain.make_plan (LLM or rules) -> arrange -> render_midi
"""

from .analysis import analyze
from .arrangement import arrange, describe
from .midi_io import load
from .model import ProductionPlan, Song, SongAnalysis
from .producer_brain import LLMProducerBrain, RuleBasedBrain, get_brain
from .renderer import render_audio, render_midi
from .template_library import TemplateLibrary

__version__ = "0.1.0"

__all__ = [
    "load", "analyze", "arrange", "describe", "render_midi", "render_audio",
    "TemplateLibrary", "get_brain", "LLMProducerBrain", "RuleBasedBrain",
    "Song", "SongAnalysis", "ProductionPlan", "produce",
]


def produce(input_path, theme: str, output_path, use_llm: bool = True,
            template: str | None = None, tempo: float | None = None,
            duration: float | None = None, template_dirs=None, audio_path=None,
            orchestrate_llm: bool = False, stems_dir=None, remeter: bool = False):
    """One-call API: produce a track from an input file and a theme brief.

    Two reasoning passes: the producer brain (structure) and the orchestration
    brain (instruments, variation, mix). The orchestration always runs — free
    rule-based by default, LLM only when orchestrate_llm=True. Pass audio_path
    to bounce a WAV, stems_dir to export per-layer WAVs, duration (seconds) to
    fit a length, remeter=True to convert a 3/4 source to 4/4.
    Returns (analysis, plan, orchestration, output_song).
    """
    from .arrangement import fit_duration
    from .meter import to_four_four
    from .orchestrator import get_orchestrator, merged_sound_design

    library = TemplateLibrary(extra_dirs=template_dirs)
    song = load(input_path)
    if remeter:
        song = to_four_four(song)
    analysis = analyze(song)

    brain = get_brain(use_llm=use_llm)
    if duration:
        theme += f" (target track length: about {duration:.0f} seconds)"
    plan = brain.make_plan(analysis, theme, library)
    if template:
        plan.template = library.get(template).name
    if tempo:
        plan.target_tempo = library.get(plan.template).clamp_tempo(tempo)
    if duration:
        beats_per_bar = analysis.time_signature[0] * 4.0 / analysis.time_signature[1]
        fit_duration(plan, duration, beats_per_bar)

    orchestrator = get_orchestrator(use_llm=use_llm and orchestrate_llm)
    orch = orchestrator.make_orchestration(analysis, plan, theme)

    out = arrange(analysis, plan, library, orch)
    render_midi(out, output_path)

    if audio_path or stems_dir:
        from .synth_engine import render_stems, render_wav
        sd = merged_sound_design(library.get(plan.template).sound_design, orch)
        if audio_path:
            render_wav(out, sd, audio_path)
        if stems_dir:
            render_stems(out, sd, stems_dir)
    return analysis, plan, orch, out
