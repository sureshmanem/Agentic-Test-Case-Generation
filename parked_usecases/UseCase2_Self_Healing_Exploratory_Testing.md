# Use Case 2: Self-Healing & Exploratory UI/API Test Execution Agent

> Part of [Brainstorm.md](Brainstorm.md). Evaluated with **DeepEval** and **Ragas**.

## Problem

Flaky, brittle automation (changed locators, timing issues, UI changes) eats maintenance time. Scripted tests also miss problems that a human exploratory tester would find.

## What the Agent Does

- Runs the existing test suites. When a step fails, it inspects the DOM, screenshots and network logs to decide whether the failure is a **real defect** or a **test/locator issue**.
- **Self-heals** broken locators and waits, then proposes the fix as a PR so a human can approve it.
- In **exploratory mode**, it navigates the app toward a goal (for example "complete checkout as a guest user"), tries unusual paths and inputs, and records the anomalies it finds.
- Produces reproducible steps, evidence (screenshots/HAR) and a draft bug report.

## Agent Workflow

1. **Execute:** run the suite in a non-production environment.
2. **Diagnose:** on failure, collect DOM, screenshot, console and network evidence.
3. **Classify:** decide whether it is a real defect, a flaky test or an outdated locator.
4. **Act:**
   - Locator issue → generate a fix and open a PR (never auto-merge).
   - Real defect → draft a bug report with evidence.
5. **Explore (optional):** pursue goal-based exploratory sessions and log anomalies.

## Agent Tools

- Playwright/Selenium MCP or browser automation
- API client
- Log / console reader
- Git (branch + PR creation)

## How to Evaluate

| Concern | Metric |
|---|---|
| Agent completes the intended goal | DeepEval `TaskCompletionMetric` |
| Calls the right tools with correct arguments | DeepEval `ToolCorrectnessMetric`, Ragas `tool_call_accuracy` |
| Efficient trajectory (no loops or wasted steps) | DeepEval `StepEfficiencyMetric` / custom trajectory `GEval` |
| Correct defect vs. flake classification | Precision/recall against a labelled set of historical failures |

**Golden dataset:** historical failed runs labelled as *real defect*, *flaky* or *locator change*, plus reference trajectories for exploratory goals.

## Value

- Less automation maintenance.
- Faster triage of red builds.
- Broader exploratory coverage between releases.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| A "healed" test masks a real regression | Healing only via PR with human approval; never auto-merge |
| Agent acts on live systems | Non-prod environments only; scoped, least-privilege credentials |
| Runaway or looping exploration | Step/time budgets; trajectory evaluation |

## Priority

| Effort | Risk | Time-to-Value |
|---|---|---|
| High | Medium | Medium |
