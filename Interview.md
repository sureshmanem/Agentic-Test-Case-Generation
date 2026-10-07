# Interview Q&A: Agentic Test Case Generation

Questions and answers on the concepts, architecture and tools used in this project. Each answer covers the general concept and **how this project applies it**. See [Explanation.md](Explanation.md) for the project overview.

**Contents**
1. [Project and Problem](#1-project-and-problem)
2. [Agentic AI Concepts](#2-agentic-ai-concepts)
3. [LangGraph and Agent Architecture](#3-langgraph-and-agent-architecture)
4. [Retrieval (RAG) and Chroma](#4-retrieval-rag-and-chroma)
5. [LLM Engineering: Prompts and Structured Output](#5-llm-engineering-prompts-and-structured-output)
6. [Evaluation: LLM-as-Judge, DeepEval, Ragas](#6-evaluation-llm-as-judge-deepeval-ragas)
7. [Observability: LangSmith](#7-observability-langsmith)
8. [Testing the AI System Itself](#8-testing-the-ai-system-itself)
9. [CI/CD and Quality Gates](#9-cicd-and-quality-gates)
10. [Tooling: uv, Pydantic, Streamlit](#10-tooling-uv-pydantic-streamlit)
11. [QA Domain Concepts](#11-qa-domain-concepts)
12. [Credit Ratings Domain](#12-credit-ratings-domain)
13. [Design Trade-offs, Failures and Lessons](#13-design-trade-offs-failures-and-lessons)
14. [Scaling, Production and Security](#14-scaling-production-and-security)
15. [Rapid-Fire](#15-rapid-fire)

---

## 1. Project and Problem

**Q1. What does this project do, in one sentence?**
It generates test cases from requirements with an agentic LangGraph workflow and proves, with DeepEval, Ragas and per-item LLM verdicts, that the agent beats a single-prompt baseline against a hand-written golden set.

**Q2. Why compare against a baseline at all?**
Without a baseline you can't tell whether the extra complexity (6–8 LLM calls instead of 1) pays off. The baseline is a *fair* single prompt that asks for coverage, all test types, concrete data and clarification questions, so any improvement comes from the agentic design, not from a weak comparison.

**Q3. What does "proving the point" mean concretely here?**
Pre-agreed success criteria: agent acceptance-criteria coverage ≥ 0.8, faithfulness ≥ 0.85, golden scenario recall ≥ 0.8, and better than the baseline. On R3/R4/R6 the agent's golden scenario recall was 1.00 / 1.00 / 0.89 against the baseline's 0.56 / 0.40 / 0.22.

**Q4. What are the main weaknesses of a single-prompt test generator?**
It invents rules it doesn't know, misses rules outside the requirement text, guesses instead of asking about ambiguities, and gets domain arithmetic wrong. In this project the baseline once gave an upgrade as "−2 notches".

**Q5. What is a golden set and why is it central?**
A set of expert-written expected outputs (here 75 test cases linked to 46 acceptance criteria, plus 18 expected ambiguities). Every quality score is measured against it, so it is the project's ground truth. That's also why it needs independent expert review.

---

## 2. Agentic AI Concepts

**Q6. What makes a system "agentic" rather than a chain of prompts?**
An agent decides and acts across multiple steps toward a goal: it plans, uses tools (here: retrieval), observes results, and **changes course based on them** (here: a review step routes to revise or finalize). A fixed chain always runs the same steps; this graph has a conditional loop driven by its own findings.

**Q7. Which agentic patterns does this project use?**
- **Plan-and-execute:** a plan step lists test conditions, then a generate step writes tests for them.
- **Tool use / RAG:** the agent writes its own search queries and retrieves domain knowledge.
- **Reflection / self-critique:** a review node critiques the tests, and a revise node fixes them.
- **Bounded loop:** at most 2 revision rounds.
- **Human-in-the-loop hooks:** clarification questions and untestable criteria are surfaced instead of guessed.

**Q8. Why is "ask instead of guess" important for a QA agent?**
A test built on an invented rule is worse than no test: it gives false confidence and will fail or pass for the wrong reason. The agent must flag ambiguities, like R4-AC6 "large downgrade", as questions for the BA/PO.

**Q9. What is reflection, and what are its risks?**
The model critiques its own output and revises it. Risks: it can approve its own mistakes, invent problems, or loop forever. Mitigations used here: a *deterministic* gap check alongside the LLM critique, a hard iteration cap, and code-level rules (untestable criteria can never get tests).

**Q10. Why combine an LLM review with a deterministic check?**
LLMs are good at semantic critique (a wrong expected result, a vague assertion) but unreliable at bookkeeping. Counting which criteria and planned conditions have no test is a simple set difference, so code does it reliably and the LLM does the judgement.

**Q11. How do you stop an agent from looping forever?**
A cap on revision iterations (`MAX_SELF_CHECK_ITERATIONS=2`). The routing function sends the graph to `finalize` when the review is clean *or* the cap is reached, and finalize records whether findings are still open.

**Q12. When would you *not* use an agent?**
When a single prompt meets the quality bar, when latency or cost dominate (the agent here takes 35–50 s and 6–8 calls), or when the task needs no external knowledge or self-correction. That's what the baseline comparison quantifies.

---

## 3. LangGraph and Agent Architecture

**Q13. What is LangGraph?**
A library for building stateful, multi-step LLM applications as graphs: nodes are functions that read and update a shared state; edges, including conditional edges, define control flow, and loops are allowed. It compiles to a runnable that supports streaming and integrates with LangChain tracing.

**Q14. Describe this project's graph.**
`START → analyse → retrieve → plan → generate → review → (revise → review)* → finalize → END`. The conditional edge after `review` uses `route_after_review` to pick `revise` or `finalize`.

**Q15. What is in the agent state?**
A `TypedDict`: the requirement, analysis, untestable criteria (provisional, then confirmed), retrieved chunks, plan, current tests, review result, uncovered criteria and conditions, iteration count, final suite, and an append-only `trace`. The trace uses an `Annotated[list, operator.add]` **reducer**, so each node appends rather than overwrites.

**Q16. What is a reducer in LangGraph?**
A function that defines how a node's returned value merges into existing state. The default replaces it; `operator.add` concatenates lists. That's how every node adds a trace entry without knowing about the others.

**Q17. Why separate "plan" from "generate"?**
Planning decides *what* to test (conditions per criterion and type, with their source); generation decides *how*. That makes coverage checkable (every condition must have a test), reduces omissions, and gives the review step something concrete to check against.

**Q18. Why did you move the "untestable" decision from analyse to plan?**
A real CI run showed that analyse, which runs *before* retrieval, flagged criteria as untestable because "the mapping table is not provided", even though it's in the knowledge base. Code then removed their tests. Now analyse only proposes, and plan, which has the knowledge, confirms. This is a general lesson: make decisions at the step that has the information.

**Q19. How does the UI show agent progress live?**
`graph.stream(..., stream_mode="values")` yields the full state after each node. The pipeline emits new trace entries to an `on_step` callback, which Streamlit writes into an `st.status` panel.

**Q20. How is dependency injection used in the agent?**
`build_agent(llm, kb, max_iterations)` receives the LLM and knowledge base. Production passes `ChatOpenAI` and a Chroma store; tests pass a `FakeLLM` and fake embeddings. That's what makes the whole graph testable offline.

---

## 4. Retrieval (RAG) and Chroma

**Q21. What is RAG and why is it needed here?**
Retrieval-Augmented Generation: fetch relevant documents and give them to the model as context. Requirements here depend on rules outside their text (rating scales, the cross-agency mapping, error codes, other requirements, existing tests), and retrieval supplies them.

**Q22. How is the knowledge base built?**
Six markdown documents are split by `#`/`##` headings (`MarkdownHeaderTextSplitter`), so each chunk is a coherent section with `source` and `section` metadata. The chunks are embedded with OpenAI `text-embedding-3-small` into an in-memory Chroma collection using cosine distance.

**Q23. Why split by headings instead of fixed-size chunks?**
The documents are structured reference material (tables and rule sections). Heading-based chunks keep a whole table or rule together, which improves precision and keeps the context readable for both the model and the judge.

**Q24. How does the agent query the store?**
It searches with the requirement title plus user story and with the 3–6 queries the analyse step wrote, takes the top k=4 per query, deduplicates, keeps the best distance per chunk, and passes the best 8 to the model, each labelled `[source > section]`.

**Q25. Why is the vector store in-memory and rebuilt each run?**
It's small (6 docs, one embeddings call), and rebuilding means it can never go stale relative to the documents. A persistent store would need invalidation logic; at this scale that cost isn't worth it.

**Q26. How do you know retrieval is working?**
Ragas `context_precision` (are retrieved chunks relevant?) and `context_recall` (does the context contain the facts the golden tests need?). The distractor document `short_term_ratings.md` exists so that retrieving it lowers precision. On R4, context recall was 0.38 with the requirement alone (baseline) and 1.00 with retrieval (agent).

---

## 5. LLM Engineering: Prompts and Structured Output

**Q27. What is structured output and why use strict mode?**
The model must return JSON that matches a schema. OpenAI's `json_schema` strict mode *guarantees* conformance, so there's no parsing or retry logic. The project calls `llm.with_structured_output(schema, method="json_schema", strict=True)`.

**Q28. What constraints does strict mode impose, and how did you handle them?**
Every property must be required, every object must forbid extra keys, and open-ended objects like `dict[str, Any]` are not allowed. So the **LLM-facing schemas are separate from the domain models**: test data is returned as `test_data_json: str` and parsed afterwards, and untestable criteria are a list of `{ac_id, reason}` instead of a dict.

**Q29. How do you know a schema is strict-compatible without calling the API?**
A unit test runs every LLM schema through the OpenAI SDK's own `to_strict_json_schema` and checks that each object has `additionalProperties: false` and requires all its properties. A negative check confirms that it rejects a non-compliant schema.

**Q30. What prompt-design principles were used?**
A clear role ("senior QA test analyst"), explicit output responsibilities per node, grounding rules ("use only facts from the requirement and the domain knowledge; never invent error codes"), concrete-data and verifiable-result requirements, and an explicit permission to ask instead of guessing.

**Q31. Why not rely on prompts alone for rules like "no tests for untestable criteria"?**
Because the model ignored that instruction in a live run: it flagged R4-AC6 and then wrote 9 tests with an invented threshold. Critical rules are **enforced in code** (conditions and tests that cover only untestable criteria are dropped at every stage); the prompt is the first line of defence, not the only one.

**Q32. Why temperature 0?**
To reduce variance in both generation and judging, which makes comparisons more stable. It doesn't remove non-determinism completely, which is why evaluation supports `--repeats`.

---

## 6. Evaluation: LLM-as-Judge, DeepEval, Ragas

**Q33. What is LLM-as-a-judge?**
Using an LLM to score outputs against criteria, references or context. It scales where human review can't, but it's noisy and can be biased, so it needs careful design, repeats and spot checks.

**Q34. What layers of evaluation does the project use?**
1. **Deterministic:** acceptance-criteria coverage, test-type diversity, unknown criterion references.
2. **Per-item LLM verdicts:** golden scenario recall and conflicts, ambiguity detection.
3. **DeepEval:** faithfulness, no-hallucination, test quality (`GEval`).
4. **Ragas:** faithfulness, context recall, context precision.

**Q35. What is DeepEval?**
An open-source LLM evaluation framework with pytest-style test cases (`LLMTestCase`) and metrics such as `FaithfulnessMetric`, `HallucinationMetric`, and `GEval` for custom criteria. Here each metric is called with `metric.measure(test_case)` and judged by `gpt-4.1-mini`.

**Q36. What is GEval?**
A DeepEval metric where you describe criteria or evaluation steps in natural language; the judge scores the output from 0 to 1. It's flexible, but holistic. This project uses it only for overall test quality.

**Q37. Why did you replace the GEval coverage and ambiguity metrics?**
On R4, a single holistic score over 16–32 tests said the agent lacked default-rating tests it actually had, and gave the baseline a higher score despite wrong notch arithmetic. One verdict per golden item (covered? matching test ids? conflicting expectation?) is **countable and auditable**: the report lists exactly which golden tests were missed or contradicted.

**Q38. What is the difference between DeepEval faithfulness and hallucination as used here?**
Faithfulness checks whether claims in the output are consistent with the retrieval context. Hallucination checks whether the output contradicts the provided context. Both use a *reference context* (the requirement plus the knowledge docs it references), so the baseline and the agent are judged against the same ground truth.

**Q39. What changed about DeepEval's HallucinationMetric, and how did you notice?**
In DeepEval 4 it scores 1 as a pass (it used to score the share of violations). A live test raised a deprecation warning; the code had treated lower as better. It's now reported as `no_hallucination`, higher is better.

**Q40. What is Ragas and which metrics are used?**
A RAG evaluation library. Here (0.4 `collections` API, `llm_factory` + `ascore`):
- `Faithfulness`: are claims supported by what the generator saw?
- `ContextRecall`: how much of the golden tests is supported by the generator's context (baseline: requirement only; agent: plus retrieval)?
- `ContextPrecisionWithReference` (agent only): are the retrieved chunks relevant?

**Q41. Why is Ragas faithfulness sometimes low even for good tests?**
It penalises claims not found in the context, and good tests contain **invented test data** (issuer ids, dates) on purpose. So it's read as a signal of groundedness, not as a correctness score. DeepEval faithfulness, which focuses on contradiction, is the primary gate metric.

**Q42. How do you deal with judge variance?**
Re-judging identical output moved a score from 0.92 to 0.53. So: temperature 0, per-item verdicts instead of holistic scores, `--repeats N` averaging, and reporting the reasons so humans can audit them.

**Q43. How did you stop the coverage metric from being gamed?**
Coverage is computed against the **golden** list of untestable criteria, not the generator's own list. Otherwise a generator could declare criteria untestable and score 100%. A unit test checks exactly that scenario.

**Q44. Why add success criteria after the first run? Isn't that moving the goalposts?**
AC coverage saturated at 100% for both modes, so "agent > baseline" on it can never pass and doesn't discriminate. Golden scenario recall was added as a criterion, the original criteria were **kept**, and the change is marked in the report (¹) and the change log. Transparency is what keeps it honest.

**Q45. What does a "conflicting expectation" mean, and what judge bug did you fix?**
A test that matches a golden scenario but expects a different outcome (for example a different notch count). The judge was marking tests with *different input data* as conflicts. Now a conflict requires equivalent inputs and a different outcome. After the fix, R6 conflicts dropped from 3.5 to 0.

---

## 7. Observability: LangSmith

**Q46. What is LangSmith and why use it here?**
A tracing and evaluation platform for LLM apps. It records each run as a tree of child runs (chains, LLM calls, retrievers) with inputs, outputs, tokens and latency. For an agent with loops it's how you see *why* a run produced what it did.

**Q47. How is tracing enabled, and what is traced?**
`LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in `.env`. Each generation is a root run (`agent R4`, `baseline R4`) with tags, metadata and a fixed `run_id` passed through a LangChain `RunnableConfig`. LangGraph nodes become child runs automatically, the Chroma search is a `@traceable(run_type="retriever")` run, and evaluations are `evaluate <mode> R<n>` traces.

**Q48. How are evaluation results connected to traces?**
Every metric score is sent with `client.create_feedback(run_id, key, score, comment, trace_id, session_id)` to the generation run it evaluated. You can then filter or sort runs by `golden_scenario_recall` and open the worst one to inspect its steps.

**Q49. How does DeepEval/Ragas judge traffic show up?**
The per-item verdict judge uses `ChatOpenAI`, so it's traced automatically. Ragas's `AsyncOpenAI` client is wrapped with `langsmith.wrappers.wrap_openai`. DeepEval uses its own client, so only its scores appear (inside the evaluation trace's outputs).

**Q50. What went wrong with tracing in tests, and how was it fixed?**
Once `.env` enabled tracing, offline tests sent 39 fake runs to LangSmith. `monkeypatch.delenv` didn't help because the LangSmith SDK **caches** environment variables. The fix is `tests/conftest.py`, which sets tracing off before anything imports the package, plus a test that asserts tests never trace.

---

## 8. Testing the AI System Itself

**Q51. How do you unit-test an LLM agent without calling an LLM?**
With a `FakeLLM` that mimics `with_structured_output(...).invoke(...)` and returns scripted Pydantic objects per schema, plus `DeterministicFakeEmbedding` for Chroma. Scripted scenarios drive the real graph: generate misses a criterion → review finds it → revise fixes it → coverage reaches 100%, and also "the review never passes" → the loop stops at 2.

**Q52. What does the offline suite cover?**
74 tests: data loading and golden coverage, renderers (the generated pytest parses and runs; Gherkin has one scenario per test), traceability, strict-schema compatibility, the full agent graph, the iteration cap, untestable enforcement and re-check, deterministic metrics, verdict counting, report rendering, gate logic, the Streamlit UI (`AppTest`), and tracing wiring (a recording tracer checks root-run names, tags and child runs).

**Q53. What are the live tests and why are they opt-in?**
Three tests marked `llm` run the real baseline, agent and judges. They're excluded by default (`addopts = "-m 'not llm'"`) so routine runs cost nothing; run them with `uv run pytest -m llm`.

**Q54. What did live tests find that offline tests could not?**
Ragas output truncated at `max_tokens=1024`, the DeepEval hallucination direction change, and model behaviour issues (an invented threshold, over-flagging untestable criteria). Offline tests verify *wiring*; live tests verify *behaviour and integrations*. You need both.

**Q55. How was the golden data itself validated?**
`scripts/validate_data.py` checks every criterion is covered (or explicitly untestable), that there are no unknown references, and that the arithmetic in the expected results is right: all 21 mappings, notch changes such as BBB→BB+ = −2, and the R6 selection rule, computed independently in code.

**Q56. How do you test a Streamlit app?**
`streamlit.testing.v1.AppTest` runs the script headless. Tests point outputs and reports at scratch folders, then assert on titles, metrics, code blocks, dataframes, expanders, and that no exceptions are raised. That includes with no outputs and with saved outputs, and switching modes.

---

## 9. CI/CD and Quality Gates

**Q57. What does the CI pipeline do?**
On every push and PR: `uv sync --locked`, data validation, offline tests. A manual job (`workflow_dispatch`) runs live generation and evaluation for selected requirements with `--repeats 2 --gate`, traced to LangSmith project `agentic-test-case-generation-ci`, and uploads `reports/` and `outputs/` as an artifact.

**Q58. What is the quality gate and why only absolute thresholds?**
`evaluate --gate` exits 1 if the agent's mean AC coverage, faithfulness or golden scenario recall falls below its threshold. Comparisons with the baseline are reported but don't block: a gate should catch regressions in the agent itself, and "coverage > baseline" can't pass when both reach 100%.

**Q59. Why is the live gate manual rather than on every push?**
It calls paid APIs and takes about 20 minutes. Running it on every push would be slow and expensive; it's run before releases or after prompt and model changes.

**Q60. What did the first live gate run teach you?**
It failed for real reasons: agent coverage was 0.82 because of the analyse-before-retrieve flaw, and R6 recall was 0.39 because of the judge's conflict bug. Both were fixed and verified (coverage 1.00, R6 recall 0.89). A gate that fails for real reasons is a gate that works.

**Q61. Any CI gotchas?**
`astral-sh/setup-uv` doesn't publish a floating major tag (`@v10` failed), so it's pinned to `@v10.2.0`. Secrets are passed as env vars; `LANGSMITH_TRACING` is set from whether the secret exists.

---

## 10. Tooling: uv, Pydantic, Streamlit

**Q62. Why uv?**
A fast Python package and project manager: creates an isolated `.venv`, resolves and locks dependencies (`uv.lock`), and runs commands in the environment (`uv run`). `uv sync --locked` gives identical environments locally and in CI.

**Q63. Why is `langchain-community` pinned below 0.4.2?**
Ragas 0.4.3 imports `langchain_community.chat_models.vertexai`, which was removed in 0.4.2, so `import ragas` failed. The pin is documented in `pyproject.toml` and should be removed once Ragas fixes it.

**Q64. How is Pydantic used?**
Domain models (`Requirement`, `TestCase`, `TestSuite`, `GoldenSet`), LLM output schemas, results (`GenerationResult`, `EvalRecord`), and JSON save/load. Validation gives type safety at every boundary between the LLM, files and the UI.

**Q65. What does the Streamlit app show?**
A requirement picker, live Baseline/Agent/Evaluate buttons (the agent streams its steps), header metrics, and tabs for: requirement and attachments, test cases (table / Gherkin / pytest / questions, with downloads), side-by-side traceability, the agent trace with the graph diagram and retrieved chunks, an evaluation table with judge reasons, the golden set, and a link to the LangSmith trace.

---

## 11. QA Domain Concepts

**Q66. What are positive, negative, boundary and edge tests?**
Positive: valid input, expected success. Negative: invalid input, expected rejection (e.g. `INVALID_RATING_SYMBOL`). Boundary: at the limits (Baa3 vs Ba1; watch age 90 vs 91 days). Edge: unusual but valid situations (`C` is valid on both scales; RD/D map one-way to `C`).

**Q67. What is a traceability matrix?**
A mapping from each requirement (here each acceptance criterion) to the tests that verify it, with status COVERED / NOT_COVERED / UNTESTABLE. It proves coverage and shows the impact of requirement changes.

**Q68. Why generate Gherkin and pytest as well as a table?**
Different consumers: tables for test management tools (Excel/TestRail import), Gherkin for BDD and business-readable specs, pytest for engineers to automate. All three come from one structured model, so they're always consistent.

**Q69. Why are the generated pytest files skeletons?**
There's no real system under test in the prototype. Each test embeds its data, steps and expected result, with a TODO for the system-under-test call, and skips until implemented. A test checks they're valid Python and run.

**Q70. How does the agent avoid duplicating existing regression tests?**
`existing_tests.md` is in the knowledge base; the plan step lists covered ids in `skipped_existing`, and the review step flags duplicates of regression tests or of other tests in the suite.

---

## 12. Credit Ratings Domain

**Q71. What is a notch, and how is notch change computed?**
One step on the rating scale. `notch_change = previous_ordinal − new_ordinal` on the agency's own scale: upgrades are positive, downgrades negative. BBB (9) → BB+ (11) = −2; Fitch-style CCC (18) → RD (22) = −4.

**Q72. What is the investment-grade boundary?**
Baa3 (Moody's-style) / BBB- (Fitch-style), common rank 10, is the lowest investment grade; Ba1 / BB+ (rank 11) is the highest speculative grade. It's a classic boundary-test target.

**Q73. Explain the regulatory rating selection rule (R6).**
Among eligible ratings (status codes excluded): one rating, use it; two, take the lower (worse); three, take the two best and use the lower of those (the second best). The result has a rank, a Fitch-style symbol, the source agency and the rule applied.

**Q74. Outlook vs. Watch?**
Outlook (Positive, Negative, Stable, Developing) is the medium-term direction; Watch (Positive, Negative, Developing) signals a short-term review and always has a direction. A rating has one or the other, never both; defaulted ratings and status codes have neither.

**Q75. Why use a synthetic domain?**
It avoids proprietary agency data and impersonation, lets the author plant ambiguities and traps on purpose, and keeps the arithmetic verifiable. The trade-off is realism, so expert review of the golden set is a next step.

---

## 13. Design Trade-offs, Failures and Lessons

**Q76. What were the most important lessons?**
1. Inspect real outputs: several "wins" and "losses" were measurement artefacts.
2. Prefer countable, per-item judgements over holistic LLM scores.
3. Enforce critical rules in code, not only in prompts.
4. Make decisions at the step that has the information (testability after retrieval).
5. LLM judges are noisy: use repeats and keep the reasons.
6. Live tests catch integration and behaviour issues that offline tests can't.

**Q77. Cost and latency trade-off of the agent?**
About 6–8 calls and 35–50 s per requirement vs. 1 call and about 10 s for the baseline. In return: much higher golden scenario recall, grounded results, no invented rules. For test design, which is done once per requirement change, that trade is usually worth it; caching and smaller models for some nodes could reduce it.

**Q78. What would you change with more time?**
A full R1–R8 run with repeats and confidence intervals; expert-reviewed goldens; a clarification loop (answers fed back into the agent); a cheaper model for analyse and review; caching; real Jira/Confluence input; executable tests against a real API; and comparing models.

**Q79. How do you keep evaluation honest?**
A fair baseline, a fixed golden set, metrics that can't be gamed, original success criteria kept and additions marked, every change logged with the reason, per-item reasons stored, and repeats to average out judge noise.

---

## 14. Scaling, Production and Security

**Q80. How would this scale to hundreds of requirements?**
Batch and parallelise per requirement (they're independent); use a persistent, incrementally updated vector store; cache embeddings and judge results; route simpler nodes to cheaper models; track cost per run in LangSmith; and run the live gate on a representative sample.

**Q81. How would you integrate it into a real QA workflow?**
Trigger on new or changed Jira stories; post clarification questions back to the story; push approved tests to Xray/Zephyr/TestRail; commit generated Gherkin and pytest to the automation repo via a PR for human review; attach the traceability matrix to the story.

**Q82. What security considerations apply?**
API keys only in `.env` (gitignored) or CI secrets; `.env.example` holds placeholders only; tests never send traces; least-privilege credentials for integrations; mask PII and confidential data before sending to an LLM; and review LangSmith data-retention settings, since traces contain prompts and outputs.

**Q83. How do you guard against prompt injection from requirement text?**
Treat requirement and document text as data, not instructions; keep system prompts separate; constrain outputs with strict schemas; enforce critical rules in code; and require human review before tests are merged or pushed to tools.

---

## 15. Rapid-Fire

| Question | Answer |
|---|---|
| Generation model? | `gpt-4.1` |
| Judge model? | `gpt-4.1-mini` |
| Embeddings? | `text-embedding-3-small` |
| Vector store? | Chroma, in-memory, cosine |
| Agent framework? | LangGraph |
| Max revision rounds? | 2 |
| Retrieval? | k=4 per query, best 8 chunks |
| Requirements / criteria / golden tests? | 8 / 46 / 75 |
| Expected ambiguities? | 18 (+1 untestable criterion, R4-AC6) |
| Offline / live tests? | 74 / 3 |
| Package manager? | uv |
| Tracing? | LangSmith (optional), scores sent as feedback |
| Demo? | Streamlit |
| CI gate thresholds? | coverage ≥ 0.8, faithfulness ≥ 0.85, golden recall ≥ 0.8 |
