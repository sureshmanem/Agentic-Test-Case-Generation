# DeepEval & Ragas: Agentic Test Case Generation

An agentic AI solution for **Quality Assurance** that generates test cases from requirements. Its output is evaluated with [DeepEval](https://github.com/confident-ai/deepeval) and [Ragas](https://github.com/explodinggradients/ragas).

## Use Case: Autonomous Test Case Generation from Requirements

The agent ingests requirements (user stories, acceptance criteria, API specs), retrieves related context, and generates functional, negative, boundary and edge-case tests, with a requirement-to-test traceability matrix.

The full design is in [UseCase1_Test_Case_Generation.md](UseCase1_Test_Case_Generation.md).

### Evaluation Approach

| Concern | Metric |
|---|---|
| Tests grounded in the requirement | Ragas `faithfulness`, DeepEval `FaithfulnessMetric` |
| Retrieved context is relevant and complete | Ragas `context_precision`, `context_recall` |
| Coverage of acceptance criteria | DeepEval `GEval` (custom coverage rubric) |
| No hallucinated fields or endpoints | DeepEval `HallucinationMetric` |

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for package management and an isolated virtual environment (`.venv`).

```bash
# Install uv (if needed)
brew install uv            # or: curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and create the environment from the lock file
git clone https://github.com/sureshmanem/DeepEval_And_Ragas.git
cd DeepEval_And_Ragas
uv sync
```

### Common Commands

```bash
uv add <package>             # add a dependency
uv remove <package>          # remove a dependency
uv run python <script>.py    # run inside the env
uv run deepeval test run <test_file>.py
source .venv/bin/activate    # optional: activate manually
```

### Dependencies

- Python 3.13
- `deepeval`
- `ragas`
- `langchain-community<0.4.2`: pinned because `ragas` 0.4.3 imports a module that was removed in `langchain-community` 0.4.2.

## Project Structure

```
.
├── README.md
├── UseCase1_Test_Case_Generation.md   # Use case design
├── pyproject.toml                     # Project & dependencies
├── uv.lock                            # Locked dependency versions
└── .python-version
```

## Roadmap

- [x] Use case design
- [x] Environment setup (uv)
- [ ] Golden dataset: requirements → expected test cases
- [ ] Test-generation agent (retrieve → plan → generate → self-check)
- [ ] DeepEval / Ragas evaluation suite
- [ ] Evaluation as a CI quality gate
