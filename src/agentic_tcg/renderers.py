"""Render a TestSuite as a table, Gherkin feature file, or pytest skeleton."""

import json
import re

from agentic_tcg.models import Requirement, TestSuite
from agentic_tcg.traceability import Traceability


def to_rows(suite: TestSuite) -> list[dict[str, str]]:
    """Flat rows for a table / DataFrame / CSV export."""
    return [
        {
            "ID": tc.id,
            "Title": tc.title,
            "Type": tc.type.value,
            "Priority": tc.priority.value,
            "Preconditions": "\n".join(tc.preconditions),
            "Steps": "\n".join(f"{i}. {s}" for i, s in enumerate(tc.steps, 1)),
            "Test data": json.dumps(tc.test_data, ensure_ascii=False) if tc.test_data else "",
            "Expected result": tc.expected_result,
            "Covers": ", ".join(tc.covers),
        }
        for tc in suite.test_cases
    ]


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>")


def to_markdown_table(suite: TestSuite) -> str:
    rows = to_rows(suite)
    if not rows:
        return "_No test cases._"
    headers = list(rows[0])
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_md_cell(r[h]) for h in headers) + " |" for r in rows]
    return "\n".join(lines)


def traceability_markdown(trace: Traceability) -> str:
    lines = ["| Acceptance criterion | Tests | Status |", "|---|---|---|"]
    for r in trace.rows:
        lines.append(f"| {r.ac_id}: {_md_cell(r.ac_text)} | {', '.join(r.test_ids) or '-'} | {r.status} |")
    return "\n".join(lines)


def to_gherkin(requirement: Requirement, suite: TestSuite) -> str:
    lines = [
        f"@{requirement.id}",
        f"Feature: {requirement.title}",
        f"  {requirement.user_story}",
        "",
    ]
    for tc in suite.test_cases:
        tags = " ".join([f"@{tc.id}", f"@{tc.type.value}", f"@{tc.priority.value}", *[f"@{c}" for c in tc.covers]])
        lines += [f"  {tags}", f"  Scenario: {tc.title}"]
        keyword = "Given"
        for pre in tc.preconditions:
            lines.append(f"    {keyword} {pre}")
            keyword = "And"
        if tc.test_data:
            lines.append(f"    {keyword} the test data {json.dumps(tc.test_data, ensure_ascii=False)}")
        keyword = "When"
        for step in tc.steps:
            lines.append(f"    {keyword} {step}")
            keyword = "And"
        lines += [f"    Then {tc.expected_result}", ""]
    return "\n".join(lines).rstrip() + "\n"


def _slug(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:max_len].rstrip("_") or "case"


def to_pytest(requirement: Requirement, suite: TestSuite) -> str:
    """Executable pytest skeletons: data, steps and expected result are embedded;
    the system-under-test calls are left as TODOs and the tests skip until implemented."""
    lines = [
        f'"""Generated tests for {requirement.id}: {requirement.title}.',
        "",
        "Skeletons: replace the TODO sections with calls to the system under test.",
        '"""',
        "",
        "import pytest",
    ]
    seen: set[str] = set()
    for tc in suite.test_cases:
        name = f"test_{_slug(tc.id)}_{_slug(tc.title, 40)}"
        while name in seen:
            name += "_x"
        seen.add(name)
        doc = [tc.title, "", f"Type: {tc.type.value} | Priority: {tc.priority.value} | Covers: {', '.join(tc.covers)}"]
        if tc.preconditions:
            doc += ["", "Preconditions:", *[f"  - {p}" for p in tc.preconditions]]
        doc += ["", "Steps:", *[f"  {i}. {s}" for i, s in enumerate(tc.steps, 1)], "", f"Expected: {tc.expected_result}"]
        docstring = "\n    ".join(d.replace('"""', "'''").replace("\\", "\\\\") for d in doc)
        lines += [
            "",
            "",
            f"def {name}():",
            f'    """{docstring}\n    """',
            f"    test_data = {tc.test_data!r}",
            "    # TODO: arrange preconditions, act on the system under test, assert the expected result",
            '    pytest.skip("Not implemented: generated skeleton")',
        ]
    text = "\n".join(lines)
    return "\n".join(line.rstrip() for line in text.splitlines()).rstrip() + "\n"
