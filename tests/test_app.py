"""Headless UI tests for app.py (Streamlit AppTest), fully offline."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agentic_tcg import config
from agentic_tcg.evaluate import EvalRecord, MetricScore, update_reports
from agentic_tcg.models import TestSuite, load_golden
from agentic_tcg.pipeline import GenerationResult, save_result

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUTS_DIR", tmp_path / "outputs")
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setenv("OPENAI_API_KEY", "")  # no live calls from the UI in tests
    return tmp_path


def fake_result(rid: str, mode: str) -> GenerationResult:
    cases = load_golden(rid).test_cases
    return GenerationResult(
        mode=mode, requirement_id=rid, model="fake", suite=TestSuite(requirement_id=rid, test_cases=cases,
                                                                     clarification_questions=["What is large?"]),
        retrieved_contexts=["[rating_rules.md > Rating Actions]\nnotch rules"] if mode == "agent" else [],
        trace=[{"step": "analyse", "summary": "1 question", "detail": {"a": 1}},
               {"step": "finalize", "summary": "done", "detail": {}}] if mode == "agent" else [],
        llm_calls=6 if mode == "agent" else 1, elapsed_seconds=30.0, created_at="now",
    )


def run(at: AppTest) -> AppTest:
    at.run(timeout=60)
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_app_renders_without_outputs(scratch):
    at = run(AppTest.from_file(APP))
    assert at.title[0].value == "Agentic Test Case Generation"
    assert any("OPENAI_API_KEY is not set" in w.value for w in at.sidebar.warning)
    assert all(b.disabled for b in at.sidebar.button)
    assert any("No output yet" in i.value for i in at.info)


def test_app_shows_saved_outputs_and_evaluation(scratch):
    for mode in ("baseline", "agent"):
        save_result(fake_result("R4", mode))
    update_reports([
        EvalRecord(requirement_id="R4", mode="baseline", test_count=10, llm_calls=1, elapsed_seconds=30,
                   metrics=[MetricScore(name="golden_scenario_recall", score=0.4, reason="missed: R4-TC01")]),
        EvalRecord(requirement_id="R4", mode="agent", test_count=10, llm_calls=6, elapsed_seconds=30,
                   metrics=[MetricScore(name="golden_scenario_recall", score=1.0, reason="missed: none")]),
    ])
    at = AppTest.from_file(APP)
    at.run(timeout=60)
    at.sidebar.selectbox[0].select("R4")
    run(at)

    assert at.subheader[0].value.startswith("R4 · Rating Actions")
    assert at.radio(key="mode").value == "agent"
    assert any("Feature: Rating Actions and Notch Change" in c.value for c in at.code)
    assert any("def test_r4_tc01" in c.value for c in at.code)
    eval_df = next(df.value for df in at.dataframe if "Metric" in df.value.columns)
    assert eval_df.iloc[0].to_dict()["Agent"] == 1.0
    assert any("1. **analyse**" in e.label for e in at.expander)

    at.radio(key="mode").set_value("baseline")
    run(at)
    assert any("Feature:" in c.value for c in at.code)
