"""Song generation via the Anthropic API.

Uses structured outputs (`client.messages.parse` with the pydantic `Song`
model) so the response is schema-validated by the SDK. If the first attempt
fails to validate, one repair round-trip feeds the error back to the model
before giving up.
"""

from __future__ import annotations

import json
import os
import re

import anthropic

from .. import config
from ..midi.model import Song
from .prompts import SYSTEM_PROMPT, build_user_prompt


class GenerationError(RuntimeError):
    pass


def _require_api_key() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise GenerationError(
            "ANTHROPIC_API_KEY is not set. Get a key at https://platform.claude.com/ "
            "and run: export ANTHROPIC_API_KEY=sk-ant-..."
        )


def _extract_json(text: str) -> str:
    """Strip markdown code fences if the model wrapped the JSON."""
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    return text.strip()


def _parse_song(text: str) -> Song:
    data = json.loads(_extract_json(text))
    return Song.model_validate(data).cleaned()


def generate_song(prompt: str, bars: int = 16, model: str = config.DEFAULT_MODEL) -> Song:
    _require_api_key()
    client = anthropic.Anthropic()
    user_prompt = build_user_prompt(prompt, bars)

    # First attempt: structured outputs — the SDK validates against Song.
    try:
        response = client.messages.parse(
            model=model,
            max_tokens=config.MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            output_format=Song,
        )
        if response.parsed_output is not None:
            return response.parsed_output.cleaned()
        raw = next((b.text for b in response.content if b.type == "text"), "")
        first_error = "response did not match the Song schema"
    except anthropic.APIError:
        raise
    except Exception as exc:  # validation / parsing failure — try to repair
        raw = getattr(exc, "response_text", "") or ""
        first_error = str(exc)

    # Repair round-trip: show the model its own output and the error.
    repair = client.messages.create(
        model=model,
        max_tokens=config.MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_prompt},
            {
                "role": "user",
                "content": (
                    "Your previous output failed validation with this error:\n"
                    f"{first_error}\n\nPrevious output:\n{raw[:8000]}\n\n"
                    "Return the corrected song JSON only."
                ),
            },
        ],
    )
    text = next((b.text for b in repair.content if b.type == "text"), "")
    try:
        return _parse_song(text)
    except Exception as exc:
        raise GenerationError(
            f"Model output failed validation twice. Last error: {exc}"
        ) from exc
