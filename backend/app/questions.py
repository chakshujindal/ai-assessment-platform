"""Question shapes shared by generation, editing, grading and the candidate view.

These Pydantic models are the single source of truth: LLM output, recruiter edits and
stored JSON are all validated against them.
"""

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator

MCQ_POINTS = 1


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class RubricCriterion(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=400)
    points: int = Field(ge=1, le=10)


class MCQQuestion(BaseModel):
    type: Literal["mcq"] = "mcq"
    prompt: str = Field(min_length=5, max_length=2000)
    options: list[str] = Field(min_length=3, max_length=6)
    correct_index: int = Field(ge=0)
    explanation: str = Field(min_length=1, max_length=1000)

    @field_validator("options")
    @classmethod
    def options_are_distinct(cls, options: list[str]) -> list[str]:
        cleaned = [option.strip() for option in options]
        if any(not option for option in cleaned):
            raise ValueError("options must not be empty")
        if len({option.lower() for option in cleaned}) != len(cleaned):
            raise ValueError("options must be distinct")
        return cleaned

    @model_validator(mode="after")
    def correct_index_in_range(self) -> "MCQQuestion":
        if self.correct_index >= len(self.options):
            raise ValueError("correct_index must point at one of the options")
        return self


class ShortAnswerQuestion(BaseModel):
    type: Literal["short_answer"] = "short_answer"
    prompt: str = Field(min_length=5, max_length=2000)
    model_answer: str = Field(min_length=1, max_length=3000)
    rubric: list[RubricCriterion] = Field(min_length=1, max_length=6)


class CodingQuestion(BaseModel):
    type: Literal["coding"] = "coding"
    prompt: str = Field(min_length=5, max_length=4000)
    language: str = Field(default="python", min_length=1, max_length=30)
    reference_solution: str = Field(min_length=1, max_length=6000)
    rubric: list[RubricCriterion] = Field(min_length=1, max_length=6)


Question = Annotated[
    MCQQuestion | ShortAnswerQuestion | CodingQuestion, Field(discriminator="type")
]
QuestionType = Literal["mcq", "short_answer", "coding"]
_question_adapter: TypeAdapter[Question] = TypeAdapter(Question)


def parse_question(data: dict[str, Any]) -> Question:
    """Validate a stored or submitted dict into the right question model."""
    return _question_adapter.validate_python(data)


def max_points(question: Question) -> int:
    if isinstance(question, MCQQuestion):
        return MCQ_POINTS
    return sum(criterion.points for criterion in question.rubric)


def candidate_view(question: Question) -> dict[str, Any]:
    """What a candidate or learner may see: no correct answer, explanation, rubric or solution."""
    view: dict[str, Any] = {
        "type": question.type,
        "prompt": question.prompt,
        "points": max_points(question),
    }
    if isinstance(question, MCQQuestion):
        view["options"] = question.options
    elif isinstance(question, CodingQuestion):
        view["language"] = question.language
    return view
