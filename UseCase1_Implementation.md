# UseCase1 Implementation Plan: Agentic Test Case Generation (Prototype)

> Living document. It tracks the implementation steps, their status, and every change to the plan.
> Design reference: [UseCase1_Test_Case_Generation.md](UseCase1_Test_Case_Generation.md)

## Goal: Prove the Point

Given requirements, the agent produces test cases that:
1. **Cover** every acceptance criterion (`GEval` coverage)
2. **Stay grounded**, with no invented fields or behaviour (faithfulness / hallucination)
3. **Outperform a single-prompt baseline** on those scores

Proposed success thresholds (to be confirmed): coverage ≥ 0.8, faithfulness ≥ 0.85, agent > baseline on both.

## Decisions

| Area | Decision |
|---|---|
| LLM | OpenAI: `gpt-4.1` for generation, `gpt-4.1-mini` as DeepEval/Ragas judge |
| Domain | Credit ratings (Moody's-style and Fitch-style scales), synthetic data, fictional issuers |
| Input data | Synthetic requirements + golden test sets |
| Agent framework | LangGraph |
| Retrieval | Yes: small local Chroma vector store |
| Output formats | Structured JSON/table, Gherkin (BDD), executable pytest |
| Demo | Streamlit app |
| Package manager | uv, isolated `.venv` |
| Secrets | `OPENAI_API_KEY` in `.env` (gitignored) |

## Progress Tracker

Status: ⬜ Not started · 🟡 In progress · ✅ Done

| Step | Description | Status |
|---|---|---|
| 0 | Environment setup (uv, git, GitHub repo) | ✅ |
| 1 | Synthetic ratings requirements, golden test sets, knowledge base | ✅ |
| 2 | Project scaffold (dependencies, package layout, config, `.env.example`) | ✅ |
| 3 | `TestCase` model + renderers (JSON/table, Gherkin, pytest) | ⬜ |
| 4 | Baseline single-prompt generator | ⬜ |
| 5 | LangGraph agent (analyse → retrieve → plan → generate → self-check → traceability) | ⬜ |
| 6 | Evaluation suite (DeepEval + Ragas), agent vs. baseline report | ⬜ |
| 7 | Streamlit demo | ⬜ |
| 8 | Wrap-up: README results, optional CI quality gate | ⬜ |

---

## Step Details

### Step 0: Environment Setup ✅
- uv project with Python 3.13, isolated `.venv`, `deepeval` + `ragas` installed.
- `langchain-community<0.4.2` pinned (ragas 0.4.3 imports a module removed in 0.4.2).
- Git initialised; private GitHub repo `sureshmanem/Agentic-Test-Case-Generation`.

### Step 1: Synthetic Data ✅
Location: `data/`

| # | Requirement | Testing focus |
|---|---|---|
| R1 | Rating symbol validation (Moody's / Fitch scales) | Boundary, negative |
| R2 | Cross-agency rating mapping | Table-driven, symmetry |
| R3 | Investment vs. speculative grade classification | IG/SG boundary (Baa3/BBB−) |
| R4 | Rating actions (upgrade/downgrade/affirm, notch change) | Business rules, dates |
| R5 | Outlook and Watch status | State consistency |
| R6 | Regulatory rating selection rule (multi-agency) | Multi-branch logic |
| R7 | Rating history and audit trail | Date ranges, immutability |
| R8 | Issuer Ratings REST API (OpenAPI) | Executable pytest output |

Delivered (see [data/README.md](data/README.md)):
- `data/requirements/`: 8 requirements, **46 acceptance criteria**, plus `R8_issuer_ratings_api.openapi.yaml`
- `data/golden/`: **75 golden test cases** (positive / negative / boundary / edge), each linked to the criteria it covers; **18 expected ambiguities**; 1 deliberately untestable criterion (R4-AC6)
- `data/knowledge/` (6 docs): `rating_scales.md`, `cross_agency_mapping.md`, `rating_rules.md`, `error_codes.md`, `existing_tests.md` (tests the agent must not duplicate), `short_term_ratings.md` (distractor, to measure retrieval precision)
- `scripts/validate_data.py`: consistency checks (AC coverage, references, mapping/notch/selection arithmetic). **All checks pass.**

Traps built in to show the agent's value over a single prompt:
- Ambiguities the agent should raise as questions instead of guessing
- A vague criterion (R4-AC6, "large downgrade") that should produce a clarification, not an invented threshold
- Cross-requirement rules that are only in the knowledge base (e.g. R6 depends on the R2 mapping; R8 depends on the R1/R4 rules)
- Existing regression tests to avoid duplicating

### Step 2: Project Scaffold ✅
- Dependencies added with uv: `langgraph`, `langchain-openai`, `langchain-chroma`, `chromadb`, `streamlit`, `python-dotenv`, `openai` (dev: `pytest`).
- `pyproject.toml`: hatchling build system so `src/agentic_tcg` installs as a package; pytest marker `llm` for tests that call OpenAI.
- `src/agentic_tcg/config.py`: paths + `Settings` (models, self-check iterations, retrieval k) from env / `.env`.
- `.env.example`: template for `OPENAI_API_KEY` and model overrides. `.chroma/` and `outputs/` are gitignored.

### Step 3: Test Case Model + Renderers ⬜
Pydantic `TestCase` (id, title, type, priority, preconditions, steps, test_data, expected_result, covers) → JSON/table, Gherkin `.feature`, pytest skeleton.

### Step 4: Baseline ⬜
Single `gpt-4.1` prompt: requirement → test cases (same schema).

### Step 5: LangGraph Agent ⬜
```
analyse → retrieve (Chroma) → plan conditions → generate → self-check ──gaps?──┐
                                                    ▲                          │
                                                    └───────── regenerate ─────┘
                                                               no gaps → traceability matrix → render
```
Self-check loop capped at 2 iterations.

### Step 6: Evaluation ⬜
- DeepEval: Faithfulness, Hallucination, `GEval` coverage, `GEval` test quality, AC coverage vs. golden.
- Ragas: `faithfulness`, `context_precision`, `context_recall`.
- Output: `reports/comparison.md` (agent vs. baseline per requirement + overall).

### Step 7: Streamlit Demo ⬜
Pick a requirement → generated tests (table / Gherkin / pytest) → traceability matrix → agent trace → scores vs. baseline.

### Step 8: Wrap-up ⬜
README run instructions + results summary; optional GitHub Actions `deepeval test run` quality gate.

---

## Change Log

| Date | Change |
|---|---|
| 2026-10-06 | Plan created. Decisions: OpenAI gpt-4.1, credit-ratings domain, LangGraph, Chroma RAG, JSON/Gherkin/pytest outputs, Streamlit demo. |
| 2026-10-06 | R6 uses three agencies (Moody's-style, Fitch-style, and fictional "Northbridge Ratings" with Fitch-style symbols), so the three-rating "second-best" rule can be tested. |
| 2026-10-06 | Deliberate ambiguities added to some requirements (e.g., R4 "large downgrade") to test whether the agent flags them instead of guessing. |
| 2026-10-06 | Step 1 completed: 8 requirements, 75 golden tests, 6 knowledge docs, validation script. Golden files gained an `untestable_acs` field (used by R4-AC6) so evaluation can tell intentionally untestable criteria apart from real coverage gaps. |
| 2026-10-06 | Golden test case schema fixed (id, title, type, priority, preconditions, steps, test_data, expected_result, covers). Step 3's Pydantic `TestCase` will use the same shape. |
| 2026-10-06 | Step 2 completed. Ragas 0.4.3 metrics are used through the new `ragas.metrics.collections` API (`llm_factory` + `ascore`), confirmed against the installed package. Offline unit tests with fake LLM/embeddings added to the plan, because the API key is only available after Step 8. |
