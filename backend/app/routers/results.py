"""Recruiter results: per-answer grades, score overrides, integrity summary, webcam snapshots."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.db import utcnow
from app.deps import CurrentRecruiter, DbSession, SettingsDep
from app.models import Answer, Invite
from app.questions import parse_question
from app.ratelimit import DEFAULT_LIMIT, limiter
from app.routers.common import invite_out, owned_invite
from app.schemas import AnswerOut, OverrideIn, ResultAnswer, ResultOut, SnapshotOut
from app.services.integrity import EventRecord, IntegritySummary, summarize

router = APIRouter(prefix="/api", tags=["results"])


def _integrity(invite: Invite) -> IntegritySummary | None:
    if invite.started_at is None:
        return None
    ended_at = invite.submitted_at or min(utcnow(), invite.deadline_at or utcnow())
    return summarize(
        [EventRecord(kind=e.kind, at=e.occurred_at, detail=e.detail) for e in invite.events],
        started_at=invite.started_at,
        ended_at=ended_at,
        snapshots_received=len(invite.snapshots),
        snapshot_interval_seconds=invite.assessment.snapshot_interval_seconds,
    )


@router.get("/invites/{invite_id}/result")
@limiter.limit(DEFAULT_LIMIT)
def get_result(
    request: Request,
    invite_id: int,
    db: DbSession,
    recruiter: CurrentRecruiter,
    settings: SettingsDep,
) -> ResultOut:
    invite = owned_invite(db, invite_id, recruiter)
    answers = [
        ResultAnswer(
            **AnswerOut.model_validate(answer).model_dump(),
            question=parse_question(answer.question.payload),
        )
        for answer in invite.answers
    ]
    return ResultOut(
        assessment_id=invite.assessment_id,
        assessment_title=invite.assessment.title,
        invite=invite_out(invite, settings.submit_grace_seconds),
        answers=answers,
        integrity=_integrity(invite),
        snapshots=[SnapshotOut.model_validate(s) for s in invite.snapshots],
    )


@router.post("/answers/{answer_id}/override")
@limiter.limit(DEFAULT_LIMIT)
def override_score(
    request: Request, answer_id: int, body: OverrideIn, db: DbSession, recruiter: CurrentRecruiter
) -> AnswerOut:
    """Set the recruiter's score. The AI score stays stored next to it for audit."""
    answer = db.get(Answer, answer_id)
    if answer is None:
        raise HTTPException(404, "Answer not found.")
    owned_invite(db, answer.invite_id, recruiter)  # 404 unless this recruiter owns it
    if body.score > answer.max_score:
        raise HTTPException(422, f"Score cannot exceed {answer.max_score:g} points.")
    answer.override_score = body.score
    answer.override_note = body.note.strip() or None
    answer.overridden_at = utcnow()
    db.commit()
    return AnswerOut.model_validate(answer)


@router.get("/invites/{invite_id}/snapshots/{snapshot_id}")
@limiter.limit(DEFAULT_LIMIT)
def get_snapshot(
    request: Request, invite_id: int, snapshot_id: int, db: DbSession, recruiter: CurrentRecruiter
) -> FileResponse:
    invite = owned_invite(db, invite_id, recruiter)
    snapshot = next((s for s in invite.snapshots if s.id == snapshot_id), None)
    if snapshot is None or not Path(snapshot.file_path).is_file():
        raise HTTPException(404, "Snapshot not found.")
    return FileResponse(snapshot.file_path, media_type=snapshot.content_type)
