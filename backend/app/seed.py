"""Seed demo data: a recruiter, a published sample assessment and one candidate invite.

Always uses FakeLLM, so it needs no API key. Run: python -m app.seed
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import Base, make_engine, utcnow
from app.llm.fake import FakeLLM
from app.models import Assessment, Invite, Question, Recruiter
from app.security import hash_password, new_invite_token
from app.services.generation import GenerationRequest, QuestionMix, generate_questions

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-password"


def seed(session_factory: sessionmaker[Session], settings: Settings) -> str:
    """Create the demo data and return the raw invite token for the candidate link."""
    with session_factory() as db:
        recruiter = db.scalar(select(Recruiter).where(Recruiter.email == DEMO_EMAIL))
        if recruiter is None:
            recruiter = Recruiter(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD))
            db.add(recruiter)
            db.flush()
        request = GenerationRequest(
            topic="Backend engineering",
            skills=["Python", "REST APIs", "SQL"],
            mix=QuestionMix(mcq=3, short_answer=1, coding=1),
        )
        generated = generate_questions(FakeLLM(), request, [], settings.dedup_threshold)
        assessment = Assessment(
            owner_id=recruiter.id,
            title="Backend Engineer Screening (demo)",
            status="published",
            duration_minutes=20,
            snapshot_interval_seconds=15,
            questions=[
                Question(position=i, payload=q.model_dump())
                for i, q in enumerate(generated.questions)
            ],
        )
        token, token_hash = new_invite_token()
        assessment.invites.append(
            Invite(
                candidate_name="Sam Candidate",
                candidate_email="sam@example.com",
                token_hash=token_hash,
                expires_at=utcnow() + timedelta(hours=settings.invite_ttl_hours),
            )
        )
        db.add(assessment)
        db.commit()
        return token


def main() -> None:
    settings = Settings()
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    token = seed(sessionmaker(engine), settings)
    print(f"Recruiter login : {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print(f"Candidate link  : http://localhost:8000/take/{token}")


if __name__ == "__main__":
    main()
