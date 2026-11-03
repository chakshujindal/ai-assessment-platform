"""Ownership checks and ORM -> response conversions shared by the recruiter routers."""

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Assessment, Invite, Recruiter
from app.models import Question as QuestionRow
from app.questions import parse_question
from app.schemas import InviteOut, QuestionOut


def owned_assessment(db: Session, assessment_id: int, recruiter: Recruiter) -> Assessment:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.owner_id != recruiter.id:
        raise HTTPException(404, "Assessment not found.")
    return assessment


def owned_invite(db: Session, invite_id: int, recruiter: Recruiter) -> Invite:
    invite = db.get(Invite, invite_id)
    if invite is None or invite.assessment.owner_id != recruiter.id:
        raise HTTPException(404, "Candidate not found.")
    return invite


def question_out(row: QuestionRow) -> QuestionOut:
    return QuestionOut(id=row.id, position=row.position, question=parse_question(row.payload))


def effective_status(invite: Invite, grace_seconds: int, now: datetime | None = None) -> str:
    """Stored status, plus the two states that only exist because time passed."""
    now = now or utcnow()
    if invite.status == "invited" and now > invite.expires_at:
        return "expired"
    if (
        invite.status == "in_progress"
        and invite.deadline_at is not None
        and now > invite.deadline_at + timedelta(seconds=grace_seconds)
    ):
        return "timed_out"
    return invite.status


def invite_out(invite: Invite, grace_seconds: int) -> InviteOut:
    graded = invite.status == "graded"
    scores = [answer.final_score for answer in invite.answers]
    status = effective_status(invite, grace_seconds)
    if graded and None in scores:
        status = "needs_review"  # some answers still need a human score
    return InviteOut(
        id=invite.id,
        candidate_name=invite.candidate_name,
        candidate_email=invite.candidate_email,
        status=status,
        expires_at=invite.expires_at,
        started_at=invite.started_at,
        submitted_at=invite.submitted_at,
        score=sum(s or 0 for s in scores) if graded else None,
        max_score=sum(answer.max_score for answer in invite.answers) if graded else None,
    )
