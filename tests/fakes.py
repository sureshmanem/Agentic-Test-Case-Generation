"""Test doubles: a fake structured-output LLM, so the pipeline runs offline."""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel


class FakeLLM:
    """Mimics `ChatOpenAI.with_structured_output(...).invoke(messages)`.

    `handler(schema, system, user)` returns an instance of `schema`. Every call is recorded.
    """

    def __init__(self, handler: Callable[[type, str, str], BaseModel]):
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    def with_structured_output(self, schema: type, **kwargs: Any) -> "_Bound":
        return _Bound(self, schema, kwargs)


class _Bound:
    def __init__(self, llm: FakeLLM, schema: type, kwargs: dict[str, Any]):
        self.llm, self.schema, self.kwargs = llm, schema, kwargs

    def invoke(self, messages: list[tuple[str, str]], config: dict[str, Any] | None = None) -> BaseModel:
        system = next(text for role, text in messages if role == "system")
        user = next(text for role, text in messages if role == "human")
        self.llm.calls.append({"schema": self.schema.__name__, "system": system, "user": user, "kwargs": self.kwargs,
                               "config": config})
        result = self.llm.handler(self.schema, system, user)
        assert isinstance(result, self.schema), f"handler returned {type(result)} for {self.schema}"
        return result
