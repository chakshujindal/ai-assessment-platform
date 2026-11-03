"""Practice mode: no login; a learner gets a quiz from notes or a topic and instant feedback."""

from fastapi import APIRouter, HTTPException, Request

from app.deps import DbSession, LLMDep, SettingsDep
from app.models import PracticeQuiz
from app.questions import MCQQuestion, Question, ShortAnswerQuestion, candidate_view, parse_question
from app.ratelimit import LLM_LIMIT, limiter
from app.schemas import CheckIn, CheckOut, PracticeQuestion, PracticeQuizOut
from app.services.generation import GenerationRequest, generate_questions
from app.services.grading import grade_answer

router = APIRouter(prefix="/api/practice", tags=["practice"])


def reference_answer(question: Question) -> str:
    """What the learner sees after checking: the right option, model answer or solution."""
    if isinstance(question, MCQQuestion):
        return question.options[question.correct_index]
    if isinstance(question, ShortAnswerQuestion):
        return question.model_answer
    return question.reference_solution


@router.post("/quizzes", status_code=201)
@limiter.limit(LLM_LIMIT)
def create_quiz(
    request: Request, body: GenerationRequest, db: DbSession, llm: LLMDep, settings: SettingsDep
) -> PracticeQuizOut:
    result = generate_questions(llm, body, [], settings.dedup_threshold)
    quiz = PracticeQuiz(questions=[question.model_dump() for question in result.questions])
    db.add(quiz)
    db.commit()
    return PracticeQuizOut(
        id=quiz.id,
        questions=[
            PracticeQuestion(index=i, **candidate_view(q)) for i, q in enumerate(result.questions)
        ],
        duplicates_removed=result.duplicates_removed,
    )


@router.post("/quizzes/{quiz_id}/check")
@limiter.limit(LLM_LIMIT)
def check_answer(
    request: Request, quiz_id: str, body: CheckIn, db: DbSession, llm: LLMDep
) -> CheckOut:
    quiz = db.get(PracticeQuiz, quiz_id)
    if quiz is None or body.index >= len(quiz.questions):
        raise HTTPException(404, "Question not found.")
    question = parse_question(quiz.questions[body.index])
    result = grade_answer(llm, question, body.response)
    return CheckOut(
        score=result.score,
        max_score=result.max_score,
        correct=result.correct,
        feedback=result.feedback,
        criteria=result.criteria,
        reference=reference_answer(question),
    )
