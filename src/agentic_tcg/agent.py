"""LangGraph agent: analyse -> retrieve -> plan -> generate -> review <-> revise -> finalize."""

import json
import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from agentic_tcg import prompts
from agentic_tcg.config import get_settings
from agentic_tcg.llm import (
    LLMTestCase,
    LLMUntestable,
    StructuredLLM,
    TestTypeLiteral,
    invoke_structured,
    renumber,
    to_test_case,
)
from agentic_tcg.models import Requirement, TestSuite
from agentic_tcg.retriever import Chunk, KnowledgeBase


# ---------- LLM-facing schemas for the agent nodes ----------

class Analysis(BaseModel):
    summary: str
    clarification_questions: list[str]
    untestable_acs: list[LLMUntestable]
    search_queries: list[str]


class TestCondition(BaseModel):
    __test__ = False

    id: str = Field(description="C1, C2, ...")
    ac_ids: list[str]
    type: TestTypeLiteral
    description: str
    source: str = Field(description="Acceptance criterion id or knowledge document name")


class Plan(BaseModel):
    conditions: list[TestCondition]
    skipped_existing: list[str] = Field(description="Existing regression test ids that already cover a condition")
    untestable_acs: list[LLMUntestable] = Field(
        description="Acceptance criteria that remain untestable after reading the domain knowledge")


class AgentTestCase(LLMTestCase):
    condition_ids: list[str]


class GeneratedTests(BaseModel):
    test_cases: list[AgentTestCase]


class ReviewIssue(BaseModel):
    test_id: str
    problem: str
    fix: str


class Review(BaseModel):
    issues: list[ReviewIssue]
    missing_conditions: list[TestCondition]


class Revision(BaseModel):
    test_cases: list[AgentTestCase] = Field(description="Replacement tests (same id) and new tests")
    remove_test_ids: list[str]


# ---------- graph state ----------

class AgentState(TypedDict, total=False):
    requirement: Requirement
    analysis: Analysis
    untestable: dict[str, str]  # AC id -> reason; provisional after analyse, confirmed by plan
    chunks: list[Chunk]
    plan: Plan
    tests: list[AgentTestCase]
    review: Review
    uncovered_acs: list[str]
    uncovered_conditions: list[str]
    iterations: int
    suite: TestSuite
    trace: Annotated[list[dict[str, Any]], operator.add]


def _context(chunks: list[Chunk]) -> str:
    return "\n\n".join(c.as_context() for c in chunks) or "(none)"


def _dump(items: list[BaseModel]) -> str:
    return json.dumps([i.model_dump() for i in items], indent=1, ensure_ascii=False)


def _gaps(state: AgentState, tests: list[AgentTestCase], plan: Plan) -> tuple[list[str], list[str]]:
    untestable = _untestable(state)
    covered_acs = {ac for t in tests for ac in t.covers}
    covered_conditions = {c for t in tests for c in t.condition_ids}
    uncovered_acs = [ac for ac in state["requirement"].ac_ids if ac not in covered_acs and ac not in untestable]
    uncovered_conditions = [c.id for c in plan.conditions if c.id not in covered_conditions]
    return uncovered_acs, uncovered_conditions


def _untestable(state: AgentState) -> set[str]:
    return set(state["untestable"])


def _untestable_text(state: AgentState) -> str:
    return ", ".join(sorted(_untestable(state))) or "none"


def _testable_conditions(conditions: list[TestCondition], untestable: set[str]) -> list[TestCondition]:
    """Drop conditions that only exercise untestable ACs (they would need invented rules)."""
    kept = []
    for c in conditions:
        acs = [a for a in c.ac_ids if a not in untestable]
        if acs:
            kept.append(c.model_copy(update={"ac_ids": acs}))
    return kept


def _testable_tests(tests: list[AgentTestCase], untestable: set[str]) -> list[AgentTestCase]:
    """Drop tests that only cover untestable ACs; strip untestable ids from the rest."""
    kept = []
    for t in tests:
        covers = [a for a in t.covers if a not in untestable]
        if covers:
            kept.append(t.model_copy(update={"covers": covers}))
    return kept


def build_agent(llm: StructuredLLM, kb: KnowledgeBase, max_iterations: int | None = None):
    max_iterations = get_settings().max_self_check_iterations if max_iterations is None else max_iterations

    def analyse(state: AgentState) -> AgentState:
        req = state["requirement"]
        analysis = invoke_structured(
            llm, Analysis, prompts.ANALYSE_SYSTEM, prompts.ANALYSE_USER.format(requirement=req.to_prompt_text())
        )
        return {
            "analysis": analysis,
            "untestable": {u.ac_id: u.reason for u in analysis.untestable_acs},
            "iterations": 0,
            "trace": [{
                "step": "analyse",
                "summary": f"{len(analysis.clarification_questions)} clarification question(s), "
                           f"{len(analysis.untestable_acs)} untestable AC(s), {len(analysis.search_queries)} search queries",
                "detail": analysis.model_dump(),
            }],
        }

    def retrieve(state: AgentState) -> AgentState:
        req = state["requirement"]
        queries = [f"{req.title}: {req.user_story}", *state["analysis"].search_queries]
        chunks = kb.search(queries)
        return {
            "chunks": chunks,
            "trace": [{
                "step": "retrieve",
                "summary": f"{len(chunks)} knowledge chunk(s) from {len({c.source for c in chunks})} document(s)",
                "detail": {"queries": queries, "chunks": [f"{c.source} > {c.section}" for c in chunks]},
            }],
        }

    def plan(state: AgentState) -> AgentState:
        req = state["requirement"]
        result = invoke_structured(
            llm, Plan, prompts.PLAN_SYSTEM,
            prompts.PLAN_USER.format(requirement=req.to_prompt_text(), untestable=_untestable_text(state),
                                     context=_context(state["chunks"])),
        )
        # the plan step has the domain knowledge, so its view of untestable ACs replaces the provisional one
        known = set(req.ac_ids)
        untestable = {u.ac_id: u.reason for u in result.untestable_acs if u.ac_id in known}
        cleared = sorted(set(state["untestable"]) - set(untestable))
        planned = len(result.conditions)
        result = result.model_copy(update={"conditions": _testable_conditions(result.conditions, set(untestable))})
        by_type: dict[str, int] = {}
        for c in result.conditions:
            by_type[c.type] = by_type.get(c.type, 0) + 1
        return {
            "plan": result,
            "untestable": untestable,
            "trace": [{
                "step": "plan",
                "summary": f"{len(result.conditions)} test condition(s) {by_type}; "
                           f"skipped existing: {', '.join(result.skipped_existing) or 'none'}"
                           + (f"; untestable after knowledge check: {', '.join(sorted(untestable)) or 'none'}")
                           + (f" (cleared {', '.join(cleared)})" if cleared else "")
                           + (f"; dropped {planned - len(result.conditions)} for untestable ACs"
                              if planned > len(result.conditions) else ""),
                "detail": result.model_dump(),
            }],
        }

    def generate(state: AgentState) -> AgentState:
        req = state["requirement"]
        result = invoke_structured(
            llm, GeneratedTests, prompts.GENERATE_SYSTEM,
            prompts.GENERATE_USER.format(
                requirement=req.to_prompt_text(), plan=_dump(state["plan"].conditions), context=_context(state["chunks"])
            ),
        )
        tests = _testable_tests(result.test_cases, _untestable(state))
        dropped = len(result.test_cases) - len(tests)
        return {
            "tests": tests,
            "trace": [{"step": "generate",
                       "summary": f"{len(tests)} test case(s) written"
                                  + (f"; dropped {dropped} for untestable ACs" if dropped else ""),
                       "detail": {}}],
        }

    def review(state: AgentState) -> AgentState:
        req = state["requirement"]
        result = invoke_structured(
            llm, Review, prompts.REVIEW_SYSTEM,
            prompts.REVIEW_USER.format(
                requirement=req.to_prompt_text(), untestable=_untestable_text(state), tests=_dump(state["tests"]),
                context=_context(state["chunks"]),
            ),
        )
        result = result.model_copy(
            update={"missing_conditions": _testable_conditions(result.missing_conditions, _untestable(state))})
        uncovered_acs, uncovered_conditions = _gaps(state, state["tests"], state["plan"])
        return {
            "review": result,
            "uncovered_acs": uncovered_acs,
            "uncovered_conditions": uncovered_conditions,
            "trace": [{
                "step": "review",
                "summary": f"{len(result.issues)} issue(s), {len(result.missing_conditions)} missing condition(s), "
                           f"uncovered ACs: {', '.join(uncovered_acs) or 'none'}, "
                           f"uncovered conditions: {', '.join(uncovered_conditions) or 'none'}",
                "detail": {**result.model_dump(), "uncovered_acs": uncovered_acs, "uncovered_conditions": uncovered_conditions},
            }],
        }

    def needs_revision(state: AgentState) -> bool:
        r = state["review"]
        return bool(r.issues or r.missing_conditions or state["uncovered_acs"] or state["uncovered_conditions"])

    def route_after_review(state: AgentState) -> str:
        return "revise" if needs_revision(state) and state["iterations"] < max_iterations else "finalize"

    def revise(state: AgentState) -> AgentState:
        req, r = state["requirement"], state["review"]
        result = invoke_structured(
            llm, Revision, prompts.REVISE_SYSTEM,
            prompts.REVISE_USER.format(
                requirement=req.to_prompt_text(),
                untestable=_untestable_text(state),
                tests=_dump(state["tests"]),
                issues=_dump(r.issues) if r.issues else "none",
                missing=_dump(r.missing_conditions) if r.missing_conditions else "none",
                uncovered_acs=", ".join(state["uncovered_acs"]) or "none",
                uncovered_conditions=", ".join(state["uncovered_conditions"]) or "none",
                context=_context(state["chunks"]),
            ),
        )
        removed = set(result.remove_test_ids)
        tests = {t.id: t for t in state["tests"] if t.id not in removed}
        revised = _testable_tests(result.test_cases, _untestable(state))
        replaced = [t.id for t in revised if t.id in tests]
        for t in revised:
            tests[t.id] = t
        # missing conditions become part of the plan so coverage of them is tracked
        plan = Plan(
            conditions=[*state["plan"].conditions, *r.missing_conditions],
            skipped_existing=state["plan"].skipped_existing,
            untestable_acs=state["plan"].untestable_acs,
        )
        return {
            "tests": list(tests.values()),
            "plan": plan,
            "iterations": state["iterations"] + 1,
            "trace": [{
                "step": "revise",
                "summary": f"iteration {state['iterations'] + 1}: {len(replaced)} replaced, "
                           f"{len(revised) - len(replaced)} added, {len(removed)} removed",
                "detail": {"replaced": replaced, "removed": sorted(removed)},
            }],
        }

    def finalize(state: AgentState) -> AgentState:
        req, analysis = state["requirement"], state["analysis"]
        cases = renumber(req.id, [to_test_case(t) for t in state["tests"]])
        suite = TestSuite(
            requirement_id=req.id,
            test_cases=cases,
            clarification_questions=analysis.clarification_questions,
            untestable_acs=dict(state["untestable"]),
        )
        open_items = needs_revision(state)
        return {
            "suite": suite,
            "trace": [{
                "step": "finalize",
                "summary": f"{len(cases)} test case(s) after {state['iterations']} revision(s)"
                           + ("; review findings still open (iteration limit reached)" if open_items else ""),
                "detail": {"open_review_findings": open_items},
            }],
        }

    graph = StateGraph(AgentState)
    for name, fn in [("analyse", analyse), ("retrieve", retrieve), ("plan", plan), ("generate", generate),
                     ("review", review), ("revise", revise), ("finalize", finalize)]:
        graph.add_node(name, fn)
    graph.add_edge(START, "analyse")
    graph.add_edge("analyse", "retrieve")
    graph.add_edge("retrieve", "plan")
    graph.add_edge("plan", "generate")
    graph.add_edge("generate", "review")
    graph.add_conditional_edges("review", route_after_review, {"revise": "revise", "finalize": "finalize"})
    graph.add_edge("revise", "review")
    graph.add_edge("finalize", END)
    return graph.compile()


def mermaid_diagram() -> str:
    """Mermaid source of the agent graph (for the demo UI and docs)."""
    from langchain_core.embeddings import DeterministicFakeEmbedding

    kb = KnowledgeBase(embeddings=DeterministicFakeEmbedding(size=8), docs={})
    return build_agent(llm=None, kb=kb).get_graph().draw_mermaid()  # type: ignore[arg-type]
