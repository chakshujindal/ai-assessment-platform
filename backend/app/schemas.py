"""Request and response bodies for the HTTP API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.questions import Question
from app.services.integrity import EventKind, IntegritySummary


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str


class AssessmentSettings(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    duration_minutes: int = Field(default=30, ge=1, le=240)
    snapshot_interval_seconds: int = Field(default=30, ge=0, le=600)
    require_seb: bool = False
    seb_browser_exam_key: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def check_proctoring(self) -> "AssessmentSettings":
        if 0 < self.snapshot_interval_seconds < 10:
            raise ValueError("snapshot interval must be 0 (off) or at least 10 seconds")
        if self.require_seb and not (self.seb_browser_exam_key or "").strip():
            raise ValueError("a Browser Exam Key is required when Safe Exam Browser is required")
        return self


class QuestionOut(BaseModel):
    id: int
    position: int
    question: Question


class AssessmentSummary(BaseModel):
    id: int
    title: str
    status: str
    duration_minutes: int
    question_count: int
    invite_count: int
    created_at: datetime


class AssessmentOut(AssessmentSettings):
    id: int
    status: str
    created_at: datetime
    questions: list[QuestionOut]


class GenerateOut(BaseModel):
    added: list[QuestionOut]
    duplicates_removed: int
    model_name: str
    prompt_version: str


class InviteCreate(BaseModel):
    candidate_name: str = Field(min_length=1, max_length=120)
    candidate_email: EmailStr
    expires_in_hours: int | None = Field(default=None, ge=1, le=720)


class InviteOut(BaseModel):
    id: int
    candidate_name: str
    candidate_email: str
    status: str
    expires_at: datetime
    started_at: datetime | None
    submitted_at: datetime | None
    score: float | None
    max_score: float | None


class InviteCreated(InviteOut):
    token: str = Field(description="Shown once; only its hash is stored.")
    link_path: str


class AnswerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_id: int
    response: str
    max_score: float
    ai_score: float | None
    final_score: float | None
    criteria: list[dict[str, Any]] | None
    feedback: str | None
    graded_by: str | None
    model_name: str | None
    prompt_version: str | None
    grading_error: str | None
    override_score: float | None
    override_note: str | None
    overridden_at: datetime | None


class ResultAnswer(AnswerOut):
    question: Question


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    taken_at: datetime


class ResultOut(BaseModel):
    assessment_id: int
    assessment_title: str
    invite: InviteOut
    answers: list[ResultAnswer]
    integrity: IntegritySummary | None
    snapshots: list[SnapshotOut]


class OverrideIn(BaseModel):
    score: float = Field(ge=0)
    note: str = Field(default="", max_length=500)


class TakeInfo(BaseModel):
    assessment_title: str
    candidate_name: str
    status: str
    duration_minutes: int
    question_count: int
    snapshot_interval_seconds: int
    remaining_seconds: int | None


class StartIn(BaseModel):
    consent: Literal[True] = Field(description="The candidate agreed to the proctoring terms.")


class PaperQuestion(BaseModel):
    id: int
    type: str
    prompt: str
    points: int
    options: list[str] | None = None
    language: str | None = None


class TestPaper(BaseModel):
    questions: list[PaperQuestion]
    remaining_seconds: int
    snapshot_interval_seconds: int


class EventIn(BaseModel):
    kind: EventKind
    detail: str = Field(default="", max_length=200)


class AnswerIn(BaseModel):
    question_id: int
    response: str = Field(default="", max_length=20_000)


class SubmitIn(BaseModel):
    answers: list[AnswerIn] = Field(max_length=200)


class PracticeQuestion(BaseModel):
    index: int
    type: str
    prompt: str
    points: int
    options: list[str] | None = None
    language: str | None = None


class PracticeQuizOut(BaseModel):
    id: str
    questions: list[PracticeQuestion]
    duplicates_removed: int


class CheckIn(BaseModel):
    index: int = Field(ge=0)
    response: str = Field(max_length=20_000)


class CheckOut(BaseModel):
    score: float
    max_score: float
    correct: bool | None
    feedback: str
    criteria: list[dict[str, Any]] | None
    reference: str
