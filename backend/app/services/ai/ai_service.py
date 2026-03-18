from app.config import settings
from app.services.ai.prompts.templates import SYSTEM_PROMPT, build_prompt
from app.services.ai.providers.base import AIProvider
from app.services.ai.providers.claude import ClaudeProvider
from app.services.ai.providers.ollama import OllamaProvider
from app.services.ai.providers.openai import OpenAIProvider


def _build_provider(
    provider_name: str,
    api_key: str | None = None,
    base_url: str | None = None,
) -> AIProvider:
    """Build an AI provider based on name, with optional user-supplied credentials."""
    if provider_name == "openai":
        key = api_key or settings.OPENAI_API_KEY
        url = base_url or settings.OPENAI_BASE_URL
        if not key:
            raise ValueError("OpenAI API key is required. Provide it in the request or server config.")
        return OpenAIProvider(api_key=key, base_url=url)

    if provider_name == "claude":
        key = api_key or settings.ANTHROPIC_API_KEY
        url = base_url or settings.ANTHROPIC_BASE_URL
        if not key:
            raise ValueError("Anthropic API key is required. Provide it in the request or server config.")
        return ClaudeProvider(api_key=key, base_url=url)

    if provider_name == "ollama":
        url = base_url or settings.OLLAMA_BASE_URL
        return OllamaProvider(base_url=url, model=settings.OLLAMA_MODEL)

    raise ValueError(f"Unknown AI provider: {provider_name}")


async def run_ai_job(
    action: str,
    text: str,
    options: dict | None = None,
    provider_name: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> str:
    """Execute an AI writing task and return the generated text."""
    provider_name = provider_name or settings.AI_DEFAULT_PROVIDER
    provider = _build_provider(provider_name, api_key, base_url)
    prompt = build_prompt(action, text, options)
    return await provider.generate(prompt=prompt, system_prompt=SYSTEM_PROMPT)
