import ast

import pytest

from agentic_tcg.models import TestSuite, load_golden, load_requirement, load_requirements
from agentic_tcg.renderers import to_gherkin, to_markdown_table, to_pytest, to_rows, traceability_markdown
from agentic_tcg.traceability import build_traceability, type_distribution

REQUIREMENT_IDS = [f"R{i}" for i in range(1, 9)]


def golden_suite(rid: str) -> TestSuite:
    g = load_golden(rid)
    return TestSuite(requirement_id=rid, test_cases=g.test_cases, untestable_acs=g.untestable_acs)


def test_all_requirements_and_golden_sets_load():
    reqs = load_requirements()
    assert [r.id for r in reqs] == REQUIREMENT_IDS
    assert sum(len(load_golden(r.id).test_cases) for r in reqs) == 75


@pytest.mark.parametrize("rid", REQUIREMENT_IDS)
def test_golden_sets_fully_cover_their_requirements(rid):
    trace = build_traceability(load_requirement(rid), golden_suite(rid))
    assert trace.coverage == 1.0
    assert trace.unknown_references == []


def test_traceability_flags_uncovered_untestable_and_unknown():
    req = load_requirement("R4")
    suite = golden_suite("R4")
    suite.test_cases = [tc for tc in suite.test_cases if "R4-AC4" not in tc.covers]
    suite.test_cases[0].covers.append("R4-AC99")
    trace = build_traceability(req, suite)
    status = {r.ac_id: r.status for r in trace.rows}
    assert status["R4-AC4"] == "NOT_COVERED"
    assert status["R4-AC6"] == "UNTESTABLE"
    assert trace.uncovered == ["R4-AC4"]
    assert trace.unknown_references == ["R4-AC99"]
    assert trace.coverage == pytest.approx(4 / 5)


def test_r8_prompt_text_includes_openapi_attachment():
    text = load_requirement("R8").to_prompt_text()
    assert "R8-AC5" in text and "openapi: 3.0.3" in text


@pytest.mark.parametrize("rid", REQUIREMENT_IDS)
def test_generated_pytest_is_valid_python_with_one_test_per_case(rid):
    req, suite = load_requirement(rid), golden_suite(rid)
    tree = ast.parse(to_pytest(req, suite))
    funcs = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert len(funcs) == len(set(funcs)) == len(suite.test_cases)
    assert all(f.startswith("test_") for f in funcs)


def test_generated_pytest_runs_and_skips(tmp_path):
    req, suite = load_requirement("R1"), golden_suite("R1")
    path = tmp_path / "test_generated_r1.py"
    path.write_text(to_pytest(req, suite))
    assert pytest.main(["-q", "-p", "no:cacheprovider", "-o", "asyncio_default_fixture_loop_scope=function", str(path)]) == pytest.ExitCode.OK


@pytest.mark.parametrize("rid", REQUIREMENT_IDS)
def test_gherkin_has_one_scenario_per_case(rid):
    req, suite = load_requirement(rid), golden_suite(rid)
    feature = to_gherkin(req, suite)
    assert feature.startswith(f"@{rid}\nFeature: {req.title}")
    assert feature.count("  Scenario: ") == len(suite.test_cases)
    assert feature.count("    Then ") == len(suite.test_cases)


def test_table_renderers():
    req, suite = load_requirement("R2"), golden_suite("R2")
    rows = to_rows(suite)
    assert len(rows) == 9 and rows[0]["ID"] == "R2-TC01"
    table = to_markdown_table(suite)
    assert table.count("\n") == len(rows) + 1
    assert "| R2-AC3:" in traceability_markdown(build_traceability(req, suite))
    assert type_distribution(suite) == {"positive": 4, "boundary": 1, "edge": 2, "negative": 2}
