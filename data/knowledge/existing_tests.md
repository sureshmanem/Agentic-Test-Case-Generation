# Existing Regression Tests (Synthetic Reference)

These tests already exist in the regression suite. New test cases should not duplicate them; extend coverage instead.

| ID | Area | Title | Data |
|---|---|---|---|
| REG-101 | Symbol validation | Accept a common Moody's-style rating | MOODYS, `A2` |
| REG-102 | Symbol validation | Accept a common Fitch-style rating | FITCH, `BBB` |
| REG-103 | Symbol validation | Reject a lowercase symbol | MOODYS, `aaa` → INVALID_RATING_SYMBOL |
| REG-201 | Mapping | Map Aaa to AAA | MOODYS `Aaa` → FITCH `AAA` |
| REG-202 | Mapping | Map Baa2 to BBB | MOODYS `Baa2` → FITCH `BBB` |
| REG-301 | Rating actions | Record a simple upgrade | MOODYS `A3` → `A2`, notch_change=+1 |
| REG-401 | API | GET ratings for a known issuer returns 200 | ISS-1001 |

Coverage gaps the QA team knows about: no tests for RD/D handling, status codes, the IG/SG boundary, or the three-agency selection rule.
