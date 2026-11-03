"""Anthropic and OpenAI implementations of LLMClient.

The SDKs' own retries are switched off (max_retries=0) so that both providers share one
explicit policy: a per-call timeout, jittered exponential backoff on 429/5xx/network
errors, and a client-side concurrency limiter.
"""

import anthropic
import openai

from app.llm.base import LLMError, RateLimiter, call_with_retries

MAX_OUTPUT_TOKENS = 16_000


def _retryable_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def _anthropic_retryable(exc: Exception) -> bool:
    if isinstance(exc, anthropic.APIStatusError):
        return _retryable_status(exc.status_code)
    return isinstance(exc, anthropic.APIConnectionError)  # includes timeouts


def _openai_retryable(exc: Exception) -> bool:
    if isinstance(exc, openai.APIStatusError):
        return _retryable_status(exc.status_code)
    return isinstance(exc, openai.APIConnectionError)  # includes timeouts


class AnthropicLLM:
    def __init__(
        self,
        model: str,
        limiter: RateLimiter,
        max_retries: int,
        client: anthropic.Anthropic,
    ) -> None:
        self.model_name = model
        self._limiter = limiter
        self._max_retries = max_retries
        self._client = client

    def complete(self, system: str, prompt: str) -> str:
        def call() -> anthropic.types.beta.BetaMessage:
            with self._limiter.slot():
                return self._client.beta.messages.create(
                    model=self.model_name,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                    # If a safety classifier declines, let the API retry on its
                    # recommended fallback model instead of failing the request.
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                )

        try:
            message = call_with_retries(
                call, is_retryable=_anthropic_retryable, max_retries=self._max_retries
            )
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic request failed: {exc}") from exc
        if message.stop_reason == "refusal":
            raise LLMError("Anthropic model declined the request")
        if message.stop_reason == "max_tokens":
            raise LLMError("Anthropic reply was cut off at max_tokens")
        return "".join(block.text for block in message.content if block.type == "text")


class OpenAILLM:
    def __init__(
        self,
        model: str,
        limiter: RateLimiter,
        max_retries: int,
        client: openai.OpenAI,
    ) -> None:
        self.model_name = model
        self._limiter = limiter
        self._max_retries = max_retries
        self._client = client

    def complete(self, system: str, prompt: str) -> str:
        def call() -> openai.types.chat.ChatCompletion:
            with self._limiter.slot():
                return self._client.chat.completions.create(
                    model=self.model_name,
                    max_completion_tokens=MAX_OUTPUT_TOKENS,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                )

        try:
            completion = call_with_retries(
                call, is_retryable=_openai_retryable, max_retries=self._max_retries
            )
        except openai.APIError as exc:
            raise LLMError(f"OpenAI request failed: {exc}") from exc
        choice = completion.choices[0]
        if choice.message.refusal:
            raise LLMError("OpenAI model declined the request")
        if choice.finish_reason == "length":
            raise LLMError("OpenAI reply was cut off at max_completion_tokens")
        return choice.message.content or ""
