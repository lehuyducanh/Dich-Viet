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
            template_dirs=None, audio_path=None):
    """One-call API: produce a track from an input file and a theme brief.

    Pass audio_path to also bounce a WAV with the built-in synth engine.
    Returns (analysis, plan, output_song).
    """
    library = TemplateLibrary(extra_dirs=template_dirs)
    song = load(input_path)
    analysis = analyze(song)
    brain = get_brain(use_llm=use_llm)
    plan = brain.make_plan(analysis, theme, library)
    if template:
        plan.template = library.get(template).name
    if tempo:
        plan.target_tempo = library.get(plan.template).clamp_tempo(tempo)
    out = arrange(analysis, plan, library)
    render_midi(out, output_path)
    if audio_path:
        from .synth_engine import render_wav
        render_wav(out, library.get(plan.template).sound_design, audio_path)
    return analysis, plan, out
