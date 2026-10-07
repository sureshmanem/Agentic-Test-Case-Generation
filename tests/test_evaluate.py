import pytest

from agentic_tcg.evaluate import (
    EvalInput,
    EvalRecord,
    MetricScore,
    build_report,
    deepeval_judge,
    deterministic_metrics,
    evaluate_result,
    ragas_judge,
)
from agentic_tcg.models import TestSuite, load_golden, load_requirement
from agentic_tcg.pipeline import GenerationResult


def result_from_golden(rid: str, mode="agent", keep=None, untestable=None, questions=()) -> GenerationResult:
    golden = load_golden(rid)
    cases = golden.test_cases if keep is None else [tc for tc in golden.test_cases if keep(tc)]
    suite = TestSuite(requirement_id=rid, test_cases=cases, untestable_acs=untestable or {},
                      clarification_questions=list(questions))
    return GenerationResult(mode=mode, requirement_id=rid, model="fake", suite=suite,
                            retrieved_contexts=["[rating_rules.md > Rating Actions]\n..."] if mode == "agent" else [],
                            llm_calls=5 if mode == "agent" else 1, elapsed_seconds=1.0, created_at="now")


def item(rid, **kw) -> EvalInput:
    return EvalInput(requirement=load_requirement(rid), golden=load_golden(rid), result=result_from_golden(rid, **kw))


def scores(metrics):
    return {m.name: m.score for m in metrics}


def test_golden_set_scores_perfectly_on_deterministic_metrics():
    s = scores(deterministic_metrics(item("R4", untestable={"R4-AC6": "large undefined"})))
    assert s["ac_coverage"] == 1.0
    assert s["test_type_diversity"] == 1.0  # R4 golden has all four test types
    assert s["unknown_ac_references"] == 0.0


def test_coverage_uses_golden_untestable_list_not_the_generators():
    # dropping all R4-AC4 tests and claiming AC4 is untestable must not hide the gap
    it = item("R4", keep=lambda tc: "R4-AC4" not in tc.covers, untestable={"R4-AC4": "cannot test dates"})
    s = scores(deterministic_metrics(it))
    assert s["ac_coverage"] == pytest.approx(4 / 5)


def test_eval_input_contexts():
    it = item("R2")
    assert it.reference_context[0].startswith("Requirement R2")
    assert any(c.startswith("[cross_agency_mapping.md]") for c in it.reference_context)
    assert len(it.model_context) == 2  # requirement + one retrieved chunk
    assert "R2-TC05" in it.golden_text and "RD" in it.golden_text
    assert "NORTHBRIDGE" in it.expected_questions_text


def fake_judge(value_by_mode):
    def judge(it: EvalInput):
        v = value_by_mode[it.result.mode]
        return [MetricScore(name="faithfulness", score=v), MetricScore(name="defect_rate", score=1 - v, higher_is_better=False)]
    return judge


def test_report_compares_modes_and_checks_success_criteria():
    judge = fake_judge({"baseline": 0.7, "agent": 0.9})
    records = [
        evaluate_result(item("R4", mode="baseline", keep=lambda tc: "R4-AC4" not in tc.covers), [judge]),
        evaluate_result(item("R4", mode="agent", untestable={"R4-AC6": "x"}), [judge]),
    ]
    snapshot = [r.model_dump() for r in records]
    report = build_report(records)
    assert [r.model_dump() for r in records] == snapshot  # report must not mutate records
    assert build_report(records) == report

    assert "| ac_coverage | 0.80 | 1.00 | 0.20 | agent |" in report
    assert "| faithfulness | 0.70 | 0.90 | 0.20 | agent |" in report
    assert "| defect_rate (lower is better) | 0.30 | 0.10 | -0.20 | agent |" in report
    assert "| llm_calls (lower is better) | 1.00 | 5.00 | 4.00 | – |" in report
    assert "Agent AC coverage ≥ 0.8 ² | ✅ pass" in report
    assert "Agent faithfulness > baseline | ✅ pass" in report
    assert "| R4 | 0.80 → 1.00 |" in report


def test_report_lists_metric_errors():
    def broken(it):
        return [MetricScore(name="faithfulness", score=None, error="RateLimitError: slow down")]
    records = [evaluate_result(item("R1", mode=m), [broken]) for m in ("baseline", "agent")]
    report = build_report(records)
    assert "## Metric errors" in report and "RateLimitError" in report
    assert "Agent faithfulness ≥ 0.85 ² | n/a" in report


def test_record_score_lookup():
    rec = EvalRecord(requirement_id="R1", mode="agent", test_count=7, llm_calls=5, elapsed_seconds=2.5,
                     metrics=[MetricScore(name="faithfulness", score=0.9)])
    assert rec.score("faithfulness") == 0.9 and rec.score("test_count") == 7.0 and rec.score("missing") is None


def test_judges_construct_offline(monkeypatch):
    """Catches API misuse in DeepEval/Ragas wiring without calling OpenAI."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    assert callable(deepeval_judge("gpt-4.1-mini"))
    assert callable(ragas_judge("gpt-4.1-mini"))


@pytest.mark.llm
def test_judges_live_openai():
    from agentic_tcg.config import get_settings

    if not get_settings().has_api_key:
        pytest.skip("OPENAI_API_KEY not set")
    rec = evaluate_result(item("R3", untestable={}), [deepeval_judge(), ragas_judge()])
    errors = [m for m in rec.metrics if m.error]
    assert not errors, errors
    assert rec.score("golden_scenario_recall") > 0.7  # golden vs itself


@pytest.mark.parametrize("schema", ["ScenarioJudgement", "AmbiguityJudgement"])
def test_verdict_schemas_are_openai_strict_compatible(schema):
    import agentic_tcg.evaluate as ev
    from test_baseline import assert_openai_strict, strict_schema

    assert_openai_strict(strict_schema(getattr(ev, schema)))


def test_verdict_judge_counts_hits_conflicts_and_ambiguities():
    from agentic_tcg.evaluate import AmbiguityJudgement, AmbiguityVerdict, ScenarioJudgement, ScenarioVerdict, verdict_judge
    from fakes import FakeLLM

    def handler(schema, system, user):
        if schema is ScenarioJudgement:
            assert "R4-TC01" in user and "Candidate test suite" in user
            v = []
            for i in range(1, 11):
                gid = f"R4-TC{i:02d}"
                # TC01-07 covered, TC05 covered but wrong notch, TC08-10 missed; TC09 omitted by the judge
                if i == 9:
                    continue
                v.append(ScenarioVerdict(golden_id=gid, covered=i <= 7, matching_test_ids=[], note="wrong sign" if i == 5 else "",
                                         conflicting_expectation=i == 5))
            return ScenarioJudgement(verdicts=v)
        assert schema is AmbiguityJudgement
        assert "A4: R4-AC6 is untestable" in user
        return AmbiguityJudgement(verdicts=[AmbiguityVerdict(expected_id="A1", raised=True, matching_question="q"),
                                            AmbiguityVerdict(expected_id="A4", raised=True, matching_question="q")])

    s = {m.name: m for m in verdict_judge(FakeLLM(handler))(item("R4"))}
    assert s["golden_scenario_recall"].score == pytest.approx(6 / 10)
    assert s["golden_scenario_recall"].reason == "missed: R4-TC08, R4-TC09, R4-TC10; conflicting: R4-TC05"
    assert s["golden_conflicts"].score == 1.0 and "wrong sign" in s["golden_conflicts"].reason
    assert s["ambiguity_detection"].score == pytest.approx(2 / 4)


def test_verdict_judge_reports_errors():
    from agentic_tcg.evaluate import verdict_judge
    from fakes import FakeLLM

    def handler(schema, system, user):
        raise TimeoutError("judge down")

    s = {m.name: m for m in verdict_judge(FakeLLM(handler))(item("R1"))}
    assert s["golden_scenario_recall"].score is None and "judge down" in s["golden_scenario_recall"].error
    assert s["ambiguity_detection"].error


def test_average_records_over_repeats():
    from agentic_tcg.evaluate import average_records

    def rec(score, error=None):
        return EvalRecord(requirement_id="R1", mode="agent", test_count=7, llm_calls=5, elapsed_seconds=1.0,
                          metrics=[MetricScore(name="faithfulness", score=score, error=error)])
    avg = average_records([rec(0.6), rec(None, "boom"), rec(1.0)])
    assert avg.score("faithfulness") == pytest.approx(0.8)
    assert avg.metrics[0].error is None and avg.metrics[0].reason.startswith("mean of 2/3 run(s)")
    assert average_records([rec(None, "boom")]).metrics[0].error == "boom"


def test_update_reports_merges_by_requirement_and_mode(tmp_path, monkeypatch):
    from agentic_tcg import config
    from agentic_tcg.evaluate import load_records, update_reports

    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path)

    def rec(rid, mode, score):
        return EvalRecord(requirement_id=rid, mode=mode, test_count=1, llm_calls=1, elapsed_seconds=1.0,
                          metrics=[MetricScore(name="faithfulness", score=score)])
    update_reports([rec("R10", "agent", 0.1), rec("R2", "baseline", 0.5), rec("R2", "agent", 0.6)])
    update_reports([rec("R2", "agent", 0.9)])
    records = load_records()
    assert [(r.requirement_id, r.mode, r.score("faithfulness")) for r in records] == [
        ("R2", "baseline", 0.5), ("R2", "agent", 0.9), ("R10", "agent", 0.1)]
    assert (tmp_path / "comparison.md").read_text().startswith("# Agent vs. Baseline")


def test_gate():
    from agentic_tcg.evaluate import gate_passed

    def rec(mode, **scores):
        return EvalRecord(requirement_id="R1", mode=mode, test_count=1, llm_calls=1, elapsed_seconds=1.0,
                          metrics=[MetricScore(name=n, score=v) for n, v in scores.items()])
    base = rec("baseline", ac_coverage=1.0, faithfulness=0.95, golden_scenario_recall=0.9)
    # comparisons with the baseline do not block the gate, only absolute thresholds do
    assert gate_passed([base, rec("agent", ac_coverage=1.0, faithfulness=0.9, golden_scenario_recall=0.85)])
    assert not gate_passed([base, rec("agent", ac_coverage=1.0, faithfulness=0.80, golden_scenario_recall=0.85)])
    assert not gate_passed([base])  # nothing measured for the agent
