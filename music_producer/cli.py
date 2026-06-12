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
    p_remix.add_argument("--template-dir", action="append", default=[],
                         help="Extra directory of custom template JSON files")

    p_batch = sub.add_parser(
        "batch", help="Produce many tracks from one plan/theme (at most one LLM call total)")
    p_batch.add_argument("inputs", nargs="+", help="Input files")
    p_batch.add_argument("--theme", "-t", default=None, help="Brief (LLM/rules run once, on the first input)")
    p_batch.add_argument("--plan", default=None, help="Saved plan JSON to apply to every input (no LLM)")
    p_batch.add_argument("--save-plan", default=None, help="Save the plan created from --theme")
    p_batch.add_argument("--output-dir", "-o", default="produced", help="Output directory")
    p_batch.add_argument("--no-llm", action="store_true")
    p_batch.add_argument("--audio", action="store_true", help="Also bounce WAVs (built-in engine)")
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
    analysis = analyze(song)
    print(f"[1/4] Analyzed input: {analysis.key_name}, {analysis.tempo:.0f} BPM, "
          f"{analysis.length_bars} bars, chords {' | '.join(analysis.chord_symbols()[:8])} ...")

    plan = _resolve_plan(args, analysis, library, log=True)
    print("[3/4] Production plan:")
    print(describe(plan, library))

    out_song = arrange(analysis, plan, library)
    output = Path(args.output) if args.output else Path(args.input).with_name(
        Path(args.input).stem + f".{plan.template}.produced.mid")
    render_midi(out_song, output)
    total_notes = sum(len(t.notes) for t in out_song.tracks)
    print(f"[4/4] Rendered {len(out_song.tracks)} tracks / {total_notes} notes -> {output}")

    if args.audio or args.fluidsynth:
        wav_path = output.with_suffix(".wav")
        if args.fluidsynth:
            wav = render_audio(output, wav_path)
            if wav:
                print(f"      Audio bounce (fluidsynth) -> {wav}")
            else:
                print("      fluidsynth bounce skipped (binary or GM soundfont not found)")
        else:
            from .synth_engine import render_wav
            template = library.get(plan.template)
            render_wav(out_song, template.sound_design, wav_path)
            print(f"      Audio bounce (built-in synth engine) -> {wav_path}")
    return 0


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
    failures = 0
    for i, input_path in enumerate(args.inputs):
        try:
            song = load(input_path)
            analysis = analyze(song)
            if plan is None:
                # one plan for the whole batch: preset file, or one brain call
                plan = _resolve_plan(args, analysis, library)
                source = f"preset {args.plan}" if args.plan else "theme (single brain call)"
                print(f"Plan: {plan.title} [{plan.template}, {plan.target_tempo:.0f} BPM, "
                      f"{plan.total_bars} bars] ({source})")
            out_song = arrange(analysis, plan, library)
            stem = Path(input_path).stem
            midi_path = out_dir / f"{stem}.{plan.template}.mid"
            render_midi(out_song, midi_path)
            line = f"[{i + 1}/{len(args.inputs)}] {input_path} -> {midi_path}"
            if args.audio:
                from .synth_engine import render_wav
                wav_path = midi_path.with_suffix(".wav")
                render_wav(out_song, library.get(plan.template).sound_design, wav_path)
                line += f" + {wav_path.name}"
            print(line)
        except Exception as exc:  # keep the batch moving
            failures += 1
            print(f"[{i + 1}/{len(args.inputs)}] {input_path} FAILED: {exc}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
