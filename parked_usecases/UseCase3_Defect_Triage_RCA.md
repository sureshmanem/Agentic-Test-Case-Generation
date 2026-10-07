# Use Case 3: Intelligent Defect Triage & Root-Cause Analysis Agent

> Part of [Brainstorm.md](Brainstorm.md). Evaluated with **DeepEval** and **Ragas**.

## Problem

After a CI run or production incident, QA spends hours reading logs, de-duplicating bugs, assigning severity and routing work to the right team.

## What the Agent Does

- Watches CI/CD pipelines and incoming bug reports.
- Clusters failures, finds **duplicates** of existing tickets, and links related failures.
- Correlates failures with recent commits, deployments, config changes and logs to propose a **probable root cause** and suspect change.
- Suggests severity/priority, owning component and assignee, and writes a clean ticket with reproduction steps.
- Recommends **risk-based regression scope** for the next run (which tests to re-run given the changed code).

## Agent Workflow

1. **Trigger:** a CI failure or a new bug report arrives.
2. **Gather:** pull logs, stack traces, recent commits and deployments.
3. **De-duplicate:** search past defects in the vector store for similar issues.
4. **Analyse:** correlate the evidence and propose a root cause with cited sources.
5. **Draft:** write or update the ticket with severity, component and owner suggestions.
6. **Recommend:** list the regression tests to re-run for the affected code.
7. **Review gate:** a human approves severity changes and ticket creation (at least initially).

## Agent Tools

- CI APIs (Jenkins / GitHub Actions / Azure DevOps)
- Jira (search, create, update)
- Log / observability search (Splunk / ELK / Datadog)
- Git history
- Vector store of past defects

## How to Evaluate

| Concern | Metric |
|---|---|
| Root-cause explanation supported by the evidence | Ragas `faithfulness`, DeepEval `FaithfulnessMetric` |
| Retrieves the right historical defects and logs | Ragas `context_precision` / `context_recall`, DeepEval `ContextualRelevancyMetric` |
| Ticket summary quality | DeepEval `SummarizationMetric`, `GEval` rubric |
| Duplicate detection / routing accuracy | Precision, recall and F1 against historical triage decisions |

**Golden dataset:** past incidents with their confirmed root cause, final severity, owning team and known duplicates.

## Value

- Shorter MTTR and triage time.
- Fewer duplicate tickets.
- Leaner, risk-focused regression cycles.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Confident but wrong root-cause claims | Always cite supporting evidence; faithfulness gate |
| Wrong severity or routing | Human approval for severity changes at first |
| Sensitive data in logs | PII masking before sending logs to the LLM |

## Priority

| Effort | Risk | Time-to-Value |
|---|---|---|
| Medium | Low–Medium | Fast |
