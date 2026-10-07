"""LangSmith tracing wiring, checked offline (no LangSmith account or network needed)."""

import os

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.tracers.base import BaseTracer

from agentic_tcg import config
from agentic_tcg.evaluate import EvalInput, EvalRecord, MetricScore, evaluate_result, send_feedback
from agentic_tcg.models import load_golden, load_requirement
from agentic_tcg.pipeline import run_agent, run_baseline
from agentic_tcg.retriever import KnowledgeBase
from fakes import FakeLLM
from test_agent import ScriptedR4
from test_baseline import fake_case
from agentic_tcg.llm import LLMTestSuite


@pytest.fixture
def no_tracing(monkeypatch):
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("env, expected", [
    ({}, False),
    ({"LANGSMITH_TRACING": "true"}, False),                                   # no key
    ({"LANGSMITH_API_KEY": "lsv2_pt_x"}, False),                              # flag off
    ({"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "lsv2_..."}, False),  # placeholder from .env.example
    ({"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "lsv2_pt_x"}, True),
    ({"LANGCHAIN_TRACING_V2": "true", "LANGCHAIN_API_KEY": "lsv2_pt_x"}, True),  # legacy names
])
def test_tracing_enabled(no_tracing, monkeypatch, env, expected):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert config.tracing_enabled() is expected


def test_default_project_is_set():
    assert os.environ["LANGSMITH_PROJECT"]
    assert config.langsmith_project() == os.environ["LANGSMITH_PROJECT"]


class RecordingTracer(BaseTracer):
    """Keeps finished root runs with their child runs (collect_runs drops the children)."""

    def __init__(self):
        super().__init__()
        self.roots = []

    def _persist_run(self, run):
        self.roots.append(run)


def test_agent_root_run_is_named_tagged_and_matches_saved_run_id(no_tracing, monkeypatch):
    import agentic_tcg.pipeline as pipeline

    tracer = RecordingTracer()
    original = pipeline.run_config
    monkeypatch.setattr(pipeline, "run_config", lambda *a: {**original(*a), "callbacks": [tracer]})
    kb = KnowledgeBase(embeddings=DeterministicFakeEmbedding(size=32))
    result = run_agent(load_requirement("R4"), llm=FakeLLM(ScriptedR4()), kb=kb)

    root = tracer.roots[0]
    assert str(root.id) == result.run_id
    assert root.name == "agent R4"
    assert {"agent", "R4"} <= set(root.tags)
    assert root.extra["metadata"]["requirement_id"] == "R4"
    assert [c.name for c in root.child_runs] == [
        "analyse", "retrieve", "plan", "generate", "review", "revise", "review", "finalize"]
    assert result.traced is False  # tracing env is off, so nothing was sent to LangSmith


def test_baseline_passes_run_config_to_the_llm(no_tracing):
    llm = FakeLLM(lambda schema, s, u: LLMTestSuite(test_cases=[fake_case("x", ["R1-AC1"])],
                                                     clarification_questions=[], untestable_acs=[]))
    result = run_baseline(load_requirement("R1"), llm=llm)
    cfg = llm.calls[0]["config"]
    assert cfg["run_name"] == "baseline R1" and cfg["tags"] == ["baseline", "R1"]
    assert str(cfg["run_id"]) == result.run_id


class FakeClient:
    def __init__(self):
        self.feedback = []

    def read_project(self, project_name):
        class Project:
            id = "project-1"
        return Project()

    def create_feedback(self, run_id, key, score, comment=None, trace_id=None, session_id=None, source_info=None):
        assert trace_id == run_id and session_id == "project-1"
        self.feedback.append((run_id, key, score, comment))


def test_send_feedback_only_for_traced_runs_and_real_scores():
    def rec(run_id):
        return EvalRecord(requirement_id="R1", mode="agent", test_count=1, llm_calls=1, elapsed_seconds=1.0, run_id=run_id,
                          metrics=[MetricScore(name="faithfulness", score=0.9, reason="ok"),
                                   MetricScore(name="test_quality", score=None, error="boom")])
    client = FakeClient()
    assert send_feedback([rec("run-1"), rec(None)], client=client) == 1
    assert client.feedback == [("run-1", "faithfulness", 0.9, "ok")]


def test_send_feedback_is_a_noop_without_tracing(no_tracing):
    rec = EvalRecord(requirement_id="R1", mode="agent", test_count=1, llm_calls=1, elapsed_seconds=1.0, run_id="run-1",
                     metrics=[MetricScore(name="faithfulness", score=0.9)])
    assert send_feedback([rec]) == 0


def test_eval_record_keeps_run_id_only_when_generation_was_traced(no_tracing):
    from test_evaluate import result_from_golden

    for traced in (False, True):
        result = result_from_golden("R1").model_copy(update={"run_id": "run-9", "traced": traced})
        item = EvalInput(requirement=load_requirement("R1"), golden=load_golden("R1"), result=result)
        assert evaluate_result(item, []).run_id == ("run-9" if traced else None)


def test_test_suite_never_traces_to_langsmith():
    from langsmith import utils

    assert utils.tracing_is_enabled() is False
    assert config.tracing_enabled() is False
