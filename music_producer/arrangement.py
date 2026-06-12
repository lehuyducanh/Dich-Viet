"""The arranger: executes a ProductionPlan against the template library,
assembling all layers section by section into a new Song."""

from __future__ import annotations

from . import generators as g
from .humanize import humanize
from .model import Chord, Note, ProductionPlan, Song, SongAnalysis, Track
from .template_library import Template, TemplateLibrary

# channel assignment per layer (9 is reserved for drums by General MIDI)
_LAYER_CHANNELS = {"bass": 0, "pad": 1, "arp": 2, "melody": 3, "lead": 4, "fx": 5}


def arrange(analysis: SongAnalysis, plan: ProductionPlan, library: TemplateLibrary) -> Song:
    template = library.get(plan.template)
    beats_per_bar = analysis.time_signature[0] * 4.0 / analysis.time_signature[1]

    chords = [Chord(c.start, c.duration, (c.root + plan.transpose) % 12, c.quality)
              for c in analysis.chords]
    melody = [Note(n.pitch + plan.transpose, n.start, n.duration, n.velocity, n.channel)
              for n in analysis.melody]

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
    for idx, section in enumerate(plan.sections):
        section_energy = section.energy * (0.6 + 0.4 * plan.energy)
        is_build = section.name == "build"
        level = "build" if is_build else g.level_for_energy(section_energy)
        next_section = plan.sections[idx + 1] if idx + 1 < len(plan.sections) else None
        next_is_peak = next_section is not None and next_section.energy >= 0.85

        for layer in section.layers:
            if layer == "drums":
                notes = g.gen_drums(template, level, section.bars, beats_per_bar,
                                    section_energy, is_build=is_build, next_is_peak=next_is_peak)
            elif layer == "bass":
                style = template.bass_style.get(level, "sustained_roots")
                notes = g.gen_bass(style, chords, cursor, section.bars, beats_per_bar, section_energy)
            elif layer == "pad":
                notes = g.gen_pad(chords, cursor, section.bars, beats_per_bar, section_energy)
            elif layer == "arp":
                notes = g.gen_arp(template.arp_style, chords, cursor, section.bars,
                                  beats_per_bar, section_energy)
            elif layer == "melody":
                notes = g.gen_melody(melody, section.bars, beats_per_bar, section_energy)
            elif layer == "lead":
                notes = g.gen_melody(melody, section.bars, beats_per_bar, section_energy,
                                     octave_shift=1)
            elif layer == "fx":
                notes = g.gen_fx(section.bars, beats_per_bar, section_energy,
                                 (analysis.key_root + plan.transpose) % 12)
            else:
                continue

            t = track(layer)
            for n in notes:
                t.notes.append(Note(n.pitch, n.start + cursor, n.duration, n.velocity, t.channel))

        cursor += section.bars * beats_per_bar

    for t in tracks.values():
        t.notes.sort(key=lambda n: n.start)
        humanize(t, swing=template.swing)
        song.tracks.append(t)
    return song


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
