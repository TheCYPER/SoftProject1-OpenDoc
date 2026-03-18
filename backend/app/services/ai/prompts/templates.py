"""Versioned prompt templates for AI writing assistant features."""

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = (
    "You are a professional writing assistant embedded in a collaborative document editor. "
    "Only output the improved text. Do not include explanations, commentary, or markdown formatting "
    "unless the original text uses it. Preserve the original meaning and facts."
)

TEMPLATES: dict[str, str] = {
    "rewrite": (
        "Rewrite the following text to improve clarity, grammar, and flow. "
        "Maintain the original meaning and tone.\n\n"
        "Original text:\n{text}"
    ),
    "summarize": (
        "Summarize the following text concisely while preserving all key points.\n\n"
        "Original text:\n{text}"
    ),
    "translate": (
        "Translate the following text into {target_language}. "
        "Preserve the original formatting and meaning.\n\n"
        "Original text:\n{text}"
    ),
    "restructure": (
        "Restructure the following text to improve its organization and logical flow. "
        "Use headings or bullet points where appropriate.\n\n"
        "Original text:\n{text}"
    ),
}


def build_prompt(action: str, text: str, options: dict | None = None) -> str:
    template = TEMPLATES.get(action)
    if template is None:
        raise ValueError(f"Unknown AI action: {action}")

    format_vars = {"text": text}
    if options:
        format_vars.update(options)

    # Use safe formatting — ignore missing keys
    try:
        return template.format(**format_vars)
    except KeyError:
        return template.format_map({**format_vars, "target_language": "English"})
