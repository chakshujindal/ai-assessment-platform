"""Recruiter assessment builder: settings, LLM generation, review/edit, publish, invites."""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from app.db import utcnow
from app.deps import CurrentRecruiter, DbSession, LLMDep, SettingsDep
from app.models import Assessment, Invite
from app.models import Question as QuestionRow
from app.questions import Question
from app.ratelimit import DEFAULT_LIMIT, LLM_LIMIT, limiter
from app.routers.common import invite_out, owned_assessment, question_out
from app.schemas import (
    AssessmentOut,
    AssessmentSettings,
    AssessmentSummary,
    GenerateOut,
    InviteCreate,
    InviteCreated,
    InviteOut,
)
from app.security import new_invite_token
from app.services.generation import PROMPT_VERSION, GenerationRequest, generate_questions

router = APIRouter(prefix="/api/assessments", tags=["assessments"])


def _assessment_out(assessment: Assessment) -> AssessmentOut:
    return AssessmentOut(
        id=assessment.id,
        title=assessment.title,
        status=assessment.status,
        duration_minutes=assessment.duration_minutes,
        snapshot_interval_seconds=assessment.snapshot_interval_seconds,
        require_seb=assessment.require_seb,
        seb_browser_exam_key=assessment.seb_browser_exam_key,
        created_at=assessment.created_at,
        questions=[question_out(row) for row in assessment.questions],
    )


def _require_draft(assessment: Assessment) -> None:
    if assessment.status != "draft":
        raise HTTPException(409, "This assessment is published, so it can no longer change.")


@router.get("")
@limiter.limit(DEFAULT_LIMIT)
def list_assessments(
    request: Request, db: DbSession, recruiter: CurrentRecruiter
) -> list[AssessmentSummary]:
    rows = db.scalars(
        select(Assessment).where(Assessment.owner_id == recruiter.id).order_by(Assessment.id.desc())
    )
    return [
        AssessmentSummary(
            id=a.id,
            title=a.title,
            status=a.status,
            duration_minutes=a.duration_minutes,
            question_count=len(a.questions),
            invite_count=len(a.invites),
            created_at=a.created_at,
        )
        for a in rows
    ]


@router.post("", status_code=201)
@limiter.limit(DEFAULT_LIMIT)
def create_assessment(
    request: Request, body: AssessmentSettings, db: DbSession, recruiter: CurrentRecruiter
) -> AssessmentOut:
    assessment = Assessment(owner_id=recruiter.id, **body.model_dump())
    db.add(assessment)
    db.commit()
    return _assessment_out(assessment)


@router.get("/{assessment_id}")
@limiter.limit(DEFAULT_LIMIT)
def get_assessment(
    request: Request, assessment_id: int, db: DbSession, recruiter: CurrentRecruiter
) -> AssessmentOut:
    return _assessment_out(owned_assessment(db, assessment_id, recruiter))


@router.put("/{assessment_id}")
@limiter.limit(DEFAULT_LIMIT)
def update_assessment(
    request: Request,
    assessment_id: int,
    body: AssessmentSettings,
    db: DbSession,
    recruiter: CurrentRecruiter,
) -> AssessmentOut:
    assessment = owned_assessment(db, assessment_id, recruiter)
    _require_draft(assessment)
    for field, value in body.model_dump().items():
        setattr(assessment, field, value)
    db.commit()
    return _assessment_out(assessment)


@router.post("/{assessment_id}/generate")
@limiter.limit(LLM_LIMIT)
def generate(
    request: Request,
    assessment_id: int,
    body: GenerationRequest,
    db: DbSession,
    recruiter: CurrentRecruiter,
    llm: LLMDep,
    settings: SettingsDep,
) -> GenerateOut:
    assessment = owned_assessment(db, assessment_id, recruiter)
    _require_draft(assessment)
    existing = [row.payload["prompt"] for row in assessment.questions]
    result = generate_questions(llm, body, existing, settings.dedup_threshold)
    rows = [
        QuestionRow(position=len(existing) + i, payload=question.model_dump())
        for i, question in enumerate(result.questions)
    ]
    assessment.questions.extend(rows)
    db.commit()
    return GenerateOut(
        added=[question_out(row) for row in rows],
        duplicates_removed=result.duplicates_removed,
        model_name=llm.model_name,
        prompt_version=PROMPT_VERSION,
    )


def _owned_question(assessment: Assessment, question_id: int) -> QuestionRow:
    row = next((q for q in assessment.questions if q.id == question_id), None)
    if row is None:
        raise HTTPException(404, "Question not found.")
    return row


@router.put("/{assessment_id}/questions/{question_id}")
@limiter.limit(DEFAULT_LIMIT)
def edit_question(
    request: Request,
    assessment_id: int,
    question_id: int,
    question: Question,
    db: DbSession,
    recruiter: CurrentRecruiter,
) -> AssessmentOut:
    assessment = owned_assessment(db, assessment_id, recruiter)
    _require_draft(assessment)
    _owned_question(assessment, question_id).payload = question.model_dump()
    db.commit()
    return _assessment_out(assessment)


@router.delete("/{assessment_id}/questions/{question_id}", status_code=204)
@limiter.limit(DEFAULT_LIMIT)
def delete_question(
    request: Request,
    assessment_id: int,
    question_id: int,
    db: DbSession,
    recruiter: CurrentRecruiter,
) -> Response:
    assessment = owned_assessment(db, assessment_id, recruiter)
    _require_draft(assessment)
    assessment.questions.remove(_owned_question(assessment, question_id))
    for position, row in enumerate(assessment.questions):
        row.position = position
    db.commit()
    return Response(status_code=204)


@router.post("/{assessment_id}/publish")
@limiter.limit(DEFAULT_LIMIT)
def publish(
    request: Request, assessment_id: int, db: DbSession, recruiter: CurrentRecruiter
) -> AssessmentOut:
    assessment = owned_assessment(db, assessment_id, recruiter)
    _require_draft(assessment)
    if not assessment.questions:
        raise HTTPException(409, "Add at least one question before publishing.")
    assessment.status = "published"
    db.commit()
    return _assessment_out(assessment)


@router.post("/{assessment_id}/invites", status_code=201)
@limiter.limit(DEFAULT_LIMIT)
def create_invite(
    request: Request,
    assessment_id: int,
    body: InviteCreate,
    db: DbSession,
    recruiter: CurrentRecruiter,
    settings: SettingsDep,
) -> InviteCreated:
    assessment = owned_assessment(db, assessment_id, recruiter)
    if assessment.status != "published":
        raise HTTPException(409, "Publish the assessment before inviting candidates.")
    token, token_hash = new_invite_token()
    hours = body.expires_in_hours or settings.invite_ttl_hours
    invite = Invite(
        candidate_name=body.candidate_name.strip(),
        candidate_email=body.candidate_email.lower(),
        token_hash=token_hash,
        expires_at=utcnow() + timedelta(hours=hours),
    )
    assessment.invites.append(invite)
    db.commit()
    summary = invite_out(invite, settings.submit_grace_seconds)
    return InviteCreated(**summary.model_dump(), token=token, link_path=f"/take/{token}")


@router.get("/{assessment_id}/invites")
@limiter.limit(DEFAULT_LIMIT)
def list_invites(
    request: Request,
    assessment_id: int,
    db: DbSession,
    recruiter: CurrentRecruiter,
    settings: SettingsDep,
) -> list[InviteOut]:
    assessment = owned_assessment(db, assessment_id, recruiter)
    return [invite_out(invite, settings.submit_grace_seconds) for invite in assessment.invites]
