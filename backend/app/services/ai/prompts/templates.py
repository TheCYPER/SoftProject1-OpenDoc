"""Versioned prompt templates for AI writing assistant features."""

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class PromptRender:
    prompt: str
    prompt_version: str
    truncated: bool
    original_length: int
    rendered_length: int


_TEMPLATE_PATH = Path(__file__).with_name("templates.json")
_CONFIG = json.loads(_TEMPLATE_PATH.read_text(encoding="utf-8"))

PROMPT_VERSION: str = _CONFIG["version"]
SYSTEM_PROMPT: str = _CONFIG["system_prompt"]
TEMPLATES: dict[str, str] = _CONFIG["templates"]
MAX_CONTEXT_CHARS: dict[str, int] = _CONFIG["max_context_chars"]


def _truncate_text(action: str, text: str) -> tuple[str, bool]:
    limit = MAX_CONTEXT_CHARS.get(action, MAX_CONTEXT_CHARS["default"])
    if len(text) <= limit:
        return text, False

    head = int(limit * 0.65)
    tail = max(0, limit - head)
    omitted = len(text) - (head + tail)
    truncated = (
        text[:head].rstrip()
        + f"\n\n[... {omitted} characters omitted for token budget ...]\n\n"
        + text[-tail:].lstrip()
    )
    return truncated, True


def render_prompt(action: str, text: str, options: dict | None = None) -> PromptRender:
    template = TEMPLATES.get(action)
    if template is None:
        raise ValueError(f"Unknown AI action: {action}")

    prepared_text, truncated = _truncate_text(action, text)
    format_vars = {"text": prepared_text}
    if options:
        format_vars.update(options)

    try:
        prompt = template.format(**format_vars)
    except KeyError:
        prompt = template.format_map({**format_vars, "target_language": "English"})

    return PromptRender(
        prompt=prompt,
        prompt_version=PROMPT_VERSION,
        truncated=truncated,
        original_length=len(text),
        rendered_length=len(prepared_text),
    )


def build_prompt(action: str, text: str, options: dict | None = None) -> str:
    return render_prompt(action, text, options).prompt
