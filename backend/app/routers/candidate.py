"""Candidate side, authorised only by the invite token in the URL.

Flow: GET info -> POST start (with consent) -> proctoring events/snapshots -> POST submit.
"""

from datetime import timedelta
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from sqlalchemy import select, update

from app import seb
from app.db import utcnow
from app.deps import DbSession, SettingsDep
from app.jobs import grade_submission
from app.models import Answer, Invite, ProctorEvent, Snapshot
from app.questions import candidate_view, max_points, parse_question
from app.ratelimit import DEFAULT_LIMIT, SNAPSHOT_LIMIT, SUBMIT_LIMIT, limiter
from app.routers.common import effective_status
from app.schemas import EventIn, PaperQuestion, StartIn, SubmitIn, TakeInfo, TestPaper
from app.security import hash_invite_token

router = APIRouter(prefix="/api/take/{token}", tags=["candidate"])

IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png"}


def candidate_invite(token: str, request: Request, db: DbSession, settings: SettingsDep) -> Invite:
    """Resolve the invite from its token and enforce Safe Exam Browser when required."""
    invite = db.scalar(select(Invite).where(Invite.token_hash == hash_invite_token(token)))
    if invite is None:
        raise HTTPException(404, "This invite link is not valid.")
    assessment = invite.assessment
    if assessment.require_seb:
        url = seb.public_url(str(request.url), settings.public_base_url)
        header = request.headers.get(seb.HEADER)
        if not seb.verify_request_hash(url, assessment.seb_browser_exam_key or "", header):
            raise HTTPException(
                403, "This assessment must be taken in Safe Exam Browser using the provided config."
            )
    return invite


CandidateInvite = Annotated[Invite, Depends(candidate_invite)]


def _remaining_seconds(invite: Invite) -> int | None:
    if invite.deadline_at is None or invite.submitted_at is not None:
        return None
    return max(0, int((invite.deadline_at - utcnow()).total_seconds()))


def _require_in_progress(invite: Invite, grace_seconds: int) -> None:
    status = effective_status(invite, grace_seconds)
    if status != "in_progress":
        raise HTTPException(409, f"The test is not in progress (status: {status}).")


@router.get("")
@limiter.limit(DEFAULT_LIMIT)
def info(request: Request, invite: CandidateInvite, settings: SettingsDep) -> TakeInfo:
    assessment = invite.assessment
    return TakeInfo(
        assessment_title=assessment.title,
        candidate_name=invite.candidate_name,
        status=effective_status(invite, settings.submit_grace_seconds),
        duration_minutes=assessment.duration_minutes,
        question_count=len(assessment.questions),
        snapshot_interval_seconds=assessment.snapshot_interval_seconds,
        remaining_seconds=_remaining_seconds(invite),
    )


@router.post("/start")
@limiter.limit(DEFAULT_LIMIT)
def start(
    request: Request, body: StartIn, invite: CandidateInvite, db: DbSession, settings: SettingsDep
) -> TestPaper:
    """Start the timer on first call; later calls resume the same attempt (e.g. after a reload)."""
    status = effective_status(invite, settings.submit_grace_seconds)
    if status == "invited":
        now = utcnow()
        invite.consented_at = invite.started_at = now
        invite.deadline_at = now + timedelta(minutes=invite.assessment.duration_minutes)
        invite.status = "in_progress"
        db.commit()
    elif status != "in_progress":
        raise HTTPException(409, f"This invite can no longer be used (status: {status}).")
    questions = [
        PaperQuestion(id=row.id, **candidate_view(parse_question(row.payload)))
        for row in invite.assessment.questions
    ]
    return TestPaper(
        questions=questions,
        remaining_seconds=_remaining_seconds(invite) or 0,
        snapshot_interval_seconds=invite.assessment.snapshot_interval_seconds,
    )


@router.post("/events", status_code=204)
@limiter.limit(DEFAULT_LIMIT)
def record_event(
    request: Request, body: EventIn, invite: CandidateInvite, db: DbSession, settings: SettingsDep
) -> Response:
    _require_in_progress(invite, settings.submit_grace_seconds)
    db.add(ProctorEvent(invite_id=invite.id, kind=body.kind, detail=body.detail))
    db.commit()
    return Response(status_code=204)


@router.post("/snapshots", status_code=204)
@limiter.limit(SNAPSHOT_LIMIT)
def upload_snapshot(
    request: Request,
    file: UploadFile,
    invite: CandidateInvite,
    db: DbSession,
    settings: SettingsDep,
) -> Response:
    _require_in_progress(invite, settings.submit_grace_seconds)
    content_type = file.content_type or ""
    if content_type not in IMAGE_TYPES:
        raise HTTPException(415, "Snapshots must be JPEG or PNG images.")
    data = file.file.read(settings.snapshot_max_bytes + 1)
    if len(data) > settings.snapshot_max_bytes:
        raise HTTPException(413, "Snapshot is too large.")
    folder = Path(settings.snapshot_dir) / str(invite.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid4().hex}{IMAGE_TYPES[content_type]}"
    path.write_bytes(data)
    db.add(Snapshot(invite_id=invite.id, file_path=str(path), content_type=content_type))
    db.commit()
    return Response(status_code=204)


@router.post("/submit", status_code=202)
@limiter.limit(SUBMIT_LIMIT)
def submit(
    request: Request,
    body: SubmitIn,
    invite: CandidateInvite,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> dict[str, str]:
    """Store the answers, close the attempt for good, and grade in the background."""
    _require_in_progress(invite, settings.submit_grace_seconds)
    # Claim the attempt atomically so two racing submits cannot both store answers.
    claimed = db.execute(
        update(Invite)
        .where(Invite.id == invite.id, Invite.status == "in_progress")
        .values(status="submitted", submitted_at=utcnow())
    )
    if claimed.rowcount != 1:
        raise HTTPException(409, "This test was already submitted.")
    responses = {answer.question_id: answer.response for answer in body.answers}
    for row in invite.assessment.questions:
        db.add(
            Answer(
                invite_id=invite.id,
                question_id=row.id,
                response=responses.get(row.id, ""),
                max_score=max_points(parse_question(row.payload)),
            )
        )
    db.commit()
    background.add_task(
        grade_submission, request.app.state.session_factory, request.app.state.llm, invite.id
    )
    return {"status": "submitted"}
