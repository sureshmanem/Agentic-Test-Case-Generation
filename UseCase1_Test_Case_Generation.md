# Use Case 1: Autonomous Test Case Generation from Requirements

> Evaluated with **DeepEval** and **Ragas**.

## Problem

Writing test cases from user stories, PRDs and API specs by hand is slow, gets uneven coverage, and falls behind when requirements change.

## What the Agent Does

- Ingests requirements (Jira stories, Confluence pages, OpenAPI/Swagger specs, acceptance criteria).
- Retrieves related context such as existing tests, domain rules and past defects through RAG.
- Plans and generates functional, negative, boundary and edge-case test cases (Gherkin/BDD or structured test steps).
- Builds a requirement-to-test **traceability matrix** and flags ambiguous or untestable requirements back to the BA/PO.
- Can optionally emit executable skeletons (pytest, Playwright, REST Assured).

## Agent Workflow

1. **Ingest:** pull the requirement and its acceptance criteria.
2. **Retrieve:** fetch related specs, existing tests and historical defects from the vector store.
3. **Plan:** identify test conditions (positive, negative, boundary, edge).
4. **Generate:** write the test cases in the target format.
5. **Self-check:** verify that every acceptance criterion maps to at least one test, and flag any gaps.
6. **Review gate:** a human approves the tests before they are pushed to the test management tool.

## Agent Tools

- Document retriever / vector store
- Spec parser (OpenAPI, Gherkin)
- Test management API (Xray / Zephyr / TestRail)
- Code writer for executable skeletons

## How to Evaluate

| Concern | Metric |
|---|---|
| Tests grounded in the requirement (no invented features) | Ragas `faithfulness`, DeepEval `FaithfulnessMetric` |
| Retrieved context is relevant and complete | Ragas `context_precision`, `context_recall` |
| Coverage of acceptance criteria | DeepEval `GEval` with a custom "requirement coverage" rubric |
| No hallucinated fields or endpoints | DeepEval `HallucinationMetric` |

**Golden dataset:** pairs of requirement → expected test cases, written and reviewed by senior QA engineers.

## Value

- 40–60% less test-design effort (typical estimate, to be validated in a pilot).
- Better negative and edge-case coverage.
- Living traceability between requirements and tests.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Hallucinated behaviour or endpoints | Faithfulness/hallucination gates in CI; human review |
| Weak coverage when specs are vague | Agent flags ambiguous requirements instead of guessing |
| Duplicate tests | Retrieve existing tests first and de-duplicate |

## Priority

| Effort | Risk | Time-to-Value |
|---|---|---|
| Medium | Low | Fast |
