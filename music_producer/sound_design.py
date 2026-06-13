"""Sound design: synth patches per layer, overridable per template.

A Patch describes how the internal synth engine renders one layer. Templates
may override any field via a "sound_design" object in their JSON, e.g.:

    "sound_design": {
        "bass": {"osc": "sine", "sub": true, "release": 0.4, "sidechain": 0.9},
        "drums": {"gain": 1.0, "reverb": 0.25},
        "_master": {"vinyl": 0.5, "cutoff": 7000}
    }
"""

from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass
class Patch:
    osc: str = "saw"          # saw | supersaw | square | triangle | sine | noise
    voices: int = 1           # unison voices (supersaw)
    detune: float = 0.0       # unison detune in semitones
    octave: int = 0           # octave shift
    sub: bool = False         # add a sine sub-oscillator one octave down
    cutoff: float = 6000.0    # lowpass cutoff in Hz
    attack: float = 0.01      # ADSR, seconds
    decay: float = 0.10
    sustain: float = 0.7      # 0-1
    release: float = 0.10
    gain: float = 0.6
    pan: float = 0.0          # -1 left .. +1 right
    width: float = 0.0        # 0-1 stereo width (Haas spread)
    delay: float = 0.0        # 0-1 send to tempo-synced delay
    reverb: float = 0.2       # 0-1 send to the reverb bus
    sidechain: float = 0.0    # 0-1 ducking from the kick
    eq_low: float = 0.0       # low-shelf gain in dB (+ boost / - cut)
    eq_high: float = 0.0      # high-shelf gain in dB
    automate: bool = True     # follow the song's filter automation

    @classmethod
    def build(cls, *overrides: dict) -> "Patch":
        valid = {f.name for f in fields(cls)}
        merged: dict = {}
        for o in overrides:
            merged.update({k: v for k, v in (o or {}).items() if k in valid})
        return cls(**merged)


# Per-layer studio defaults: a usable electronic mix out of the box.
LAYER_DEFAULTS: dict[str, dict] = {
    "bass": dict(osc="saw", sub=True, cutoff=900, attack=0.004, decay=0.08,
                 sustain=0.85, release=0.06, gain=0.85, reverb=0.0,
                 sidechain=0.75),
    "pad": dict(osc="supersaw", voices=5, detune=0.14, cutoff=3200,
                attack=0.35, decay=0.3, sustain=0.8, release=0.7,
                gain=0.32, width=0.8, reverb=0.5, sidechain=0.55),
    "arp": dict(osc="square", cutoff=5200, attack=0.002, decay=0.14,
                sustain=0.25, release=0.08, gain=0.42, width=0.4,
                delay=0.35, reverb=0.25, sidechain=0.35, pan=0.15),
    "melody": dict(osc="saw", voices=3, detune=0.08, cutoff=4800,
                   attack=0.008, decay=0.15, sustain=0.7, release=0.18,
                   gain=0.6, delay=0.22, reverb=0.3, sidechain=0.2),
    "lead": dict(osc="supersaw", voices=7, detune=0.28, cutoff=8500,
                 attack=0.005, decay=0.2, sustain=0.75, release=0.2,
                 gain=0.55, width=0.7, delay=0.28, reverb=0.35,
                 sidechain=0.3, pan=-0.1),
    "fx": dict(osc="noise", cutoff=9000, attack=0.01, decay=0.1,
               sustain=0.9, release=0.3, gain=0.35, width=0.9, reverb=0.6),
    "drums": dict(gain=0.95, reverb=0.12),
}


def patch_for(layer: str, template_sound_design: dict | None) -> Patch:
    overrides = (template_sound_design or {}).get(layer, {})
    return Patch.build(LAYER_DEFAULTS.get(layer, {}), overrides)


def master_options(template_sound_design: dict | None) -> dict:
    """Master-bus options: {"vinyl": 0-1 crackle amount, "cutoff": Hz}."""
    return (template_sound_design or {}).get("_master", {})
