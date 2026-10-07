"""Run the baseline or the agent for a requirement, and save/load the results."""

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from agentic_tcg.agent import build_agent
from agentic_tcg.baseline import generate_baseline
from agentic_tcg.config import OUTPUTS_DIR, get_settings
from agentic_tcg.llm import StructuredLLM, get_chat_model
from agentic_tcg.models import Requirement, TestSuite, load_requirement, save_json
from agentic_tcg.renderers import to_gherkin, to_markdown_table, to_pytest, traceability_markdown
from agentic_tcg.retriever import KnowledgeBase
from agentic_tcg.traceability import build_traceability

Mode = Literal["baseline", "agent"]
MODES: tuple[Mode, ...] = ("baseline", "agent")


class GenerationResult(BaseModel):
    mode: Mode
    requirement_id: str
    model: str
    suite: TestSuite
    retrieved_contexts: list[str] = []
    trace: list[dict[str, Any]] = []
    llm_calls: int
    elapsed_seconds: float
    created_at: str


class CountingLLM:
    """Wraps a structured-output LLM and counts invocations."""

    def __init__(self, llm: StructuredLLM):
        self.llm, self.calls = llm, 0

    def with_structured_output(self, schema: type, **kwargs: Any) -> Any:
        bound, outer = self.llm.with_structured_output(schema, **kwargs), self

        class _Counted:
            def invoke(self, messages: Any) -> Any:
                outer.calls += 1
                return bound.invoke(messages)

        return _Counted()


def run_baseline(requirement: Requirement, llm: StructuredLLM | None = None) -> GenerationResult:
    counter = CountingLLM(llm or get_chat_model())
    start = time.perf_counter()
    suite = generate_baseline(requirement, counter)
    return GenerationResult(
        mode="baseline", requirement_id=requirement.id, model=get_settings().generation_model, suite=suite,
        llm_calls=counter.calls, elapsed_seconds=round(time.perf_counter() - start, 2),
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def run_agent(
    requirement: Requirement, llm: StructuredLLM | None = None, kb: KnowledgeBase | None = None
) -> GenerationResult:
    counter = CountingLLM(llm or get_chat_model())
    start = time.perf_counter()
    graph = build_agent(counter, kb or KnowledgeBase())
    state = graph.invoke({"requirement": requirement, "trace": []})
    return GenerationResult(
        mode="agent", requirement_id=requirement.id, model=get_settings().generation_model, suite=state["suite"],
        retrieved_contexts=[c.as_context() for c in state["chunks"]], trace=state["trace"],
        llm_calls=counter.calls, elapsed_seconds=round(time.perf_counter() - start, 2),
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def result_dir(mode: Mode, root: Path = OUTPUTS_DIR) -> Path:
    return root / mode


def save_result(result: GenerationResult, root: Path = OUTPUTS_DIR) -> Path:
    """Write the result JSON plus Gherkin, pytest, table and traceability renderings."""
    req = load_requirement(result.requirement_id)
    out = result_dir(result.mode, root)
    rid = result.requirement_id
    save_json(result, out / f"{rid}.json")
    (out / "features").mkdir(parents=True, exist_ok=True)
    (out / "features" / f"{rid}.feature").write_text(to_gherkin(req, result.suite))
    (out / "pytest").mkdir(parents=True, exist_ok=True)
    (out / "pytest" / f"test_{rid.lower()}_generated.py").write_text(to_pytest(req, result.suite))
    trace = build_traceability(req, result.suite)
    (out / f"{rid}.md").write_text(
        f"# {rid}: {req.title} ({result.mode})\n\n## Test cases\n\n{to_markdown_table(result.suite)}\n\n"
        f"## Traceability (coverage {trace.coverage:.0%})\n\n{traceability_markdown(trace)}\n\n"
        "## Clarification questions\n\n" + ("\n".join(f"- {q}" for q in result.suite.clarification_questions) or "_None_") + "\n"
    )
    return out / f"{rid}.json"


def load_result(mode: Mode, requirement_id: str, root: Path = OUTPUTS_DIR) -> GenerationResult | None:
    path = result_dir(mode, root) / f"{requirement_id}.json"
    return GenerationResult.model_validate_json(path.read_text()) if path.exists() else None
