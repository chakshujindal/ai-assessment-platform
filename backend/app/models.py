"""SQLAlchemy tables. An Invite is one candidate's single-use seat and also holds their attempt."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime, utcnow


class Recruiter(Base):
    __tablename__ = "recruiters"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("recruiters.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | published
    duration_minutes: Mapped[int] = mapped_column(default=30)
    snapshot_interval_seconds: Mapped[int] = mapped_column(default=30)  # 0 disables webcam
    require_seb: Mapped[bool] = mapped_column(default=False)
    seb_browser_exam_key: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    questions: Mapped[list["Question"]] = relationship(
        order_by="Question.position", cascade="all, delete-orphan"
    )
    invites: Mapped[list["Invite"]] = relationship(
        back_populates="assessment", order_by="Invite.id", cascade="all, delete-orphan"
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    position: Mapped[int]
    # Validated with app.questions.parse_question on every write and read.
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    candidate_name: Mapped[str] = mapped_column(String(120))
    candidate_email: Mapped[str] = mapped_column(String(255))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # invited -> in_progress -> submitted -> graded
    status: Mapped[str] = mapped_column(String(20), default="invited")
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    consented_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    deadline_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    assessment: Mapped[Assessment] = relationship(back_populates="invites")
    answers: Mapped[list["Answer"]] = relationship(
        order_by="Answer.id", cascade="all, delete-orphan"
    )
    events: Mapped[list["ProctorEvent"]] = relationship(
        order_by="ProctorEvent.id", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list["Snapshot"]] = relationship(
        order_by="Snapshot.id", cascade="all, delete-orphan"
    )


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    invite_id: Mapped[int] = mapped_column(ForeignKey("invites.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    response: Mapped[str] = mapped_column(Text, default="")
    max_score: Mapped[float]
    # AI (or automatic) grade, kept even after a recruiter override for auditability.
    ai_score: Mapped[float | None]
    criteria: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    feedback: Mapped[str | None] = mapped_column(Text)
    graded_by: Mapped[str | None] = mapped_column(String(10))  # auto | llm
    model_name: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    grading_error: Mapped[str | None] = mapped_column(Text)
    override_score: Mapped[float | None]
    override_note: Mapped[str | None] = mapped_column(Text)
    overridden_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    question: Mapped[Question] = relationship()

    @property
    def final_score(self) -> float | None:
        return self.override_score if self.override_score is not None else self.ai_score


class ProctorEvent(Base):
    __tablename__ = "proctor_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    invite_id: Mapped[int] = mapped_column(ForeignKey("invites.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    detail: Mapped[str] = mapped_column(String(200), default="")
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    invite_id: Mapped[int] = mapped_column(ForeignKey("invites.id"), index=True)
    file_path: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(30))
    taken_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PracticeQuiz(Base):
    __tablename__ = "practice_quizzes"

    # Random id so quizzes cannot be enumerated; practice needs no login.
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
