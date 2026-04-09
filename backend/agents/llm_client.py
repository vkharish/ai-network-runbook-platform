"""Abstract LLM client + provider factory — mirrors embedding_engine.py pattern."""

from abc import ABC, abstractmethod

from backend.core.config import LLMProvider, settings
from backend.core.logging import get_logger

log = get_logger(__name__)


MAX_PROMPT_CHARS = 400_000  # ~100k tokens, well under all provider limits


class BaseLLMClient(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str: ...

    def _guard_prompt_size(self, messages: list[dict]) -> list[dict]:
        """Truncate the last user message if total prompt exceeds MAX_PROMPT_CHARS."""
        total = sum(len(m.get("content", "")) for m in messages)
        if total <= MAX_PROMPT_CHARS:
            return messages
        overflow = total - MAX_PROMPT_CHARS
        trimmed = []
        for m in reversed(messages):
            if m.get("role") == "user" and overflow > 0:
                content = m["content"]
                cut = max(100, len(content) - overflow)
                trimmed.insert(0, {**m, "content": content[:cut] + "\n…[prompt truncated to fit context limit]"})
                overflow -= len(content) - cut
            else:
                trimmed.insert(0, m)
        log.warning("prompt_truncated", original_chars=total, max_chars=MAX_PROMPT_CHARS)
        return trimmed


class OpenAIClient(BaseLLMClient):
    def complete(self, messages: list[dict], temperature: float = 0.2, max_tokens: int = 2048) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=self._guard_prompt_size(messages),  # type: ignore[arg-type]
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""


class AnthropicClient(BaseLLMClient):
    def complete(self, messages: list[dict], temperature: float = 0.2, max_tokens: int = 2048) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msgs = [m for m in messages if m["role"] != "system"]
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=max_tokens,
            system=system_msg,
            messages=self._guard_prompt_size(user_msgs),  # type: ignore[arg-type]
            temperature=temperature,
        )
        return response.content[0].text  # type: ignore[union-attr]


class OllamaClient(BaseLLMClient):
    def complete(self, messages: list[dict], temperature: float = 0.2, max_tokens: int = 2048) -> str:
        import ollama

        response = ollama.chat(
            model=settings.ollama_model,
            messages=self._guard_prompt_size(messages),
            options={"temperature": temperature, "num_predict": max_tokens},
        )
        return response["message"]["content"]


def get_llm_client() -> BaseLLMClient:
    """Factory — returns the configured LLM client."""
    if settings.llm_provider == LLMProvider.OPENAI:
        log.info("llm_client_openai", model=settings.llm_model)
        return OpenAIClient()
    elif settings.llm_provider == LLMProvider.ANTHROPIC:
        log.info("llm_client_anthropic", model=settings.llm_model)
        return AnthropicClient()
    else:
        log.info("llm_client_ollama", model=settings.ollama_model)
        return OllamaClient()
