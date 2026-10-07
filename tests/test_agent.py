import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from agentic_tcg.agent import (
    AgentTestCase,
    Analysis,
    GeneratedTests,
    Plan,
    Review,
    ReviewIssue,
    Revision,
    TestCondition,
    mermaid_diagram,
)
from agentic_tcg.llm import LLMUntestable
from agentic_tcg.models import load_requirement
from agentic_tcg.pipeline import load_result, run_agent, save_result
from agentic_tcg.retriever import KnowledgeBase
from agentic_tcg.traceability import build_traceability
from fakes import FakeLLM
from test_baseline import assert_openai_strict, strict_schema


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase(embeddings=DeterministicFakeEmbedding(size=64))


def case(tc_id, ac, cond, expected="recorded"):
    return AgentTestCase(
        id=tc_id, title=f"Test {tc_id}", type="positive", priority="high", preconditions=[],
        steps=["submit the action"], test_data_json="{}", expected_result=expected, covers=[ac], condition_ids=[cond],
    )


def cond(cid, ac):
    return TestCondition(id=cid, ac_ids=[ac], type="positive", description=f"check {ac}", source=ac)


class ScriptedR4:
    """Analysis -> plan C1..C5 -> generate misses C5 and has a wrong notch -> review -> revise -> clean review."""

    def __init__(self, reviews_with_issues: int = 1):
        self.reviews_with_issues = reviews_with_issues
        self.reviews = 0

    def __call__(self, schema, system, user):
        if schema is Analysis:
            return Analysis(
                summary="Rating actions",
                clarification_questions=["R4-AC6: what counts as a 'large' downgrade?"],
                untestable_acs=[LLMUntestable(ac_id="R4-AC6", reason="'large' undefined")],
                search_queries=["notch change ordinal", "rating action error codes"],
            )
        if schema is Plan:
            return Plan(conditions=[cond(f"C{i}", f"R4-AC{i}") for i in range(1, 6)], skipped_existing=["REG-301"])
        if schema is GeneratedTests:
            tests = [case(f"T{i}", f"R4-AC{i}", f"C{i}") for i in range(1, 5)]
            tests[2] = case("T3", "R4-AC3", "C3", expected="notch_change = -3")  # wrong: should be -2
            return GeneratedTests(test_cases=tests)
        if schema is Review:
            self.reviews += 1
            if self.reviews <= self.reviews_with_issues:
                return Review(
                    issues=[ReviewIssue(test_id="T3", problem="BBB->BB+ is -2 notches", fix="expect -2")],
                    missing_conditions=[cond("C90", "R4-AC2")],
                )
            return Review(issues=[], missing_conditions=[])
        if schema is Revision:
            return Revision(
                test_cases=[
                    case("T3", "R4-AC3", "C3", expected="notch_change = -2"),
                    case("T5", "R4-AC5", "C5"),
                    case("T90", "R4-AC2", "C90"),
                ],
                remove_test_ids=[],
            )
        raise AssertionError(f"unexpected schema {schema}")


@pytest.mark.parametrize("schema", [Analysis, Plan, GeneratedTests, Review, Revision])
def test_agent_schemas_are_openai_strict_compatible(schema):
    assert_openai_strict(strict_schema(schema))


def test_knowledge_base_splits_and_searches(kb):
    sources = {d.metadata["source"] for d in kb.documents}
    assert len(sources) == 6 and len(kb.documents) > 6
    chunks = kb.search(["notch change", "error codes"], k=3, max_chunks=4)
    assert 1 <= len(chunks) <= 4
    assert len({(c.source, c.section, c.text) for c in chunks}) == len(chunks)
    assert chunks[0].as_context().startswith(f"[{chunks[0].source} > ")


def test_agent_runs_full_loop_and_fixes_gaps(kb):
    req = load_requirement("R4")
    llm = FakeLLM(ScriptedR4())
    result = run_agent(req, llm=llm, kb=kb)

    assert [c["schema"] for c in llm.calls] == ["Analysis", "Plan", "GeneratedTests", "Review", "Revision", "Review"]
    assert result.llm_calls == 6
    assert [t["step"] for t in result.trace] == [
        "analyse", "retrieve", "plan", "generate", "review", "revise", "review", "finalize"
    ]
    first_review = result.trace[4]["detail"]
    assert first_review["uncovered_acs"] == ["R4-AC5"] and first_review["uncovered_conditions"] == ["C5"]

    suite = result.suite
    assert len(suite.test_cases) == 6  # 4 generated + 2 added, T3 replaced in place
    assert [tc.id for tc in suite.test_cases] == [f"R4-TC{i:02d}" for i in range(1, 7)]
    assert "notch_change = -2" in [tc.expected_result for tc in suite.test_cases]
    assert suite.untestable_acs == {"R4-AC6": "'large' undefined"}
    assert suite.clarification_questions

    trace = build_traceability(req, suite)
    assert trace.coverage == 1.0
    assert {r.ac_id: r.status for r in trace.rows}["R4-AC6"] == "UNTESTABLE"
    assert result.retrieved_contexts and all(c.startswith("[") for c in result.retrieved_contexts)

    # retrieval queries include the requirement itself plus the analysis queries
    assert result.trace[1]["detail"]["queries"][1:] == ["notch change ordinal", "rating action error codes"]
    # agent prompts carry the retrieved knowledge; the baseline never does
    plan_prompt = next(c for c in llm.calls if c["schema"] == "Plan")["user"]
    assert "Domain knowledge:" in plan_prompt and "[" in plan_prompt


class ScriptedR4InventsThreshold(ScriptedR4):
    """The LLM ignores the untestable flag on R4-AC6 at every stage."""

    def __call__(self, schema, system, user):
        out = super().__call__(schema, system, user)
        if schema is Plan:
            out.conditions.append(cond("C6", "R4-AC6"))
        if schema is GeneratedTests:
            out.test_cases.append(case("T6", "R4-AC6", "C6", expected="downgrade > 3 notches is flagged"))
            out.test_cases[0].covers.append("R4-AC6")
        if schema is Review and out.missing_conditions:
            out.missing_conditions.append(cond("C91", "R4-AC6"))
        if schema is Revision:
            out.test_cases.append(case("T91", "R4-AC6", "C91"))
        return out


def test_agent_never_keeps_tests_for_untestable_acs(kb):
    req = load_requirement("R4")
    llm = FakeLLM(ScriptedR4InventsThreshold())
    result = run_agent(req, llm=llm, kb=kb)
    assert all("R4-AC6" not in tc.covers for tc in result.suite.test_cases)
    assert len(result.suite.test_cases) == 6  # same as the clean run: T6 and T91 dropped, T1 kept
    assert "dropped 1 for untestable ACs" in result.trace[2]["summary"]  # plan
    assert "dropped 1 for untestable ACs" in result.trace[3]["summary"]  # generate
    review_prompt = next(c for c in llm.calls if c["schema"] == "Review")["user"]
    assert "Untestable acceptance criteria (no tests until clarified): R4-AC6" in review_prompt


def test_agent_stops_at_iteration_limit(kb):
    llm = FakeLLM(ScriptedR4(reviews_with_issues=99))
    result = run_agent(load_requirement("R4"), llm=llm, kb=kb)
    steps = [t["step"] for t in result.trace]
    assert steps.count("revise") == 2 and steps.count("review") == 3
    assert result.trace[-1]["detail"]["open_review_findings"] is True


def test_save_and_load_result(kb, tmp_path):
    result = run_agent(load_requirement("R4"), llm=FakeLLM(ScriptedR4()), kb=kb)
    path = save_result(result, root=tmp_path)
    out = tmp_path / "agent"
    assert path == out / "R4.json"
    assert (out / "features" / "R4.feature").read_text().startswith("@R4")
    compile((out / "pytest" / "test_r4_generated.py").read_text(), "generated", "exec")
    assert "coverage 100%" in (out / "R4.md").read_text()
    loaded = load_result("agent", "R4", root=tmp_path)
    assert loaded == result
    assert load_result("baseline", "R4", root=tmp_path) is None


def test_mermaid_diagram_shows_review_loop():
    diagram = mermaid_diagram()
    for node in ["analyse", "retrieve", "plan", "generate", "review", "revise", "finalize"]:
        assert node in diagram


@pytest.mark.llm
def test_agent_live_openai():
    from agentic_tcg.config import get_settings

    if not get_settings().has_api_key:
        pytest.skip("OPENAI_API_KEY not set")
    req = load_requirement("R3")
    result = run_agent(req)
    assert result.suite.test_cases
    assert build_traceability(req, result.suite).coverage >= 0.8
