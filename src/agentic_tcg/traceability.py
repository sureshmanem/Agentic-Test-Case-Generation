"""Requirement-to-test traceability and deterministic coverage measures."""

from pydantic import BaseModel

from agentic_tcg.models import Requirement, TestSuite


class TraceRow(BaseModel):
    ac_id: str
    ac_text: str
    test_ids: list[str]
    status: str  # COVERED | NOT_COVERED | UNTESTABLE


class Traceability(BaseModel):
    requirement_id: str
    rows: list[TraceRow]
    unknown_references: list[str]  # ids in `covers` that are not acceptance criteria

    @property
    def uncovered(self) -> list[str]:
        return [r.ac_id for r in self.rows if r.status == "NOT_COVERED"]

    @property
    def coverage(self) -> float:
        """Share of testable acceptance criteria covered by at least one test."""
        testable = [r for r in self.rows if r.status != "UNTESTABLE"]
        return 1.0 if not testable else sum(r.status == "COVERED" for r in testable) / len(testable)


def build_traceability(requirement: Requirement, suite: TestSuite) -> Traceability:
    rows = []
    for ac in requirement.acceptance_criteria:
        test_ids = [tc.id for tc in suite.test_cases if ac.id in tc.covers]
        if test_ids:
            status = "COVERED"
        elif ac.id in suite.untestable_acs:
            status = "UNTESTABLE"
        else:
            status = "NOT_COVERED"
        rows.append(TraceRow(ac_id=ac.id, ac_text=ac.text, test_ids=test_ids, status=status))
    known = set(requirement.ac_ids)
    unknown = sorted({c for tc in suite.test_cases for c in tc.covers if c not in known})
    return Traceability(requirement_id=requirement.id, rows=rows, unknown_references=unknown)


def type_distribution(suite: TestSuite) -> dict[str, int]:
    dist: dict[str, int] = {}
    for tc in suite.test_cases:
        dist[tc.type.value] = dist.get(tc.type.value, 0) + 1
    return dist
