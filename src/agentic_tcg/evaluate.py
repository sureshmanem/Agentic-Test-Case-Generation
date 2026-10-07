"""Evaluate generated test suites (baseline vs. agent) with deterministic metrics, DeepEval and Ragas.

    uv run python -m agentic_tcg.evaluate                  # evaluate saved outputs for all requirements
    uv run python -m agentic_tcg.evaluate -r R4,R6 --no-ragas
    uv run python -m agentic_tcg.evaluate --repeats 3       # average 3 judgements per output
    uv run python -m agentic_tcg.evaluate --gate            # exit 1 below thresholds (CI)

Reads outputs/<mode>/<R>.json (from `agentic_tcg.generate`). Results are merged into
reports/results.json (same requirement + mode replaced) and reports/comparison.md is rebuilt.
"""

import argparse
import asyncio
import json
import os
import sys
import warnings
from collections.abc import Callable
from statistics import mean

from pydantic import BaseModel, Field

from agentic_tcg import config
from agentic_tcg.config import get_settings
from agentic_tcg.llm import StructuredLLM, get_chat_model, invoke_structured
from agentic_tcg.models import GoldenSet, Requirement, TestSuite, load_golden, load_knowledge_docs, load_requirement, load_requirements
from agentic_tcg.pipeline import MODES, GenerationResult, Mode, load_result
from agentic_tcg.renderers import questions_text, to_text
from agentic_tcg.traceability import build_traceability, type_distribution

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
# The direction change it announces is handled: we report it as `no_hallucination` (higher is better)
warnings.filterwarnings("ignore", message=".*HallucinationMetric. now scores", category=DeprecationWarning)

# Success criteria from UseCase1_Implementation.md
THRESHOLDS = {"ac_coverage": 0.8, "faithfulness": 0.85, "golden_scenario_recall": 0.8}
# Run facts shown in the report next to the metrics (lower is better for cost/time)
INFO_FIELDS = ("test_count", "llm_calls", "elapsed_seconds")


class MetricScore(BaseModel):
    name: str
    score: float | None
    reason: str = ""
    higher_is_better: bool = True
    error: str | None = None


class EvalRecord(BaseModel):
    requirement_id: str
    mode: Mode
    test_count: int
    llm_calls: int
    elapsed_seconds: float
    metrics: list[MetricScore]

    def score(self, name: str) -> float | None:
        if name in INFO_FIELDS:
            return float(getattr(self, name))
        return next((m.score for m in self.metrics if m.name == name), None)


class EvalInput(BaseModel):
    """Everything a judge needs about one generated suite."""

    requirement: Requirement
    golden: GoldenSet
    result: GenerationResult

    @property
    def requirement_text(self) -> str:
        return self.requirement.to_prompt_text()

    @property
    def reference_context(self) -> list[str]:
        """Ground truth used to judge faithfulness: the requirement plus the knowledge docs it references."""
        docs = load_knowledge_docs()
        return [self.requirement_text, *[f"[{name}]\n{docs[name]}" for name in self.requirement.references if name in docs]]

    @property
    def model_context(self) -> list[str]:
        """What the generator actually saw: the requirement, plus retrieved knowledge for the agent."""
        return [self.requirement_text, *self.result.retrieved_contexts]

    @property
    def golden_text(self) -> str:
        return to_text(TestSuite(requirement_id=self.golden.requirement_id, test_cases=self.golden.test_cases))

    @property
    def expected_questions_text(self) -> str:
        lines = [f"- {a}" for a in self.golden.expected_ambiguities]
        lines += [f"- {ac} is untestable as written: {why}" for ac, why in self.golden.untestable_acs.items()]
        return "\n".join(lines)


Judge = Callable[[EvalInput], list[MetricScore]]


# ---------- deterministic metrics ----------

def deterministic_metrics(item: EvalInput) -> list[MetricScore]:
    suite, golden, req = item.result.suite, item.golden, item.requirement
    # The golden set decides which ACs are untestable, so a generator cannot raise its
    # coverage by declaring criteria untestable.
    graded = TestSuite(requirement_id=suite.requirement_id, test_cases=suite.test_cases, untestable_acs=golden.untestable_acs)
    trace = build_traceability(req, graded)
    types = type_distribution(suite)
    return [
        MetricScore(name="ac_coverage", score=trace.coverage,
                    reason=f"uncovered: {', '.join(trace.uncovered) or 'none'}"),
        MetricScore(name="test_type_diversity", score=len(types) / 4, reason=json.dumps(types)),
        MetricScore(name="unknown_ac_references", score=float(len(trace.unknown_references)), higher_is_better=False,
                    reason=", ".join(trace.unknown_references)),
    ]


# ---------- DeepEval ----------

def deepeval_judge(model: str | None = None) -> Judge:
    from deepeval.metrics import FaithfulnessMetric, GEval, HallucinationMetric
    from deepeval.test_case import LLMTestCase, SingleTurnParams

    model = model or get_settings().judge_model
    P = SingleTurnParams

    def build_metrics():
        return {
            "faithfulness": FaithfulnessMetric(model=model, async_mode=False),
            # deepeval >= 4: 1.0 = no contradiction with the context (higher is better)
            "no_hallucination": HallucinationMetric(model=model, async_mode=False),
            "test_quality": GEval(
                name="Test quality", model=model, async_mode=False,
                evaluation_params=[P.INPUT, P.ACTUAL_OUTPUT],
                evaluation_steps=[
                    "Check that every test has clear, executable steps a tester could follow without guessing.",
                    "Check that test data is concrete (actual symbols, dates, ids), not placeholders.",
                    "Check that expected results are verifiable (exact values, statuses, error codes), not vague.",
                    "Check that the test type (positive/negative/boundary/edge) matches what the test does.",
                    "Penalise duplicated tests and tests that verify nothing from the requirement.",
                ],
            ),
        }

    def judge(item: EvalInput) -> list[MetricScore]:
        tests_text = to_text(item.result.suite)
        cases = {
            "faithfulness": LLMTestCase(input=item.requirement_text, actual_output=tests_text,
                                        retrieval_context=item.reference_context),
            "no_hallucination": LLMTestCase(input=item.requirement_text, actual_output=tests_text,
                                            context=item.reference_context),
            "test_quality": LLMTestCase(input=item.requirement_text, actual_output=tests_text),
        }
        scores = []
        for name, metric in build_metrics().items():
            try:
                metric.measure(cases[name], _show_indicator=False)
                scores.append(MetricScore(name=name, score=metric.score, reason=metric.reason or ""))
            except Exception as exc:  # keep the rest of the evaluation running
                scores.append(MetricScore(name=name, score=None, error=f"{type(exc).__name__}: {exc}"))
        return scores

    return judge


# ---------- per-item verdicts (golden scenarios, ambiguities) ----------
# Holistic GEval scores over 16-30 tests proved unreliable in the first live run
# (R4: a suite with correct default-rating boundary tests was said to lack them, and
# wrong notch arithmetic went unnoticed). One verdict per golden item is countable
# and auditable instead.

class ScenarioVerdict(BaseModel):
    golden_id: str
    covered: bool = Field(description="A candidate test checks the same scenario (wording and ids may differ)")
    matching_test_ids: list[str]
    conflicting_expectation: bool = Field(
        description="The matching test expects a different outcome (e.g. a different value or error code)")
    note: str


class ScenarioJudgement(BaseModel):
    verdicts: list[ScenarioVerdict]


class AmbiguityVerdict(BaseModel):
    expected_id: str
    raised: bool = Field(description="The candidate raises the same concern, in any wording")
    matching_question: str


class AmbiguityJudgement(BaseModel):
    verdicts: list[AmbiguityVerdict]


SCENARIO_SYSTEM = """You compare a candidate test suite with reference test cases written by a senior QA engineer.
Return one verdict per reference test case, in order.
- covered: a candidate test checks the same scenario (same condition and same kind of input). Wording, ids and exact data may differ.
- conflicting_expectation: a matching candidate test expects a different outcome than the reference (different value, sign, status or error code). Check the arithmetic.
- note: one short sentence."""

AMBIGUITY_SYSTEM = """You check whether a candidate raised known ambiguities in a requirement.
Return one verdict per expected item, in order.
- raised: the candidate's questions or untestable-criteria notes raise the same concern, in any wording.
- matching_question: the candidate text that raises it, or an empty string."""


def verdict_judge(llm: StructuredLLM | None = None) -> Judge:
    """LLM-as-judge with one verdict per golden scenario and per expected ambiguity."""
    llm = llm or get_chat_model(get_settings().judge_model)

    def judge(item: EvalInput) -> list[MetricScore]:
        scores = []
        golden_ids = [tc.id for tc in item.golden.test_cases]
        try:
            out = invoke_structured(
                llm, ScenarioJudgement, SCENARIO_SYSTEM,
                f"{item.requirement_text}\n\nReference test cases:\n{item.golden_text}\n\n"
                f"Candidate test suite:\n{to_text(item.result.suite) or '(empty)'}",
            )
            by_id = {v.golden_id: v for v in out.verdicts}
            hits = [gid for gid in golden_ids if (v := by_id.get(gid)) and v.covered and not v.conflicting_expectation]
            conflicts = [gid for gid in golden_ids if (v := by_id.get(gid)) and v.covered and v.conflicting_expectation]
            missed = [gid for gid in golden_ids if gid not in hits and gid not in conflicts]
            scores += [
                MetricScore(name="golden_scenario_recall", score=len(hits) / len(golden_ids),
                            reason=f"missed: {', '.join(missed) or 'none'}; conflicting: {', '.join(conflicts) or 'none'}"),
                MetricScore(name="golden_conflicts", score=float(len(conflicts)), higher_is_better=False,
                            reason="; ".join(f"{gid}: {by_id[gid].note}" for gid in conflicts)),
            ]
        except Exception as exc:
            scores += [MetricScore(name="golden_scenario_recall", score=None, error=f"{type(exc).__name__}: {exc}"),
                       MetricScore(name="golden_conflicts", score=None, higher_is_better=False,
                                   error=f"{type(exc).__name__}: {exc}")]

        expected = [*item.golden.expected_ambiguities,
                    *[f"{ac} is untestable as written: {why}" for ac, why in item.golden.untestable_acs.items()]]
        ids = [f"A{i}" for i in range(1, len(expected) + 1)]
        try:
            out = invoke_structured(
                llm, AmbiguityJudgement, AMBIGUITY_SYSTEM,
                f"{item.requirement_text}\n\nExpected items:\n"
                + "\n".join(f"{i}: {e}" for i, e in zip(ids, expected))
                + f"\n\nCandidate questions and notes:\n{questions_text(item.result.suite)}",
            )
            by_id = {v.expected_id: v for v in out.verdicts}
            raised = [i for i in ids if (v := by_id.get(i)) and v.raised]
            scores.append(MetricScore(name="ambiguity_detection", score=len(raised) / len(ids) if ids else None,
                                      reason=f"raised {', '.join(raised) or 'none'} of {', '.join(ids)}"))
        except Exception as exc:
            scores.append(MetricScore(name="ambiguity_detection", score=None, error=f"{type(exc).__name__}: {exc}"))
        return scores

    return judge


# ---------- Ragas ----------

def ragas_judge(model: str | None = None) -> Judge:
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.metrics.collections import ContextPrecisionWithReference, ContextRecall, Faithfulness

    # Ragas defaults to max_tokens=1024, too small for statement extraction over a full test suite
    llm = llm_factory(model or get_settings().judge_model, client=AsyncOpenAI(), max_tokens=16000)
    faithfulness, precision, recall = Faithfulness(llm=llm), ContextPrecisionWithReference(llm=llm), ContextRecall(llm=llm)

    async def run(item: EvalInput) -> list[MetricScore]:
        tests_text, golden_text = to_text(item.result.suite), item.golden_text
        jobs: dict[str, object] = {
            # groundedness in what the generator actually saw
            "ragas_faithfulness": faithfulness.ascore(
                user_input=item.requirement_text, response=tests_text, retrieved_contexts=item.model_context),
            # how much of the golden tests is supported by the generator's context
            # (baseline: requirement only; agent: requirement + retrieved knowledge)
            "ragas_context_recall": recall.ascore(
                user_input=item.requirement_text, retrieved_contexts=item.model_context, reference=golden_text),
        }
        if item.result.retrieved_contexts:
            # are the retrieved chunks relevant (agent only)
            jobs["ragas_context_precision"] = precision.ascore(
                user_input=item.requirement_text, reference=golden_text, retrieved_contexts=item.result.retrieved_contexts)
        outcomes = await asyncio.gather(*jobs.values(), return_exceptions=True)
        scores = []
        for name, outcome in zip(jobs, outcomes):
            if isinstance(outcome, BaseException):
                scores.append(MetricScore(name=name, score=None, error=f"{type(outcome).__name__}: {outcome}"))
            else:
                scores.append(MetricScore(name=name, score=float(outcome.value)))
        return scores

    return lambda item: asyncio.run(run(item))


# ---------- orchestration and report ----------

def evaluate_result(item: EvalInput, judges: list[Judge]) -> EvalRecord:
    metrics = deterministic_metrics(item)
    for judge in judges:
        metrics += judge(item)
    r = item.result
    return EvalRecord(requirement_id=r.requirement_id, mode=r.mode, test_count=len(r.suite.test_cases),
                      llm_calls=r.llm_calls, elapsed_seconds=r.elapsed_seconds, metrics=metrics)


def average_records(records: list[EvalRecord]) -> EvalRecord:
    """Average repeated judgements of the same output (LLM judges vary between runs)."""
    first = records[0]
    metrics = []
    for m in first.metrics:
        values = [s for r in records if (s := r.score(m.name)) is not None]
        errors = [x.error for r in records for x in r.metrics if x.name == m.name and x.error]
        metrics.append(m.model_copy(update={
            "score": mean(values) if values else None,
            "reason": m.reason if len(records) == 1 else f"mean of {len(values)}/{len(records)} run(s); first: {m.reason}",
            "error": None if values else (errors[0] if errors else m.error),
        }))
    return first.model_copy(update={"metrics": metrics})


def _avg(records: list[EvalRecord], mode: Mode, name: str) -> float | None:
    values = [s for r in records if r.mode == mode and (s := r.score(name)) is not None]
    return mean(values) if values else None


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def success_criteria(records: list[EvalRecord]) -> list[tuple[str, bool | None, str]]:
    """(label, passed or None if not measured, detail). Labels marked ² form the CI gate."""
    a = {n: _avg(records, "agent", n) for n in THRESHOLDS}
    b = {n: _avg(records, "baseline", n) for n in THRESHOLDS}

    def ge(n: str) -> tuple[bool | None, str]:
        return (None if a[n] is None else a[n] >= THRESHOLDS[n]), _fmt(a[n])

    def gt(n: str) -> tuple[bool | None, str]:
        return (None if a[n] is None or b[n] is None else a[n] > b[n]), f"{_fmt(a[n])} vs {_fmt(b[n])}"

    return [
        (f"Agent AC coverage ≥ {THRESHOLDS['ac_coverage']} ²", *ge("ac_coverage")),
        (f"Agent faithfulness ≥ {THRESHOLDS['faithfulness']} ²", *ge("faithfulness")),
        ("Agent coverage > baseline", *gt("ac_coverage")),
        ("Agent faithfulness > baseline", *gt("faithfulness")),
        (f"Agent golden scenario recall ≥ {THRESHOLDS['golden_scenario_recall']} ¹ ²", *ge("golden_scenario_recall")),
        ("Agent golden scenario recall > baseline ¹", *gt("golden_scenario_recall")),
    ]


def gate_passed(records: list[EvalRecord]) -> bool:
    """CI gate: every measured absolute threshold (²) passes, and at least one was measured."""
    gated = [ok for label, ok, _ in success_criteria(records) if "²" in label and ok is not None]
    return bool(gated) and all(gated)


def build_report(records: list[EvalRecord]) -> str:
    names: list[str] = []
    lower_better: set[str] = set()
    for r in records:
        for m in r.metrics:
            if m.name not in names:
                names.append(m.name)
            if not m.higher_is_better:
                lower_better.add(m.name)
    names += list(INFO_FIELDS)
    lower_better |= {"llm_calls", "elapsed_seconds"}
    informational = set(INFO_FIELDS)

    lines = ["# Agent vs. Baseline: Evaluation Report", "",
             f"Requirements: {', '.join(sorted({r.requirement_id for r in records}))}  ",
             f"Judge model: `{get_settings().judge_model}`  ", f"Generation model: `{get_settings().generation_model}`", "",
             "## Overall (mean across requirements)", "",
             "| Metric | Baseline | Agent | Δ (agent − baseline) | Better |", "|---|---|---|---|---|"]
    for name in names:
        b, a = _avg(records, "baseline", name), _avg(records, "agent", name)
        delta = None if a is None or b is None else a - b
        if delta is None or name in informational or abs(delta) < 1e-9:
            better = "–"
        else:
            better = "agent" if (delta < 0 if name in lower_better else delta > 0) else "baseline"
        arrow = " (lower is better)" if name in lower_better else ""
        lines.append(f"| {name}{arrow} | {_fmt(b)} | {_fmt(a)} | {_fmt(delta)} | {better} |")

    lines += ["", "## Success criteria", "", "| Criterion | Result |", "|---|---|"]
    for label, ok, detail in success_criteria(records):
        lines.append(f"| {label} | {'n/a' if ok is None else ('✅ pass' if ok else '❌ fail')} ({detail}) |")
    lines += ["", "¹ Added after the first live run: AC coverage only needs one test per criterion, so both modes reach "
              "100% and it cannot tell them apart. Scenario recall measures coverage against the 75 golden tests.",
              "² Used by the CI quality gate (`--gate`)."]

    key = [n for n in ["ac_coverage", "golden_scenario_recall", "golden_conflicts", "faithfulness", "no_hallucination", "ambiguity_detection", "test_quality"] if n in names]
    lines += ["", "## Per requirement (baseline → agent)", "",
              "| Req | " + " | ".join(key) + " | tests |", "|---|" + "---|" * (len(key) + 1)]
    by = {(r.requirement_id, r.mode): r for r in records}
    for rid in sorted({r.requirement_id for r in records}):
        b, a = by.get((rid, "baseline")), by.get((rid, "agent"))
        cells = [f"{_fmt(b.score(n) if b else None)} → {_fmt(a.score(n) if a else None)}" for n in key]
        cells.append(f"{b.test_count if b else '–'} → {a.test_count if a else '–'}")
        lines.append(f"| {rid} | " + " | ".join(cells) + " |")

    errors = [(r.requirement_id, r.mode, m) for r in records for m in r.metrics if m.error]
    if errors:
        lines += ["", "## Metric errors", ""] + [f"- {rid} {mode} `{m.name}`: {m.error}" for rid, mode, m in errors]
    lines += ["", "Metric definitions: see `UseCase1_Implementation.md`, Step 6."]
    return "\n".join(lines) + "\n"


def default_judges(deepeval: bool = True, ragas: bool = True) -> list[Judge]:
    judges: list[Judge] = []
    if deepeval:
        judges += [verdict_judge(), deepeval_judge()]
    if ragas:
        judges.append(ragas_judge())
    return judges


def evaluate_requirement(requirement: Requirement, judges: list[Judge], repeats: int = 1) -> list[EvalRecord]:
    """Evaluate the saved baseline and agent outputs of one requirement (missing outputs are skipped)."""
    golden = load_golden(requirement.id)
    records = []
    for mode in MODES:
        result = load_result(mode, requirement.id)
        if result is None:
            continue
        item = EvalInput(requirement=requirement, golden=golden, result=result)
        records.append(average_records([evaluate_result(item, judges) for _ in range(max(1, repeats))]))
    return records


def load_records() -> list[EvalRecord]:
    path = config.REPORTS_DIR / "results.json"
    return [EvalRecord.model_validate(r) for r in json.loads(path.read_text())] if path.exists() else []


def update_reports(new: list[EvalRecord]) -> list[EvalRecord]:
    """Merge records into reports/results.json (replacing the same requirement+mode) and rebuild comparison.md."""
    keys = {(r.requirement_id, r.mode) for r in new}
    records = [r for r in load_records() if (r.requirement_id, r.mode) not in keys] + new
    records.sort(key=lambda r: (int(r.requirement_id[1:]), MODES.index(r.mode)))
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (config.REPORTS_DIR / "results.json").write_text(json.dumps([r.model_dump() for r in records], indent=2) + "\n")
    (config.REPORTS_DIR / "comparison.md").write_text(build_report(records))
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-r", "--requirements", help="Comma-separated ids (default: all)")
    parser.add_argument("--no-deepeval", action="store_true")
    parser.add_argument("--no-ragas", action="store_true")
    parser.add_argument("--repeats", type=int, default=1, help="Judge each output N times and average (default 1)")
    parser.add_argument("--gate", action="store_true", help="Exit 1 if the agent misses an absolute threshold (for CI)")
    args = parser.parse_args(argv)

    if not get_settings().has_api_key and not (args.no_deepeval and args.no_ragas):
        print("OPENAI_API_KEY is not set (needed for the judge model). Use --no-deepeval --no-ragas "
              "for deterministic metrics only.", file=sys.stderr)
        return 2

    judges = default_judges(deepeval=not args.no_deepeval, ragas=not args.no_ragas)
    reqs = [load_requirement(r.strip()) for r in args.requirements.split(",")] if args.requirements else load_requirements()
    records = []
    for req in reqs:
        print(f"evaluating {req.id} ...", file=sys.stderr)
        found = evaluate_requirement(req, judges, repeats=args.repeats)
        if not found:
            print(f"skip {req.id}: no outputs (run agentic_tcg.generate first)", file=sys.stderr)
        records += found
    if not records:
        print("Nothing to evaluate.", file=sys.stderr)
        return 1

    all_records = update_reports(records)
    print(build_report(all_records))
    if args.gate and not gate_passed(records):
        print("Quality gate FAILED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
