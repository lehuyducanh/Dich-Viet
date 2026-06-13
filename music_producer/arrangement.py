"""The arranger: executes a ProductionPlan against the template library,
assembling all layers section by section into a new Song."""

from __future__ import annotations

from . import generators as g
from .humanize import humanize
from .model import (Chord, Note, OrchestrationPlan, ProductionPlan, Song,
                    SongAnalysis, Track)
from .template_library import Template, TemplateLibrary
from .variation import gen_fill, transpose_notes

# channel assignment per layer (9 is reserved for drums by General MIDI)
_LAYER_CHANNELS = {"bass": 0, "pad": 1, "arp": 2, "melody": 3, "lead": 4, "fx": 5}
_PEAK_NAMES = ("drop", "chorus")


def arrange(analysis: SongAnalysis, plan: ProductionPlan, library: TemplateLibrary,
            orchestration: OrchestrationPlan | None = None) -> Song:
    template = library.get(plan.template)
    beats_per_bar = analysis.time_signature[0] * 4.0 / analysis.time_signature[1]
    orch = orchestration

    chords = [Chord(c.start, c.duration, (c.root + plan.transpose) % 12, c.quality)
              for c in analysis.chords]
    melody = [Note(n.pitch + plan.transpose, n.start, n.duration, n.velocity, n.channel)
              for n in analysis.melody]
    vary = bool(orch.melody_variation) if orch else False

    # the last peak section (final drop/chorus) optionally gets a key lift
    lift = orch.final_lift if orch else 0
    lift_idx = max((i for i, s in enumerate(plan.sections) if s.name in _PEAK_NAMES),
                   default=-1) if lift else -1

    song = Song(tempo=plan.target_tempo, time_signature=analysis.time_signature)
    tracks: dict[str, Track] = {}

    def track(layer: str) -> Track:
        if layer not in tracks:
            tracks[layer] = Track(
                name=layer,
                program=0 if layer == "drums" else template.instruments.get(layer, 80),
                channel=9 if layer == "drums" else _LAYER_CHANNELS.get(layer, 6),
                is_drums=(layer == "drums"),
            )
        return tracks[layer]

    cursor = 0.0
    automation: list[tuple[float, float, float]] = []
    for idx, section in enumerate(plan.sections):
        section_energy = section.energy * (0.6 + 0.4 * plan.energy)
        is_build = section.name == "build"
        level = "build" if is_build else g.level_for_energy(section_energy)
        next_section = plan.sections[idx + 1] if idx + 1 < len(plan.sections) else None
        next_is_peak = next_section is not None and next_section.energy >= 0.85

        sec_chords, sec_melody, sec_key = chords, melody, (analysis.key_root + plan.transpose) % 12
        if idx == lift_idx:  # final-drop key lift
            sec_chords = [Chord(c.start, c.duration, (c.root + lift) % 12, c.quality) for c in chords]
            sec_melody = transpose_notes(melody, lift)
            sec_key = (sec_key + lift) % 12

        # filter automation: from orchestration if present, else energy-derived;
        # builds ramp upward across the section
        if orch and idx < len(orch.section_filter):
            bright = orch.section_filter[idx]
        else:
            bright = min(1.0, 0.25 + 0.75 * section.energy)
        sec_start, sec_end = cursor, cursor + section.bars * beats_per_bar
        if is_build:
            automation.append((sec_start, sec_end, ("ramp", max(0.2, bright - 0.5), bright)))
        else:
            automation.append((sec_start, sec_end, ("flat", bright, bright)))

        for layer in section.layers:
            if layer == "drums":
                notes = g.gen_drums(template, level, section.bars, beats_per_bar,
                                    section_energy, is_build=is_build, next_is_peak=next_is_peak)
            elif layer == "bass":
                style = template.bass_style.get(level, "sustained_roots")
                notes = g.gen_bass(style, sec_chords, cursor, section.bars, beats_per_bar, section_energy)
            elif layer == "pad":
                notes = g.gen_pad(sec_chords, cursor, section.bars, beats_per_bar, section_energy)
            elif layer == "arp":
                notes = g.gen_arp(template.arp_style, sec_chords, cursor, section.bars,
                                  beats_per_bar, section_energy)
            elif layer == "melody":
                notes = g.gen_melody(sec_melody, section.bars, beats_per_bar, section_energy,
                                     vary=vary, key_mode=analysis.key_mode)
            elif layer == "lead":
                notes = g.gen_melody(sec_melody, section.bars, beats_per_bar, section_energy,
                                     octave_shift=1, vary=vary, key_mode=analysis.key_mode)
            elif layer == "fx":
                notes = g.gen_fx(section.bars, beats_per_bar, section_energy, sec_key)
            else:
                continue

            t = track(layer)
            for n in notes:
                t.notes.append(Note(n.pitch, n.start + cursor, n.duration, n.velocity, t.channel))

        cursor += section.bars * beats_per_bar

    if orch and orch.fills_every and "drums" in tracks:
        _inject_fills(tracks["drums"], plan, beats_per_bar, orch.fills_every)

    for t in tracks.values():
        t.notes.sort(key=lambda n: n.start)
        humanize(t, swing=template.swing)
        song.tracks.append(t)

    song.automation = automation
    if orch:
        song.master_lufs = orch.master_lufs
    return song


def _inject_fills(drums: Track, plan: ProductionPlan, beats_per_bar: float, every: int) -> None:
    """Add a drum fill on the last bar of every `every`-bar phrase block,
    skipping bars that already lead into a peak (those carry their own fill)."""
    # bars that precede a peak section already get a snare fill in gen_drums
    skip_bars: set[int] = set()
    bar = 0
    for i, s in enumerate(plan.sections):
        nxt = plan.sections[i + 1] if i + 1 < len(plan.sections) else None
        if nxt is not None and nxt.energy >= 0.85:
            skip_bars.add(bar + s.bars - 1)
        bar += s.bars
    total = plan.total_bars
    for gbar in range(every - 1, total, every):
        if gbar in skip_bars or gbar >= total:
            continue
        kind = "snare" if (gbar // every) % 2 == 1 else "tom"
        energy = 0.8
        for n in gen_fill(beats_per_bar, energy, kind):
            drums.notes.append(Note(n.pitch, gbar * beats_per_bar + n.start,
                                    n.duration, n.velocity, 9))


def fit_duration(plan: ProductionPlan, seconds: float, beats_per_bar: float = 4.0) -> ProductionPlan:
    """Stretch/shrink the arrangement so the track lasts ~`seconds` at the
    plan's tempo. Sections scale proportionally in 2-bar steps; rounding
    drift lands on the longest sections (the drops), like a real edit."""
    target_bars = max(8, round(seconds * plan.target_tempo / 60.0 / beats_per_bar / 2) * 2)
    if not plan.sections or plan.total_bars == 0:
        return plan
    ratio = target_bars / plan.total_bars
    for s in plan.sections:
        s.bars = max(2, round(s.bars * ratio / 2) * 2)

    for _ in range(64):  # settle rounding drift, 2 bars at a time
        diff = target_bars - plan.total_bars
        if diff == 0:
            break
        step = 2 if diff > 0 else -2
        for s in sorted(plan.sections, key=lambda s: -s.bars):
            if s.bars + step >= 2:
                s.bars += step
                break
    return plan


def describe(plan: ProductionPlan, library: TemplateLibrary) -> str:
    """Human-readable summary of the plan, printed by the CLI."""
    template = library.get(plan.template)
    lines = [
        f"Title:    {plan.title}",
        f"Template: {template.display_name} ({plan.template})",
        f"Tempo:    {plan.target_tempo:.0f} BPM | transpose {plan.transpose:+d} st | energy {plan.energy:.2f}",
        f"Length:   {plan.total_bars} bars",
        "Arrangement:",
    ]
    bar = 1
    for s in plan.sections:
        lines.append(f"  bar {bar:>3}-{bar + s.bars - 1:<3} {s.name:<10} energy {s.energy:.2f}  [{', '.join(s.layers)}]")
        bar += s.bars
    if plan.notes:
        lines.append(f"Producer notes: {plan.notes}")
    return "\n".join(lines)
