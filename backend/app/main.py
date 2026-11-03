"""FastAPI app factory. Run with: uvicorn --factory app.main:create_app"""

import logging
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db import Base, make_engine
from app.llm.base import LLMClient, LLMError
from app.llm.factory import build_llm
from app.ratelimit import DEFAULT_LIMIT, limiter, rate_limit_exceeded
from app.routers import assessments, auth, candidate, practice, results

logger = logging.getLogger(__name__)
_TOKEN_IN_PATH = re.compile(r"/take/[^/?\s\"]+")


class RedactInviteTokens(logging.Filter):
    """Invite tokens are credentials, so keep them out of the access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                _TOKEN_IN_PATH.sub("/take/<redacted>", arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True


def llm_failed(request: Request, exc: LLMError) -> JSONResponse:
    """The single place LLM failures in a request are logged; clients get a generic message."""
    logger.error("LLM step failed on %s %s: %s", request.method, request.url.path, exc)
    detail = "The AI step failed. Please try again in a moment."
    return JSONResponse({"detail": detail}, status_code=502)


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built React app (demo / single-process deploys) with SPA fallback."""
    if not (dist / "index.html").is_file():
        return
    root = dist.resolve()
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    @limiter.limit(DEFAULT_LIMIT)
    def spa(request: Request, path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        file = (root / path).resolve()
        if path and file.is_file() and root in file.parents:
            return FileResponse(file)
        return FileResponse(root / "index.html")


def create_app(settings: Settings | None = None, llm: LLMClient | None = None) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for name in ("uvicorn.access", "slowapi"):  # both log request paths
        path_logger = logging.getLogger(name)
        if not any(isinstance(f, RedactInviteTokens) for f in path_logger.filters):
            path_logger.addFilter(RedactInviteTokens())
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)

    app = FastAPI(title="AI Assessment Platform", version="0.1.0")
    app.state.settings = settings
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.llm = llm or build_llm(settings)
    limiter.enabled = settings.rate_limit_enabled
    app.state.limiter = limiter

    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded)  # type: ignore[arg-type]
    app.add_exception_handler(LLMError, llm_failed)  # type: ignore[arg-type]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in (
        auth.router,
        assessments.router,
        results.router,
        candidate.router,
        practice.router,
    ):
        app.include_router(router)

    @app.get("/api/health")
    @limiter.limit(DEFAULT_LIMIT)
    def health(request: Request) -> dict[str, str]:
        return {"status": "ok", "llm": app.state.llm.model_name}

    mount_frontend(app, Path(settings.frontend_dist))
    return app
