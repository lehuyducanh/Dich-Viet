"""Genre template library.

Templates are JSON files describing how a genre is produced: tempo range,
drum-pattern grids per intensity level, bass style, instrumentation (GM
programs) and a default arrangement. They are data, not code — add a new
genre by dropping a JSON file into music_producer/templates/ (or pass
--template-dir on the CLI).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

BUILTIN_DIR = Path(__file__).parent / "templates"

LEVELS = ("low", "mid", "high", "build")
LAYERS = ("drums", "bass", "pad", "arp", "melody", "lead", "fx")
SECTION_NAMES = ("intro", "verse", "build", "drop", "chorus", "breakdown", "bridge", "outro")


@dataclass
class Template:
    name: str
    display_name: str
    description: str
    tempo_range: tuple[float, float]
    default_energy: float
    swing: float                                  # 0.0 straight .. ~0.6 heavy swing
    instruments: dict[str, int]                   # layer -> GM program
    drum_patterns: dict[str, dict[str, str]]      # level -> {drum_name: 16-step grid}
    bass_style: dict[str, str]                    # level -> style name
    arp_style: str
    default_arrangement: list[dict] = field(default_factory=list)

    @property
    def default_tempo(self) -> float:
        lo, hi = self.tempo_range
        return (lo + hi) / 2

    def clamp_tempo(self, bpm: float) -> float:
        lo, hi = self.tempo_range
        # allow user/LLM some freedom, but keep it within a plausible window
        return max(lo * 0.85, min(hi * 1.15, bpm))


def _validate(raw: dict, source: str) -> None:
    required = ("name", "display_name", "description", "tempo_range", "instruments",
                "drum_patterns", "bass_style", "arp_style", "default_arrangement")
    for key in required:
        if key not in raw:
            raise ValueError(f"{source}: template missing required field '{key}'")
    for level, grids in raw["drum_patterns"].items():
        if level not in LEVELS:
            raise ValueError(f"{source}: unknown drum pattern level '{level}'")
        for drum, grid in grids.items():
            if len(grid) != 16:
                raise ValueError(f"{source}: drum grid '{level}.{drum}' must have 16 steps, got {len(grid)}")
    for section in raw["default_arrangement"]:
        for layer in section.get("layers", []):
            if layer not in LAYERS:
                raise ValueError(f"{source}: unknown layer '{layer}' in default_arrangement")


def load_template_file(path: Path) -> Template:
    raw = json.loads(path.read_text(encoding="utf-8"))
    _validate(raw, str(path))
    return Template(
        name=raw["name"],
        display_name=raw["display_name"],
        description=raw["description"],
        tempo_range=tuple(raw["tempo_range"]),
        default_energy=raw.get("default_energy", 0.8),
        swing=raw.get("swing", 0.0),
        instruments=raw["instruments"],
        drum_patterns=raw["drum_patterns"],
        bass_style=raw["bass_style"],
        arp_style=raw["arp_style"],
        default_arrangement=raw["default_arrangement"],
    )


class TemplateLibrary:
    def __init__(self, extra_dirs: list[Path] | None = None):
        self.templates: dict[str, Template] = {}
        dirs = [BUILTIN_DIR] + list(extra_dirs or [])
        for d in dirs:
            if not d.is_dir():
                continue
            for f in sorted(d.glob("*.json")):
                tpl = load_template_file(f)
                self.templates[tpl.name] = tpl
        if not self.templates:
            raise RuntimeError(f"No templates found in {dirs}")

    def get(self, name: str) -> Template:
        if name not in self.templates:
            raise KeyError(f"Unknown template '{name}'. Available: {', '.join(self.templates)}")
        return self.templates[name]

    def names(self) -> list[str]:
        return list(self.templates)

    def catalog_for_llm(self) -> str:
        """Compact catalog the LLM reads to choose a template."""
        lines = []
        for t in self.templates.values():
            lines.append(
                f"- {t.name}: {t.display_name} | tempo {t.tempo_range[0]}-{t.tempo_range[1]} BPM | {t.description}"
            )
        return "\n".join(lines)
