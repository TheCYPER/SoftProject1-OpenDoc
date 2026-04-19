from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class AIProvider(ABC):
    @abstractmethod
    async def stream(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield generated text chunks from the provider."""
        raise NotImplementedError

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str | None = None,
    ) -> str:
        parts: list[str] = []
        async for chunk in self.stream(prompt=prompt, system_prompt=system_prompt, model=model):
            parts.append(chunk)
        return "".join(parts)
