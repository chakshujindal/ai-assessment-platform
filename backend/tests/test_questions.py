import pytest
from pydantic import ValidationError

from app.questions import (
    CodingQuestion,
    MCQQuestion,
    ShortAnswerQuestion,
    candidate_view,
    max_points,
    parse_question,
)

RUBRIC = [{"name": "Accuracy", "description": "Correct facts", "points": 3}]


def mcq(**overrides: object) -> dict[str, object]:
    data = {
        "type": "mcq",
        "prompt": "What is 2 + 2?",
        "options": ["3", "4", "5"],
        "correct_index": 1,
        "explanation": "Basic sums.",
    }
    return {**data, **overrides}


def test_parse_picks_the_right_model() -> None:
    assert isinstance(parse_question(mcq()), MCQQuestion)
    short = {"type": "short_answer", "prompt": "Explain X", "model_answer": "X", "rubric": RUBRIC}
    assert isinstance(parse_question(short), ShortAnswerQuestion)
    code = {"type": "coding", "prompt": "Write f()", "reference_solution": "...", "rubric": RUBRIC}
    assert isinstance(parse_question(code), CodingQuestion)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"correct_index": 3}, "correct_index"),
        ({"options": ["a", "A", "b"]}, "distinct"),
        ({"options": ["a", " ", "b"]}, "empty"),
    ],
)
def test_invalid_mcq_is_rejected(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        parse_question(mcq(**overrides))


def test_max_points_and_candidate_view_hide_answers() -> None:
    question = parse_question(mcq())
    assert max_points(question) == 1
    view = candidate_view(question)
    assert view == {
        "type": "mcq",
        "prompt": "What is 2 + 2?",
        "points": 1,
        "options": ["3", "4", "5"],
    }

    code = parse_question(
        {"type": "coding", "prompt": "Write f()", "reference_solution": "secret", "rubric": RUBRIC}
    )
    assert max_points(code) == 3
    assert candidate_view(code) == {
        "type": "coding",
        "prompt": "Write f()",
        "points": 3,
        "language": "python",
    }
