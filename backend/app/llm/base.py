"""The LLM provider protocol plus the retry and rate-limit helpers every provider shares."""

import logging
import random
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Protocol

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Anything that can turn a system prompt + user prompt into text."""

    model_name: str

    def complete(self, system: str, prompt: str) -> str: ...


class LLMError(RuntimeError):
    """The provider failed (after retries), refused, or returned unusable output."""


class LLMOutputError(LLMError):
    """The model's output failed schema validation even after one repair attempt."""


class RateLimiter:
    """Client-side limiter: at most `max_concurrency` calls in flight, starts spaced apart."""

    def __init__(
        self,
        max_concurrency: int,
        min_interval_seconds: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._slots = threading.BoundedSemaphore(max_concurrency)
        self._lock = threading.Lock()
        self._min_interval = min_interval_seconds
        self._next_start = 0.0
        self._clock = clock
        self._sleep = sleep

    @contextmanager
    def slot(self) -> Iterator[None]:
        with self._slots:
            with self._lock:
                now = self._clock()
                wait = self._next_start - now
                self._next_start = max(now, self._next_start) + self._min_interval
            if wait > 0:
                self._sleep(wait)
            yield


def backoff_delay(
    attempt: int, base: float = 1.0, cap: float = 30.0, rand: Callable[[], float] = random.random
) -> float:
    """Exponential backoff with full jitter: a random delay in [0, min(cap, base * 2^attempt))."""
    return rand() * min(cap, base * 2**attempt)


def call_with_retries[T](
    call: Callable[[], T],
    *,
    is_retryable: Callable[[Exception], bool],
    max_retries: int,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run `call`, retrying retryable failures (429, 5xx, timeouts) with jittered backoff."""
    for attempt in range(max_retries + 1):
        try:
            return call()
        except Exception as exc:  # filtered by is_retryable; anything else is re-raised
            if attempt == max_retries or not is_retryable(exc):
                raise
            delay = backoff_delay(attempt)
            logger.warning(
                "LLM call failed (%s); retry %d/%d in %.1fs",
                type(exc).__name__,
                attempt + 1,
                max_retries,
                delay,
            )
            sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover
