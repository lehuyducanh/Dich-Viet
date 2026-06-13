"""Command-line interface.

    python -m music_producer remix input.mid --theme "EDM sôi động, drop mạnh" -o out.mid
    python -m music_producer templates
    python -m music_producer analyze input.mid
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import analyze, arrange, describe, get_brain, load, render_audio, render_midi
from .arrangement import fit_duration
from .meter import to_four_four
from .orchestrator import get_orchestrator, merged_sound_design
from .template_library import TemplateLibrary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="music_producer",
        description="Simulate a professional music producer: basic MIDI/sheet in, produced track out.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_remix = sub.add_parser("remix", help="Produce a track from an input file and a theme brief")
    p_remix.add_argument("input", help="Input .mid/.midi/.xml/.musicxml/.mxl file")
    p_remix.add_argument("--theme", "-t", default=None,
                         help='Production brief, e.g. "EDM sôi động 128bpm, drop thật mạnh"')
    p_remix.add_argument("--plan", default=None,
                         help="Reuse a saved production plan JSON (skips the LLM entirely)")
    p_remix.add_argument("--save-plan", default=None,
                         help="Save the production plan as a reusable preset JSON")
    p_remix.add_argument("--output", "-o", default=None, help="Output MIDI path")
    p_remix.add_argument("--template", default=None, help="Force a specific template")
    p_remix.add_argument("--tempo", type=float, default=None, help="Force output BPM")
    p_remix.add_argument("--duration", type=float, default=None,
                         help="Target track length in seconds (arrangement is scaled to fit)")
    p_remix.add_argument("--no-llm", action="store_true",
                         help="Skip the LLM and use the rule-based planner")
    p_remix.add_argument("--audio", action="store_true",
                         help="Also bounce a .wav with the built-in synth engine (no DAW/soundfont needed)")
    p_remix.add_argument("--fluidsynth", action="store_true",
                         help="Bounce audio via fluidsynth + GM soundfont instead of the built-in engine")
    p_remix.add_argument("--stems", action="store_true",
                         help="Export each layer as its own .wav (for DAW finishing)")
    p_remix.add_argument("--orchestrate", action="store_true",
                         help="Use the LLM orchestration pass (instrument selection, mix)")
    p_remix.add_argument("--orch-plan", default=None,
                         help="Reuse a saved orchestration JSON (no LLM)")
    p_remix.add_argument("--save-orch", default=None,
                         help="Save the orchestration as a reusable preset JSON")
    p_remix.add_argument("--remeter", action="store_true",
                         help="Re-meter a 3/4 or 6/8 source into 4/4 before producing")
    p_remix.add_argument("--template-dir", action="append", default=[],
                         help="Extra directory of custom template JSON files")

    p_batch = sub.add_parser(
        "batch", help="Produce many tracks from one plan/theme (at most one LLM call total)")
    p_batch.add_argument("inputs", nargs="+", help="Input files")
    p_batch.add_argument("--theme", "-t", default=None, help="Brief (LLM/rules run once, on the first input)")
    p_batch.add_argument("--plan", default=None, help="Saved plan JSON to apply to every input (no LLM)")
    p_batch.add_argument("--save-plan", default=None, help="Save the plan created from --theme")
    p_batch.add_argument("--orch-plan", default=None, help="Saved orchestration JSON applied to every input")
    p_batch.add_argument("--output-dir", "-o", default="produced", help="Output directory")
    p_batch.add_argument("--no-llm", action="store_true")
    p_batch.add_argument("--audio", action="store_true", help="Also bounce WAVs (built-in engine)")
    p_batch.add_argument("--stems", action="store_true", help="Export per-layer stems for each track")
    p_batch.add_argument("--remeter", action="store_true", help="Re-meter 3/4 or 6/8 sources to 4/4")
    p_batch.add_argument("--duration", type=float, default=None)
    p_batch.add_argument("--template", default=None)
    p_batch.add_argument("--tempo", type=float, default=None)
    p_batch.add_argument("--template-dir", action="append", default=[])

    p_tpl = sub.add_parser("templates", help="List available genre templates")
    p_tpl.add_argument("--template-dir", action="append", default=[])

    p_an = sub.add_parser("analyze", help="Analyze an input file and print the findings")
    p_an.add_argument("input")

    args = parser.parse_args(argv)

    if args.command == "templates":
        library = TemplateLibrary(extra_dirs=[Path(d) for d in args.template_dir])
        for t in library.templates.values():
            print(f"{t.name:<12} {t.display_name:<28} {t.tempo_range[0]:.0f}-{t.tempo_range[1]:.0f} BPM")
            print(f"{'':<12} {t.description}")
        return 0

    if args.command == "analyze":
        analysis = analyze(load(args.input))
        print(f"Tempo:  {analysis.tempo:.1f} BPM")
        print(f"Time:   {analysis.time_signature[0]}/{analysis.time_signature[1]}")
        print(f"Key:    {analysis.key_name}")
        print(f"Length: {analysis.length_bars} bars")
        print(f"Chords: {' | '.join(analysis.chord_symbols())}")
        print(f"Melody: {len(analysis.melody)} notes")
        return 0

    library = TemplateLibrary(extra_dirs=[Path(d) for d in args.template_dir])

    if args.command == "batch":
        return _batch(args, library)

    # remix
    song = load(args.input)
    if args.remeter:
        song = to_four_four(song)
    analysis = analyze(song)
    print(f"[1/5] Analyzed input: {analysis.key_name}, {analysis.tempo:.0f} BPM, "
          f"{analysis.time_signature[0]}/{analysis.time_signature[1]}, "
          f"{analysis.length_bars} bars, chords {' | '.join(analysis.chord_symbols()[:8])} ...")

    plan = _resolve_plan(args, analysis, library, log=True)
    print("[3/5] Production plan:")
    print(describe(plan, library))

    orch = _resolve_orchestration(args, analysis, plan, log=True)

    out_song = arrange(analysis, plan, library, orch)
    output = Path(args.output) if args.output else Path(args.input).with_name(
        Path(args.input).stem + f".{plan.template}.produced.mid")
    render_midi(out_song, output)
    total_notes = sum(len(t.notes) for t in out_song.tracks)
    print(f"[5/5] Rendered {len(out_song.tracks)} tracks / {total_notes} notes -> {output}")

    sd = merged_sound_design(library.get(plan.template).sound_design, orch)
    if args.audio or args.fluidsynth:
        wav_path = output.with_suffix(".wav")
        if args.fluidsynth:
            wav = render_audio(output, wav_path)
            print(f"      Audio bounce (fluidsynth) -> {wav}" if wav
                  else "      fluidsynth bounce skipped (binary or GM soundfont not found)")
        else:
            from .synth_engine import render_wav
            render_wav(out_song, sd, wav_path)
            print(f"      Audio bounce (built-in synth engine) -> {wav_path}")
    if args.stems:
        from .synth_engine import render_stems
        stem_dir = output.with_suffix("")
        paths = render_stems(out_song, sd, stem_dir)
        print(f"      Stems ({len(paths)}) -> {stem_dir}/")
    return 0


def _resolve_orchestration(args, analysis, plan, log: bool = False):
    """Orchestration precedence: preset (--orch-plan) > LLM (--orchestrate)
    > free rule-based default (always on, improves quality at zero cost)."""
    from .plan_io import load_orchestration, save_orchestration

    if getattr(args, "orch_plan", None):
        orch = load_orchestration(args.orch_plan, plan)
        if log:
            print(f"[4/5] Orchestration: preset {args.orch_plan} (no LLM call)")
    else:
        use_llm = getattr(args, "orchestrate", False) and not getattr(args, "no_llm", False)
        orchestrator = get_orchestrator(use_llm=use_llm)
        orch = orchestrator.make_orchestration(analysis, plan, getattr(args, "theme", None) or "")
        if log:
            kind = type(orchestrator).__name__
            print(f"[4/5] Orchestration: {kind} | instruments "
                  + ", ".join(f"{k}={v}" for k, v in orch.instruments.items()))
    if getattr(args, "save_orch", None):
        save_orchestration(orch, args.save_orch)
        print(f"      Orchestration preset saved -> {args.save_orch}")
    return orch


def _resolve_plan(args, analysis, library: TemplateLibrary, log: bool = False):
    """Plan precedence: saved preset (--plan, zero LLM) > brain (--theme)."""
    from .plan_io import load_plan, save_plan

    if args.plan:
        plan = load_plan(args.plan, library)
        if log:
            print(f"[2/4] Producer brain: preset {args.plan} (no LLM call)")
    else:
        if not args.theme:
            raise SystemExit("error: provide --theme or --plan")
        brain = get_brain(use_llm=not args.no_llm)
        if log:
            print(f"[2/4] Producer brain: {type(brain).__name__}")
        theme = args.theme
        if args.duration:
            theme += f" (target track length: about {args.duration:.0f} seconds)"
        plan = brain.make_plan(analysis, theme, library)

    if args.template:
        plan.template = library.get(args.template).name
    if args.tempo:
        plan.target_tempo = library.get(plan.template).clamp_tempo(args.tempo)
    if args.duration:
        beats_per_bar = analysis.time_signature[0] * 4.0 / analysis.time_signature[1]
        fit_duration(plan, args.duration, beats_per_bar)
    if args.save_plan:
        save_plan(plan, args.save_plan)
        print(f"      Plan preset saved -> {args.save_plan}")
    return plan


def _batch(args, library: TemplateLibrary) -> int:
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    plan = None
    orch = None
    sd = None
    failures = 0
    for i, input_path in enumerate(args.inputs):
        try:
            song = load(input_path)
            if args.remeter:
                song = to_four_four(song)
            analysis = analyze(song)
            if plan is None:
                # one plan + one orchestration for the whole batch (≤1 LLM call each)
                plan = _resolve_plan(args, analysis, library)
                orch = _resolve_orchestration(args, analysis, plan)
                sd = merged_sound_design(library.get(plan.template).sound_design, orch)
                source = f"preset {args.plan}" if args.plan else "theme (single brain call)"
                print(f"Plan: {plan.title} [{plan.template}, {plan.target_tempo:.0f} BPM, "
                      f"{plan.total_bars} bars] ({source})")
            out_song = arrange(analysis, plan, library, orch)
            stem = Path(input_path).stem
            midi_path = out_dir / f"{stem}.{plan.template}.mid"
            render_midi(out_song, midi_path)
            line = f"[{i + 1}/{len(args.inputs)}] {input_path} -> {midi_path}"
            if args.audio:
                from .synth_engine import render_wav
                wav_path = midi_path.with_suffix(".wav")
                render_wav(out_song, sd, wav_path)
                line += f" + {wav_path.name}"
            if args.stems:
                from .synth_engine import render_stems
                render_stems(out_song, sd, out_dir / stem)
                line += " + stems"
            print(line)
        except Exception as exc:  # keep the batch moving
            failures += 1
            print(f"[{i + 1}/{len(args.inputs)}] {input_path} FAILED: {exc}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
