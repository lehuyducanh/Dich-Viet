"""The orchestration brain — the SECOND reasoning pass.

The first pass (producer_brain) decides the macro structure: genre, tempo,
arrangement arc, which layers play in each section. This pass decides the
micro craft a real producer obsesses over once the skeleton exists:

  - which specific instrument voices each layer (sound selection)
  - how bright/open each section is (filter automation over time)
  - drum-fill cadence, melody variation, a final key lift for the last drop
  - the loudness target for the master

Like the production plan, the orchestration plan is a small JSON document —
one LLM call, then cache and reuse it across as many tracks as you like.
"""

from __future__ import annotations

import json
import os

from . import instruments as inst
from .model import OrchestrationPlan, ProductionPlan, SongAnalysis

MODEL = "claude-opus-4-8"

ORCH_SCHEMA = {
    "type": "object",
    "properties": {
        "instruments": {
            "type": "object",
            "description": "Map each layer (bass, pad, arp, melody, lead, fx) to ONE "
                           "instrument name from the menu for that layer.",
            "properties": {layer: {"type": "string"} for layer in inst.LAYER_ROLE},
            "additionalProperties": False,
        },
        "section_filter": {
            "type": "array",
            "description": "Brightness/filter-open 0.0-1.0 for each section in order "
                           "(0 = dark/closed, 1 = fully open). Builds should ramp up, "
                           "drops sit near 1.0, breakdowns lower.",
            "items": {"type": "number"},
        },
        "fills_every": {"type": "integer", "description": "Drum-fill cadence in bars (4/8/16; 0 = off)"},
        "final_lift": {"type": "integer", "description": "Semitone key change on the last peak section, 0-4"},
        "melody_variation": {"type": "boolean", "description": "Vary the melody between repeats"},
        "master_lufs": {"type": "number", "description": "Master loudness target, approx LUFS (-8 loud .. -16 soft)"},
        "notes": {"type": "string", "description": "2-3 sentences on the sound-selection rationale"},
    },
    "required": ["instruments", "section_filter", "fills_every", "final_lift",
                 "melody_variation", "master_lufs", "notes"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You are a professional music producer doing the orchestration and mix pass. The \
arrangement (sections, layers, tempo, genre) is already decided. Your job is the \
craft that separates a demo from a release:

- Sound selection: pick ONE instrument per layer from the provided menu so the \
palette is cohesive and fits the genre and brief. Avoid two instruments fighting \
for the same frequency range (e.g. a bright lead over a bright arp).
- Filter automation: give each section a brightness 0.0-1.0. Tell the story over \
time — dark/filtered intros and breakdowns, builds RAMPING up toward the next \
drop, drops near 1.0. The list length MUST equal the number of sections.
- Drum fills every 8 bars is standard (4 for busy genres, 16 for sparse).
- A final_lift of 1-2 semitones on the last drop/chorus is a classic lift; use 0 \
to keep it grounded.
- master_lufs: modern club/EDM ≈ -9, pop ≈ -11, lofi/chill ≈ -14.
Keep choices musical and genre-appropriate. Respond as JSON."""


class LLMOrchestratorBrain:
    def __init__(self, model: str = MODEL):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = model

    def make_orchestration(self, analysis: SongAnalysis, plan: ProductionPlan,
                           theme: str) -> OrchestrationPlan:
        section_lines = "\n".join(
            f"  {i}. {s.name} ({s.bars} bars, energy {s.energy:.2f}, layers: {', '.join(s.layers)})"
            for i, s in enumerate(plan.sections)
        )
        user_prompt = (
            f"## Track\n{plan.title} — genre {plan.template}, {plan.target_tempo:.0f} BPM, "
            f"key {analysis.key_name}, {len(plan.sections)} sections / {plan.total_bars} bars.\n\n"
            f"## Sections (in order)\n{section_lines}\n\n"
            f"## Instrument menu (pick one per layer)\n{inst.catalog_for_llm()}\n\n"
            f"## Client brief\n{theme}\n\n"
            f"Design the orchestration & mix as JSON. section_filter must have "
            f"exactly {len(plan.sections)} numbers."
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            output_config={"format": {"type": "json_schema", "schema": ORCH_SCHEMA}},
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("LLM declined; rerun without --orchestrate for the rule-based default")
        text = next(b.text for b in response.content if b.type == "text")
        return orch_from_dict(json.loads(text), plan)


class RuleBasedOrchestrator:
    """Genre-aware defaults — no API key needed. Instruments come from the
    template's sound_design hints (falling back to the catalog defaults), and
    the filter curve is derived from each section's planned energy."""

    def make_orchestration(self, analysis: SongAnalysis, plan: ProductionPlan,
                           theme: str, template=None) -> OrchestrationPlan:
        instruments = {}
        for layer in inst.LAYER_ROLE:
            instruments[layer] = _default_instrument(layer, template)

        section_filter = []
        for i, s in enumerate(plan.sections):
            if s.name == "build":
                section_filter.append(round(min(1.0, 0.45 + 0.5 * s.energy), 2))
            else:
                section_filter.append(round(min(1.0, 0.25 + 0.75 * s.energy), 2))

        master = {"lofi": -14.0, "trap": -10.0, "house": -11.0,
                  "dnb": -9.0, "synthwave": -12.0}.get(plan.template, -10.0)

        return OrchestrationPlan(
            instruments=instruments,
            section_filter=section_filter,
            fills_every=8,
            final_lift=2 if plan.template in ("edm", "house", "synthwave") else 0,
            melody_variation=True,
            master_lufs=master,
            notes=f"Rule-based orchestration for '{plan.template}': "
                  f"catalog defaults, energy-driven filter automation.",
        )


def _default_instrument(layer: str, template) -> str:
    options = inst.options_for(layer)
    if not options:
        return ""
    # honor a template sound_design oscillator hint loosely, else catalog default
    default = inst.DEFAULT_INSTRUMENT.get(layer, options[0])
    return default if default in options else options[0]


def orch_from_dict(raw: dict, plan: ProductionPlan, template=None) -> OrchestrationPlan:
    """Validate/clamp orchestration JSON against the catalog and the plan."""
    instruments = {}
    for layer in inst.LAYER_ROLE:
        choice = (raw.get("instruments") or {}).get(layer)
        options = inst.options_for(layer)
        if choice in options:
            instruments[layer] = choice
        else:
            instruments[layer] = _default_instrument(layer, template)

    n = len(plan.sections)
    sf = [min(1.0, max(0.0, float(x))) for x in raw.get("section_filter", [])]
    if len(sf) < n:                       # pad from energy if the LLM gave too few
        sf += [min(1.0, 0.25 + 0.75 * plan.sections[i].energy) for i in range(len(sf), n)]
    sf = sf[:n]

    fills = int(raw.get("fills_every", 8))
    fills = fills if fills in (0, 4, 8, 16) else 8
    return OrchestrationPlan(
        instruments=instruments,
        section_filter=sf,
        fills_every=fills,
        final_lift=max(0, min(4, int(raw.get("final_lift", 0)))),
        melody_variation=bool(raw.get("melody_variation", True)),
        master_lufs=max(-20.0, min(-6.0, float(raw.get("master_lufs", -10.0)))),
        notes=raw.get("notes", ""),
    )


def get_orchestrator(use_llm: bool = True, model: str = MODEL):
    if use_llm and (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        try:
            return LLMOrchestratorBrain(model=model)
        except Exception:
            pass
    return RuleBasedOrchestrator()


def merged_sound_design(template_sound_design: dict, orch: OrchestrationPlan) -> dict:
    """Template sound design + the orchestration's instrument choices, so the
    synth engine renders the chosen voices."""
    merged = dict(template_sound_design or {})
    for layer, instrument in orch.instruments.items():
        ov = inst.overrides_for(layer, instrument)
        if ov:
            merged[layer] = {**merged.get(layer, {}), **ov}
    return merged
