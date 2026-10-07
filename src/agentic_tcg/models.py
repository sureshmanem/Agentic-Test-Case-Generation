"""Domain models for requirements and generated test cases, plus data loaders."""

import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agentic_tcg.config import GOLDEN_DIR, KNOWLEDGE_DIR, REQUIREMENTS_DIR


class AcceptanceCriterion(BaseModel):
    id: str
    text: str


class Requirement(BaseModel):
    id: str
    title: str
    component: str
    user_story: str
    acceptance_criteria: list[AcceptanceCriterion]
    references: list[str] = Field(default_factory=list)
    attachments: list[str] = Field(default_factory=list)

    @property
    def ac_ids(self) -> list[str]:
        return [ac.id for ac in self.acceptance_criteria]

    def attachment_texts(self) -> dict[str, str]:
        return {name: (REQUIREMENTS_DIR / name).read_text() for name in self.attachments}

    def to_prompt_text(self, include_attachments: bool = True) -> str:
        lines = [
            f"Requirement {self.id}: {self.title}",
            f"Component: {self.component}",
            f"User story: {self.user_story}",
            "Acceptance criteria:",
            *[f"- {ac.id}: {ac.text}" for ac in self.acceptance_criteria],
        ]
        if include_attachments:
            for name, text in self.attachment_texts().items():
                lines += ["", f"Attachment {name}:", text]
        return "\n".join(lines)


class TestType(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    BOUNDARY = "boundary"
    EDGE = "edge"


class Priority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TestCase(BaseModel):
    """One test case. Same shape as the golden test cases in data/golden."""

    __test__ = False  # not a pytest test class

    id: str = Field(description="Unique id, e.g. R1-TC01")
    title: str
    type: TestType
    priority: Priority
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str]
    test_data: dict[str, Any] = Field(default_factory=dict)
    expected_result: str
    covers: list[str] = Field(description="Acceptance criterion ids this test verifies, e.g. ['R1-AC1']")


class TestSuite(BaseModel):
    __test__ = False

    requirement_id: str
    test_cases: list[TestCase] = Field(default_factory=list)
    clarification_questions: list[str] = Field(
        default_factory=list,
        description="Ambiguities or gaps in the requirement that need an answer from the BA/PO",
    )
    untestable_acs: dict[str, str] = Field(
        default_factory=dict, description="Acceptance criterion id -> why it cannot be tested as written"
    )


class GoldenSet(BaseModel):
    requirement_id: str
    expected_ambiguities: list[str] = Field(default_factory=list)
    untestable_acs: dict[str, str] = Field(default_factory=dict)
    test_cases: list[TestCase]


# ---------- loaders ----------

def _find(directory: Path, prefix: str) -> Path:
    matches = sorted(directory.glob(f"{prefix}_*.json"))
    if not matches:
        raise FileNotFoundError(f"No file for {prefix} in {directory}")
    return matches[0]


def load_requirement(requirement_id: str) -> Requirement:
    return Requirement.model_validate_json(_find(REQUIREMENTS_DIR, requirement_id).read_text())


def load_requirements() -> list[Requirement]:
    return [Requirement.model_validate_json(p.read_text()) for p in sorted(REQUIREMENTS_DIR.glob("R*_*.json"))]


def load_golden(requirement_id: str) -> GoldenSet:
    return GoldenSet.model_validate_json((GOLDEN_DIR / f"{requirement_id}_golden.json").read_text())


def load_knowledge_docs() -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(KNOWLEDGE_DIR.glob("*.md"))}


def save_json(model: BaseModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n")
