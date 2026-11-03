"""Per-client rate limits (slowapi), keyed by IP + path.

Every route carries an explicit @limiter.limit(...); tests check that none is missing.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

DEFAULT_LIMIT = "120/minute"
AUTH_LIMIT = "10/minute"
SUBMIT_LIMIT = "5/minute"
LLM_LIMIT = "10/minute"
SNAPSHOT_LIMIT = "20/minute"

limiter = Limiter(key_func=get_remote_address)


def rate_limit_exceeded(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """429 with Retry-After set to the limit's window, the longest a client must wait."""
    retry_after = exc.limit.limit.get_expiry()
    return JSONResponse(
        {"detail": f"Too many requests ({exc.detail}). Try again in {retry_after}s."},
        status_code=429,
        headers={"Retry-After": str(retry_after)},
    )
