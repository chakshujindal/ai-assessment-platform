"""A deterministic stand-in for a real model, used by the tests and the no-API-key demo.

Every prompt we send embeds a machine-readable `REQUEST_JSON:` line (harmless context for
a real model). FakeLLM reads that line and builds valid JSON from small templates, so the
whole app runs offline and the same input always gives the same output.
"""

import json
import re
from collections import Counter
from typing import Any

REQUEST_LINE = re.compile(r"^REQUEST_JSON: (.+)$", re.MULTILINE)
MATERIAL_BLOCK = re.compile(r"<material>\n?(.*?)\n?</material>", re.DOTALL)
ANSWER_BLOCK = re.compile(r"<answer>\n?(.*?)\n?</answer>", re.DOTALL)
REFERENCE_BLOCK = re.compile(r"Reference answer:\n(.*?)\n\nRubric", re.DOTALL)
WORD = re.compile(r"[A-Za-z][A-Za-z-]+")
STOPWORDS = frozenset(
    "about after also because been before being between both could does each from have into "
    "just like make many more most much must only other over same should some such than that "
    "their them then there these they this those through under uses using very what when where "
    "which while will with would your".split()
)

MCQ_BANK = [
    (
        "Which practice most improves the long-term maintainability of {s} code?",
        [
            "Small, well-named functions covered by tests",
            "One large module that shares global state",
            "Copying similar logic wherever it is needed",
            "Skipping code review to ship faster",
        ],
        "Small, tested units are easier to read, change and verify.",
    ),
    (
        "A {s} feature fails only in production. What is the best first step?",
        [
            "Read the logs and reproduce it with production-like data",
            "Rewrite the feature from scratch",
            "Turn off monitoring to reduce noise",
            "Ask users to retry later",
        ],
        "Evidence first: logs and a reproduction show the real cause.",
    ),
    (
        "What is the main benefit of automated tests in {s} work?",
        [
            "They catch regressions before release",
            "They make the code run faster",
            "They replace the need for documentation",
            "They guarantee there are no bugs",
        ],
        "Tests protect behaviour that already works when the code changes.",
    ),
    (
        "How should a {s} service handle invalid input?",
        [
            "Validate it at the boundary and return a clear error",
            "Ignore it and carry on",
            "Crash the whole process",
            "Log it silently and report success",
        ],
        "Failing early with a clear message keeps bad data out and helps the caller fix it.",
    ),
    (
        "Before optimising a slow {s} code path, what should you do first?",
        [
            "Measure to find the real bottleneck",
            "Rewrite it in another language",
            "Add caching everywhere",
            "Buy bigger servers",
        ],
        "Profiling shows where time is actually spent, so effort goes to the right place.",
    ),
]

SHORT_BANK = [
    (
        "Explain how you would design error handling for a {s} service.",
        "Validate input at the boundary, return clear error responses with useful status "
        "codes, and log each failure once with request context.",
        [
            ("Validation", "Validates input at the boundary before processing", 2),
            ("Error responses", "Returns clear error messages and status codes", 2),
            ("Logging", "Logs failures with context such as request ids", 1),
        ],
    ),
    (
        "Describe how you would test a new {s} feature before release.",
        "Unit-test the core logic, add integration tests across the database or API "
        "boundary, cover edge cases and failure paths, and run everything in CI.",
        [
            ("Unit tests", "Uses unit tests for the core logic", 2),
            ("Integration tests", "Adds integration tests across the database or API", 2),
            ("Edge cases", "Covers edge cases and failure paths", 1),
        ],
    ),
    (
        "What trade-offs would you weigh when adding a cache to a {s} application?",
        "A cache cuts latency and load, but risks stale data, needs an invalidation "
        "strategy, and costs memory.",
        [
            ("Staleness", "Discusses stale data and cache invalidation", 2),
            ("Performance", "Explains the latency and load benefits", 2),
            ("Resources", "Mentions memory cost and eviction", 1),
        ],
    ),
]

CODING_BANK = [
    (
        "In a {s} project, write a function `dedupe(items)` that removes duplicates from a "
        "list, keeping the first occurrence of each item and the original order.",
        "def dedupe(items):\n    seen = set()\n    result = []\n    for item in items:\n"
        "        if item not in seen:\n            seen.add(item)\n"
        "            result.append(item)\n    return result\n",
        "Removes duplicates and preserves the original order",
    ),
    (
        "In a {s} project, write a function `word_counts(text)` that returns a dict mapping "
        "each lowercase word to the number of times it appears.",
        "def word_counts(text):\n    counts = {}\n    for word in text.lower().split():\n"
        "        counts[word] = counts.get(word, 0) + 1\n    return counts\n",
        "Counts each lowercase word correctly using a dict",
    ),
    (
        "In a {s} project, write a function `is_balanced(s)` that returns True when every "
        "bracket in s - (), [] and {{}} - is closed in the right order.",
        "def is_balanced(s):\n    pairs = {')': '(', ']': '[', '}': '{'}\n    stack = []\n"
        "    for ch in s:\n        if ch in '([{':\n            stack.append(ch)\n"
        "        elif ch in pairs:\n            if not stack or stack.pop() != pairs[ch]:\n"
        "                return False\n    return not stack\n",
        "Uses a stack to match each closing bracket to the latest opening one",
    ),
]


class FakeLLM:
    model_name = "fake-llm"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, system: str, prompt: str) -> str:
        self.calls += 1
        request = _read_request(prompt)
        if request["task"] == "generate_questions":
            material = _find(MATERIAL_BLOCK, prompt)
            questions = [_make_question(request, material, i) for i in range(request["count"])]
            return json.dumps({"questions": questions})
        if request["task"] == "grade_answer":
            answer, reference = _find(ANSWER_BLOCK, prompt), _find(REFERENCE_BLOCK, prompt)
            criteria = [_grade(c, answer, reference) for c in request["rubric"]]
            return json.dumps({"criteria": criteria})
        raise ValueError(f"FakeLLM cannot handle task {request['task']!r}")


def _read_request(prompt: str) -> dict[str, Any]:
    match = REQUEST_LINE.search(prompt)
    if match is None:
        raise ValueError("FakeLLM needs a REQUEST_JSON line in the prompt")
    return json.loads(match.group(1))


def _find(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _terms(text: str) -> list[str]:
    """Distinct lowercase content words, in order of first appearance."""
    words = [w.lower() for w in WORD.findall(text)]
    return list(dict.fromkeys(w for w in words if len(w) >= 4 and w not in STOPWORDS))


def _rotate(options: list[str], i: int) -> tuple[list[str], int]:
    """Rotate options so the correct one (index 0) lands in a different slot each time."""
    shift = i % len(options)
    return options[shift:] + options[:shift], (len(options) - shift) % len(options)


def _make_question(request: dict[str, Any], material: str, i: int) -> dict[str, Any]:
    kind = request["question_type"]
    subjects = request.get("skills") or [request.get("topic") or "software"]
    subject = subjects[i % len(subjects)]
    if material:
        from_notes = _question_from_material(kind, material, i)
        if from_notes is not None:
            return from_notes
        subject = request.get("topic") or "this topic"
    if kind == "mcq":
        prompt, options, explanation = MCQ_BANK[i % len(MCQ_BANK)]
        rotated, correct = _rotate(options, i)
        return {
            "type": "mcq",
            "prompt": prompt.format(s=subject),
            "options": rotated,
            "correct_index": correct,
            "explanation": explanation,
        }
    if kind == "short_answer":
        prompt, model_answer, rubric = SHORT_BANK[i % len(SHORT_BANK)]
        return {
            "type": "short_answer",
            "prompt": prompt.format(s=subject),
            "model_answer": model_answer,
            "rubric": [{"name": n, "description": d, "points": p} for n, d, p in rubric],
        }
    prompt, solution, correctness = CODING_BANK[i % len(CODING_BANK)]
    return {
        "type": "coding",
        "prompt": prompt.format(s=subject),
        "language": "python",
        "reference_solution": solution,
        "rubric": [
            {"name": "Correctness", "description": correctness, "points": 3},
            {"name": "Edge cases", "description": "Handles empty input and repeats", "points": 1},
            {
                "name": "Readability",
                "description": "Clear names and simple control flow",
                "points": 1,
            },
        ],
    }


def _question_from_material(kind: str, material: str, i: int) -> dict[str, Any] | None:
    """Build a cloze MCQ or a short-answer question from the learner's own notes."""
    sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", material) if len(WORD.findall(s)) >= 6
    ]
    if not sentences or kind == "coding":
        return None
    sentence = sentences[i % len(sentences)]
    ranked = [w for w, _ in Counter(_terms_all(material)).most_common()]
    in_sentence = [w for w in ranked if w in _terms(sentence) and len(w) >= 5]
    if not in_sentence:
        return None
    key = in_sentence[0]
    if kind == "short_answer":
        return {
            "type": "short_answer",
            "prompt": f'What do your notes say about "{key}"? Answer in two or three sentences.',
            "model_answer": sentence,
            "rubric": [
                {"name": "Key idea", "description": f"Explains {key} correctly", "points": 2},
                {"name": "Accuracy", "description": f"Agrees with: {sentence[:300]}", "points": 2},
            ],
        }
    distractors = [w for w in ranked if w not in _terms(sentence) and len(w) >= 5][:3]
    if len(distractors) < 3:
        return None
    blanked = re.sub(rf"\b{re.escape(key)}\b", "_____", sentence, count=1, flags=re.IGNORECASE)
    options, correct = _rotate([key, *distractors], i)
    return {
        "type": "mcq",
        "prompt": f'Fill in the blank from your notes: "{blanked}"',
        "options": options,
        "correct_index": correct,
        "explanation": f'Your notes say: "{sentence}"',
    }


def _terms_all(text: str) -> list[str]:
    """All content words including repeats, so they can be ranked by frequency."""
    words = [w.lower() for w in WORD.findall(text)]
    return [w for w in words if len(w) >= 4 and w not in STOPWORDS]


def _grade(criterion: dict[str, Any], answer: str, reference: str) -> dict[str, Any]:
    """Score a criterion by the key terms the answer mentions, or by how much of the
    reference answer's vocabulary it shares (which is what makes code answers score)."""
    terms = _terms(f"{criterion['name']} {criterion['description']}")
    text = answer.lower()
    hits = [term for term in terms if term[:6] in text]  # crude stemming: shared prefix
    keyword_share = min(1.0, len(hits) / max(1, min(3, len(terms))))
    reference_words = set(re.findall(r"[a-z_]{3,}", reference.lower()))
    overlap = len(reference_words & set(re.findall(r"[a-z_]{3,}", text)))
    reference_share = overlap / len(reference_words) if reference_words else 0.0
    score = round(criterion["points"] * max(keyword_share, reference_share))
    if reference_share > keyword_share:
        justification = f"Shares {reference_share:.0%} of the reference answer's key terms."
    elif hits:
        justification = f"Mentions {', '.join(hits[:3])}."
    else:
        justification = "Does not address this criterion."
    return {"name": criterion["name"], "score": score, "justification": justification}
