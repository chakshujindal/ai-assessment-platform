"""Pick the LLM provider from settings. Fails at startup if a real provider has no key."""

import anthropic
import openai
from pydantic import SecretStr

from app.config import Settings
from app.llm.base import LLMClient, RateLimiter
from app.llm.fake import FakeLLM
from app.llm.providers import AnthropicLLM, OpenAILLM


def build_llm(settings: Settings) -> LLMClient:
    if settings.llm_provider == "fake":
        return FakeLLM()
    limiter = RateLimiter(settings.llm_max_concurrency, min_interval_seconds=0.2)
    if settings.llm_provider == "anthropic":
        client = anthropic.Anthropic(
            api_key=_require(settings.anthropic_api_key, "ANTHROPIC_API_KEY"),
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
        return AnthropicLLM(settings.anthropic_model, limiter, settings.llm_max_retries, client)
    openai_client = openai.OpenAI(
        api_key=_require(settings.openai_api_key, "OPENAI_API_KEY"),
        timeout=settings.llm_timeout_seconds,
        max_retries=0,
    )
    return OpenAILLM(settings.openai_model, limiter, settings.llm_max_retries, openai_client)


def _require(secret: SecretStr | None, name: str) -> str:
    if secret is None or not secret.get_secret_value():
        raise ValueError(f"{name} must be set when LLM_PROVIDER uses that provider")
    return secret.get_secret_value()
