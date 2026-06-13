"""Plan persistence: save LLM-generated production plans as reusable presets.

A ProductionPlan is a small JSON document. Calling the LLM once per *theme*
and saving the result gives you a growing preset library — every later track
with the same vibe costs zero LLM calls:

    music_producer remix song1.mid -t "EDM sôi động" --save-plan presets/edm_party.json
    music_producer remix song2.mid --plan presets/edm_party.json      # no LLM
    music_producer batch songs/*.mid --plan presets/edm_party.json    # no LLM
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .model import OrchestrationPlan, ProductionPlan
from .producer_brain import _plan_from_dict
from .template_library import TemplateLibrary


def save_plan(plan: ProductionPlan, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(plan), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_plan(path: str | Path, library: TemplateLibrary) -> ProductionPlan:
    """Load and re-validate a saved plan against the current template library
    (same clamping as LLM output, so hand-edited presets are safe too)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return _plan_from_dict(raw, library)


def save_orchestration(orch: OrchestrationPlan, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(orch), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_orchestration(path: str | Path, plan: ProductionPlan) -> OrchestrationPlan:
    """Load and re-validate a saved orchestration against the plan it will run on."""
    from .orchestrator import orch_from_dict
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return orch_from_dict(raw, plan)
