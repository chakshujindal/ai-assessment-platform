"""Retry/backoff, the rate limiter, and the structured-output (validate + one repair) layer."""

import pytest
from pydantic import BaseModel

from app.llm import base
from app.llm.base import LLMOutputError, RateLimiter, backoff_delay, call_with_retries
from app.llm.structured import complete_json, extract_json
from tests.conftest import ScriptedLLM


class Point(BaseModel):
    x: int
    y: int


class Retryable(Exception):
    pass


def test_backoff_is_exponential_jittered_and_capped() -> None:
    assert backoff_delay(0, rand=lambda: 1.0) == 1.0
    assert backoff_delay(3, rand=lambda: 1.0) == 8.0
    assert backoff_delay(10, rand=lambda: 1.0) == 30.0
    assert backoff_delay(3, rand=lambda: 0.5) == 4.0


def test_call_with_retries_retries_then_succeeds() -> None:
    outcomes: list[object] = [Retryable(), Retryable(), "ok"]
    sleeps: list[float] = []

    def call() -> str:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return str(outcome)

    result = call_with_retries(
        call, is_retryable=lambda e: isinstance(e, Retryable), max_retries=3, sleep=sleeps.append
    )
    assert result == "ok"
    assert len(sleeps) == 2


def test_call_with_retries_gives_up_and_skips_non_retryable() -> None:
    def always_fails() -> str:
        raise Retryable()

    with pytest.raises(Retryable):
        call_with_retries(
            always_fails, is_retryable=lambda e: True, max_retries=2, sleep=lambda s: None
        )

    calls: list[int] = []

    def bad_request() -> str:
        calls.append(1)
        raise ValueError("400")

    with pytest.raises(ValueError):
        call_with_retries(bad_request, is_retryable=lambda e: False, max_retries=5)
    assert calls == [1]


def test_rate_limiter_spaces_call_starts() -> None:
    now = [100.0]
    waits: list[float] = []
    limiter = RateLimiter(2, min_interval_seconds=0.5, clock=lambda: now[0], sleep=waits.append)
    for _ in range(3):
        with limiter.slot():
            pass
    assert waits == [0.5, 1.0]


def test_extract_json_handles_fences_and_prose() -> None:
    assert extract_json('```json\n{"x": 1}\n```') == '{"x": 1}'
    assert extract_json('Sure! {"x": 1} hope that helps') == '{"x": 1}'
    with pytest.raises(ValueError, match="no JSON"):
        extract_json("no braces here")


def test_complete_json_valid_on_first_try() -> None:
    llm = ScriptedLLM('{"x": 1, "y": 2}')
    assert complete_json(llm, "sys", "prompt", Point) == Point(x=1, y=2)
    assert len(llm.prompts) == 1


def test_complete_json_repairs_once() -> None:
    llm = ScriptedLLM('{"x": 1}', '{"x": 1, "y": 2}')
    assert complete_json(llm, "sys", "prompt", Point) == Point(x=1, y=2)
    assert "previous reply was invalid" in llm.prompts[1]


def test_complete_json_fails_clearly_after_one_repair() -> None:
    llm = ScriptedLLM("nope", '{"x": "a"}', "never used")
    with pytest.raises(LLMOutputError, match="Point output was still invalid"):
        complete_json(llm, "sys", "prompt", Point)
    assert len(llm.prompts) == 2


def test_domain_check_failure_triggers_repair() -> None:
    def positive(point: Point) -> None:
        if point.x < 0:
            raise ValueError("x must be positive")

    llm = ScriptedLLM('{"x": -1, "y": 0}', '{"x": 1, "y": 0}')
    assert complete_json(llm, "sys", "p", Point, check=positive).x == 1
    assert "x must be positive" in llm.prompts[1]


def test_retry_warning_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    outcomes: list[object] = [Retryable(), "ok"]

    def call() -> str:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return str(outcome)

    with caplog.at_level("WARNING", logger=base.__name__):
        call_with_retries(call, is_retryable=lambda e: True, max_retries=1, sleep=lambda s: None)
    assert "retry 1/1" in caplog.text
