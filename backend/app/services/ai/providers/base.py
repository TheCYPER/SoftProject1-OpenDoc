from abc import ABC, abstractmethod


class AIProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str | None = None,
    ) -> str:
        """Send a prompt to the AI provider and return the generated text."""
        ...
