# Rating Business Rules (Synthetic Reference)

## Grade Classification
- **Investment Grade (IG):** common rank 1–10 (Aaa…Baa3 / AAA…BBB-).
- **Speculative Grade (SG):** common rank 11–21, plus Fitch-style RD and D.
- **In default:** only Fitch-style RD and D set `in_default=true`.
- **Not Rated:** status codes WR, WD, NR.
- **Split rated:** an issuer with at least one IG and at least one SG rating from different agencies. "Crossing the IG boundary" means a move between rank 10 and rank 11.

## Rating Actions
- Action types: NEW, UPGRADE, DOWNGRADE, AFFIRM, WITHDRAW, CORRECTION (CORRECTION is used only for audit corrections).
- `notch_change = previous_ordinal − new_ordinal` on the agency's own scale. Upgrades are positive and downgrades negative.
  - Example: BBB (9) → BB+ (11) = −2. A2 (6) → A1 (5) = +1.
  - Fitch-style default symbols extend the scale: RD = 22, D = 23. Example: CCC (18) → RD (22) = −4.
- Effective dates can be today or in the past, never in the future.
- Only one active rating per issuer per agency. WITHDRAW sets WR (MOODYS) or WD (FITCH/NORTHBRIDGE).

## Outlook and Watch
- Outlook: POSITIVE, NEGATIVE, STABLE, DEVELOPING. This is the medium-term direction.
- Watch: WATCH_POSITIVE, WATCH_NEGATIVE, WATCH_DEVELOPING. It signals a short-term review and always has a direction.
- A rating carries either an outlook or a watch, never both. Placing it on watch clears the outlook. Coming off watch requires an outlook to be set.
- Defaulted ratings (RD, D) and status codes carry neither.
- Aged watch: active for more than 90 calendar days (day 91 onwards).

## Regulatory Rating Selection (Multi-Agency)
Eligible ratings are those from MOODYS, FITCH and NORTHBRIDGE that are not status codes.

| Eligible ratings | Rule | Result |
|---|---|---|
| 0 | n/a | UNRATED |
| 1 | SINGLE | That rating |
| 2 | LOWER_OF_TWO | The worse (higher common rank) of the two |
| 3 | SECOND_BEST | Sort by common rank, take the second best |

The regulatory rating is expressed as a common rank plus a Fitch-style symbol.

## Rating History and Audit
- History records are append-only and immutable.
- Corrections create a new CORRECTION record that references the original `action_id`.
- History queries are limited to a maximum range of 10 years. Both dates are inclusive.
