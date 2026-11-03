"""Background grading of a submitted attempt (runs after the submit response is sent)."""

import logging

from sqlalchemy.orm import Session, sessionmaker

from app.llm.base import LLMClient
from app.models import Answer, Invite
from app.questions import Question, parse_question
from app.services.grading import GradeResult, grade_answer

logger = logging.getLogger(__name__)
GRADING_FAILED = "AI grading failed; please score this answer yourself."


def grade_submission(
    session_factory: sessionmaker[Session], llm: LLMClient, invite_id: int
) -> None:
    """Read the answers, grade them with no DB transaction open, then write all results.

    Holding a transaction during slow LLM calls would lock SQLite for every other request.
    """
    with session_factory() as db:
        invite = _load(db, invite_id)
        pending = [(a.id, parse_question(a.question.payload), a.response) for a in invite.answers]

    outcomes = {
        answer_id: _grade_safely(llm, invite_id, answer_id, question, response)
        for answer_id, question, response in pending
    }

    with session_factory() as db:
        invite = _load(db, invite_id)
        for answer in invite.answers:
            _store(answer, outcomes[answer.id])
        invite.status = "graded"
        db.commit()


def _load(db: Session, invite_id: int) -> Invite:
    invite = db.get(Invite, invite_id)
    if invite is None:
        raise LookupError(f"invite {invite_id} disappeared before grading")
    return invite


def _grade_safely(
    llm: LLMClient, invite_id: int, answer_id: int, question: Question, response: str
) -> GradeResult | None:
    """Job boundary: one failing answer is logged and left for the recruiter, not fatal."""
    try:
        return grade_answer(llm, question, response)
    except Exception:  # logged with traceback; the recruiter scores this answer by hand
        logger.exception("Grading failed: invite=%s answer=%s", invite_id, answer_id)
        return None


def _store(answer: Answer, result: GradeResult | None) -> None:
    if result is None:
        answer.grading_error = GRADING_FAILED
        return
    answer.ai_score = result.score
    answer.criteria = result.criteria
    answer.feedback = result.feedback
    answer.graded_by = result.graded_by
    answer.model_name = result.model_name
    answer.prompt_version = result.prompt_version
    answer.grading_error = None
