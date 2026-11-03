"""Provider adapters, exercised through the real SDKs over a mocked HTTP transport (no network)."""

from collections.abc import Callable
from typing import Any

import anthropic
import httpx2
import openai
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.llm import base
from app.llm.base import LLMError, RateLimiter
from app.llm.factory import build_llm
from app.llm.fake import FakeLLM
from app.llm.providers import AnthropicLLM, OpenAILLM

Handler = Callable[[httpx2.Request], httpx2.Response]


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base, "backoff_delay", lambda attempt: 0.0)


def sequence(*responses: httpx2.Response) -> tuple[Handler, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []
    queue = list(responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return queue.pop(0)

    return handler, seen


def claude_message(text: str = '{"ok": true}', stop_reason: str = "end_turn") -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 3, "output_tokens": 4},
    }


def anthropic_llm(handler: Handler) -> AnthropicLLM:
    client = anthropic.Anthropic(
        api_key="test",
        max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return AnthropicLLM("claude-sonnet-5-5", RateLimiter(2), max_retries=2, client=client)


def openai_completion(content: str | None = '{"ok": true}', **message: Any) -> dict[str, Any]:
    finish_reason = message.pop("finish_reason", "stop")
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-6.1-sol",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": content, "refusal": None, **message},
            }
        ],
    }


def openai_llm(handler: Handler) -> OpenAILLM:
    client = openai.OpenAI(
        api_key="test",
        max_retries=0,
        http_client=openai.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return OpenAILLM("gpt-6.1-sol", RateLimiter(2), max_retries=2, client=client)


RATE_LIMITED = {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}


def test_anthropic_retries_429_then_returns_text() -> None:
    handler, seen = sequence(
        httpx2.Response(429, json=RATE_LIMITED), httpx2.Response(200, json=claude_message())
    )
    assert anthropic_llm(handler).complete("sys", "hi") == '{"ok": true}'
    assert len(seen) == 2
    body = seen[-1].read().decode()
    assert '"fallbacks":"default"' in body.replace(" ", "")
    assert seen[-1].headers["anthropic-beta"] == "server-side-fallback-2026-07-01"


def test_anthropic_does_not_retry_bad_request() -> None:
    error = {"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}}
    handler, seen = sequence(httpx2.Response(400, json=error))
    with pytest.raises(LLMError, match="Anthropic request failed"):
        anthropic_llm(handler).complete("sys", "hi")
    assert len(seen) == 1


def test_anthropic_gives_up_after_max_retries() -> None:
    handler, seen = sequence(*[httpx2.Response(529, json=RATE_LIMITED) for _ in range(3)])
    with pytest.raises(LLMError):
        anthropic_llm(handler).complete("sys", "hi")
    assert len(seen) == 3


@pytest.mark.parametrize(
    ("stop_reason", "message"), [("refusal", "declined"), ("max_tokens", "cut off")]
)
def test_anthropic_unusable_stop_reasons(stop_reason: str, message: str) -> None:
    handler, _ = sequence(httpx2.Response(200, json=claude_message(stop_reason=stop_reason)))
    with pytest.raises(LLMError, match=message):
        anthropic_llm(handler).complete("sys", "hi")


def test_anthropic_retries_connection_errors() -> None:
    calls: list[int] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx2.ConnectError("boom", request=request)
        return httpx2.Response(200, json=claude_message("done"))

    assert anthropic_llm(handler).complete("sys", "hi") == "done"


def test_openai_retries_5xx_and_sends_json_mode() -> None:
    handler, seen = sequence(
        httpx2.Response(500, json={"error": {"message": "oops"}}),
        httpx2.Response(200, json=openai_completion()),
    )
    assert openai_llm(handler).complete("sys", "hi") == '{"ok": true}'
    assert '"json_object"' in seen[-1].read().decode()


def test_openai_errors_are_wrapped() -> None:
    handler, seen = sequence(httpx2.Response(401, json={"error": {"message": "no key"}}))
    with pytest.raises(LLMError, match="OpenAI request failed"):
        openai_llm(handler).complete("sys", "hi")
    assert len(seen) == 1

    def offline(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("offline", request=request)

    with pytest.raises(LLMError):
        openai_llm(offline).complete("sys", "hi")


@pytest.mark.parametrize(
    ("completion", "message"),
    [
        (openai_completion(None, refusal="I can't help with that"), "declined"),
        (openai_completion('{"a"', finish_reason="length"), "cut off"),
    ],
)
def test_openai_unusable_replies(completion: dict[str, Any], message: str) -> None:
    handler, _ = sequence(httpx2.Response(200, json=completion))
    with pytest.raises(LLMError, match=message):
        openai_llm(handler).complete("sys", "hi")


def test_factory_picks_provider_and_requires_keys() -> None:
    assert isinstance(build_llm(Settings(_env_file=None, llm_provider="fake")), FakeLLM)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        build_llm(Settings(_env_file=None, llm_provider="anthropic", anthropic_api_key=None))  # type: ignore[call-arg]
    claude = build_llm(
        Settings(_env_file=None, llm_provider="anthropic", anthropic_api_key=SecretStr("k"))  # type: ignore[call-arg]
    )
    assert isinstance(claude, AnthropicLLM)
    assert claude.model_name == "claude-sonnet-5-5"
    gpt = build_llm(
        Settings(_env_file=None, llm_provider="openai", openai_api_key=SecretStr("k"))  # type: ignore[call-arg]
    )
    assert isinstance(gpt, OpenAILLM)
