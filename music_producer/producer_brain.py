"""The producer brain: turns (song analysis + user theme) into a ProductionPlan.

Two implementations:
  - LLMProducerBrain: Claude with structured JSON output. The model acts as a
    professional music producer reading a lead sheet plus the client brief.
  - RuleBasedBrain:   offline fallback (no API key / --no-llm) using keyword
    matching against the template catalog and template defaults.
"""

from __future__ import annotations

import json
import os
import re

from .model import PlanSection, ProductionPlan, SongAnalysis
from .template_library import LAYERS, SECTION_NAMES, Template, TemplateLibrary

MODEL = "claude-opus-4-8"

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "template": {"type": "string", "description": "Template name from the catalog, exactly as listed"},
        "target_tempo": {"type": "number", "description": "Output BPM, within the chosen template's range"},
        "transpose": {"type": "integer", "description": "Semitones to transpose the harmonic material, -11..11. 0 keeps the original key."},
        "energy": {"type": "number", "description": "Overall track energy 0.0-1.0"},
        "title": {"type": "string"},
        "notes": {"type": "string", "description": "Short producer rationale: why this template/arrangement fits the brief"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "enum": list(SECTION_NAMES)},
                    "bars": {"type": "integer"},
                    "energy": {"type": "number"},
                    "layers": {"type": "array", "items": {"type": "string", "enum": list(LAYERS)}},
                },
                "required": ["name", "bars", "energy", "layers"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["template", "target_tempo", "transpose", "energy", "title", "notes", "sections"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You are a professional music producer. You receive (1) an analysis of a client's \
basic demo track (key, tempo, chord progression, melody summary) and (2) the \
client's brief describing the vibe they want. You must design a full production \
plan using one genre template from the studio's library.

Guidelines:
- Choose the template whose genre best matches the brief (the brief may be in \
Vietnamese or English).
- Respect the template's tempo range. If the brief names a BPM, honor it when plausible.
- Design a complete arrangement (typically 56-80 bars) with a dramatic arc: \
intro -> verse -> build -> drop/chorus -> breakdown -> build -> drop/chorus -> outro. \
Section bar counts should be multiples of 4.
- 'energy' per section drives drum intensity and velocities (0.0 quiet .. 1.0 peak). \
Builds should sit just below the following drop.
- Layers available: drums, bass, pad, arp, melody, lead, fx. 'melody' replays the \
client's original melody; 'lead' doubles it an octave up for drops/choruses; 'fx' \
adds risers (use it on build sections). Strip layers down in intros/breakdowns.
- 'transpose' shifts the song's key if a different register suits the genre \
(e.g. trap often sits lower). Usually 0.
- Keep 'notes' to 2-3 sentences, in the language of the brief."""


class LLMProducerBrain:
    def __init__(self, model: str = MODEL):
        import anthropic  # imported lazily so offline use never requires the SDK
        self.client = anthropic.Anthropic()
        self.model = model

    def make_plan(self, analysis: SongAnalysis, theme: str, library: TemplateLibrary) -> ProductionPlan:
        user_prompt = (
            f"## Client demo analysis\n"
            f"- Key: {analysis.key_name}\n"
            f"- Original tempo: {analysis.tempo:.0f} BPM\n"
            f"- Time signature: {analysis.time_signature[0]}/{analysis.time_signature[1]}\n"
            f"- Length: {analysis.length_bars} bars\n"
            f"- Chord progression (per bar): {' | '.join(analysis.chord_symbols()[:32])}\n"
            f"- Melody: {len(analysis.melody)} notes, range "
            f"{min((n.pitch for n in analysis.melody), default=0)}-{max((n.pitch for n in analysis.melody), default=0)} (MIDI)\n\n"
            f"## Studio template library\n{library.catalog_for_llm()}\n\n"
            f"## Client brief\n{theme}\n\n"
            f"Produce the production plan as JSON."
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            output_config={"format": {"type": "json_schema", "schema": PLAN_SCHEMA}},
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("LLM declined the request; rerun with --no-llm for the rule-based fallback")
        text = next(b.text for b in response.content if b.type == "text")
        return _plan_from_dict(json.loads(text), library)


class RuleBasedBrain:
    """Keyword-matching fallback so the pipeline works without an API key."""

    KEYWORDS = {
        "edm": ["edm", "festival", "big room", "sôi động", "soi dong", "bốc", "party",
                "energetic", "electro", "rave", "quẩy", "quay"],
        "house": ["house", "deep", "club", "groove", "groovy", "dance", "disco"],
        "trap": ["trap", "hiphop", "hip hop", "hip-hop", "808", "rap", "drill", "dark"],
        "lofi": ["lofi", "lo-fi", "chill", "study", "relax", "thư giãn", "thu gian", "nhẹ nhàng", "nhe nhang"],
        "synthwave": ["synthwave", "retro", "80s", "retrowave", "vaporwave", "night drive", "hoài niệm", "hoai niem"],
        "dnb": ["dnb", "drum and bass", "drum & bass", "jungle", "liquid", "nhanh", "dồn dập", "don dap"],
    }

    def make_plan(self, analysis: SongAnalysis, theme: str, library: TemplateLibrary) -> ProductionPlan:
        theme_lower = theme.lower()
        scores = {name: sum(1 for kw in kws if kw in theme_lower)
                  for name, kws in self.KEYWORDS.items() if name in library.templates}
        template_name = max(scores, key=scores.get) if any(scores.values()) else "edm"
        if template_name not in library.templates:
            template_name = library.names()[0]
        template = library.get(template_name)

        bpm_match = re.search(r"(\d{2,3})\s*bpm", theme_lower)
        tempo = template.clamp_tempo(float(bpm_match.group(1))) if bpm_match else template.default_tempo

        sections = [
            PlanSection(name=s["section"], bars=s["bars"], energy=s["energy"], layers=list(s["layers"]))
            for s in template.default_arrangement
        ]
        return ProductionPlan(
            template=template.name,
            target_tempo=tempo,
            transpose=0,
            energy=template.default_energy,
            sections=sections,
            title=f"{template.display_name} Remix",
            notes=f"Rule-based fallback: matched template '{template.name}' from the theme keywords.",
        )


def _plan_from_dict(raw: dict, library: TemplateLibrary) -> ProductionPlan:
    """Validate and coerce the LLM output; fall back to template defaults per field."""
    name = raw.get("template", "")
    if name not in library.templates:
        name = library.names()[0]
    template = library.get(name)

    sections: list[PlanSection] = []
    for s in raw.get("sections", []):
        bars = max(1, min(64, int(s["bars"])))
        layers = [layer for layer in s["layers"] if layer in LAYERS]
        if not layers:
            continue
        sections.append(PlanSection(
            name=s["name"] if s["name"] in SECTION_NAMES else "verse",
            bars=bars,
            energy=min(1.0, max(0.0, float(s["energy"]))),
            layers=layers,
        ))
    if not sections:
        sections = [PlanSection(s["section"], s["bars"], s["energy"], list(s["layers"]))
                    for s in template.default_arrangement]

    return ProductionPlan(
        template=template.name,
        target_tempo=template.clamp_tempo(float(raw.get("target_tempo", template.default_tempo))),
        transpose=max(-11, min(11, int(raw.get("transpose", 0)))),
        energy=min(1.0, max(0.0, float(raw.get("energy", template.default_energy)))),
        sections=sections,
        title=raw.get("title", "Untitled"),
        notes=raw.get("notes", ""),
    )


def get_brain(use_llm: bool = True, model: str = MODEL):
    if use_llm and (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        try:
            return LLMProducerBrain(model=model)
        except Exception:
            pass
    return RuleBasedBrain()
