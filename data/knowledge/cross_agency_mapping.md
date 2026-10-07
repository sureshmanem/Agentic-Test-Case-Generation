# Cross-Agency Rating Mapping (Synthetic Reference)

The **common rank** equals the Moody's-style ordinal position (1 = highest, 21 = lowest). All agencies are compared on the common rank.

| Common rank | Moody's-style | Fitch-style | Grade |
|---|---|---|---|
| 1 | Aaa | AAA | Investment |
| 2 | Aa1 | AA+ | Investment |
| 3 | Aa2 | AA | Investment |
| 4 | Aa3 | AA- | Investment |
| 5 | A1 | A+ | Investment |
| 6 | A2 | A | Investment |
| 7 | A3 | A- | Investment |
| 8 | Baa1 | BBB+ | Investment |
| 9 | Baa2 | BBB | Investment |
| 10 | Baa3 | BBB- | Investment (lowest IG) |
| 11 | Ba1 | BB+ | Speculative (highest SG) |
| 12 | Ba2 | BB | Speculative |
| 13 | Ba3 | BB- | Speculative |
| 14 | B1 | B+ | Speculative |
| 15 | B2 | B | Speculative |
| 16 | B3 | B- | Speculative |
| 17 | Caa1 | CCC+ | Speculative |
| 18 | Caa2 | CCC | Speculative |
| 19 | Caa3 | CCC- | Speculative |
| 20 | Ca | CC | Speculative |
| 21 | C | C | Speculative |

## One-Way Mappings

| Fitch-style | Moody's-style | Common rank | lossy |
|---|---|---|---|
| RD | C | 21 | true |
| D | C | 21 | true |

Converting Moody's-style `C` to Fitch-style always returns `C` (never RD or D).

## Not Mappable

Status codes `WR`, `WD` and `NR` have no common rank. Mapping them returns `NOT_MAPPABLE`.
