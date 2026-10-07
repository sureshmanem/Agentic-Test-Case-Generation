# Long-Term Rating Scales (Synthetic Reference)

> Simplified scales for the prototype, modelled on the publicly known Moody's-style and Fitch-style long-term symbols. This is not official agency methodology.

Ordinal position 1 is the highest credit quality. Symbols are case-sensitive.

## Moody's-Style Scale (agency code `MOODYS`): 21 symbols

| Ordinal | Symbol | Ordinal | Symbol | Ordinal | Symbol |
|---|---|---|---|---|---|
| 1 | Aaa | 8 | Baa1 | 15 | B2 |
| 2 | Aa1 | 9 | Baa2 | 16 | B3 |
| 3 | Aa2 | 10 | Baa3 | 17 | Caa1 |
| 4 | Aa3 | 11 | Ba1 | 18 | Caa2 |
| 5 | A1 | 12 | Ba2 | 19 | Caa3 |
| 6 | A2 | 13 | Ba3 | 20 | Ca |
| 7 | A3 | 14 | B1 | 21 | C |

Numeric modifiers 1, 2 and 3 apply only from Aa to Caa. Aaa, Ca and C carry no modifier.

## Fitch-Style Scale (agency codes `FITCH`, `NORTHBRIDGE`): 23 symbols

| Ordinal | Symbol | Ordinal | Symbol | Ordinal | Symbol |
|---|---|---|---|---|---|
| 1 | AAA | 9 | BBB | 17 | CCC+ |
| 2 | AA+ | 10 | BBB- | 18 | CCC |
| 3 | AA | 11 | BB+ | 19 | CCC- |
| 4 | AA- | 12 | BB | 20 | CC |
| 5 | A+ | 13 | BB- | 21 | C |
| 6 | A | 14 | B+ | 22 | RD |
| 7 | A- | 15 | B | 23 | D |
| 8 | BBB+ | 16 | B- | | |

Modifiers + and − apply only from AA to CCC. AAA, CC, C, RD and D carry no modifier.
RD = Restricted Default, D = Default.

`NORTHBRIDGE` is a fictional third agency that uses the Fitch-style symbols.

## Status Codes (not ratings)

| Agency | Code | Meaning |
|---|---|---|
| MOODYS | WR | Withdrawn |
| FITCH / NORTHBRIDGE | WD | Withdrawn |
| All | NR | Not Rated |

Status codes are stored with `is_rating=false`. They have no ordinal position, no grade other than NOT_RATED, and cannot carry an outlook or watch.

## Symbols Valid on Both Scales

`C` and `NR` are valid for both MOODYS and FITCH, so submitting them under either agency is not a scale mismatch.
