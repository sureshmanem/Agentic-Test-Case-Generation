"""Run the baseline or the agent for a requirement, and save/load the results."""

import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from agentic_tcg.agent import build_agent
from agentic_tcg.baseline import generate_baseline
from agentic_tcg import config
from agentic_tcg.config import get_settings, tracing_enabled
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
    run_id: str | None = None  # root run id; also the LangSmith trace id when `traced`
    traced: bool = False


class CountingLLM:
    """Wraps a structured-output LLM and counts invocations."""

    def __init__(self, llm: StructuredLLM):
        self.llm, self.calls = llm, 0

    def with_structured_output(self, schema: type, **kwargs: Any) -> Any:
        bound, outer = self.llm.with_structured_output(schema, **kwargs), self

        class _Counted:
            def invoke(self, messages: Any, config: Any = None) -> Any:
                outer.calls += 1
                return bound.invoke(messages, config=config)

        return _Counted()


def run_config(mode: Mode, requirement: Requirement, run_id: str) -> dict[str, Any]:
    """RunnableConfig that names and tags the root run, so LangSmith traces are easy to find and filter."""
    return {
        "run_id": uuid.UUID(run_id),
        "run_name": f"{mode} {requirement.id}",
        "tags": [mode, requirement.id],
        "metadata": {"mode": mode, "requirement_id": requirement.id, "requirement_title": requirement.title,
                     "generation_model": get_settings().generation_model},
    }


def run_baseline(requirement: Requirement, llm: StructuredLLM | None = None) -> GenerationResult:
    counter = CountingLLM(llm or get_chat_model())
    run_id = str(uuid.uuid4())
    start = time.perf_counter()
    suite = generate_baseline(requirement, counter, config=run_config("baseline", requirement, run_id))
    return GenerationResult(
        mode="baseline", requirement_id=requirement.id, model=get_settings().generation_model, suite=suite,
        llm_calls=counter.calls, elapsed_seconds=round(time.perf_counter() - start, 2),
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        run_id=run_id, traced=tracing_enabled(),
    )


def run_agent(
    requirement: Requirement,
    llm: StructuredLLM | None = None,
    kb: KnowledgeBase | None = None,
    on_step: Callable[[dict[str, Any]], None] | None = None,
) -> GenerationResult:
    """Run the agent graph. `on_step` receives each trace entry as soon as its node finishes."""
    counter = CountingLLM(llm or get_chat_model())
    run_id = str(uuid.uuid4())
    start = time.perf_counter()
    graph = build_agent(counter, kb or KnowledgeBase())
    state: dict[str, Any] = {}
    seen = 0
    config = run_config("agent", requirement, run_id)
    for state in graph.stream({"requirement": requirement, "trace": []}, config=config, stream_mode="values"):
        for entry in state.get("trace", [])[seen:]:
            if on_step:
                on_step(entry)
        seen = len(state.get("trace", []))
    return GenerationResult(
        mode="agent", requirement_id=requirement.id, model=get_settings().generation_model, suite=state["suite"],
        retrieved_contexts=[c.as_context() for c in state["chunks"]], trace=state["trace"],
        llm_calls=counter.calls, elapsed_seconds=round(time.perf_counter() - start, 2),
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        run_id=run_id, traced=tracing_enabled(),
    )


def result_dir(mode: Mode, root: Path | None = None) -> Path:
    return (root or config.OUTPUTS_DIR) / mode


def save_result(result: GenerationResult, root: Path | None = None) -> Path:
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


def load_result(mode: Mode, requirement_id: str, root: Path | None = None) -> GenerationResult | None:
    path = result_dir(mode, root) / f"{requirement_id}.json"
    return GenerationResult.model_validate_json(path.read_text()) if path.exists() else None
