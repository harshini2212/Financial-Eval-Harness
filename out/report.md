# tieout - multi-filing verification report

Constraint-layer verification of LLM-extracted figures vs SEC XBRL ground truth, with three-way violation attribution.


---

## COSTCO WHOLESALE CORP /NEW (COST) - 10-K FY2025

| Extractor | Facts | Agree | Disagree | sat | viol(hard) | soft | indet |
|---|--:|--:|--:|--:|--:|--:|--:|
| Claude (text) | 19 | 13 | 0 | 6 | 0 | 0 | 10 |
| Baseline (regex) | 10 | 0 | 9 | 1 | 0 | 0 | 15 |

*Verified: Claude's 13 extracted figures all reconcile against ground truth - zero false positives.*

---

## AMAZON COM INC (AMZN) - 10-K FY2025

| Extractor | Facts | Agree | Disagree | sat | viol(hard) | soft | indet |
|---|--:|--:|--:|--:|--:|--:|--:|
| Claude (text) | 20 | 13 | 0 | 4 | 0 | 0 | 12 |
| Baseline (regex) | 10 | 0 | 9 | 0 | 0 | 0 | 16 |

*Verified: Claude's 13 extracted figures all reconcile against ground truth - zero false positives.*

---

## Kraft Heinz Co (KHC) - 10-K FY2025

| Extractor | Facts | Agree | Disagree | sat | viol(hard) | soft | indet |
|---|--:|--:|--:|--:|--:|--:|--:|
| Claude (text) | 25 | 18 | 0 | 8 | 1 | 0 | 7 |
| Baseline (regex) | 13 | 0 | 11 | 0 | 1 | 0 | 15 |

**Claude (text)** attribution - undetermined: 1
- `opinc.segments_sum` -> **undetermined** - no complete XBRL ground truth to disambiguate

**Baseline (regex)** attribution - extraction_error: 1
- `bs.balance` -> **extraction_error** - assets.total: text=27 vs xbrl=81,786,000,000 (delta -81,785,999,973); liabilities.total: text=39,997 vs xbrl=39,997,000,000 (delta -39,996,960,003); equity.total: text=41,777 vs xbrl=41,777,000,000 (delta -41,776,958,223); equity.temporary: text=12 vs xbrl=12,000,000 (delta -11,999,988)
