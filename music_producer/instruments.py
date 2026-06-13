"""Instrument catalog — the studio's sound library.

Each instrument is a named bundle of synth-patch overrides (compatible with
sound_design.Patch) plus a 'role' saying which layer it belongs to. The
orchestration layer picks one instrument per layer from this catalog; the
chosen overrides are merged on top of the template's sound design before the
synth engine renders.

This is what lets one template host many timbres: a "supersaw_lead" drop vs a
"square_lead" drop, a "reese_bass" vs an "808", without touching code.
"""

from __future__ import annotations

# role -> {instrument_name: patch overrides}
CATALOG: dict[str, dict[str, dict]] = {
    "bass": {
        "sub_bass":    dict(osc="sine", sub=True, cutoff=260, attack=0.004,
                            decay=0.1, sustain=0.9, release=0.08, gain=0.9),
        "saw_bass":    dict(osc="saw", sub=True, cutoff=900, attack=0.004,
                            decay=0.08, sustain=0.85, release=0.06, gain=0.85),
        "reese_bass":  dict(osc="saw", voices=2, detune=0.3, sub=True, cutoff=750,
                            attack=0.004, sustain=0.85, release=0.07, gain=0.85),
        "808":         dict(osc="sine", sub=True, cutoff=320, attack=0.002,
                            decay=0.35, sustain=0.85, release=0.5, gain=1.0),
        "pluck_bass":  dict(osc="square", cutoff=1100, attack=0.002, decay=0.12,
                            sustain=0.2, release=0.06, gain=0.8),
    },
    "pad": {
        "warm_pad":    dict(osc="triangle", voices=2, detune=0.06, cutoff=2200,
                            attack=0.4, release=0.8, gain=0.34, width=0.7, reverb=0.5),
        "supersaw_pad": dict(osc="supersaw", voices=7, detune=0.16, cutoff=3200,
                             attack=0.35, release=0.7, gain=0.32, width=0.85, reverb=0.5),
        "string_pad":  dict(osc="saw", voices=4, detune=0.1, cutoff=2600,
                            attack=0.6, release=1.0, gain=0.3, width=0.8, reverb=0.6),
        "organ_pad":   dict(osc="square", voices=2, detune=0.02, cutoff=2400,
                            attack=0.02, release=0.3, sustain=0.85, gain=0.3, reverb=0.35),
    },
    "pluck": {
        "pluck":       dict(osc="square", cutoff=5000, attack=0.002, decay=0.14,
                            sustain=0.2, release=0.08, gain=0.42, width=0.4, delay=0.35),
        "bell":        dict(osc="sine", cutoff=6000, attack=0.002, decay=0.3,
                            sustain=0.1, release=0.3, gain=0.4, delay=0.3, reverb=0.4),
        "ep_keys":     dict(osc="triangle", cutoff=3200, attack=0.005, decay=0.25,
                            sustain=0.4, release=0.3, gain=0.42, delay=0.2, reverb=0.3),
        "saw_arp":     dict(osc="saw", cutoff=5500, attack=0.002, decay=0.12,
                            sustain=0.25, release=0.08, gain=0.4, delay=0.35, width=0.4),
    },
    "lead": {
        "supersaw_lead": dict(osc="supersaw", voices=7, detune=0.28, cutoff=9000,
                              attack=0.005, decay=0.2, sustain=0.75, release=0.2,
                              gain=0.58, width=0.7, delay=0.28, reverb=0.35),
        "saw_lead":    dict(osc="saw", voices=3, detune=0.08, cutoff=6500,
                            attack=0.006, sustain=0.7, release=0.18, gain=0.6, delay=0.25),
        "square_lead": dict(osc="square", cutoff=5500, attack=0.004, decay=0.18,
                            sustain=0.6, release=0.15, gain=0.5, delay=0.25, reverb=0.3),
        "sine_lead":   dict(osc="sine", voices=2, detune=0.04, cutoff=7000,
                            attack=0.008, decay=0.3, sustain=0.6, release=0.25,
                            gain=0.6, delay=0.3, reverb=0.4),
    },
    "fx": {
        "noise_riser": dict(osc="noise", cutoff=9000, attack=0.01, sustain=0.9,
                            release=0.3, gain=0.35, width=0.9, reverb=0.6),
        "white_sweep": dict(osc="noise", cutoff=11000, attack=0.02, sustain=0.85,
                            release=0.4, gain=0.3, width=1.0, reverb=0.5),
    },
}

# which catalog role feeds each arrangement layer
LAYER_ROLE = {
    "bass": "bass", "pad": "pad", "arp": "pluck",
    "melody": "lead", "lead": "lead", "fx": "fx",
}

# sensible default instrument per layer when nothing else is specified
DEFAULT_INSTRUMENT = {
    "bass": "saw_bass", "pad": "supersaw_pad", "arp": "pluck",
    "melody": "saw_lead", "lead": "supersaw_lead", "fx": "noise_riser",
}


def options_for(layer: str) -> list[str]:
    """Instrument names available for a layer."""
    return list(CATALOG.get(LAYER_ROLE.get(layer, ""), {}).keys())


def overrides_for(layer: str, instrument: str) -> dict:
    """Patch-override dict for a (layer, instrument), or {} if unknown."""
    role = LAYER_ROLE.get(layer, "")
    return CATALOG.get(role, {}).get(instrument, {})


def catalog_for_llm() -> str:
    """Compact instrument menu the orchestrator LLM picks from."""
    lines = []
    for layer, role in LAYER_ROLE.items():
        names = ", ".join(CATALOG.get(role, {}))
        lines.append(f"- {layer}: {names}")
    return "\n".join(lines)
