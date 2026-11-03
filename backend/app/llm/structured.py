"""Ask an LLM for JSON and validate it with Pydantic, allowing exactly one repair attempt."""

import re
from collections.abc import Callable

from pydantic import BaseModel

from app.llm.base import LLMClient, LLMOutputError

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> str:
    """Pull the JSON object out of a reply that may be wrapped in prose or a code fence."""
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object found in the model reply")
    return text[start : end + 1]


def parse_reply[M: BaseModel](
    text: str, schema: type[M], check: Callable[[M], None] | None = None
) -> M:
    """Validate a reply against the schema, then run any extra domain check."""
    result = schema.model_validate_json(extract_json(text))
    if check is not None:
        check(result)
    return result


def complete_json[M: BaseModel](
    llm: LLMClient,
    system: str,
    prompt: str,
    schema: type[M],
    check: Callable[[M], None] | None = None,
) -> M:
    """Call the model; if the reply is invalid, show it the error once and ask for a fix."""
    reply = llm.complete(system, prompt)
    try:
        return parse_reply(reply, schema, check)
    except ValueError as first_error:  # pydantic.ValidationError is a ValueError too
        repair_prompt = (
            f"{prompt}\n\nYour previous reply was invalid: {_short(first_error)}\n"
            f"Previous reply:\n{reply[:3000]}\n\n"
            "Reply again with ONLY the corrected JSON object."
        )
        second_reply = llm.complete(system, repair_prompt)
        try:
            return parse_reply(second_reply, schema, check)
        except ValueError as second_error:
            raise LLMOutputError(
                f"{schema.__name__} output was still invalid after one repair attempt: "
                f"{_short(second_error)}"
            ) from second_error


def _short(error: Exception, limit: int = 500) -> str:
    return str(error).replace("\n", " ")[:limit]
