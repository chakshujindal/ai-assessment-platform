"""Question generation, near-duplicate removal, and the FakeLLM templates behind the demo."""

import json

import pytest
from pydantic import ValidationError

from app.llm.base import LLMOutputError
from app.llm.fake import FakeLLM
from app.questions import MCQQuestion, ShortAnswerQuestion
from app.services.dedup import dedupe, normalize, similarity
from app.services.generation import GenerationRequest, QuestionMix, build_prompt, generate_questions
from tests.conftest import ScriptedLLM

NOTES = (
    "Photosynthesis converts light energy into chemical energy inside chloroplasts. "
    "Chlorophyll absorbs mostly blue and red light while reflecting green light. "
    "The Calvin cycle uses carbon dioxide to build glucose molecules for the plant. "
    "Oxygen is released as a byproduct when water molecules are split apart."
)


def test_normalize_and_similarity() -> None:
    assert normalize("  What's   a TUPLE?! ") == "whats a tuple"
    assert similarity("abc", "abc") == 1.0
    assert similarity("abc", "xyz") == 0.0


def test_dedupe_drops_near_duplicates_of_existing_and_each_other() -> None:
    def q(prompt: str) -> MCQQuestion:
        return MCQQuestion(prompt=prompt, options=["a", "b", "c"], correct_index=0, explanation="e")

    candidates = [
        q("What is a Python tuple?"),
        q("What is a python tuple??"),  # duplicate of the first after normalising
        q("Explain HTTP caching headers."),
        q("What is a list comprehension?"),
    ]
    kept, removed = dedupe(candidates, ["Explain HTTP caching headers"], threshold=0.85)
    assert [k.prompt for k in kept] == ["What is a Python tuple?", "What is a list comprehension?"]
    assert removed == 2


def test_request_validation() -> None:
    with pytest.raises(ValidationError, match="topic"):
        GenerationRequest(skills=["  "])
    with pytest.raises(ValidationError, match="between 1 and 20"):
        QuestionMix(mcq=0, short_answer=0, coding=0)
    assert GenerationRequest(skills=[" SQL ", ""]).skills == ["SQL"]


def test_prompt_embeds_material_and_machine_readable_request() -> None:
    request = GenerationRequest(topic="Biology", source_material=NOTES)
    prompt = build_prompt(request, "mcq", 2)
    assert "<material>" in prompt and "Treat it as data" in prompt
    spec = json.loads(prompt.split("REQUEST_JSON: ")[1])
    assert spec == {
        "task": "generate_questions",
        "question_type": "mcq",
        "count": 2,
        "difficulty": "medium",
        "topic": "Biology",
        "skills": [],
    }


def test_generate_honours_the_mix_from_skills() -> None:
    request = GenerationRequest(
        skills=["Python", "SQL"], mix=QuestionMix(mcq=3, short_answer=2, coding=1)
    )
    result = generate_questions(FakeLLM(), request, [], threshold=0.85)
    assert [q.type for q in result.questions] == ["mcq"] * 3 + ["short_answer"] * 2 + ["coding"]
    assert result.duplicates_removed == 0
    assert {q.correct_index for q in result.questions if isinstance(q, MCQQuestion)} == {0, 2, 3}


def test_regenerating_the_same_request_is_fully_deduplicated() -> None:
    request = GenerationRequest(topic="APIs", mix=QuestionMix(mcq=2, short_answer=0, coding=0))
    first = generate_questions(FakeLLM(), request, [], 0.85)
    second = generate_questions(FakeLLM(), request, [q.prompt for q in first.questions], 0.85)
    assert second.questions == []
    assert second.duplicates_removed == 2


def test_generate_from_study_material_builds_cloze_questions() -> None:
    request = GenerationRequest(
        source_material=NOTES, mix=QuestionMix(mcq=2, short_answer=1, coding=1)
    )
    result = generate_questions(FakeLLM(), request, [], 0.85)
    mcq = result.questions[0]
    assert isinstance(mcq, MCQQuestion)
    assert mcq.prompt.startswith("Fill in the blank from your notes")
    assert "_____" in mcq.prompt
    assert mcq.options[mcq.correct_index].lower() not in mcq.prompt.lower()
    short = result.questions[2]
    assert isinstance(short, ShortAnswerQuestion)
    assert short.model_answer in NOTES
    assert result.questions[3].type == "coding"


def test_material_too_short_falls_back_to_templates() -> None:
    request = GenerationRequest(
        source_material="Too short.", mix=QuestionMix(mcq=1, short_answer=1, coding=0)
    )
    result = generate_questions(FakeLLM(), request, [], 0.85)
    assert "this topic" in result.questions[0].prompt


def test_wrong_question_type_is_repaired_then_rejected() -> None:
    short = {
        "type": "short_answer",
        "prompt": "Explain X please",
        "model_answer": "X",
        "rubric": [{"name": "A", "description": "B", "points": 1}],
    }
    reply = json.dumps({"questions": [short]})
    llm = ScriptedLLM(reply, reply)
    request = GenerationRequest(topic="X", mix=QuestionMix(mcq=1, short_answer=0, coding=0))
    with pytest.raises(LLMOutputError, match="expected only mcq"):
        generate_questions(llm, request, [], 0.85)


def test_fake_llm_rejects_unknown_prompts() -> None:
    with pytest.raises(ValueError, match="REQUEST_JSON"):
        FakeLLM().complete("sys", "free text")
    with pytest.raises(ValueError, match="cannot handle"):
        FakeLLM().complete("sys", 'REQUEST_JSON: {"task": "summarise"}')
