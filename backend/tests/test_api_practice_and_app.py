"""Practice mode, frontend serving, health, and the demo seed."""

import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db import Base, make_engine
from app.jobs import grade_submission
from app.llm.fake import FakeLLM
from app.main import create_app
from app.seed import DEMO_EMAIL, DEMO_PASSWORD, seed
from tests.conftest import FailingLLM
from tests.test_generation import NOTES


def test_practice_quiz_from_notes_gives_instant_feedback(client: TestClient) -> None:
    body = {"source_material": NOTES, "mix": {"mcq": 2, "short_answer": 1, "coding": 0}}
    created = client.post("/api/practice/quizzes", json=body)
    assert created.status_code == 201
    quiz = created.json()
    assert [q["index"] for q in quiz["questions"]] == [0, 1, 2]
    assert "correct_index" not in str(quiz)

    url = f"/api/practice/quizzes/{quiz['id']}/check"
    checks = [client.post(url, json={"index": 0, "response": str(i)}).json() for i in range(4)]
    assert sum(1 for c in checks if c["correct"]) == 1
    assert all(c["reference"] for c in checks)

    short = client.post(url, json={"index": 2, "response": "Chlorophyll absorbs light."}).json()
    assert short["correct"] is None and short["criteria"] and short["reference"] in NOTES
    assert client.post(url, json={"index": 9, "response": "x"}).status_code == 404
    assert (
        client.post(
            "/api/practice/quizzes/nope/check", json={"index": 0, "response": "x"}
        ).status_code
        == 404
    )


def test_practice_coding_reference_is_the_solution(client: TestClient) -> None:
    body = {"topic": "Python", "mix": {"mcq": 0, "short_answer": 0, "coding": 1}}
    quiz = client.post("/api/practice/quizzes", json=body).json()
    url = f"/api/practice/quizzes/{quiz['id']}/check"
    checked = client.post(url, json={"index": 0, "response": "def dedupe(items): ..."}).json()
    assert checked["reference"].startswith("def dedupe")


def test_practice_llm_failure_is_502(client: TestClient) -> None:
    client.app.state.llm = FailingLLM()  # type: ignore[attr-defined]
    response = client.post("/api/practice/quizzes", json={"topic": "Rust"})
    assert response.status_code == 502
    assert response.json()["detail"] == "The AI step failed. Please try again in a moment."


def test_health_reports_model(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok", "llm": "fake-llm"}


def test_built_frontend_is_served_with_spa_fallback(settings: Settings, tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id=root></div>")
    (dist / "favicon.svg").write_text("<svg/>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    settings.frontend_dist = str(dist)
    with TestClient(create_app(settings, FakeLLM())) as app_client:
        assert app_client.get("/").text == "<div id=root></div>"
        assert app_client.get("/take/some-token").text == "<div id=root></div>"
        assert app_client.get("/favicon.svg").text == "<svg/>"
        assert app_client.get("/assets/app.js").text == "console.log(1)"
        assert app_client.get("/api/missing").status_code == 404


def test_seed_creates_a_working_demo(settings: Settings) -> None:
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    seed(sessionmaker(engine), settings)
    token = seed(sessionmaker(engine), settings)  # re-running reuses the demo recruiter
    with TestClient(create_app(settings, FakeLLM())) as app_client:
        login = app_client.post(
            "/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
        ).json()
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        assessments = app_client.get("/api/assessments", headers=headers).json()
        assert len(assessments) == 2
        assert assessments[0]["status"] == "published" and assessments[0]["question_count"] == 5
        assert app_client.get(f"/api/take/{token}").json()["candidate_name"] == "Sam Candidate"


def test_grading_job_fails_loudly_for_unknown_invite(settings: Settings) -> None:
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    with pytest.raises(LookupError):
        grade_submission(sessionmaker(engine), FakeLLM(), 12345)


def test_seed_main_prints_credentials(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    from app import seed as seed_module

    monkeypatch.setattr(seed_module, "Settings", lambda: settings)
    seed_module.main()
    output = capsys.readouterr().out
    assert DEMO_EMAIL in output and "/take/" in output


def test_access_log_redacts_invite_tokens() -> None:
    from app.main import RedactInviteTokens

    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s" %d',
        ("127.0.0.1", "POST", "/api/take/s3cret-Token_x/submit?a=1", 202),
        None,
    )
    assert RedactInviteTokens().filter(record)
    assert "s3cret" not in record.getMessage()
    assert "/api/take/<redacted>/submit?a=1" in record.getMessage()
