# Prototype Data: Credit Ratings Domain (Synthetic)

All data is **synthetic**. Issuers are fictional, and the rating scales are simplified versions of the publicly known Moody's-style and Fitch-style long-term symbols. `NORTHBRIDGE` is a fictional third agency that uses Fitch-style symbols. Nothing here is official agency methodology.

## Layout

| Folder | Purpose | Used by |
|---|---|---|
| `requirements/` | 8 requirements (user story + numbered acceptance criteria). R8 also has an OpenAPI spec. | Agent and baseline input |
| `golden/` | Expected test cases per requirement, each linked to the criteria it covers (`covers`), plus `expected_ambiguities` and `untestable_acs` | Evaluation (coverage, ambiguity detection) |
| `knowledge/` | Documents for the Chroma retrieval store | Agent retrieval step, Ragas context metrics |

## Requirements

| ID | Title | ACs | Golden tests |
|---|---|---|---|
| R1 | Rating Symbol Validation | 6 | 10 |
| R2 | Cross-Agency Rating Mapping | 6 | 9 |
| R3 | Investment vs. Speculative Grade Classification | 5 | 9 |
| R4 | Rating Actions and Notch Change | 6 | 10 |
| R5 | Outlook and Watch Status | 5 | 9 |
| R6 | Regulatory Rating Selection Rule | 6 | 9 |
| R7 | Rating History and Audit Trail | 6 | 9 |
| R8 | Issuer Ratings REST API | 6 | 10 |
| | **Total** | **46** | **75** |

## Golden Test Case Schema

```json
{
  "id": "R1-TC01",
  "title": "...",
  "type": "positive | negative | boundary | edge",
  "priority": "high | medium | low",
  "preconditions": ["..."],
  "steps": ["..."],
  "test_data": {},
  "expected_result": "...",
  "covers": ["R1-AC1"]
}
```

## Deliberate Traps

These traps check whether the agent **asks** instead of **guessing**:
- **Ambiguities:** every golden file lists `expected_ambiguities`, the gaps or unclear points a good test designer should flag (e.g. the tie-break rule in R6, "10 years" in R7).
- **Untestable criterion:** R4-AC6 ("large downgrades must be highlighted") is vague on purpose. The golden file marks it in `untestable_acs`.
- **Existing tests:** `knowledge/existing_tests.md` lists tests the agent should not duplicate.
- **Distractor document:** `knowledge/short_term_ratings.md` is out of scope. Retrieving it lowers context precision.

## Validation

```bash
uv run python scripts/validate_data.py
```
It checks JSON validity, acceptance-criteria coverage, unknown references, and the rating arithmetic (mappings, notch changes, regulatory selection).
