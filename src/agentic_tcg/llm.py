"""OpenAI chat model factory, structured-output helper, and LLM-facing schemas.

The LLM-facing schemas are kept separate from the domain models because OpenAI
strict structured output requires every field to be required and forbids
open-ended objects. So test data travels as a JSON string and is converted back.
"""

import json
from typing import Any, Literal, Protocol, TypeVar

from pydantic import BaseModel, Field

from agentic_tcg.config import get_settings
from agentic_tcg.models import TestCase, TestSuite

T = TypeVar("T", bound=BaseModel)

TestTypeLiteral = Literal["positive", "negative", "boundary", "edge"]
PriorityLiteral = Literal["high", "medium", "low"]


class StructuredLLM(Protocol):
    """Anything with LangChain's `with_structured_output` (a ChatOpenAI, or a fake in tests)."""

    def with_structured_output(self, schema: type, **kwargs: Any) -> Any: ...


def get_chat_model(model: str | None = None, temperature: float = 0.0):
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model or get_settings().generation_model, temperature=temperature)


def invoke_structured(
    llm: StructuredLLM, schema: type[T], system: str, user: str, config: dict[str, Any] | None = None
) -> T:
    """`config` is a LangChain RunnableConfig (run_name, tags, metadata, run_id) used for LangSmith tracing."""
    runnable = llm.with_structured_output(schema, method="json_schema", strict=True)
    return runnable.invoke([("system", system), ("human", user)], config=config)


# ---------- LLM-facing schemas ----------

class LLMTestCase(BaseModel):
    id: str = Field(description="Test id, e.g. R1-TC01")
    title: str
    type: TestTypeLiteral
    priority: PriorityLiteral
    preconditions: list[str]
    steps: list[str]
    test_data_json: str = Field(description='Concrete test data as a JSON object string, "{}" if none')
    expected_result: str = Field(description="Verifiable outcome: exact values, statuses or error codes")
    covers: list[str] = Field(description="Acceptance criterion ids verified by this test")


class LLMUntestable(BaseModel):
    ac_id: str
    reason: str


class LLMTestSuite(BaseModel):
    test_cases: list[LLMTestCase]
    clarification_questions: list[str] = Field(description="Ambiguities or gaps to raise with the BA/PO")
    untestable_acs: list[LLMUntestable] = Field(description="Acceptance criteria that cannot be tested as written")


def parse_test_data(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw) if raw and raw.strip() else {}
    except json.JSONDecodeError:
        return {"raw": raw}
    return data if isinstance(data, dict) else {"value": data}


def to_test_case(tc: LLMTestCase) -> TestCase:
    return TestCase(
        id=tc.id,
        title=tc.title,
        type=tc.type,
        priority=tc.priority,
        preconditions=tc.preconditions,
        steps=tc.steps,
        test_data=parse_test_data(tc.test_data_json),
        expected_result=tc.expected_result,
        covers=tc.covers,
    )


def renumber(requirement_id: str, cases: list[TestCase]) -> list[TestCase]:
    """Give test cases stable, unique ids: R1-TC01, R1-TC02, ..."""
    return [c.model_copy(update={"id": f"{requirement_id}-TC{i:02d}"}) for i, c in enumerate(cases, 1)]


def to_test_suite(requirement_id: str, out: LLMTestSuite) -> TestSuite:
    return TestSuite(
        requirement_id=requirement_id,
        test_cases=renumber(requirement_id, [to_test_case(tc) for tc in out.test_cases]),
        clarification_questions=out.clarification_questions,
        untestable_acs={u.ac_id: u.reason for u in out.untestable_acs},
    )
