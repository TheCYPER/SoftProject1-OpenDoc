from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.config import settings
from app.services.ai.prompts.templates import SYSTEM_PROMPT, PromptRender, render_prompt
from app.services.ai.providers.base import AIProvider
from app.services.ai.providers.claude import ClaudeProvider
from app.services.ai.providers.ollama import OllamaProvider
from app.services.ai.providers.openai import OpenAIProvider


@dataclass(frozen=True)
class AIExecutionPlan:
    provider_name: str
    model_name: str
    model_profile: str
    prompt: str
    prompt_render: PromptRender
    system_prompt: str


def _build_provider(provider_name: str) -> tuple[AIProvider, str]:
    """Build an AI provider from server-side configuration only."""
    if provider_name == "openai":
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not configured.")
        return (
            OpenAIProvider(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
                default_model=settings.OPENAI_MODEL,
            ),
            settings.OPENAI_MODEL,
        )

    if provider_name == "groq":
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not configured.")
        return (
            OpenAIProvider(
                api_key=settings.GROQ_API_KEY,
                base_url=settings.GROQ_BASE_URL,
                default_model=settings.GROQ_MODEL,
            ),
            settings.GROQ_MODEL,
        )

    if provider_name == "claude":
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not configured.")
        return (
            ClaudeProvider(
                api_key=settings.ANTHROPIC_API_KEY,
                base_url=settings.ANTHROPIC_BASE_URL,
                default_model=settings.ANTHROPIC_MODEL,
            ),
            settings.ANTHROPIC_MODEL,
        )

    if provider_name == "ollama":
        return (
            OllamaProvider(base_url=settings.OLLAMA_BASE_URL, model=settings.OLLAMA_MODEL),
            settings.OLLAMA_MODEL,
        )

    raise ValueError(f"Unknown AI provider: {provider_name}")


def build_execution_plan(
    action: str,
    text: str,
    options: dict | None = None,
    provider_name: str | None = None,
    model: str | None = None,
) -> tuple[AIProvider, AIExecutionPlan]:
    resolved_provider_name = provider_name or settings.AI_DEFAULT_PROVIDER
    provider, default_model = _build_provider(resolved_provider_name)
    prompt_render = render_prompt(action, text, options)
    resolved_model_name = model or default_model
    execution_plan = AIExecutionPlan(
        provider_name=resolved_provider_name,
        model_name=resolved_model_name,
        model_profile=f"{resolved_provider_name}:{resolved_model_name}",
        prompt=prompt_render.prompt,
        prompt_render=prompt_render,
        system_prompt=SYSTEM_PROMPT,
    )
    return provider, execution_plan


async def stream_ai_job(
    action: str,
    text: str,
    options: dict | None = None,
    provider_name: str | None = None,
    model: str | None = None,
) -> tuple[AIExecutionPlan, AsyncIterator[str]]:
    provider, execution_plan = build_execution_plan(
        action=action,
        text=text,
        options=options,
        provider_name=provider_name,
        model=model,
    )
    return (
        execution_plan,
        provider.stream(
            prompt=execution_plan.prompt,
            system_prompt=execution_plan.system_prompt,
            model=execution_plan.model_name,
        ),
    )


async def run_ai_job(
    action: str,
    text: str,
    options: dict | None = None,
    provider_name: str | None = None,
    model: str | None = None,
) -> tuple[AIExecutionPlan, str]:
    execution_plan, stream = await stream_ai_job(
        action=action,
        text=text,
        options=options,
        provider_name=provider_name,
        model=model,
    )
    parts: list[str] = []
    async for chunk in stream:
        parts.append(chunk)
    return execution_plan, "".join(parts)
