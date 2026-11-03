"""Auth, the assessment builder, invites, and rate limiting over HTTP."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ratelimit import limiter
from tests.conftest import register


def test_register_login_and_me(client: TestClient) -> None:
    headers = register(client, "Lead@Example.com")
    assert client.get("/api/auth/me", headers=headers).json() == {"email": "lead@example.com"}
    again = client.post(
        "/api/auth/register", json={"email": "lead@example.com", "password": "secret-pass"}
    )
    assert again.status_code == 409
    good = client.post(
        "/api/auth/login", json={"email": "LEAD@example.com", "password": "secret-pass"}
    )
    assert good.status_code == 200 and good.json()["token_type"] == "bearer"
    bad = client.post(
        "/api/auth/login", json={"email": "lead@example.com", "password": "wrong-pass"}
    )
    assert bad.status_code == 401


def test_protected_routes_need_a_valid_token(client: TestClient) -> None:
    assert client.get("/api/assessments").status_code == 401
    garbage = {"Authorization": "Bearer not-a-jwt"}
    assert client.get("/api/assessments", headers=garbage).status_code == 401


def test_token_for_deleted_user_is_rejected(client: TestClient, settings: Any) -> None:
    from app.security import create_access_token

    token = create_access_token(999, settings.jwt_secret, 5)
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_login_is_rate_limited_with_retry_after(client: TestClient) -> None:
    limiter.enabled = True
    try:
        body = {"email": "x@example.com", "password": "wrong-pass"}
        statuses = [client.post("/api/auth/login", json=body).status_code for _ in range(11)]
        assert statuses[:10] == [401] * 10
        assert statuses[10] == 429
        blocked = client.post("/api/auth/login", json=body)
        assert int(blocked.headers["Retry-After"]) == 60
    finally:
        limiter.enabled = False


def test_health_is_rate_limited_too(client: TestClient) -> None:
    limiter.enabled = True
    try:
        statuses = {client.get("/api/health").status_code for _ in range(121)}
        assert statuses == {200, 429}
    finally:
        limiter.enabled = False


def test_create_list_and_update_settings(client: TestClient, auth: dict[str, str]) -> None:
    created = client.post("/api/assessments", json={"title": "Data role"}, headers=auth)
    assert created.status_code == 201
    assessment_id = created.json()["id"]
    update = {"title": "Data role v2", "duration_minutes": 45, "snapshot_interval_seconds": 0}
    updated = client.put(f"/api/assessments/{assessment_id}", json=update, headers=auth)
    assert updated.json()["duration_minutes"] == 45
    listing = client.get("/api/assessments", headers=auth).json()
    assert listing[0]["title"] == "Data role v2" and listing[0]["question_count"] == 0


def test_settings_validation(client: TestClient, auth: dict[str, str]) -> None:
    seb_without_key = {"title": "T", "require_seb": True}
    assert client.post("/api/assessments", json=seb_without_key, headers=auth).status_code == 422
    tiny_interval = {"title": "T", "snapshot_interval_seconds": 3}
    assert client.post("/api/assessments", json=tiny_interval, headers=auth).status_code == 422


def test_generate_then_regenerate_dedupes(
    client: TestClient, auth: dict[str, str], draft: dict[str, Any]
) -> None:
    assert [q["question"]["type"] for q in draft["questions"]] == [
        "mcq",
        "mcq",
        "short_answer",
        "coding",
    ]
    body = {
        "topic": "Backend",
        "skills": ["Python"],
        "mix": {"mcq": 2, "short_answer": 1, "coding": 1},
    }
    again = client.post(f"/api/assessments/{draft['id']}/generate", json=body, headers=auth).json()
    assert again["added"] == [] and again["duplicates_removed"] == 4
    assert again["model_name"] == "fake-llm" and again["prompt_version"] == "generate-v1"


def test_generation_failure_is_a_502_with_details_only_in_the_log(
    client: TestClient, auth: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    from tests.conftest import ScriptedLLM

    client.app.state.llm = ScriptedLLM("not json", "still not json")  # type: ignore[attr-defined]
    created = client.post("/api/assessments", json={"title": "T"}, headers=auth).json()
    with caplog.at_level("ERROR", logger="app.main"):
        response = client.post(
            f"/api/assessments/{created['id']}/generate", json={"topic": "Go"}, headers=auth
        )
    assert response.status_code == 502
    assert response.json()["detail"] == "The AI step failed. Please try again in a moment."
    assert "still invalid after one repair" in caplog.text


def test_every_route_has_an_explicit_rate_limit() -> None:
    from app.routers import assessments, auth, candidate, practice, results

    endpoints = [
        route.endpoint
        for module in (assessments, auth, candidate, practice, results)
        for route in module.router.routes
    ]
    limited = set(limiter._route_limits)  # slowapi's registry of decorated endpoints
    missing = [e.__name__ for e in endpoints if f"{e.__module__}.{e.__name__}" not in limited]
    assert missing == []


def test_candidate_routes_are_rate_limited(client: TestClient, invite: dict[str, Any]) -> None:
    limiter.enabled = True
    try:
        statuses = {client.get(f"/api/take/{invite['token']}").status_code for _ in range(121)}
        assert statuses == {200, 429}
    finally:
        limiter.enabled = False


def test_edit_and_delete_questions(
    client: TestClient, auth: dict[str, str], draft: dict[str, Any]
) -> None:
    first = draft["questions"][0]
    edited = {**first["question"], "prompt": "Which option is correct here?", "correct_index": 2}
    url = f"/api/assessments/{draft['id']}/questions/{first['id']}"
    response = client.put(url, json=edited, headers=auth)
    assert response.json()["questions"][0]["question"]["prompt"] == "Which option is correct here?"
    invalid = {**edited, "correct_index": 9}
    assert client.put(url, json=invalid, headers=auth).status_code == 422
    assert client.delete(url, headers=auth).status_code == 204
    remaining = client.get(f"/api/assessments/{draft['id']}", headers=auth).json()["questions"]
    assert [q["position"] for q in remaining] == [0, 1, 2]
    assert client.delete(url, headers=auth).status_code == 404


def test_publish_locks_the_assessment(
    client: TestClient, auth: dict[str, str], published: dict[str, Any]
) -> None:
    assessment_id = published["id"]
    assert published["status"] == "published"
    locked = client.put(f"/api/assessments/{assessment_id}", json={"title": "New"}, headers=auth)
    assert locked.status_code == 409
    again = client.post(f"/api/assessments/{assessment_id}/publish", headers=auth)
    assert again.status_code == 409


def test_cannot_publish_empty_or_invite_to_draft(client: TestClient, auth: dict[str, str]) -> None:
    created = client.post("/api/assessments", json={"title": "Empty"}, headers=auth).json()
    assert client.post(f"/api/assessments/{created['id']}/publish", headers=auth).status_code == 409
    body = {"candidate_name": "A", "candidate_email": "a@example.com"}
    invite = client.post(f"/api/assessments/{created['id']}/invites", json=body, headers=auth)
    assert invite.status_code == 409


def test_invites_are_listed_without_tokens(
    client: TestClient, auth: dict[str, str], invite: dict[str, Any], published: dict[str, Any]
) -> None:
    assert invite["link_path"] == f"/take/{invite['token']}"
    listing = client.get(f"/api/assessments/{published['id']}/invites", headers=auth).json()
    assert listing[0]["status"] == "invited" and "token" not in listing[0]


def test_other_recruiters_cannot_see_your_work(
    client: TestClient, published: dict[str, Any], invite: dict[str, Any]
) -> None:
    intruder = register(client, "intruder@example.com")
    assert client.get(f"/api/assessments/{published['id']}", headers=intruder).status_code == 404
    result = client.get(f"/api/invites/{invite['id']}/result", headers=intruder)
    assert result.status_code == 404
