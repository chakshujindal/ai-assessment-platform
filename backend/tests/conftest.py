from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.llm.base import LLMError
from app.llm.fake import FakeLLM
from app.main import create_app
from app.ratelimit import limiter


class ScriptedLLM:
    """Returns queued replies in order (an Exception in the queue is raised instead)."""

    model_name = "scripted-llm"

    def __init__(self, *replies: str | Exception) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def complete(self, system: str, prompt: str) -> str:
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class FailingLLM:
    model_name = "failing-llm"

    def complete(self, system: str, prompt: str) -> str:
        raise LLMError("provider unavailable")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=f"sqlite:///{tmp_path}/test.db",
        jwt_secret="test-secret-that-is-at-least-32-bytes",
        snapshot_dir=str(tmp_path / "snapshots"),
        frontend_dist=str(tmp_path / "no-frontend"),
        rate_limit_enabled=False,
    )


@pytest.fixture
def llm() -> Any:
    return FakeLLM()


@pytest.fixture
def client(settings: Settings, llm: Any) -> Iterator[TestClient]:
    limiter.reset()
    with TestClient(create_app(settings, llm)) as test_client:
        yield test_client


def register(client: TestClient, email: str = "rec@example.com") -> dict[str, str]:
    response = client.post("/api/auth/register", json={"email": email, "password": "secret-pass"})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def auth(client: TestClient) -> dict[str, str]:
    return register(client)


@pytest.fixture
def draft(client: TestClient, auth: dict[str, str]) -> dict[str, Any]:
    """A draft assessment with 2 MCQs, 1 short-answer and 1 coding question."""
    created = client.post("/api/assessments", json={"title": "Backend screen"}, headers=auth)
    assessment_id = created.json()["id"]
    body = {
        "topic": "Backend",
        "skills": ["Python"],
        "mix": {"mcq": 2, "short_answer": 1, "coding": 1},
    }
    generated = client.post(f"/api/assessments/{assessment_id}/generate", json=body, headers=auth)
    assert generated.status_code == 200, generated.text
    return client.get(f"/api/assessments/{assessment_id}", headers=auth).json()


@pytest.fixture
def published(client: TestClient, auth: dict[str, str], draft: dict[str, Any]) -> dict[str, Any]:
    response = client.post(f"/api/assessments/{draft['id']}/publish", headers=auth)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def invite(client: TestClient, auth: dict[str, str], published: dict[str, Any]) -> dict[str, Any]:
    body = {"candidate_name": "Ada", "candidate_email": "ada@example.com"}
    response = client.post(f"/api/assessments/{published['id']}/invites", json=body, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()
