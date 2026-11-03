"""The candidate flow end to end: consent, timed test, proctoring, submit, grading, results."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.db import utcnow
from app.jobs import GRADING_FAILED
from app.models import Invite
from app.routers import candidate
from app.seb import request_hash
from tests.conftest import FailingLLM

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100


def take(invite: dict[str, Any], path: str = "") -> str:
    return f"/api/take/{invite['token']}{path}"


def start(client: TestClient, invite: dict[str, Any]) -> dict[str, Any]:
    response = client.post(take(invite, "/start"), json={"consent": True})
    assert response.status_code == 200, response.text
    return response.json()


def answers_for(paper: dict[str, Any]) -> list[dict[str, Any]]:
    """Correct MCQ index is unknown to the candidate; pick 0 and write real prose."""
    prose = "I validate input at the boundary and return clear error messages, with unit tests."
    return [
        {"question_id": q["id"], "response": "0" if q["type"] == "mcq" else prose}
        for q in paper["questions"]
    ]


def set_invite(client: TestClient, invite_id: int, **values: Any) -> None:
    with client.app.state.session_factory() as db:  # type: ignore[attr-defined]
        db.execute(update(Invite).where(Invite.id == invite_id).values(**values))
        db.commit()


def test_result_before_start_has_no_integrity_yet(
    client: TestClient, auth: dict[str, str], invite: dict[str, Any]
) -> None:
    result = client.get(f"/api/invites/{invite['id']}/result", headers=auth).json()
    assert result["integrity"] is None and result["answers"] == []
    assert result["invite"]["score"] is None


def test_info_before_start(client: TestClient, invite: dict[str, Any]) -> None:
    info = client.get(take(invite)).json()
    assert info["status"] == "invited"
    assert info["question_count"] == 4
    assert info["remaining_seconds"] is None
    assert client.get("/api/take/not-a-real-token").status_code == 404


def test_start_requires_consent(client: TestClient, invite: dict[str, Any]) -> None:
    assert client.post(take(invite, "/start"), json={"consent": False}).status_code == 422
    assert client.post(take(invite, "/events"), json={"kind": "copy"}).status_code == 409


def test_paper_hides_answers_and_resumes_after_reload(
    client: TestClient, invite: dict[str, Any]
) -> None:
    paper = start(client, invite)
    assert 0 < paper["remaining_seconds"] <= 30 * 60
    serialized = str(paper)
    for secret in ("correct_index", "explanation", "rubric", "reference_solution", "model_answer"):
        assert secret not in serialized
    resumed = start(client, invite)
    assert [q["id"] for q in resumed["questions"]] == [q["id"] for q in paper["questions"]]
    assert client.get(take(invite)).json()["status"] == "in_progress"


def test_full_attempt_is_graded_and_reviewable(
    client: TestClient, auth: dict[str, str], invite: dict[str, Any]
) -> None:
    paper = start(client, invite)
    for kind in ("tab_hidden", "tab_visible", "paste", "fullscreen_exit"):
        assert client.post(take(invite, "/events"), json={"kind": kind}).status_code == 204
    assert client.post(take(invite, "/events"), json={"kind": "telepathy"}).status_code == 422
    upload = {"file": ("snap.jpg", JPEG, "image/jpeg")}
    assert client.post(take(invite, "/snapshots"), files=upload).status_code == 204

    submitted = client.post(take(invite, "/submit"), json={"answers": answers_for(paper)})
    assert submitted.status_code == 202

    result = client.get(f"/api/invites/{invite['id']}/result", headers=auth).json()
    assert result["invite"]["status"] == "graded"
    assert result["invite"]["max_score"] == sum(q["points"] for q in paper["questions"])
    rubric_answers = [a for a in result["answers"] if a["graded_by"] == "llm"]
    assert len(rubric_answers) == 2
    assert all(
        a["model_name"] == "fake-llm" and a["prompt_version"] == "grade-v1" for a in rubric_answers
    )
    assert all(c["justification"] for a in rubric_answers for c in a["criteria"])
    integrity = result["integrity"]
    assert integrity["counts"]["paste"] == 1
    assert integrity["snapshots_received"] == 1
    assert [e["kind"] for e in integrity["timeline"]][:2] == ["tab_hidden", "tab_visible"]

    snapshot_id = result["snapshots"][0]["id"]
    image = client.get(f"/api/invites/{invite['id']}/snapshots/{snapshot_id}", headers=auth)
    assert image.content == JPEG and image.headers["content-type"] == "image/jpeg"
    missing = client.get(f"/api/invites/{invite['id']}/snapshots/999", headers=auth)
    assert missing.status_code == 404


def test_invite_is_single_use(client: TestClient, invite: dict[str, Any]) -> None:
    paper = start(client, invite)
    assert (
        client.post(take(invite, "/submit"), json={"answers": answers_for(paper)}).status_code
        == 202
    )
    assert client.post(take(invite, "/submit"), json={"answers": []}).status_code == 409
    assert client.post(take(invite, "/start"), json={"consent": True}).status_code == 409


def test_racing_submit_is_rejected_by_the_atomic_claim(
    client: TestClient, invite: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    start(client, invite)
    assert client.post(take(invite, "/submit"), json={"answers": []}).status_code == 202
    monkeypatch.setattr(candidate, "_require_in_progress", lambda invite, grace: None)
    assert client.post(take(invite, "/submit"), json={"answers": []}).status_code == 409


def test_expired_invite_cannot_start(client: TestClient, invite: dict[str, Any]) -> None:
    set_invite(client, invite["id"], expires_at=utcnow() - timedelta(minutes=1))
    assert client.get(take(invite)).json()["status"] == "expired"
    assert client.post(take(invite, "/start"), json={"consent": True}).status_code == 409


def test_submission_after_deadline_and_grace_is_refused(
    client: TestClient, auth: dict[str, str], invite: dict[str, Any]
) -> None:
    start(client, invite)
    set_invite(client, invite["id"], deadline_at=utcnow() - timedelta(minutes=5))
    response = client.post(take(invite, "/submit"), json={"answers": []})
    assert response.status_code == 409 and "timed_out" in response.json()["detail"]
    result = client.get(f"/api/invites/{invite['id']}/result", headers=auth).json()
    assert result["invite"]["status"] == "timed_out"
    assert result["integrity"] is not None


def test_snapshot_validation(client: TestClient, invite: dict[str, Any], settings: Any) -> None:
    start(client, invite)
    text_file = {"file": ("notes.txt", b"hello", "text/plain")}
    assert client.post(take(invite, "/snapshots"), files=text_file).status_code == 415
    huge = {"file": ("big.jpg", b"0" * (settings.snapshot_max_bytes + 1), "image/jpeg")}
    assert client.post(take(invite, "/snapshots"), files=huge).status_code == 413


def test_grading_failure_is_recorded_and_recruiter_can_override(
    client: TestClient, auth: dict[str, str], invite: dict[str, Any]
) -> None:
    paper = start(client, invite)
    client.app.state.llm = FailingLLM()  # type: ignore[attr-defined]
    client.post(take(invite, "/submit"), json={"answers": answers_for(paper)})
    result = client.get(f"/api/invites/{invite['id']}/result", headers=auth).json()
    assert result["invite"]["status"] == "needs_review"
    failed = [a for a in result["answers"] if a["grading_error"]]
    assert len(failed) == 2 and failed[0]["ai_score"] is None
    assert failed[0]["grading_error"] == GRADING_FAILED  # provider details stay in the log

    target = failed[0]
    url = f"/api/answers/{target['id']}/override"
    too_high = client.post(url, json={"score": target["max_score"] + 1}, headers=auth)
    assert too_high.status_code == 422
    ok = client.post(url, json={"score": 2, "note": "  Solid answer  "}, headers=auth).json()
    assert ok["final_score"] == 2 and ok["override_note"] == "Solid answer"
    assert ok["ai_score"] is None
    assert (
        client.post("/api/answers/999/override", json={"score": 1}, headers=auth).status_code == 404
    )


def test_seb_required_assessment_checks_the_request_hash(
    client: TestClient, auth: dict[str, str], settings: Any
) -> None:
    key = "a" * 64
    body = {"title": "Locked down", "require_seb": True, "seb_browser_exam_key": key}
    assessment = client.post("/api/assessments", json=body, headers=auth).json()
    client.post(
        f"/api/assessments/{assessment['id']}/generate", json={"topic": "SQL"}, headers=auth
    )
    client.post(f"/api/assessments/{assessment['id']}/publish", headers=auth)
    created = client.post(
        f"/api/assessments/{assessment['id']}/invites",
        json={"candidate_name": "B", "candidate_email": "b@example.com"},
        headers=auth,
    ).json()

    path = f"/api/take/{created['token']}"
    blocked = client.get(path)
    assert blocked.status_code == 403 and "Safe Exam Browser" in blocked.json()["detail"]
    good = request_hash(f"http://testserver{path}", key)
    assert client.get(path, headers={"X-SafeExamBrowser-RequestHash": good}).status_code == 200

    settings.public_base_url = "https://exams.example.com"
    behind_proxy = request_hash(f"https://exams.example.com{path}", key)
    ok = client.get(path, headers={"X-SafeExamBrowser-RequestHash": behind_proxy})
    assert ok.status_code == 200
